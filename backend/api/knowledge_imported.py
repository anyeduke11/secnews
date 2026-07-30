"""Phase 8 — 资讯收藏聚合视图 API

提供 5 源数据聚合查询端点：
- GET /api/knowledge/imported — 聚合 favorites / cubox / bookmark / secnews_archive / secnews

与 /api/favorites 的分工：
- /api/favorites: favorites 单表，严格"已收藏"语义
- /api/knowledge/imported: 5 源聚合，"看看我导入了什么"全景视图
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.logging_config import logger
from backend.services.imported_aggregator import ImportedAggregator

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

aggregator = ImportedAggregator()


@router.get("/imported")
async def list_imported(
    type: Optional[str] = Query(None, description="数据源类型: favorites/cubox/bookmark/secnews_archive/secnews"),
    keyword: Optional[str] = Query(None, min_length=1, max_length=100, description="标题/内容搜索"),
    since: Optional[str] = Query(None, description="起始时间 (ISO 格式)"),
    until: Optional[str] = Query(None, description="截止时间 (ISO 格式)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """聚合 5 源数据，去重后排序（ingested_at DESC），分页返回。"""
    try:
        result = aggregator.get_items(
            source_type=type,
            keyword=keyword,
            since=since,
            until=until,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [item.__dict__ for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }
    except Exception as e:
        logger.error(f"Failed to get imported items: {e}")
        raise HTTPException(status_code=500, detail={"message": "Failed to get imported items"})


__all__ = ["router"]