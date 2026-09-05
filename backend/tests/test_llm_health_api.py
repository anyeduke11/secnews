"""v0.8.1 Day 4 — /api/observability/llm/health + 迁移审计 + 场景权重测试。

端点走独立 app + obs_router (对齐 test_api_observability 模式);
审计断言查 audit_log 表 (temp_db); 场景重排断言 deep 只重排、light 零变化。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import TraceIDMiddleware
from backend.api.observability_router import router as obs_router
from backend.exceptions import register_exception_handlers
from backend.quality.scenario_router import (
    scenario_fallback_order,
    task_to_scenario,
)
from backend.services.ai_hub.provider_health import (
    get_provider_health,
    reset_provider_health,
)
from backend.tests.test_ai_hub_failover import _make_svc, _trip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def health(monkeypatch):
    reset_provider_health()
    yield get_provider_health()
    reset_provider_health()


@pytest.fixture
def client(temp_db):
    app = FastAPI()
    app.include_router(obs_router)
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------
class TestLlmHealthEndpoints:
    def test_get_health_empty(self, client):
        resp = client.get("/api/observability/llm/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["providers"] == {}

    def test_get_health_after_records(self, client, health):
        health.record("sensenova", ok=True)
        health.record("sensenova", ok=False)
        resp = client.get("/api/observability/llm/health")
        body = resp.json()
        assert body["ok"] is True
        snap = body["providers"]["sensenova"]
        assert snap["windows"]["1m"]["total"] == 2
        assert snap["windows"]["1m"]["failures"] == 1
        assert snap["breaker"]["state"] == "closed"

    def test_post_reset_reopens_breaker(self, client, health):
        _trip(health, "sensenova")
        assert health.get_breaker("sensenova").state == "open"
        resp = client.post("/api/observability/llm/health/sensenova/reset")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["state"] == "closed"
        assert health.get_breaker("sensenova").state == "closed"

    def test_reset_writes_audit(self, client, temp_db):
        client.post("/api/observability/llm/health/sensenova/reset")
        from backend.repository.db import get_connection
        row = get_connection().execute(
            "SELECT actor, action, target FROM audit_log "
            "WHERE action='llm_breaker.reset' AND target='sensenova'"
        ).fetchone()
        assert row is not None
        assert row[0] == "web"


# ---------------------------------------------------------------------------
# breaker 状态迁移 → audit_log (PRD §2.2 迁移 100% 留痕)
# ---------------------------------------------------------------------------
class TestTransitionAudit:
    def test_verdict_trip_writes_audit(self, temp_db, health):
        for _ in range(4):
            health.record("sensenova", ok=False)  # 4 失败 → 判定 → trip
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT detail FROM audit_log WHERE action='llm_breaker.transition' "
            "AND target='sensenova'"
        ).fetchall()
        assert len(rows) == 1  # closed→open 恰一次 (后续 no-op 不重复)
        assert '"to": "open"' in rows[0][0] or "'to': 'open'" in rows[0][0] or "open" in rows[0][0]

    def test_probe_success_transition_audited(self, temp_db, monkeypatch):
        """探针成功 → half_open→closed 迁移 + trip 行, 共 2 条审计。"""
        import time as _t
        monkeypatch.setenv("HOTSPOT_BREAKER_RECOVERY_TIMEOUT", "0.05")
        reset_provider_health()
        ph = get_provider_health()
        for _ in range(4):
            ph.record("sensenova", ok=False)  # closed→open (window_verdict)
        _t.sleep(0.06)
        breaker = ph.get_breaker("sensenova")
        assert breaker.allow() is True  # 探针授予
        ph.record("sensenova", ok=True)  # 探针成功 → half_open→closed
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT detail FROM audit_log WHERE action='llm_breaker.transition' "
            "AND target='sensenova'"
        ).fetchall()
        assert len(rows) == 2
        assert '"to": "open"' in rows[0][0]
        assert '"to": "closed"' in rows[1][0] and "probe_success" in rows[1][0]
        reset_provider_health()

    def test_noop_trip_no_audit(self, temp_db, health):
        """已 OPEN 时再失败 (no-op trip) 不写迁移审计。"""
        health.get_breaker("sensenova").trip()  # 手动 OPEN (无审计 — 非 record 路径)
        from backend.repository.db import get_connection
        before = get_connection().execute(
            "SELECT count(*) FROM audit_log WHERE action='llm_breaker.transition'"
        ).fetchone()[0]
        for _ in range(6):
            health.record("sensenova", ok=False)  # 已 OPEN → no-op
        after = get_connection().execute(
            "SELECT count(*) FROM audit_log WHERE action='llm_breaker.transition'"
        ).fetchone()[0]
        assert after == before

    def test_audit_failure_does_not_break_record(self, temp_db, health, monkeypatch):
        """record_audit 抛异常 → record 仍正常完成 (观测不可拖垮业务)。"""
        def _boom(*a, **k):
            raise RuntimeError("audit down")
        monkeypatch.setattr(
            "backend.observability_records.record_audit", _boom
        )
        for _ in range(4):
            health.record("sensenova", ok=False)
        assert health.get_breaker("sensenova").state == "open"


# ---------------------------------------------------------------------------
# 场景权重 (CRITICAL_REVIEW §2.1 场景感知)
# ---------------------------------------------------------------------------
class TestScenarioWeights:
    def test_task_to_scenario(self):
        assert task_to_scenario("deep_read") == "deep"
        assert task_to_scenario("deep") == "deep"
        assert task_to_scenario("score") == "light"
        assert task_to_scenario("summary") == "light"
        assert task_to_scenario("anything") == "light"

    def test_light_unchanged(self):
        base = ["ollama", "openai"]
        assert scenario_fallback_order("score", base) == base

    def test_deep_reorders_by_quality(self):
        base = ["ollama", "openai", "anthropic"]
        order = scenario_fallback_order("deep_read", base)
        assert order == ["anthropic", "openai", "ollama"]

    def test_deep_unknown_provider_appended(self):
        base = ["custom_llm", "ollama"]
        order = scenario_fallback_order("deep_read", base)
        assert order == ["ollama", "custom_llm"]  # 表内按权重, 表外缀尾

    def test_gateway_deep_read_uses_weights(self, temp_db, monkeypatch, health):
        """gateway._try_order: deep_read 重排 fallback 尾部 (router 首位不动)。

        route_model 可能 pin 首位 → 本测显式置 None, 隔离验证权重重排。
        """
        calls: list = []
        svc = _make_svc(
            monkeypatch, providers=("openai", "anthropic"),
            behavior={"openai": "ok", "anthropic": "ok"}, calls=calls,
        )
        monkeypatch.setattr(svc, "resolve_provider_for_task", lambda _t: None)
        assert svc._try_order("deep_read") == ["anthropic", "openai"]
        assert svc._try_order("score") == ["openai", "anthropic"]  # light 零变化

    def test_gateway_light_path_untouched(self, temp_db, monkeypatch, health):
        """light 场景: a 失败落 b, 顺序 = 配置 fallback_order (无权重重排)。"""
        calls: list = []
        svc = _make_svc(
            monkeypatch, providers=("a", "b"),
            behavior={"a": "fail", "b": "ok"}, calls=calls,
        )
        asyncio.run(svc.score("content"))
        assert calls == ["a", "b"]  # light 场景按配置顺序
