"""observability_query_service.py — 观测面 query 侧服务层 (Batch 2 SQL 下沉).

把 api 层 (observability_router / observability_metrics_api / observability_audit_api)
的直连 SQL 收敛到此服务: api handler 只做参数解析 + 调 service + 响应组装,
响应 JSON 形状逐字不变 (as_of / version 等信封字段仍由 api 层补).

数据来源 (写侧在别处, 本模块只读 + 一个 ack UPDATE):
- api_events            — TraceIDMiddleware 落表 (backend/observability_records.py)
- api_metrics_hourly    — observability_aggregator_job 预计算
- llm_usage_log         — LLM 调用记录
- observability_alerts  — threshold_check_job / 手工插入
- alert_deliveries      — alert_dispatcher 投递回执
- audit_log             — record_audit 各处写入

依赖方向: service → repository (get_connection), 严禁 import backend.api.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


def _since_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# ── api_events 查询 ───────────────────────────────────────────────────────


def query_api_summary(hours: int = 1) -> dict[str, Any]:
    """最近 N 小时概览: total / errors / error_rate_pct / p95 / top 5 慢路径.

    直接从 api_events 单表聚合, 不读 hourly roll-up (后者有 5min 延迟且
    仅供趋势查询). p95 走子查询 OFFSET (与 aggregator 同款近似).
    """
    since = _since_iso(hours)
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
        "window_minutes": hours * 60,
        "total": total,
        "errors": errors,
        "error_rate_pct": round(error_rate, 2),
        "p95_latency_ms": p95,
        "top_slow_paths": top_slow,
    }


def query_recent_api_events(limit: int = 20) -> list[dict[str, Any]]:
    """api_events 最近 N 条 (occurred_at DESC) — StatusBar / Dashboard 实时面板."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, trace_id, method, path_template, status, "
        "       duration_ms, error, occurred_at "
        "FROM api_events ORDER BY occurred_at DESC LIMIT ?",
        (int(limit),),
    )
    return [
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
    ]


def query_hourly_timeseries(
    hours: int = 24, path_template: str | None = None
) -> list[dict[str, Any]]:
    """api_metrics_hourly 预聚合时序点 (hour 升序), 可按 path_template 过滤."""
    conn = get_connection()
    since_hour = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H")
    if path_template:
        cur = conn.execute(
            "SELECT hour, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? AND path_template = ? "
            "ORDER BY hour ASC",
            (since_hour, path_template),
        )
    else:
        cur = conn.execute(
            "SELECT hour, path_template, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? "
            "ORDER BY hour ASC",
            (since_hour,),
        )
    return [
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
    ]


def query_recent_llm_usage(limit: int = 20) -> list[dict[str, Any]]:
    """llm_usage_log 最近 N 条原始调用行; 表缺失等异常降级返空."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, provider, model, task, ok, latency_ms, "
            "       error, scene, started_at "
            "FROM llm_usage_log ORDER BY started_at DESC LIMIT ?",
            (int(limit),),
        )
    except Exception:
        return []
    return [
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
    ]


# ── observability_alerts 查询 + ack ──────────────────────────────────────


def query_active_alerts() -> dict[str, Any]:
    """活跃告警 (acked=0, fired_at 在最近 24h), critical 先 / 触发时间倒序.

    失败降级返空 — 不阻塞前端展示, 仅日志.
    """
    try:
        cutoff = _since_iso(24)
        conn = get_connection()
        cur = conn.execute(
            "SELECT id, level, metric, value, threshold, window_minutes, "
            "       detail, fired_at, cooldown_until "
            "FROM observability_alerts "
            "WHERE acked = 0 AND fired_at > ? "
            "ORDER BY "
            "  CASE level WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, "
            "  fired_at DESC",
            (cutoff,),
        )
        items = []
        for r in cur.fetchall():
            items.append({
                "id": int(r["id"]),
                "level": r["level"],
                "metric": r["metric"],
                "value": float(r["value"]),
                "threshold": float(r["threshold"]),
                "window_minutes": int(r["window_minutes"]),
                "detail": r["detail"],
                "fired_at": r["fired_at"],
                "cooldown_until": r["cooldown_until"],
            })
        return {
            "items": items,
            "critical_count": sum(1 for i in items if i["level"] == "critical"),
            "warn_count": sum(1 for i in items if i["level"] == "warn"),
        }
    except Exception as e:
        logger.warning(f"query_active_alerts failed: {e}")
        return {"items": [], "critical_count": 0, "warn_count": 0}


def ack_alert(alert_id: int) -> dict[str, Any]:
    """标记告警已读 (acked=1, 不删 — 保留追溯链路).

    返回 {"already": True} (已 ack 或 id 不存在, 幂等) 或 {"acked_at": iso};
    调用方补 {"ok": True, "id": ...} 信封.
    """
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE observability_alerts SET acked = 1, acked_at = ? "
        "WHERE id = ? AND acked = 0",
        (now, int(alert_id)),
    )
    if cur.rowcount == 0:
        return {"already": True}
    return {"acked_at": now}


def query_recent_deliveries(limit: int = 50) -> list[dict[str, Any]]:
    """最近 alert_deliveries (审计 "告警是否真的发出去了")."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, alert_id, channel, ok, status_code, error, delivered_at "
        "FROM alert_deliveries ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "alert_id": r["alert_id"],
            "channel": r["channel"],
            "ok": bool(r["ok"]),
            "status_code": r["status_code"],
            "error": r["error"],
            "delivered_at": r["delivered_at"],
        }
        for r in rows
    ]


# ── audit_log 查询 (v1.0 T16 收口) ───────────────────────────────────────


def query_audit_log_items(action: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """audit_log 最近 N 条 (occurred_at DESC), action 可选过滤; detail 反序列化.

    detail 是 JSON-encoded 文本, 解析失败原样保留 (与旧 api 层行为一致).
    """
    conn = get_connection()
    if action:
        rows = conn.execute(
            "SELECT actor, action, target, detail, occurred_at "
            "FROM audit_log WHERE action = ? ORDER BY occurred_at DESC LIMIT ?",
            (action, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT actor, action, target, detail, occurred_at "
            "FROM audit_log ORDER BY occurred_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    items = []
    for r in rows:
        item = {
            "actor": r[0], "action": r[1], "target": r[2],
            "occurred_at": r[4],
        }
        try:
            item["detail"] = json.loads(r[3]) if r[3] else {}
        except (json.JSONDecodeError, TypeError):
            item["detail"] = r[3]
        items.append(item)
    return items


__all__ = [
    "ack_alert",
    "query_active_alerts",
    "query_api_summary",
    "query_audit_log_items",
    "query_hourly_timeseries",
    "query_recent_api_events",
    "query_recent_deliveries",
    "query_recent_llm_usage",
]
