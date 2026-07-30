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
    region: str = Query("", description="标讯地区筛选（仅 category=bid 有效）"),
    tags: str = Query("", description="v1.7: 逗号分隔 tag id, 触发标签筛选"),
    tag_mode: str = Query("or", pattern="^(and|or)$", description="v1.7: 标签筛选模式"),
):
    """列表查询（cursor 分页）。

    Phase 9 修复：同步 DB query 放 thread pool，避免 cache miss 时阻塞 event loop。
    Phase 8: 新增 region 参数，仅对 category=bid 生效。
    v1.7 Phase 1: 新增 tags/tag_mode 标签筛选 (AND/OR), 传入 tags 时走 list_by_tags。
    """
    tag_ids = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if tag_ids:
        return await asyncio.to_thread(
            _service.list_by_tags, tag_ids, tag_mode, limit
        )
    return await asyncio.to_thread(
        _service.list_hotspots,
        category=category,
        time_range=time_range,
        cursor=cursor or None,
        limit=limit,
        keyword=keyword,
        region=region or None,
    )


@router.get("/regions")
async def list_regions():
    """列出所有标讯地区（仅 category=bid 且 region 非空）。"""
    from backend.repository.hotspot_repo import HotspotRepository
    regions = await asyncio.to_thread(HotspotRepository().list_regions)
    return {"regions": regions}


@router.get("/{item_id}")
async def get_hotspot(item_id: str):
    """单 item 详情。Phase 9 修复：同步 DB query 放 thread pool。"""
    return await asyncio.to_thread(_service.get_hotspot, item_id)
