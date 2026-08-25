"""CRM 全栈 E2E (v0.6 方案 C T5) — PRD US-1/US-2/US-3 主链路。

与 test_crm_api.py 的差别: 这里通过 ``register_routers`` 注册完整 app
(经 feature gate 扩展注册路径), 验证 crm 三路由真实可达后走完
「录入客户 → 商机四级推进赢单 → 座舱 KPI 复盘」业务链。
DB 隔离同前: tmp sqlite 只跑 071 migration + 逐模块 patch get_connection
(P2-2 from-import 绑定教训)。

Playwright 浏览器级 E2E 受沙箱约束暂缓, 记录于 docs/P2_6_COCKPIT_EVAL.md §决议。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    db_file = tmp_path / "test_crm_e2e.db"
    setup_conn = sqlite3.connect(str(db_file))
    with open(
        "backend/repository/migrations/071_crm_cockpit.sql", encoding="utf-8"
    ) as f:
        setup_conn.executescript(f.read())
    setup_conn.commit()
    setup_conn.close()

    shared_conn = sqlite3.connect(
        str(db_file), check_same_thread=False, timeout=30.0
    )
    shared_conn.row_factory = sqlite3.Row
    shared_conn.execute("PRAGMA foreign_keys=ON")

    def _get_conn():
        return shared_conn

    from backend.repository import crm_customer_repo as cust_mod
    from backend.repository import crm_opportunity_repo as opp_mod
    from backend.services import crm_stats_service as stats_mod

    for mod in (cust_mod, opp_mod, stats_mod):
        monkeypatch.setattr(mod, "get_connection", _get_conn)

    from backend.extensions import is_extension_enabled
    assert is_extension_enabled("crm"), "conftest 应保证测试环境 gates 全开"

    app = FastAPI()
    from backend.api import register_routers
    register_routers(app)
    yield TestClient(app)
    shared_conn.close()


def test_full_app_registers_crm_routes(client):
    """扩展注册链路: register_routers 经 crm gate 挂载三路由。"""
    resp = client.get("/api/crm/meta")
    assert resp.status_code == 200
    meta = resp.json()
    assert meta["stages"][-2:] == ["赢单", "输单"]


def test_us1_us2_us3_business_chain(client):
    """US-1 录入客户 → US-2 商机推进 → US-3 座舱复盘 完整闭环。"""
    # ── US-1: 录入两个客户 ──
    c1 = client.post("/api/crm/customers", json={
        "name": "甲方科技", "industry": "网络安全服务", "level": "A",
        "region": "华东", "nps_score": 9,
    })
    assert c1.status_code == 201, c1.text
    c2 = client.post("/api/crm/customers", json={
        "name": "乙方集团", "level": "B", "region": "华南",
    })
    assert c2.status_code == 201
    cust_id = c1.json()["id"]

    # 列表可检索 (updated_at DESC)
    listed = client.get("/api/crm/customers", params={"q": "甲方"}).json()
    assert [r["name"] for r in listed["items"]] == ["甲方科技"]

    # ── US-2: 商机创建 + 四级推进至赢单 ──
    opp = client.post("/api/crm/opportunities", json={
        "customer_id": cust_id, "name": "等保三级测评", "amount": 500000, "cost": 180000,
    })
    assert opp.status_code == 201
    oid = opp.json()["id"]
    assert opp.json()["stage"] == "需求沟通"

    for stage in ("方案提交", "商务谈判", "合同签订"):
        step = client.post(f"/api/crm/opportunities/{oid}/transition",
                           json={"to_stage": stage})
        assert step.status_code == 200, step.text

    won = client.post(f"/api/crm/opportunities/{oid}/transition",
                      json={"to_stage": "赢单"})
    assert won.status_code == 200
    body = won.json()
    assert body["stage"] == "赢单"
    assert body["won_at"] is not None

    # 状态机事件留痕: created + 4 推进
    detail = client.get(f"/api/crm/opportunities/{oid}").json()
    assert len(detail["events"]) == 5

    # 终态冻结
    frozen = client.post(f"/api/crm/opportunities/{oid}/transition",
                         json={"to_stage": "输单"})
    assert frozen.status_code == 400

    # ── US-3: 座舱 KPI 反映本笔赢单 ──
    stats = client.get("/api/crm/stats").json()["kpi"]
    assert stats["annual_revenue"] == 500000.0
    assert stats["gross_margin"] == round((500000 - 180000) / 500000, 4)
    assert stats["customers_total"] == 2
    assert stats["win_rate"] == 1.0          # 1 胜 0 负
    assert stats["in_pipeline"] == 0
