"""CRM 业绩座舱 API 测试 (v0.6 方案 C T3, PRD US-1/2/3)。

覆盖: Token 鉴权三态、客户 CRUD、商机状态机唯一入口、座舱 KPI 聚合口径。
DB 隔离: tmp sqlite 只跑 071 migration; 按 P2-2 教训, get_connection 的
from-import 绑定必须逐个 patch 到使用方模块 (repo × 2 + stats 服务)。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    db_file = tmp_path / "test_crm_api.db"
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

    from backend.api import (
        crm_customers_api,
        crm_opportunities_api,
        crm_stats_api,
    )

    app = FastAPI()
    app.include_router(crm_customers_api.router)
    app.include_router(crm_opportunities_api.router)
    app.include_router(crm_stats_api.router)
    yield TestClient(app)
    shared_conn.close()


def _make_customer(client: TestClient, name: str, **fields) -> dict:
    payload = {"name": name, **fields}
    resp = client.post("/api/crm/customers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_opp(client: TestClient, customer_id: int, name: str, **fields) -> dict:
    resp = client.post(
        "/api/crm/opportunities", json={"customer_id": customer_id, "name": name, **fields}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _walk_to_win(client: TestClient, opp_id: int) -> dict:
    """状态机只允许逐级推进, 赢单必须走满四级。"""
    for stage in ("方案提交", "商务谈判", "合同签订", "赢单"):
        resp = client.post(
            f"/api/crm/opportunities/{opp_id}/transition",
            json={"to_stage": stage},
        )
        assert resp.status_code == 200, resp.text
    return resp.json()


class TestAuth:
    def test_local_mode_passes_without_header(self, client, monkeypatch):
        monkeypatch.delenv("HOTSPOT_CRM_TOKEN", raising=False)
        assert client.get("/api/crm/meta").status_code == 200

    def test_missing_token_401_when_set(self, client, monkeypatch):
        monkeypatch.setenv("HOTSPOT_CRM_TOKEN", "s3cret")
        assert client.get("/api/crm/stats").status_code == 401

    def test_wrong_token_401(self, client, monkeypatch):
        monkeypatch.setenv("HOTSPOT_CRM_TOKEN", "s3cret")
        resp = client.get("/api/crm/stats", headers={"X-CRM-Token": "nope"})
        assert resp.status_code == 401

    def test_correct_token_passes(self, client, monkeypatch):
        monkeypatch.setenv("HOTSPOT_CRM_TOKEN", "s3cret")
        resp = client.get("/api/crm/meta", headers={"X-CRM-Token": "s3cret"})
        assert resp.status_code == 200


class TestCustomerCrud:
    def test_create_with_db_defaults(self, client):
        data = _make_customer(client, "盾山科技")
        assert data["name"] == "盾山科技"
        assert data["level"] == "B"
        assert data["status"] == "活跃"
        assert data["region"] == "华东"
        assert data["contract_amount"] == 0.0

    def test_duplicate_name_conflict_409(self, client):
        _make_customer(client, "重复客户")
        resp = client.post("/api/crm/customers", json={"name": "重复客户"})
        assert resp.status_code == 409

    def test_invalid_level_422(self, client):
        resp = client.post("/api/crm/customers", json={"name": "X", "level": "F"})
        assert resp.status_code == 422

    def test_list_filters_by_status_and_level(self, client):
        _make_customer(client, "活跃A", level="A")
        _make_customer(client, "流失C", level="C", status="流失")
        resp = client.get("/api/crm/customers", params={"status": "流失"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "流失C"

    def test_search_q_matches_contact(self, client):
        _make_customer(client, "甲公司", contact_name="李四")
        _make_customer(client, "乙公司", contact_name="王五")
        resp = client.get("/api/crm/customers", params={"q": "李四"})
        names = [r["name"] for r in resp.json()["items"]]
        assert names == ["甲公司"]

    def test_patch_partial_update(self, client):
        cid = _make_customer(client, "补丁客户")["id"]
        resp = client.patch(f"/api/crm/customers/{cid}", json={"level": "S", "nps_score": 9})
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "S"
        assert data["nps_score"] == 9
        assert data["name"] == "补丁客户"  # 未提交字段不被清空

    def test_delete_cascades_opportunities(self, client):
        cid = _make_customer(client, "待删客户")["id"]
        _create_opp(client, cid, "关联商机")
        resp = client.delete(f"/api/crm/customers/{cid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1
        assert client.get(f"/api/crm/customers/{cid}").status_code == 404
        remaining = client.get("/api/crm/opportunities").json()
        assert remaining["total"] == 0


class TestOpportunityStateMachine:
    def test_create_defaults_to_first_stage(self, client):
        cid = _make_customer(client, "商机客户")["id"]
        data = _create_opp(client, cid, "等保测评-2026")
        assert data["stage"] == "需求沟通"
        assert data["amount"] == 0.0

    def test_create_unknown_customer_404(self, client):
        resp = client.post(
            "/api/crm/opportunities", json={"customer_id": 99999, "name": "孤儿商机"}
        )
        assert resp.status_code == 404

    def test_win_walk_sets_won_at_and_events(self, client):
        cid = _make_customer(client, "赢单客户")["id"]
        opp = _create_opp(client, cid, "全流程赢单", amount=100)
        detail = client.get(f"/api/crm/opportunities/{opp['id']}").json()
        assert len(detail["events"]) == 1  # 仅 created
        final = _walk_to_win(client, opp["id"])
        assert final["stage"] == "赢单"
        assert final["won_at"] is not None
        events = client.get(f"/api/crm/opportunities/{opp['id']}").json()["events"]
        # created + 4 次推进 = 5 条, 时间倒序
        assert len(events) == 5

    def test_illegal_jump_rejected_400(self, client):
        cid = _make_customer(client, "跳级客户")["id"]
        opp = _create_opp(client, cid, "跳级尝试")
        resp = client.post(
            f"/api/crm/opportunities/{opp['id']}/transition", json={"to_stage": "赢单"}
        )
        assert resp.status_code == 400

    def test_terminal_stage_frozen_400(self, client):
        cid = _make_customer(client, "终态客户")["id"]
        opp = _create_opp(client, cid, "终态冻结")
        _walk_to_win(client, opp["id"])
        resp = client.post(
            f"/api/crm/opportunities/{opp['id']}/transition", json={"to_stage": "输单"}
        )
        assert resp.status_code == 400

    def test_unknown_opportunity_404(self, client):
        resp = client.post(
            "/api/crm/opportunities/99999/transition", json={"to_stage": "输单"}
        )
        assert resp.status_code == 404

    def test_patch_cannot_change_stage(self, client):
        """改阶段必须走 /transition; PATCH 里塞 stage 应被忽略 (pydantic 白名单)。"""
        cid = _make_customer(client, "白名单客户")["id"]
        opp = _create_opp(client, cid, "字段白名单")
        resp = client.patch(f"/api/crm/opportunities/{opp['id']}", json={"stage": "赢单"})
        assert resp.status_code == 200
        assert resp.json()["stage"] == "需求沟通"


class TestCockpitStats:
    def _seed_scenario(self, client: TestClient) -> None:
        a = _make_customer(client, "华东大客", region="华东", nps_score=9)
        b = _make_customer(client, "华南新客", region="华南", nps_score=5)
        c = _make_customer(client, "华东西客", region="华东", nps_score=10)
        d = _make_customer(client, "单胜客户", region="华东")

        o1 = _create_opp(client, a["id"], "首单", amount=100, cost=30)
        _walk_to_win(client, o1["id"])
        o2 = _create_opp(client, a["id"], "复购单", amount=50, cost=20)
        _walk_to_win(client, o2["id"])
        o3 = _create_opp(client, b["id"], "丢单演示", amount=200)
        client.post(
            f"/api/crm/opportunities/{o3['id']}/transition",
            json={"to_stage": "输单", "lost_reason": "预算砍掉"},
        )
        _create_opp(client, c["id"], "在途商机", amount=80)
        od = _create_opp(client, d["id"], "单笔赢单", amount=30, cost=10)
        _walk_to_win(client, od["id"])

    def test_kpi_aggregation_matches_prd_formulas(self, client):
        self._seed_scenario(client)
        kpi = client.get("/api/crm/stats").json()["kpi"]
        assert kpi["annual_revenue"] == 180.0          # 本年三笔赢单
        assert kpi["gross_margin"] == 0.6667           # (180-60)/180
        assert kpi["customers_total"] == 4
        assert kpi["repeat_rate"] == 0.5               # 胜过单的客户 {A,D}: A≥2 → 1/2
        assert kpi["in_pipeline"] == 1                 # 仅在途商机
        assert kpi["win_rate"] == 0.75                 # 3 胜 / (3 胜+1 负)
        assert kpi["avg_deal_size"] == 60.0            # 180/3
        assert kpi["nps"] == 33                        # (2/3 − 1/3)×100

    def test_charts_funnel_region_monthly(self, client):
        self._seed_scenario(client)
        charts = client.get("/api/crm/stats").json()["charts"]
        funnel = {f["stage"]: f for f in charts["funnel"]}
        assert funnel["需求沟通"]["count"] == 1
        assert funnel["需求沟通"]["amount"] == 80.0
        regions = {r["region"]: r["amount"] for r in charts["region_distribution"]}
        assert regions["华东"] == 180.0                # A 两单 + D 一单
        assert "华南" not in regions                    # 输单不计入区域营收
        monthly_total = sum(m["revenue"] for m in charts["monthly_revenue"])
        assert monthly_total == 180.0                  # 近 12 月滚动窗含本年三单

    def test_meta_enums(self, client):
        _make_customer(client, "行业客户", industry="网络安全服务")
        meta = client.get("/api/crm/meta").json()
        assert meta["stages"][0] == "需求沟通"
        assert meta["levels"] == ["S", "A", "B", "C"]
        assert "网络安全服务" in meta["industries"]
