"""GET /api/kl/planning-actions — 规划动作列表 (Phase 13).

支持 ?status= 过滤与 PUT 状态更新。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.planning_service import PlanningService

router = APIRouter(prefix="/api/kl", tags=["kl"])


class StatusUpdate(BaseModel):
    """PUT /planning-actions/{id}/status 请求体."""
    status: str


@router.get("/planning-actions")
def get_planning_actions(
    status: str | None = Query(None, description="状态过滤: pending/in_progress/completed/dismissed"),
) -> list:
    """返回规划动作列表，支持按状态过滤."""
    svc = PlanningService()
    try:
        return svc.get_actions(status=status, limit=50)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/planning-actions/{action_id}/status")
def update_planning_action_status(action_id: int, body: StatusUpdate) -> dict:
    """更新指定规划动作的状态."""
    svc = PlanningService()
    try:
        ok = svc.update_action_status(action_id, body.status)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"状态更新失败: action_id={action_id} 不存在或状态转换不合法",
            )
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


__all__ = ["router"]