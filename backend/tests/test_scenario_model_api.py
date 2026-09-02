"""S7 验证 — POST /api/settings/scenario-model 端点 (v0.7.4-image).

覆盖:
- 合法 scenario + model → 200 + settings.kv 写入 + audit_log 一行
- 非法 scenario (foo) → 422 (Pydantic pattern)
- 空 model → 422 (Pydantic min_length)
- audit_log 写入 (mock)
- 端点写入后, scenarios.resolve_scenario_model 读到 kv (端到端)
- 优先级: env > kv (端到端验证)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.settings import router as settings_router
from backend.exceptions import register_exception_handlers
from backend.repository.settings_repo import SettingsRepository
from backend.version import APP_VERSION


@pytest.fixture
def client(temp_db):
    app = FastAPI(title="test", version=APP_VERSION)
    register_exception_handlers(app)
    app.include_router(settings_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_set_scenario_model_writes_kv(client):
    """合法入参 → 200 + settings.kv 'llm.scenario.deep_model' 落值。"""
    r = client.post(
        "/api/settings/scenario-model",
        json={"scenario": "deep", "model": "custom-deep-model", "actor": "test"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["scenario"] == "deep"
    assert d["new_model"] == "custom-deep-model"
    # 落 kv
    kv = SettingsRepository().get("llm.scenario.deep_model")
    assert kv == "custom-deep-model", f"settings.kv 写入失败, 实际 {kv!r}"


def test_invalid_scenario_422(client):
    """scenario='foo' → 422 (Pydantic pattern)."""
    r = client.post(
        "/api/settings/scenario-model",
        json={"scenario": "foo", "model": "x", "actor": "test"},
    )
    assert r.status_code == 422


def test_empty_model_422(client):
    """model='' → 422 (Pydantic min_length=1)."""
    r = client.post(
        "/api/settings/scenario-model",
        json={"scenario": "deep", "model": "", "actor": "test"},
    )
    assert r.status_code == 422


def test_audit_recorded_on_set(client):
    """成功路径写 record_audit (mock)."""
    with patch("backend.observability_records.record_audit") as mock_audit:
        r = client.post(
            "/api/settings/scenario-model",
            json={"scenario": "image", "model": "sensenova-u1.5-lite", "actor": "alice"},
        )
        assert r.status_code == 200
        assert mock_audit.called
        kwargs = mock_audit.call_args.kwargs
        assert kwargs["actor"] == "alice"
        assert kwargs["action"] == "llm.scenario_model.set"
        assert kwargs["target"] == "llm.scenario.image_model"
        assert kwargs["detail"]["scenario"] == "image"
        assert kwargs["detail"]["to"] == "sensenova-u1.5-lite"


def test_set_then_resolve_scenario_model_reads_kv(client, monkeypatch):
    """端到端: 写 kv 后, resolve_scenario_model 读到 kv."""
    monkeypatch.delenv("HOTSPOT_SCENARIO_LIGHT_MODEL", raising=False)
    r = client.post(
        "/api/settings/scenario-model",
        json={"scenario": "light", "model": "custom-light", "actor": "test"},
    )
    assert r.status_code == 200

    # 现在 resolve_scenario_model 应读到 kv
    from backend.services.ai_hub.scenarios import Scenario, resolve_scenario_model
    route = resolve_scenario_model(Scenario.LIGHT)
    assert route.model == "custom-light", (
        f"端到端失败, resolve 期望 custom-light, 实际 {route.model!r}"
    )


def test_scenario_model_priority_over_router(client, monkeypatch):
    """优先级: env > kv > router > default — 设 kv 后 router 命中, kv 胜。"""
    monkeypatch.delenv("HOTSPOT_SCENARIO_DEEP_MODEL", raising=False)
    # 写 kv
    r = client.post(
        "/api/settings/scenario-model",
        json={"scenario": "deep", "model": "kv-wins", "actor": "test"},
    )
    assert r.status_code == 200

    from backend.services.ai_hub.scenarios import Scenario, resolve_scenario_model
    # 不 mock router, 实际跑 (yaml t3_summary=deepseek-v4-pro 才是 router 真值)
    # kv 胜 → 应得 kv-wins
    route = resolve_scenario_model(Scenario.DEEP)
    assert route.model == "kv-wins", (
        f"kv 应胜 router, 实际 {route.model!r} (yaml router=deepseek-v4-pro 应被 kv 覆盖)"
    )

    # 现在设 env, env 应胜
    monkeypatch.setenv("HOTSPOT_SCENARIO_DEEP_MODEL", "env-wins")
    route = resolve_scenario_model(Scenario.DEEP)
    assert route.model == "env-wins", f"env 应胜 kv, 实际 {route.model!r}"
