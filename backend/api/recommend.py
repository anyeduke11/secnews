"""v1.7 Phase 4 — 上下文推荐 API.

PRD §3.2.7: 基于标签重叠度的上下文推荐端点。

端点
----
- ``GET /api/recommend/{entity_type}/{entity_id}?limit=`` — 获取推荐列表
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.services.recommend_service import recommend

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


@router.get("/{entity_type}/{entity_id}")
async def get_recommendations(
    entity_type: str,
    entity_id: str,
    limit: int = Query(5, ge=1, le=20, description="最大返回条数"),
):
    """获取基于标签重叠的上下文推荐。

    Parameters
    ----------
    entity_type:
        ``"knowledge"`` 或 ``"hotspot"``。
    entity_id:
        种子实体 ID。
    limit:
        最多返回条数 (1-20)。

    Returns
    -------
    dict
        ``{"version": "1.7.0", "entity_type", "entity_id", "items": [...]}``
    """
    items = recommend(entity_type, entity_id, limit=limit)
    return {
        "version": "1.7.0",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "items": items,
    }
