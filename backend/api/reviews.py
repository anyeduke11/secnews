"""v1.7 Phase 2 — Reviews API (SM-2 间隔复习)。

路由清单
--------
- ``GET  /api/reviews/due``                  到期复习队列
- ``POST /api/reviews/{entity_type}/{entity_id}/grade``  提交评分
- ``GET  /api/reviews/stats``                复习统计
- ``POST /api/reviews/{entity_type}/{entity_id}``       为新概念创建首条复习
- ``GET  /api/reviews/{entity_type}/{entity_id}``       查看某对象复习状态
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.reviews_repo import ReviewRepository
from backend.services.review_service import (
    create_review,
    list_due,
    stats,
    submit_grade,
)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class GradeRequest(BaseModel):
    """评分请求体。grade 0-5 (0-2 失败, 3-5 通过)。"""

    grade: int = Field(..., ge=0, le=5, description="SM-2 评分 0-5")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _list_due(limit: int) -> dict:
    items = list_due(limit=limit)
    return {"version": "1.7.0", "count": len(items), "items": items}


def _grade(entity_type: str, entity_id: str, grade: int) -> dict:
    try:
        row = submit_grade(entity_type, entity_id, grade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    return {"version": "1.7.0", "status": "ok", "item": row}


def _create(entity_type: str, entity_id: str, interval_days: int) -> dict:
    row = create_review(entity_type, entity_id, initial_interval_days=interval_days)
    return {"version": "1.7.0", "item": row}


def _get(entity_type: str, entity_id: str) -> dict:
    row = ReviewRepository().get(entity_type, entity_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"无复习记录: {entity_type}/{entity_id}"},
        )
    return {"version": "1.7.0", "item": row}


def _stats() -> dict:
    return {"version": "1.7.0", "stats": stats()}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/due")
async def due_reviews(
    limit: int = Query(20, ge=1, le=200, description="最多返回条数"),
):
    """列出到期复习记录 (due_at <= now)。"""
    return await asyncio.to_thread(_list_due, limit)


@router.post("/{entity_type}/{entity_id}/grade")
async def grade_review(entity_type: str, entity_id: str, req: GradeRequest):
    """提交评分 (0-5), 更新 SM-2 状态。"""
    return await asyncio.to_thread(_grade, entity_type, entity_id, req.grade)


@router.post("/{entity_type}/{entity_id}", status_code=201)
async def create_review_endpoint(
    entity_type: str,
    entity_id: str,
    interval_days: int = Query(1, ge=0, le=365, description="首次到期天数"),
):
    """为新学概念创建首条复习记录 (验收 1)。已存在则返回现有, 不覆盖。"""
    return await asyncio.to_thread(_create, entity_type, entity_id, interval_days)


@router.get("/{entity_type}/{entity_id}")
async def get_review(entity_type: str, entity_id: str):
    """查看某对象的复习状态。"""
    return await asyncio.to_thread(_get, entity_type, entity_id)


@router.get("/stats")
async def review_stats():
    """复习统计: 总数 / 到期数 / 平均 easiness。"""
    return await asyncio.to_thread(_stats)


__all__ = ["router"]
