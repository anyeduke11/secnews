"""v0.7 Batch ③: API 观测 middleware 落表 + aggregator + router 单测.

覆盖:
1. record_api_call 落 api_events (正常 / 异常)
2. TraceIDMiddleware 200 / 4xx / 5xx 三种路径都落表
3. middleware 排除路径 (/api/health) 不落表
4. middleware path_template 用 FastAPI 路由模板 (不是 raw URL)
5. aggregator 跨小时聚合 (INSERT OR REPLACE 幂等)
6. /api/observability/summary 计算 error_rate + p95
7. /api/observability/recent 倒序 + limit
8. /api/observability/timeseries 按 hour 升序
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import TraceIDMiddleware
from backend.api.observability_router import router as obs_router
from backend.exceptions import register_exception_handlers
from backend.observability_records import record_api_call
from backend.repository.db import get_connection
from backend.scheduler.jobs.maintenance import observability_aggregator_job


@pytest.fixture
def client(temp_db):
    """构造测试 app: 自定义路由 + TraceIDMiddleware + observability router."""
    app = FastAPI(title="test obs api")
    app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
    register_exception_handlers(app)

    @app.get("/test-ok")
    async def test_ok():
        return {"ok": True}

    @app.get("/test-bad")
    async def test_bad():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="bad")

    @app.get("/test-500")
    async def test_500():
        raise RuntimeError("boom")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.include_router(obs_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. record_api_call 落表 (正常 / 异常) ────────────────────────


def test_record_api_call_inserts_row(temp_db):
    record_api_call(
        trace_id="abc123",
        method="GET",
        path_template="/test-ok",
        status=200,
        duration_ms=42,
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT trace_id, method, path_template, status, duration_ms "
        "FROM api_events WHERE trace_id = ?",
        ("abc123",),
    ).fetchone()
    assert row is not None
    assert row["method"] == "GET"
    assert row["status"] == 200
    assert row["duration_ms"] == 42


def test_record_api_call_error_truncated(temp_db):
    long_err = "x" * 1000
    record_api_call(
        trace_id="err1",
        method="POST",
        path_template="/test-500",
        status=500,
        duration_ms=100,
        error=long_err,
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT error FROM api_events WHERE trace_id = ?", ("err1",)
    ).fetchone()
    assert row is not None
    assert len(row["error"]) == 500  # truncated[:500]


# ── 2. middleware 落表 (200 / 4xx / 5xx) ──────────────────────────


def test_middleware_writes_2xx(client, temp_db):
    r = client.get("/test-ok", headers={"X-Trace-Id": "trace-2xx"})
    assert r.status_code == 200
    conn = get_connection()
    row = conn.execute(
        "SELECT status, path_template, trace_id FROM api_events "
        "WHERE trace_id = ?",
        ("trace-2xx",),
    ).fetchone()
    assert row is not None
    assert row["status"] == 200
    assert row["path_template"] == "/test-ok"


def test_middleware_writes_4xx(client, temp_db):
    r = client.get("/test-bad", headers={"X-Trace-Id": "trace-4xx"})
    assert r.status_code == 400
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM api_events WHERE trace_id = ?", ("trace-4xx",)
    ).fetchone()
    assert row is not None
    assert row["status"] == 400


def test_middleware_writes_5xx_with_error(client, temp_db):
    r = client.get("/test-500", headers={"X-Trace-Id": "trace-5xx"})
    assert r.status_code == 500
    conn = get_connection()
    row = conn.execute(
        "SELECT status, error FROM api_events WHERE trace_id = ?",
        ("trace-5xx",),
    ).fetchone()
    assert row is not None
    assert row["status"] == 500
    assert row["error"] is not None
    assert "RuntimeError" in row["error"]


# ── 3. 排除路径不入表 ─────────────────────────────────────────────


def test_excluded_health_path_not_recorded(client, temp_db):
    r = client.get("/api/health")
    assert r.status_code == 200
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM api_events WHERE path_template = '/api/health'"
    ).fetchone()
    assert int(row["n"]) == 0


# ── 4. aggregator 跨小时聚合 ──────────────────────────────────────


def test_aggregator_rolls_up_api_events(temp_db):
    """往 api_events 插 3 行 (跨 2 小时), 跑 aggregator, 验证 metrics_hourly."""
    now = datetime.now(timezone.utc)
    # 同一 path_template, 3 个 duration_ms, 跨 2 小时 (now / now-1h)
    rows_to_insert = [
        ("trace-a", "GET", "/api/foo", 200, 10, None,
         now.isoformat()),
        ("trace-b", "GET", "/api/foo", 200, 20, None,
         (now.replace(minute=0, second=0, microsecond=0)).isoformat()),
        ("trace-c", "GET", "/api/foo", 500, 100, "boom",
         (now - timedelta(hours=1)).isoformat()),
    ]
    conn = get_connection()
    for row in rows_to_insert:
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, error, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )

    asyncio.run(observability_aggregator_job())

    rows = conn.execute(
        "SELECT path_template, total, errors, p50_ms, p95_ms, max_ms "
        "FROM api_metrics_hourly WHERE path_template = '/api/foo'"
    ).fetchall()
    assert len(rows) >= 1
    total = sum(int(r["total"]) for r in rows)
    assert total == 3
    errors = sum(int(r["errors"]) for r in rows)
    assert errors == 1


# ── 5. /api/observability/summary ────────────────────────────────


def test_summary_endpoint_computes_error_rate(client, temp_db):
    """插 5 行: 4 200 + 1 500, summary 应该 total=5 errors=1 rate=20."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i, status in enumerate([200, 200, 200, 200, 500]):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/x', ?, ?, ?)",
            (f"sum-{i}", status, 50 + i, now.isoformat()),
        )
    r = client.get("/api/observability/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert data["errors"] == 1
    assert data["error_rate_pct"] == 20.0
    assert "p95_latency_ms" in data
    assert "top_slow_paths" in data


# ── 6. /api/observability/recent ─────────────────────────────────


def test_recent_endpoint_returns_desc(client, temp_db):
    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i in range(3):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/y', 200, 10, ?)",
            (f"rec-{i}", now.isoformat()),
        )
    r = client.get("/api/observability/recent?limit=2")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2


# ── 7. /api/observability/timeseries ─────────────────────────────


def test_timeseries_endpoint_returns_hourly_aggregates(client, temp_db):
    now = datetime.now(timezone.utc)
    hour_str = now.strftime("%Y-%m-%dT%H")
    conn = get_connection()
    # 直接往 hourly 表插一行, 不依赖 aggregator (避免本次跑两次 job)
    conn.execute(
        "INSERT OR REPLACE INTO api_metrics_hourly "
        "(hour, path_template, total, errors, p50_ms, p95_ms, max_ms) "
        "VALUES (?, '/api/z', 100, 5, 30, 80, 200)",
        (hour_str,),
    )
    r = client.get("/api/observability/timeseries?hours=24&path_template=/api/z")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) >= 1
    assert points[-1]["path_template"] == "/api/z"
    assert points[-1]["total"] == 100


# ── 8. observability_query_service 直接单测 (Batch 2 SQL 下沉) ──────────


def test_query_api_summary_shape(temp_db):
    """service 层 summary: total/errors/error_rate_pct/top_slow_paths 齐全."""
    from backend.services.observability_query_service import query_api_summary

    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i, status in enumerate([200, 500]):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/s', ?, ?, ?)",
            (f"svc-{i}", status, 40 + i, now.isoformat()),
        )
    data = query_api_summary(hours=1)
    assert data["window_minutes"] == 60
    assert data["total"] == 2
    assert data["errors"] == 1
    assert data["error_rate_pct"] == 50.0
    assert isinstance(data["p95_latency_ms"], int)
    assert data["top_slow_paths"][0]["path_template"] == "/api/s"


def test_query_recent_api_events_desc_limit(temp_db):
    from backend.services.observability_query_service import query_recent_api_events

    now = datetime.now(timezone.utc)
    conn = get_connection()
    for i in range(3):
        conn.execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, occurred_at) "
            "VALUES (?, 'GET', '/api/r', 200, 10, ?)",
            (f"qr-{i}", now.isoformat()),
        )
    items = query_recent_api_events(limit=2)
    assert len(items) == 2
    assert set(items[0].keys()) == {
        "id", "trace_id", "method", "path_template", "status",
        "duration_ms", "error", "occurred_at",
    }


def test_query_hourly_timeseries_with_and_without_filter(temp_db):
    from backend.services.observability_query_service import query_hourly_timeseries

    hour_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO api_metrics_hourly "
        "(hour, path_template, total, errors, p50_ms, p95_ms, max_ms) "
        "VALUES (?, '/api/t1', 10, 1, 5, 9, 20)",
        (hour_str,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO api_metrics_hourly "
        "(hour, path_template, total, errors, p50_ms, p95_ms, max_ms) "
        "VALUES (?, '/api/t2', 20, 2, 6, 10, 30)",
        (hour_str,),
    )
    filtered = query_hourly_timeseries(hours=24, path_template="/api/t1")
    assert len(filtered) == 1
    # 过滤分支下 path_template 用查询参数回填 (原 api 层行为)
    assert filtered[0]["path_template"] == "/api/t1"
    assert filtered[0]["total"] == 10
    unfiltered = query_hourly_timeseries(hours=24)
    assert {p["path_template"] for p in unfiltered} == {"/api/t1", "/api/t2"}


def test_query_recent_llm_usage_missing_table_returns_empty(temp_db):
    """llm_usage_log 表不存在 → 降级返空 (与原 api 层 try/except 行为一致)."""
    from backend.services.observability_query_service import query_recent_llm_usage

    assert query_recent_llm_usage(limit=5) == []


def test_query_active_alerts_and_ack_roundtrip(temp_db):
    from backend.services.observability_query_service import (
        ack_alert,
        query_active_alerts,
    )

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO observability_alerts "
        "(level, metric, value, threshold, window_minutes, detail, "
        "fired_at, cooldown_until, acked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        ("warn", "api.p95_latency_ms", 900.0, 800.0, 60, "{}",
         now, now),
    )
    alert_id = cur.lastrowid

    active = query_active_alerts()
    assert active["warn_count"] == 1
    assert active["critical_count"] == 0

    first = ack_alert(alert_id)
    assert "acked_at" in first
    second = ack_alert(alert_id)
    assert second == {"already": True}
    assert not any(
        it["id"] == alert_id for it in query_active_alerts()["items"]
    )


def test_query_recent_deliveries_shape(temp_db):
    from backend.services.observability_query_service import query_recent_deliveries

    conn = get_connection()
    conn.execute(
        "INSERT INTO alert_deliveries (alert_id, channel, ok, status_code, delivered_at) "
        "VALUES (1, 'status_bar', 1, 200, '2026-01-01T00:00:00')"
    )
    rows = query_recent_deliveries(limit=10)
    assert len(rows) == 1
    assert rows[0]["channel"] == "status_bar"
    assert rows[0]["ok"] is True


def test_query_audit_log_items_detail_parse(temp_db):
    from backend.services.observability_query_service import query_audit_log_items

    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log (actor, action, target, detail, occurred_at) "
        "VALUES ('web', 'test.act', 't1', '{\"k\": 1}', '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO audit_log (actor, action, target, detail, occurred_at) "
        "VALUES ('web', 'test.act2', 't2', 'not-json', '2026-01-01T00:00:01')"
    )
    items = query_audit_log_items(action="test.act", limit=10)
    assert len(items) == 1
    assert items[0]["detail"] == {"k": 1}
    items_all = query_audit_log_items(limit=10)
    assert len(items_all) == 2
    assert items_all[0]["detail"] == "not-json"  # 坏 JSON 原样保留
    assert items_all[0]["occurred_at"] == "2026-01-01T00:00:01"