"""observability_router.py — v0.7 Batch ③ 观测面 query API.

暴露 4 个 GET 端点供前端 Dashboard / StatusBar 用, 不写数据 (写由 TraceIDMiddleware
+ record_api_call + scheduler job 负责). 全部无鉴权 (与 /api/health 同级,
观测面板是 ops self-service 工具, 不属于敏感路径).

约定: 所有 endpoint 同步 (def) — async→def 线程池派发 (P3-1 教训). FastAPI 调
sync def handler 在线程池跑, 不阻塞事件循环.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from backend.repository.db import get_connection

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/summary")
def get_summary():
    """最近 1h 概览: total / error_count / error_rate / p95_latency_ms.

    直接从 api_events 单表聚合, 不读 hourly roll-up (后者有 5min 延迟且
    仅供趋势查询). Dashboard 卡片用此 endpoint.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_connection()
    cur = conn.execute(
        "SELECT COUNT(*) AS total, "
        "       SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS errors "
        "FROM api_events WHERE occurred_at > ?",
        (since,),
    )
    row = cur.fetchone()
    total = int(row["total"] or 0)
    errors = int(row["errors"] or 0)
    error_rate = (errors / total * 100) if total else 0.0

    # p95 走子查询 OFFSET (与 aggregator 同款近似)
    cur = conn.execute(
        "SELECT duration_ms FROM api_events "
        "WHERE occurred_at > ? "
        "ORDER BY duration_ms LIMIT 1 "
        "OFFSET (SELECT CAST(COUNT(*) * 0.95 AS INTEGER) FROM api_events "
        "         WHERE occurred_at > ?)",
        (since, since),
    )
    p95_row = cur.fetchone()
    p95 = int(p95_row["duration_ms"]) if p95_row else 0

    # Top 5 慢路径
    cur = conn.execute(
        "SELECT path_template, COUNT(*) AS n, MAX(duration_ms) AS mx "
        "FROM api_events WHERE occurred_at > ? "
        "GROUP BY path_template ORDER BY mx DESC LIMIT 5",
        (since,),
    )
    top_slow = [
        {"path_template": r["path_template"], "count": int(r["n"]),
         "max_ms": int(r["mx"])}
        for r in cur.fetchall()
    ]

    return {
        "window_minutes": 60,
        "total": total,
        "errors": errors,
        "error_rate_pct": round(error_rate, 2),
        "p95_latency_ms": p95,
        "top_slow_paths": top_slow,
        "as_of": _now_iso(),
    }


@router.get("/recent")
def get_recent(limit: int = Query(20, ge=1, le=200)):
    """api_events 最近 N 条 — StatusBar 与 Dashboard 实时面板用.

    按 occurred_at DESC 返回, 默认 20 条 (StatusBar 5s 刷新, 200 上限避免
    一次拉太多).
    """
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, trace_id, method, path_template, status, "
        "       duration_ms, error, occurred_at "
        "FROM api_events ORDER BY occurred_at DESC LIMIT ?",
        (int(limit),),
    )
    return {
        "items": [
            {
                "id": int(r["id"]),
                "trace_id": r["trace_id"],
                "method": r["method"],
                "path_template": r["path_template"],
                "status": int(r["status"]),
                "duration_ms": int(r["duration_ms"]),
                "error": r["error"],
                "occurred_at": r["occurred_at"],
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


@router.get("/timeseries")
def get_timeseries(hours: int = Query(24, ge=1, le=168),
                   path_template: str | None = None):
    """时序数据 (前端画图用) — 从 api_metrics_hourly 读聚合预计算.

    默认 24h, 上限 7d (168h). 按 hour 升序返回.
    """
    conn = get_connection()
    if path_template:
        cur = conn.execute(
            "SELECT hour, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? AND path_template = ? "
            "ORDER BY hour ASC",
            (
                (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
                    "%Y-%m-%dT%H"
                ),
                path_template,
            ),
        )
    else:
        cur = conn.execute(
            "SELECT hour, path_template, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? "
            "ORDER BY hour ASC",
            (
                (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
                    "%Y-%m-%dT%H"
                ),
            ),
        )
    return {
        "hours": hours,
        "path_template": path_template,
        "points": [
            {
                "hour": r["hour"],
                "path_template": r["path_template"] if "path_template" in r.keys() else path_template,
                "total": int(r["total"]),
                "errors": int(r["errors"]),
                "p50_ms": int(r["p50_ms"]),
                "p95_ms": int(r["p95_ms"]),
                "max_ms": int(r["max_ms"]),
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


@router.get("/llm-usage")
def get_llm_usage_recent(limit: int = Query(20, ge=1, le=200)):
    """llm_usage_log 最近 N 条 — 与 Batch ③ /api/llm/status observability 块
    复用, 但这个 endpoint 返回原始行而非聚合统计.

    与 /api/llm/status 区别: 后者返回 24h success_rate 等聚合, 本 endpoint
    返回原始调用行. 供 Dashboard "实时" 卡片用.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, provider, model, task, ok, latency_ms, "
            "       error, scene, started_at "
            "FROM llm_usage_log ORDER BY started_at DESC LIMIT ?",
            (int(limit),),
        )
    except Exception:
        return {"items": [], "as_of": _now_iso()}
    return {
        "items": [
            {
                "id": int(r["id"]),
                "provider": r["provider"],
                "model": r["model"],
                "task": r["task"],
                "ok": bool(r["ok"]),
                "latency_ms": int(r["latency_ms"]) if r["latency_ms"] is not None else None,
                "error": r["error"],
                "scene": r["scene"],
                "started_at": r["started_at"],
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


__all__ = ["router"]