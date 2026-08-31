"""v0.7 Batch ⑤: 端到端集成测试 — middleware → api_events → aggregator → metrics_hourly → summary → threshold_check → alerts → ack.

覆盖:
1. middleware 落表 → aggregator 聚合 → metrics_hourly 命中 summary endpoint
2. threshold_check_job 触发 breach → observability_alerts → /alerts/active 可见
3. cooldown 期间不重复触发
4. /alerts/{id}/ack 后从 active 列表消失
5. record_api_call 失败 swallow 不阻塞响应 (用闭包覆盖 raise)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import TraceIDMiddleware
from backend.api.observability_router import router as obs_router
from backend.exceptions import register_exception_handlers
from backend.repository.db import get_connection
from backend.scheduler.jobs.maintenance import (
    observability_aggregator_job,
    observability_threshold_check_job,
)


@pytest.fixture
def client(temp_db):
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
    register_exception_handlers(app)

    @app.get("/test-ok")
    async def test_ok():
        return {"ok": True}

    @app.get("/test-500")
    async def test_500():
        raise RuntimeError("boom")

    app.include_router(obs_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. middleware → aggregator → summary 端到端 ───────────────────


def test_end_to_end_api_event_to_summary(client, temp_db):
    """middleware 落 5 行 (3 200 + 2 500) → 跑 aggregator → /summary 报 total=5 errors=2."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i, status in enumerate([200, 200, 200, 500, 500]):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/x', ?, ?, ?)",
            (f"e2e-{i}", status, 30 + i, now.isoformat()),
        )
    asyncio.run(observability_aggregator_job())

    r = client.get("/api/observability/summary")
    data = r.json()
    assert data["total"] == 5
    assert data["errors"] == 2


# ── 2. threshold breach → alert 可见 ─────────────────────────────


def test_threshold_breach_creates_alert(client, temp_db):
    """插 1 行 500 → threshold_check_job 应触发 critical breach."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    # 100 行 500 错误 → error_rate 100% → critical (>15)
    for i in range(100):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/y', 500, 30, ?)",
            (f"breach-{i}", now.isoformat()),
        )
    asyncio.run(observability_threshold_check_job())

    r = client.get("/api/observability/alerts/active")
    data = r.json()
    # 至少 1 条 critical (api.error_rate_pct)
    levels = [it["level"] for it in data["items"]]
    metrics = [it["metric"] for it in data["items"]]
    assert "critical" in levels
    assert "api.error_rate_pct" in metrics


# ── 3. cooldown 期间不重复触发 ────────────────────────────────────


def test_cooldown_dedupes_breach(client, temp_db):
    """同一 breach 连跑 2 次 → 只产生 1 条 alert (cooldown_until 兜底)."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i in range(100):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/y', 500, 30, ?)",
            (f"cd-{i}", now.isoformat()),
        )
    asyncio.run(observability_threshold_check_job())
    asyncio.run(observability_threshold_check_job())

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM observability_alerts "
        "WHERE metric = 'api.error_rate_pct' AND level = 'critical'"
    ).fetchone()
    assert int(rows["n"]) == 1


# ── 4. ack 后从 active 列表消失 ───────────────────────────────────


def test_ack_removes_from_active(client, temp_db):
    """ack 一条 alert → /alerts/active 不再包含它."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO observability_alerts "
        "(level, metric, value, threshold, window_minutes, detail, "
        "fired_at, cooldown_until, acked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        ("critical", "api.error_rate_pct", 20.0, 15.0, 60, "{}",
        now.isoformat(), now.isoformat()),
    )
    alert_id = cur.lastrowid

    r1 = client.get("/api/observability/alerts/active")
    assert any(it["id"] == alert_id for it in r1.json()["items"])

    r2 = client.post(f"/api/observability/alerts/{alert_id}/ack")
    assert r2.status_code == 200

    r3 = client.get("/api/observability/alerts/active")
    assert not any(it["id"] == alert_id for it in r3.json()["items"])


# ── 5. record_api_call 失败 swallow 不阻塞响应 ────────────────────


def test_record_api_call_failure_swallowed(client, temp_db):
    """模拟 DB 抛异常 → /test-ok 仍 200 (业务响应不被阻塞)."""
    def boom(*a, **kw):
        raise RuntimeError("simulated DB failure")
    with patch("backend.api.middleware.record_api_call", side_effect=boom):
        r = client.get("/test-ok")
        assert r.status_code == 200