"""v1.7 Phase 3 — 统一搜索 API.

PRD §3.2.12 / §6.8: 跨 hotspots + knowledge_items 的统一搜索端点。

端点
----
- ``GET /api/search?q=&sources=&limit=`` — 统一搜索
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.services.search_service import unified_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query("", description="搜索关键词"),
    sources: Optional[str] = Query(
        None, description="实体类型过滤，逗号分隔 (hotspot,knowledge)"
    ),
    limit: int = Query(20, ge=1, le=100, description="最大返回条数"),
):
    """统一跨层搜索。

    返回结构::

        {
          "version": "1.7.0",
          "result": {
            "query": "...",
            "items": [...],
            "grouped": {"hotspot": [...], "knowledge": [...]}
          }
        }
    """
    source_list = (
        [s.strip() for s in sources.split(",") if s.strip()]
        if sources
        else None
    )
    result = unified_search(q, sources=source_list, limit=limit)
    return {"version": "1.7.0", "result": result}
