"""Phase 12 — Alert API v2.

端点:
- GET    /api/alerts/v2                 告警事件列表 (支持 status/severity 筛选)
- GET    /api/alerts/v2/unread-count    未读告警数
- PUT    /api/alerts/v2/{id}/read       标记已读
- PUT    /api/alerts/v2/read-all        全部标记已读
- PUT    /api/alerts/v2/{id}/resolve    标记已解决
- POST   /api/alerts/v2/evaluate        手动触发规则评估
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.repository.db import get_connection
from backend.services.alert_engine import AlertEngine

router = APIRouter(prefix="/api/alerts/v2", tags=["alerts-v2"])


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


@router.get("")
async def list_alerts(
    status: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List alert events, with optional status/severity filtering."""
    sql = "SELECT * FROM alert_events WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    items = [_row_to_dict(r) for r in rows]
    return {"count": len(items), "items": items}


@router.get("/unread-count")
async def unread_count():
    """Get the count of unread alerts."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM alert_events WHERE status = 'unread'"
    ).fetchone()
    return {"count": row["c"]}


@router.put("/{alert_id}/read")
async def mark_read(alert_id: int):
    """Mark a single alert as read."""
    from datetime import datetime, timezone

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE alert_events SET status = 'read', read_at = ? WHERE id = ? AND status = 'unread'",
        (now, alert_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Alert not found or already read: {alert_id}"},
        )
    return {"status": "ok", "alert_id": alert_id}


@router.put("/read-all")
async def mark_all_read():
    """Mark all unread alerts as read."""
    from datetime import datetime, timezone

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE alert_events SET status = 'read', read_at = ? WHERE status = 'unread'",
        (now,),
    )
    return {"status": "ok", "updated": cur.rowcount}


@router.put("/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """Mark a single alert as resolved."""
    from datetime import datetime, timezone

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE alert_events SET status = 'resolved', read_at = ? WHERE id = ?",
        (now, alert_id),
    )
    if cur.rowcount == 0:
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