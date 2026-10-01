"""Phase 12 — Alert API v2.

端点:
- GET    /api/alerts/v2                 告警事件列表 (支持 status/severity 筛选)
- GET    /api/alerts/v2/unread-count    未读告警数
- PUT    /api/alerts/v2/{id}/read       标记已读
- PUT    /api/alerts/v2/read-all        全部标记已读
- PUT    /api/alerts/v2/{id}/resolve    标记已解决
- POST   /api/alerts/v2/evaluate        手动触发规则评估

Batch 2 SQL 下沉: alert_events 读写全部经 backend.services.alert_service
(alert_events 暂无 repo, 直写 SQL 位于 alert_service).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.services.alert_engine import AlertEngine
from backend.services.alert_service import (
    list_alert_events,
    mark_alert_read,
    mark_all_alerts_read,
    resolve_alert_event,
    unread_alert_count,
)

router = APIRouter(prefix="/api/alerts/v2", tags=["alerts-v2"])


@router.get("")
def list_alerts(
    status: str | None = Query(None),
    severity: str | None = Query(None),
    rule_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List alert events, with optional status/severity/rule_type filtering."""
    items = list_alert_events(
        status=status, severity=severity, rule_type=rule_type, limit=limit,
    )
    return {"count": len(items), "items": items}


@router.get("/unread-count")
def unread_count(scope: str = Query("all")):
    """未读告警数. scope=news → 仅资讯告警 4 规则 (首页徽标用)."""
    from backend.services.alert_service import NEWS_ALERT_RULE_TYPES

    if scope == "news":
        return {"count": unread_alert_count(rule_types=NEWS_ALERT_RULE_TYPES)}
    return {"count": unread_alert_count()}


@router.put("/{alert_id}/read")
def mark_read(alert_id: int):
    """Mark a single alert as read."""
    if not mark_alert_read(alert_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Alert not found or already read: {alert_id}"},
        )
    return {"status": "ok", "alert_id": alert_id}


@router.put("/read-all")
def mark_all_read():
    """Mark all unread alerts as read."""
    return {"status": "ok", "updated": mark_all_alerts_read()}


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    """Mark a single alert as resolved."""
    if not resolve_alert_event(alert_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Alert not found: {alert_id}"},
        )
    return {"status": "ok", "alert_id": alert_id}


@router.post("/evaluate")
async def evaluate_alerts():
    """Manually trigger alert rule evaluation."""
    engine = AlertEngine()
    results = engine.evaluate_all()
    return {"status": "ok", "results": results}


__all__ = ["router"]
