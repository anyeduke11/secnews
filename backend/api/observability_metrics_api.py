"""observability_metrics_api.py — 观测面 metrics/breach 查询端点 (Batch 2 SQL 下沉).

本文件的路由由 observability_router.py 聚合 include (同 prefix /api/observability),
_registry.py 只挂 observability_router.router — 本文件不单独注册。

路由清单:
- GET  /api/observability/summary
- GET  /api/observability/recent
- GET  /api/observability/timeseries
- GET  /api/observability/llm-usage
- GET  /api/observability/alerts/active
- POST /api/observability/alerts/{alert_id}/ack
- GET  /api/observability/deliveries

约定: 全部 SQL 已下沉 backend/services/observability_query_service.py,
本层只做参数解析 + 调 service + 响应组装; 所有 endpoint 同步 (def) —
async→def 线程池派发 (P3-1 教训). 全部无鉴权 (与 /api/health 同级).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.services.observability_query_service import (
    ack_alert,
    query_active_alerts,
    query_api_summary,
    query_hourly_timeseries,
    query_recent_api_events,
    query_recent_deliveries,
    query_recent_llm_usage,
)

# 无 prefix — 聚合文件 observability_router.py 统一提供 /api/observability
metrics_router = APIRouter(tags=["observability"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@metrics_router.get("/summary")
def get_summary():
    """最近 1h 概览: total / error_count / error_rate / p95_latency_ms.

    Dashboard 卡片用此 endpoint.
    """
    return {**query_api_summary(hours=1), "as_of": _now_iso()}


@metrics_router.get("/recent")
def get_recent(limit: int = Query(20, ge=1, le=200)):
    """api_events 最近 N 条 — StatusBar 与 Dashboard 实时面板用.

    按 occurred_at DESC 返回, 默认 20 条 (StatusBar 5s 刷新, 200 上限避免
    一次拉太多).
    """
    return {"items": query_recent_api_events(limit), "as_of": _now_iso()}


@metrics_router.get("/timeseries")
def get_timeseries(hours: int = Query(24, ge=1, le=168),
                   path_template: str | None = None):
    """时序数据 (前端画图用) — 从 api_metrics_hourly 读聚合预计算.

    默认 24h, 上限 7d (168h). 按 hour 升序返回.
    """
    return {
        "hours": hours,
        "path_template": path_template,
        "points": query_hourly_timeseries(hours, path_template),
        "as_of": _now_iso(),
    }


@metrics_router.get("/llm-usage")
def get_llm_usage_recent(limit: int = Query(20, ge=1, le=200)):
    """llm_usage_log 最近 N 条 — 与 Batch ③ /api/llm/status observability 块
    复用, 但这个 endpoint 返回原始行而非聚合统计.

    与 /api/llm/status 区别: 后者返回 24h success_rate 等聚合, 本 endpoint
    返回原始调用行. 供 Dashboard "实时" 卡片用.
    """
    return {"items": query_recent_llm_usage(limit), "as_of": _now_iso()}


@metrics_router.get("/alerts/active")
def get_alerts_active():
    """活跃告警 (acked=0, fired_at 在最近 24h), 按 critical 先 / 触发时间倒序.

    前端 Dashboard 顶部活跃横幅 + StatusBar 角标共用. 限制 24h 窗口避免
    历史告警堆积; acked 告警走 /alerts/recent (Batch ⑤ 视情况再加).
    """
    return {**query_active_alerts(), "as_of": _now_iso()}


@metrics_router.post("/alerts/{alert_id}/ack")
def post_alerts_ack(alert_id: int):
    """标记告警已读 (acked=1). 不删 — 保留追溯链路.

    不写 audit_log (acm 是 self-service 操作, 非策略变更).
    """
    result = ack_alert(alert_id)
    if result.get("already"):
        # 已 ack 或 id 不存在 — idempotent 返 200, 客户端无需刷新
        return {"ok": True, "id": int(alert_id), "already": True}
    return {"ok": True, "id": int(alert_id), "acked_at": result["acked_at"]}


@metrics_router.get("/deliveries")
def get_deliveries(limit: int = Query(50, ge=1, le=500)):
    """列最近 alert_deliveries (审计 "告警是否真的发出去了")."""
    return {"deliveries": query_recent_deliveries(limit)}
