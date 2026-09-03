"""skill_registry_api — v0.8 Phase A Task A3 集成测试 (15 case).

覆盖 (任务书 13 项映射):
- 列表: 20 条全量 / category 过滤 / enabled_only 过滤 / 无 prompt 全文 + has_prompt
- 详情: schema + C 类 prompt / A 类无 prompt / 未知 id 404 信封逐字段
- 启停: enable→kv True / disable→kv False / 未知 id 404
- run: 已启用入队 (trigger_tickets pending 直查) / 未启用 409 / 限流 429
- 注册门控: gate off → register_routers 不注册 (GET 404) / gate on → 注册

测试策略 (与 test_info_filter_api 同款): 自建小 FastAPI 只挂本 router —
不走 conftest e2e_api_client (其 HOTSPOT_FEATURE_GATES env 未含
skill_registry → gate 读 TOML false → register_routers 不挂载, 404)。
DB 走 temp_db (settings + trigger_tickets 全 schema); 父 gate True 路径
monkeypatch gate 模块的 is_extension_enabled (test_skill_registry 同款)。
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.repository.settings_repo import SettingsRepository


@pytest.fixture()
def client(temp_db, monkeypatch):
    """小 app 只挂 skill_registry router; 父 gate 强制 True (True 路径基线)。"""
    monkeypatch.setattr(
        "backend.services.skill_registry.gate.is_extension_enabled",
        lambda name: True,
    )
    from backend.api.skill_registry_api import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


# ===========================================================================
# 1. 列表
# ===========================================================================
def test_list_returns_all_20(client):
    """GET 列表返回 BUILTIN 全量 20 条 (plan §4 官方清单)。"""
    r = client.get("/api/skill-registry")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 20
    ids = {it["id"] for it in items}
    assert "source-health-scan" in ids  # operations A 类
    assert "daily-briefing" in ids  # report C 类


def test_list_category_filter(client):
    """?category=operations → 恰好 8 条且全部 operations (§6.3 分类对账)。"""
    r = client.get("/api/skill-registry", params={"category": "operations"})
    items = r.json()
    assert len(items) == 8
    assert all(it["category"] == "operations" for it in items)


def test_list_enabled_only_filter(client):
    """?enabled_only=true → 只含已启用 (先 enable 一个, 全默认关 → 恰 1 条)。"""
    client.post("/api/skill-registry/source-health-scan/enable")
    items = client.get(
        "/api/skill-registry", params={"enabled_only": "true"}
    ).json()
    assert [it["id"] for it in items] == ["source-health-scan"]


def test_list_omits_prompt_and_flags_has_prompt(client):
    """列表不泄 prompt_template 全文; C/D 类 has_prompt=True, A/B 类 False。

    列表是卡片流量的主入口, prompt 全文只应出现在详情页 (按需加载)。
    """
    items = client.get("/api/skill-registry").json()
    by_id = {it["id"]: it for it in items}
    assert all("prompt_template" not in it for it in items)
    assert by_id["weekly-top-events"]["has_prompt"] is True  # C
    assert by_id["daily-briefing"]["has_prompt"] is True  # C
    assert by_id["collector-failure-analysis"]["has_prompt"] is True  # D
    assert by_id["source-health-scan"]["has_prompt"] is False  # A
    assert by_id["agent-task-audit"]["has_prompt"] is False  # B


def test_list_item_enabled_reads_gate(client):
    """列表项 enabled 默认 False (kv 未写 → default_enabled=False, 父 gate 开)。"""
    items = client.get("/api/skill-registry").json()
    assert all(it["enabled"] is False for it in items)


# ===========================================================================
# 2. 详情
# ===========================================================================
def test_detail_contains_schemas_and_prompt(client):
    """C 类详情含 input/output schema (类型名) + prompt_template 全文。"""
    r = client.get("/api/skill-registry/weekly-top-events")
    assert r.status_code == 200
    body = r.json()
    assert body["input_schema"] == {"top_n": "int"}
    assert body["output_schema"] == {"top_events": "list", "report_md": "str"}
    assert "{{ steps.0.output }}" in body["prompt_template"]
    assert body["skill_type"] == "C"
    assert body["has_prompt"] is True


def test_detail_a_class_has_no_prompt(client):
    """A 类详情无 prompt_template 键 (契约规则 3: prompt 仅 C/D)。"""
    body = client.get("/api/skill-registry/source-health-scan").json()
    assert "prompt_template" not in body
    assert body["has_prompt"] is False
    assert body["input_schema"] == {"top_n": "int"}


def test_detail_unknown_404_envelope_field_by_field(client):
    """未知 id → 404; detail 三字段逐字段断言 (P3-2 错误信封)。"""
    r = client.get("/api/skill-registry/no-such-skill")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert set(detail.keys()) == {"message", "code", "hint"}
    assert "no-such-skill" in detail["message"]
    assert detail["code"] == "SKILL_NOT_FOUND"
    assert isinstance(detail["hint"], str) and detail["hint"]


# ===========================================================================
# 3. 启停
# ===========================================================================
def test_enable_writes_kv_and_returns(client, temp_db):
    """POST enable → settings kv True + 响应 {"enabled": true}。"""
    r = client.post("/api/skill-registry/source-health-scan/enable")
    assert r.status_code == 200
    assert r.json() == {"enabled": True}
    assert SettingsRepository().get("skill.source-health-scan.enabled") is True


def test_disable_writes_kv_and_returns(client, temp_db):
    """POST disable → settings kv False + 响应 {"enabled": false}。"""
    client.post("/api/skill-registry/source-health-scan/enable")
    r = client.post("/api/skill-registry/source-health-scan/disable")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    assert SettingsRepository().get("skill.source-health-scan.enabled") is False


def test_enable_unknown_404(client):
    """enable 未知 id → 404 SKILL_NOT_FOUND (不写无人认领的 kv key)。"""
    r = client.post("/api/skill-registry/no-such-skill/enable")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SKILL_NOT_FOUND"


# ===========================================================================
# 4. run (Phase A 预注册态: 仅入队)
# ===========================================================================
def test_run_enabled_submits_ticket(client, temp_db):
    """已启用 skill run → 200 ticket_id + trigger_tickets 落 pending 行。

    Phase A 语义: run = 入队 ≠ 执行 (runner 接线在 B5); 落库证据是
    本端点唯一可验证的副作用, 必须直查表锁定 (防只返回假 ticket_id)。
    """
    client.post("/api/skill-registry/source-health-scan/enable")
    r = client.post(
        "/api/skill-registry/source-health-scan/run",
        json={"inputs": {"top_n": 5}},
    )
    assert r.status_code == 200
    ticket_id = r.json()["ticket_id"]
    assert ticket_id.startswith("tg-")

    from backend.repository.db import get_connection

    row = get_connection().execute(
        "SELECT target_type, target_id, status, priority, source, inputs "
        "FROM trigger_tickets WHERE ticket_id = ?",
        (ticket_id,),
    ).fetchone()
    assert row is not None
    assert row["target_type"] == "skill"
    assert row["target_id"] == "source-health-scan"
    assert row["status"] == "pending"
    assert row["priority"] == 0  # REALTIME
    assert row["source"] == "manual"
    assert json.loads(row["inputs"]) == {"top_n": 5}


def test_run_disabled_409(client):
    """未启用 skill run → 409 SKILL_DISABLED (票据不入队)。"""
    r = client.post("/api/skill-registry/source-health-scan/run")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "SKILL_DISABLED"
    assert set(detail.keys()) == {"message", "code", "hint"}


def test_run_unknown_404(client):
    """run 未知 id → 404 (先于启用检查, 与 get/enable 一致)。"""
    r = client.post("/api/skill-registry/no-such-skill/run")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SKILL_NOT_FOUND"


def test_run_throttled_429(client, temp_db, monkeypatch):
    """限流超限 → 429 THROTTLED + retry_after_seconds (票据不落库)。

    单例换小桶 (per_user=1/min): 第一发放行, 第二发匿名桶空 → 429;
    retry_after ≈ 60s (两次请求间隙有少量回填, 断言区间而非精确值)。
    """
    from backend.services.trigger_gate import TriggerThrottle, trigger_gate

    client.post("/api/skill-registry/source-health-scan/enable")
    monkeypatch.setattr(
        trigger_gate, "_throttle", TriggerThrottle(per_user_per_minute=1)
    )
    assert (
        client.post("/api/skill-registry/source-health-scan/run").status_code == 200
    )
    r = client.post("/api/skill-registry/source-health-scan/run")
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["code"] == "THROTTLED"
    assert 0 < detail["retry_after_seconds"] <= 60.0
    assert {"message", "code", "hint"} <= set(detail.keys())


# ===========================================================================
# 5. 注册门控 (gate off → 路由不注册)
# ===========================================================================
def _build_app_with_gate(monkeypatch, on: bool) -> FastAPI:
    """按 test_feature_gates.build_app 模式: patch _load_gates 后真实注册。"""
    import backend.extensions as extensions
    from backend.api import register_routers

    monkeypatch.setattr(extensions, "_load_gates", lambda: {"skill_registry": on})
    app = FastAPI()
    register_routers(app)
    return app


def _paths(app: FastAPI) -> set[str]:
    """递归收集全部注册路径 (含 _IncludedRouter 嵌套 — test_feature_gates 同款)。

    本环境 FastAPI 的 include_router 产出 _IncludedRouter 包装对象 (无 .path),
    平铺 getattr 会漏掉全部挂载路由, 断言退化为 vacuous true。
    """
    paths: set[str] = set()
    stack = list(app.routes)
    while stack:
        r = stack.pop()
        path = getattr(r, "path", None)
        if path:
            paths.add(path)
            continue
        router = getattr(r, "original_router", None) or getattr(r, "router", None)
        if router is not None:
            stack.extend(router.routes)
    return paths


def test_gate_off_route_not_registered(monkeypatch):
    """gate off → register_routers 后 /api/skill-registry* 不存在 → GET 404。

    fail-closed 语义: TOML 默认 false 即路由不可达, 不是注册了返回 503。
    """
    app = _build_app_with_gate(monkeypatch, on=False)
    assert not any(p.startswith("/api/skill-registry") for p in _paths(app))
    with TestClient(app) as c:
        assert c.get("/api/skill-registry").status_code == 404


def test_gate_on_route_registered(monkeypatch):
    """gate on → 路由注册 (与 off 用例合成注册分支的双向验证)。"""
    app = _build_app_with_gate(monkeypatch, on=True)
    assert any(p.startswith("/api/skill-registry") for p in _paths(app))
