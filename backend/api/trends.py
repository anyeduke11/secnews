"""Phase 4 /api/trends router."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.services.trend_service import TrendService

router = APIRouter(prefix="/api/trends", tags=["trends"])
_service = TrendService()


@router.get("")
async def get_trends(
    hours: int = Query(24, ge=1, le=168, description="小时数"),
    by_category: bool = Query(False, description="是否按类别拆分"),
):
    """24h 趋势。Phase 9 修复：同步 DB query 放 thread pool。"""
    if by_category:
        return await asyncio.to_thread(_service.get_category_trends, hours=hours)
    return await asyncio.to_thread(_service.get_trends, hours=hours)
