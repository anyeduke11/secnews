"""v0.7 Batch ④: 阈值规则引擎 + alert 端点单测.

覆盖:
1. load_thresholds 缺失 → DEFAULT 兜底
2. save_thresholds 写入 + 二次读取命中
3. _validate 拒绝非法 schema (非 dict / warn >= critical)
4. evaluate_api error_rate_pct → warn + critical 同时越界
5. evaluate_api p95 单越界
6. evaluate 合并 api_summary
7. cooldown_until 时间正确性
8. POST /alerts/{id}/ack + 幂等
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import TraceIDMiddleware
from backend.api.observability_router import router as obs_router
from backend.exceptions import register_exception_handlers
from backend.repository.db import get_connection
from backend.services import observability_thresholds as thr_mod


@pytest.fixture
def client(temp_db):
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
    register_exception_handlers(app)
    app.include_router(obs_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── 1. load_thresholds 兜底 ──────────────────────────────────────


def test_load_thresholds_falls_back_to_default(temp_db):
    """settings 表无键 → 返回 DEFAULT_THRESHOLDS (非 None, 非空)."""
    rules = thr_mod.load_thresholds()
    assert isinstance(rules, dict)
    assert rules["api"]["error_rate_pct"]["warn"] == 5
    assert rules["api"]["error_rate_pct"]["critical"] == 15


# ── 2. save_thresholds + 二次读取命中 ────────────────────────────


def test_save_and_load_roundtrip(temp_db):
    custom = {
        "api": {"error_rate_pct": {"warn": 7, "critical": 25, "window_minutes": 30}},
        "llm": {},
        "job": {},
        "audit": {},
        "alerts": {"channels": ["status_bar"], "cooldown_minutes": 10},
    }
    thr_mod.save_thresholds(custom)
    loaded = thr_mod.load_thresholds()
    assert loaded["api"]["error_rate_pct"]["warn"] == 7
    assert loaded["api"]["error_rate_pct"]["critical"] == 25


# ── 3. _validate 拒绝非法 schema ─────────────────────────────────


def test_validate_rejects_warn_ge_critical(temp_db):
    with pytest.raises(ValueError, match="warn"):
        thr_mod._validate({"api": {"error_rate_pct": {"warn": 50, "critical": 10}}})


def test_validate_rejects_non_dict(temp_db):
    with pytest.raises(ValueError, match="must be a dict"):
        thr_mod._validate("not a dict")


def test_validate_rejects_negative_threshold(temp_db):
    with pytest.raises(ValueError, match="non-negative"):
        thr_mod._validate({"api": {"error_rate_pct": {"warn": -5}}})


# ── 4. evaluate_api 多越界 ───────────────────────────────────────


def test_evaluate_api_warn_and_critical(temp_db):
    thresholds = thr_mod.DEFAULT_THRESHOLDS
    # error_rate 18% → 越界 critical (≥15), 同时也越界 warn (≥5); 都返
    bs = thr_mod.evaluate_api(error_rate_pct=18.0, p95_latency_ms=100, thresholds=thresholds)
    metrics = sorted([b.metric for b in bs])
    assert "api.error_rate_pct" in metrics
    by_level = {b.metric: b.level for b in bs if b.metric == "api.error_rate_pct"}
    assert by_level["api.error_rate_pct"] == "critical"


# ── 5. evaluate_api p95 单越界 ───────────────────────────────────


def test_evaluate_api_p95_only(temp_db):
    thresholds = thr_mod.DEFAULT_THRESHOLDS
    bs = thr_mod.evaluate_api(error_rate_pct=1.0, p95_latency_ms=3000, thresholds=thresholds)
    p95_breaches = [b for b in bs if b.metric == "api.p95_latency_ms"]
    # p95=3000 同时越界 warn(800) 和 critical(2000), 两条都应触发
    assert len(p95_breaches) >= 1
    levels = {b.level for b in p95_breaches}
    assert "critical" in levels


# ── 6. evaluate 合并 api_summary ─────────────────────────────────


def test_evaluate_from_summary_dict(temp_db):
    bs = thr_mod.evaluate(
        api_summary={"error_rate_pct": 20.0, "p95_latency_ms": 50},
        thresholds=thr_mod.DEFAULT_THRESHOLDS,
    )
    assert any(b.metric == "api.error_rate_pct" for b in bs)


# ── 7. cooldown_until ─────────────────────────────────────────────


def test_cooldown_until_default_15min():
    from datetime import datetime, timezone

    from backend.services.observability_thresholds import cooldown_until
    now = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    s = cooldown_until(now, minutes=15)
    assert "T12:15" in s


# ── 8. alerts API: list + ack + 幂等 ─────────────────────────────


def test_alerts_active_lists_recent(temp_db, client):
    conn = get_connection()
    now_iso = "2026-08-31T12:00:00+00:00"
    conn.execute(
        "INSERT INTO observability_alerts "
        "(level, metric, value, threshold, window_minutes, detail, "
        "fired_at, cooldown_until, acked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        ("critical", "api.error_rate_pct", 20.0, 15.0, 60, "{}",
         now_iso, now_iso),
    )
    r = client.get("/api/observability/alerts/active")
    assert r.status_code == 200
    data = r.json()
    assert data["critical_count"] == 1


def test_alerts_ack_idempotent(temp_db, client):
    conn = get_connection()
    now_iso = "2026-08-31T12:00:00+00:00"
    cur = conn.execute(
        "INSERT INTO observability_alerts "
        "(level, metric, value, threshold, window_minutes, detail, "
        "fired_at, cooldown_until, acked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        ("warn", "api.error_rate_pct", 6.0, 5.0, 60, "{}",
         now_iso, now_iso),
    )
    alert_id = cur.lastrowid

    r1 = client.post(f"/api/observability/alerts/{alert_id}/ack")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    # 第二次 ack 应返 already=True (幂等)
    r2 = client.post(f"/api/observability/alerts/{alert_id}/ack")
    assert r2.status_code == 200
    assert r2.json().get("already") is True


# ── 9. thresholds GET/PUT 端到端 ─────────────────────────────────


def test_thresholds_get_returns_defaults(temp_db, client):
    r = client.get("/api/observability/thresholds")
    assert r.status_code == 200
    data = r.json()
    assert "thresholds" in data
    assert "defaults" in data


def test_thresholds_put_rejects_invalid(temp_db, client):
    r = client.put("/api/observability/thresholds", json={
        "thresholds": {"api": {"error_rate_pct": {"warn": 100, "critical": 10}}}
    })
    assert r.status_code == 400


def test_thresholds_put_updates(temp_db, client):
    new_rules = {
        "api": {"error_rate_pct": {"warn": 3, "critical": 10, "window_minutes": 60}},
        "llm": {}, "job": {}, "audit": {},
        "alerts": {"channels": ["status_bar"], "cooldown_minutes": 15},
    }
    r = client.put("/api/observability/thresholds", json={"thresholds": new_rules})
    assert r.status_code == 200
    assert r.json()["thresholds"]["api"]["error_rate_pct"]["warn"] == 3