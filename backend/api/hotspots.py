"""Phase 4 /api/hotspots router."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.services.hotspot_service import HotspotService

router = APIRouter(prefix="/api/hotspots", tags=["hotspots"])
_service = HotspotService()


@router.get("")
async def list_hotspots(
    category: str = Query("all", description="分类筛选，all 或具体值"),
    time_range: str = Query("7d", description="时间范围: 1d / 7d / 30d"),
    cursor: str = Query("", description="游标分页（首次为空）"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    keyword: str = Query("", description="关键词搜索"),
):
    """列表查询（cursor 分页）。

    Phase 9 修复：同步 DB query 放 thread pool，避免 cache miss 时阻塞 event loop。
    """
    return await asyncio.to_thread(
        _service.list_hotspots,
        category=category,
        time_range=time_range,
        cursor=cursor or None,
        limit=limit,
        keyword=keyword,
    )


@router.get("/{item_id}")
async def get_hotspot(item_id: str):
    """单 item 详情。Phase 9 修复：同步 DB query 放 thread pool。"""
    return await asyncio.to_thread(_service.get_hotspot, item_id)
