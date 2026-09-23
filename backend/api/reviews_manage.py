"""Reviews 管理面 API (2026-09-21 复习栈能力丰富设计稿 §3.3)。

既有路径 (/due /stats /{type}/{id}) 留在 ``reviews.py`` 原地扩展;
新路径全部在本文件, 同 prefix ``/api/reviews``。

路由清单
--------
- ``GET    /api/reviews/forecast?days=7``            未来 N 天逐日到期数
- ``GET    /api/reviews/history?limit=50``           评分流水倒序 (含 reverted)
- ``GET    /api/reviews/cards?limit=200``            全部卡片 (管理视图数据源, enrich)
- ``POST   /api/reviews/{type}/{id}/undo``           撤销最近一次评分 (无活跃 log → 409)
- ``PATCH  /api/reviews/{type}/{id}``                暂停/恢复 {suspended: bool}
- ``DELETE /api/reviews/{type}/{id}``                删卡
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.reviews_log_repo import ReviewLogRepository
from backend.repository.reviews_repo import ReviewRepository
from backend.services import review_service
from backend.services.review_enrich import enrich_rows
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class SuspendRequest(BaseModel):
    """暂停/恢复请求体。"""

    suspended: bool = Field(..., description="true=暂停, false=恢复")


def _forecast(days: int) -> dict:
    return {
        "version": API_VERSION,
        "days": days,
        "items": review_service.forecast(days=days),
    }


def _history(limit: int) -> dict:
    items = ReviewLogRepository().list_recent(limit=limit)
    return {"version": API_VERSION, "count": len(items), "items": items}


def _cards(limit: int) -> dict:
    items = enrich_rows(ReviewRepository().list_all(limit=limit))
    return {"version": API_VERSION, "count": len(items), "items": items}


def _undo(entity_type: str, entity_id: str) -> dict:
    try:
        item = review_service.undo_grade(entity_type, entity_id)
    except KeyError as e:
        raise HTTPException(status_code=409, detail={"message": str(e)})
    return {"version": API_VERSION, "status": "ok", "item": item}


def _suspend(entity_type: str, entity_id: str, suspended: bool) -> dict:
    rows = review_service.set_suspended(entity_type, entity_id, suspended)
    if rows == 0:
        raise HTTPException(
            status_code=404,
            detail={"message": f"无复习记录: {entity_type}/{entity_id}"},
        )
    return {"version": API_VERSION, "status": "ok", "suspended": suspended}


def _delete(entity_type: str, entity_id: str) -> dict:
    rows = ReviewRepository().delete(entity_type, entity_id)
    if rows == 0:
        raise HTTPException(
            status_code=404,
            detail={"message": f"无复习记录: {entity_type}/{entity_id}"},
        )
    return {"version": API_VERSION, "status": "ok", "deleted": rows}


@router.get("/forecast")
async def forecast_endpoint(
    days: int = Query(7, ge=1, le=30, description="预报窗口天数"),
):
    """未来 N 天逐日到期计数 (排除 suspended, 含今日)。"""
    return await asyncio.to_thread(_forecast, days)


@router.get("/history")
async def history_endpoint(
    limit: int = Query(50, ge=1, le=500, description="最多返回条数"),
):
    """评分流水倒序流 (review_log, 含 reverted 标记)。"""
    return await asyncio.to_thread(_history, limit)


@router.get("/cards")
async def cards_endpoint(
    limit: int = Query(200, ge=1, le=500, description="最多返回条数"),
):
    """全部卡片列表 (管理视图表格数据源; 含 suspended, enrich 后返回)。"""
    return await asyncio.to_thread(_cards, limit)


@router.post("/{entity_type}/{entity_id}/undo")
async def undo_endpoint(entity_type: str, entity_id: str):
    """撤销最近一次评分, 恢复 prev 状态 (首评撤销 = 删卡)。"""
    return await asyncio.to_thread(_undo, entity_type, entity_id)


@router.patch("/{entity_type}/{entity_id}")
async def suspend_endpoint(entity_type: str, entity_id: str, req: SuspendRequest):
    """暂停/恢复一张卡 (suspended 卡不进 due 队列与预报)。"""
    return await asyncio.to_thread(_suspend, entity_type, entity_id, req.suspended)


@router.delete("/{entity_type}/{entity_id}")
async def delete_endpoint(entity_type: str, entity_id: str):
    """删除一张复习卡 (repo.delete, 不可逆)。"""
    return await asyncio.to_thread(_delete, entity_type, entity_id)


__all__ = ["router"]
