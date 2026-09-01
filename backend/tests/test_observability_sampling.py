"""v0.7 Batch ⑧ D4: api_events 采样降级 tests.

覆盖:
- DEFAULT_SAMPLING 兜底 / SamplingConfig 边界 clamp
- should_record_api_event 三档规则 (error / slow / success)
- 随机性稳定性 (固定 random.seed 测 100% / 0%)
- env 覆盖优先级高于 settings.kv
- save/load 写回 settings.kv
- API 端点: GET 返回当前值, PUT 校验 + 写 settings.kv + 落 audit
- middleware 集成: 调用 record_api_call 前会被 sampling 拦截
"""
from __future__ import annotations

import os
import random
from unittest.mock import patch

import pytest

from backend.repository.db import get_connection

# ── DEFAULT / SamplingConfig ─────────────────────────────────────────


def test_default_sampling_constants():
    from backend.services.observability_sampling import DEFAULT_SAMPLING

    assert DEFAULT_SAMPLING["success_rate_pct"] == 10
    assert DEFAULT_SAMPLING["error_rate_pct"] == 100
    assert DEFAULT_SAMPLING["slow_rate_pct"] == 100
    assert DEFAULT_SAMPLING["slow_threshold_ms"] == 2000


def test_sampling_config_clamp_pct():
    """rate_pct 钳制 0-100, slow_threshold_ms 钳制 >= 0."""
    from backend.services.observability_sampling import SamplingConfig

    c = SamplingConfig.from_dict(
        {"success_rate_pct": -5, "error_rate_pct": 999, "slow_threshold_ms": -1, "slow_rate_pct": 50}
    )
    assert c.success_rate_pct == 0
    assert c.error_rate_pct == 100
    assert c.slow_threshold_ms == 0
    assert c.slow_rate_pct == 50


def test_sampling_config_uses_default_for_missing_keys():
    from backend.services.observability_sampling import DEFAULT_SAMPLING, SamplingConfig

    c = SamplingConfig.from_dict({})
    assert c.success_rate_pct == DEFAULT_SAMPLING["success_rate_pct"]
    assert c.error_rate_pct == DEFAULT_SAMPLING["error_rate_pct"]
    assert c.slow_threshold_ms == DEFAULT_SAMPLING["slow_threshold_ms"]
    assert c.slow_rate_pct == DEFAULT_SAMPLING["slow_rate_pct"]


# ── should_record_api_event 规则 ────────────────────────────────────


def test_error_status_always_recorded_when_rate_100(monkeypatch):
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")  # 全降级
    from backend.services.observability_sampling import should_record_api_event

    for status in (500, 502, 503, 504):
        assert should_record_api_event(status=status, duration_ms=10.0) is True


def test_error_status_respects_rate_when_below_100(monkeypatch):
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "100")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_ERROR_RATE_PCT", "0")
    from backend.services.observability_sampling import should_record_api_event

    for status in (500, 502, 503):
        assert should_record_api_event(status=status, duration_ms=10.0) is False


def test_slow_request_uses_slow_threshold_and_rate(monkeypatch):
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS", "1000")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_RATE_PCT", "100")
    from backend.services.observability_sampling import should_record_api_event

    # < 阈值走 success_rate=0 → False
    assert should_record_api_event(status=200, duration_ms=500.0) is False
    # >= 阈值走 slow_rate=100 → True
    assert should_record_api_event(status=200, duration_ms=1000.0) is True
    assert should_record_api_event(status=200, duration_ms=5000.0) is True


def test_success_rate_100_keeps_everything(monkeypatch):
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "100")
    from backend.services.observability_sampling import should_record_api_event

    for status in (200, 201, 204, 301, 400, 404):
        assert should_record_api_event(status=status, duration_ms=50.0) is True


def test_success_rate_0_drops_everything_below_threshold(monkeypatch):
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS", "10000")
    from backend.services.observability_sampling import should_record_api_event

    for status in (200, 201, 204, 400, 404):
        assert should_record_api_event(status=status, duration_ms=50.0) is False


def test_random_distribution_within_tolerance(monkeypatch):
    """rate=30 跑 10000 次, 命中率应在 [25%, 35%] 之间 (容差 ±5%)."""
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "30")
    random.seed(42)
    from backend.services.observability_sampling import should_record_api_event

    n = 10_000
    hits = sum(
        1 for _ in range(n) if should_record_api_event(status=200, duration_ms=10.0)
    )
    pct = hits / n * 100
    assert 25 <= pct <= 35, f"rate=30 actual={pct:.1f}%"


def test_fail_open_on_exception():
    """任何内部异常都返回 True (观测不能丢)."""
    from backend.services.observability_sampling import should_record_api_event

    with patch(
        "backend.services.observability_sampling.effective_sampling",
        side_effect=RuntimeError("boom"),
    ):
        assert should_record_api_event(status=200, duration_ms=10.0) is True


# ── load / save settings.kv 集成 ────────────────────────────────────


def test_load_returns_default_when_settings_kv_empty(temp_db):
    from backend.services.observability_sampling import DEFAULT_SAMPLING, load_sampling

    cfg = load_sampling()
    assert cfg.success_rate_pct == DEFAULT_SAMPLING["success_rate_pct"]


def test_save_and_load_roundtrip(temp_db):
    from backend.services.observability_sampling import (
        SamplingConfig,
        load_sampling,
        save_sampling,
    )

    cfg = SamplingConfig(success_rate_pct=25, error_rate_pct=80, slow_threshold_ms=500, slow_rate_pct=90)
    save_sampling(cfg)
    loaded = load_sampling()
    assert loaded.success_rate_pct == 25
    assert loaded.error_rate_pct == 80
    assert loaded.slow_threshold_ms == 500
    assert loaded.slow_rate_pct == 90


def test_save_rejects_invalid_via_Pydantic_typeerror():
    from backend.services.observability_sampling import SamplingConfig

    # success_rate_pct 必须是 int — 传 str 触发 ValueError
    with pytest.raises((TypeError, ValueError)):
        SamplingConfig.from_dict({"success_rate_pct": "not-int"})


# ── env 覆盖 ─────────────────────────────────────────────────────────


def test_env_override_beats_settings_kv(temp_db):
    """settings.kv 设 50, env 设 5 — effective 应取 5."""
    from backend.services.observability_sampling import (
        SamplingConfig,
        effective_sampling,
        save_sampling,
    )

    save_sampling(SamplingConfig(success_rate_pct=50, error_rate_pct=100, slow_threshold_ms=2000, slow_rate_pct=100))
    os.environ["HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT"] = "5"
    try:
        cfg = effective_sampling()
        assert cfg.success_rate_pct == 5
        assert cfg.error_rate_pct == 100  # 没设 env, 走 settings.kv
    finally:
        os.environ.pop("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", None)


def test_env_invalid_value_warns_and_ignored(temp_db, caplog):
    """env 非 int 应 warn + 走 settings.kv / default."""
    from backend.services.observability_sampling import DEFAULT_SAMPLING, effective_sampling

    os.environ["HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT"] = "not-an-int"
    try:
        cfg = effective_sampling()
        # 仍走默认
        assert cfg.success_rate_pct == DEFAULT_SAMPLING["success_rate_pct"]
    finally:
        os.environ.pop("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", None)


# ── API 端点 ─────────────────────────────────────────────────────────


def _sampling_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.observability_router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_get_sampling_returns_default(temp_db, monkeypatch):
    """清掉 conftest autouse 设的 env (success/error/slow=100%), 走默认 (10% success)."""
    for k in (
        "HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT",
        "HOTSPOT_API_SAMPLING_ERROR_RATE_PCT",
        "HOTSPOT_API_SAMPLING_SLOW_RATE_PCT",
        "HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS",
    ):
        monkeypatch.delenv(k, raising=False)
    client = _sampling_client()
    r = client.get("/api/observability/sampling")
    assert r.status_code == 200
    body = r.json()
    assert body["sampling"]["success_rate_pct"] == 10
    assert body["sampling"]["error_rate_pct"] == 100
    assert body["sampling"]["slow_threshold_ms"] == 2000
    assert body["sampling"]["slow_rate_pct"] == 100
    assert "defaults" in body


def test_api_put_sampling_validates(temp_db):
    client = _sampling_client()
    # success_rate_pct 必须是 int, 传 str 触发 ValueError → 400
    r = client.put(
        "/api/observability/sampling",
        json={"sampling": {"success_rate_pct": "abc"}},
    )
    assert r.status_code == 400


def test_api_put_sampling_requires_sampling_key(temp_db):
    client = _sampling_client()
    r = client.put("/api/observability/sampling", json={})
    assert r.status_code == 400


def test_api_put_sampling_writes_audit_and_roundtrips(temp_db, monkeypatch):
    """清掉 conftest autouse 设的 env, 走默认 + 显式 PUT 后落 audit."""
    for k in (
        "HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT",
        "HOTSPOT_API_SAMPLING_ERROR_RATE_PCT",
        "HOTSPOT_API_SAMPLING_SLOW_RATE_PCT",
        "HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS",
    ):
        monkeypatch.delenv(k, raising=False)
    client = _sampling_client()
    r = client.put(
        "/api/observability/sampling",
        json={"sampling": {"success_rate_pct": 50, "error_rate_pct": 90, "slow_threshold_ms": 1500, "slow_rate_pct": 80}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sampling"]["success_rate_pct"] == 50

    # 落 audit
    row = get_connection().execute(
        "SELECT action, detail FROM audit_log "
        "WHERE action = 'observability.sampling.update' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert "success=50%" in row["detail"]

    # GET 回读一致
    r2 = client.get("/api/observability/sampling")
    assert r2.json()["sampling"]["success_rate_pct"] == 50


def test_api_put_sampling_clamps_out_of_range(temp_db):
    """超过 100 / 小于 0 自动 clamp, 不报错."""
    client = _sampling_client()
    r = client.put(
        "/api/observability/sampling",
        json={"sampling": {"success_rate_pct": 9999}},
    )
    assert r.status_code == 200
    assert r.json()["sampling"]["success_rate_pct"] == 100


# ── middleware 集成 (走 sampling 拦截) ──────────────────────────────


def test_middleware_drops_success_path_when_rate_zero(temp_db, monkeypatch):
    """success_rate=0 时, 即使 record_api_call 调用, 实际不应 INSERT."""
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")
    # 慢请求阈值设很高, 确保 200 status 走 success 路径
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS", "100000")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.middleware import TraceIDMiddleware

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=[])

    @app.get("/x")
    def _x():
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/x")
    assert r.status_code == 200

    n = get_connection().execute("SELECT COUNT(*) AS n FROM api_events").fetchone()["n"]
    assert n == 0


def test_middleware_keeps_error_path_when_success_rate_zero(temp_db, monkeypatch):
    """success_rate=0 但 error_rate=100 — 错误请求仍落表."""
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_ERROR_RATE_PCT", "100")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.middleware import TraceIDMiddleware

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=[])

    @app.get("/boom")
    def _boom():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500

    n = get_connection().execute(
        "SELECT COUNT(*) AS n FROM api_events WHERE status >= 500"
    ).fetchone()["n"]
    assert n == 1


def test_middleware_keeps_slow_path_when_success_rate_zero(temp_db, monkeypatch):
    """success_rate=0 但 slow_rate=100, 慢请求仍落表."""
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT", "0")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_RATE_PCT", "100")
    monkeypatch.setenv("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS", "10")

    import time

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.middleware import TraceIDMiddleware

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=[])

    @app.get("/slow")
    def _slow():
        time.sleep(0.05)  # 50ms, 大于阈值 10ms
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/slow")
    assert r.status_code == 200

    n = get_connection().execute(
        "SELECT COUNT(*) AS n FROM api_events WHERE duration_ms >= 10"
    ).fetchone()["n"]
    assert n == 1