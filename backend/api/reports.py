"""Reports API — 日报 / 月报独立端点 (v1.9 Editorial).

解耦前 RoutePage 的日报和月报共享 /api/hotspots?time_range=1d/30d，
现拆为独立 API，每个返回报告专用的结构化数据。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.services.daily_report_overview_service import (
    generate_daily_overview,
)
from backend.services.hotspot_service import HotspotService
from backend.services.monthly_report_service import (
    generate_monthly_overview,
    list_available_months,
)
from backend.services.weekly_report_overview_service import (
    generate_weekly_overview,
    list_available_weeks,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])
_service = HotspotService()


@router.get("/daily")
async def daily_report():
    """日报: 当日热点 + 分类汇总统计。

    返回结构与 /api/hotspots?time_range=1d 一致，但明确为报告场景定制。
    """
    result = await asyncio.to_thread(
        _service.list_hotspots,
        category="all",
        time_range="24h",
        limit=200,
    )
    return result


@router.get("/daily/overview")
async def daily_overview():
    """日报概览: 今日主线条 + 热点分析 + 分类看点 + 其他资讯."""
    return await asyncio.to_thread(generate_daily_overview)


@router.get("/monthly")
async def monthly_report():
    """月报: 近 30 天热点 + 分类汇总统计。

    返回结构与 /api/hotspots?time_range=30d 一致，但明确为报告场景定制。
    """
    result = await asyncio.to_thread(
        _service.list_hotspots,
        category="all",
        time_range="30d",
        limit=500,
    )
    return result


@router.get("/monthly/overview")
async def monthly_overview(offset: int = Query(0, description="月份偏移: 0=本月, -1=上月")):
    """月报概览: 主线条 + 分类看点 + 精选文章 (结构化数据)."""
    return await asyncio.to_thread(generate_monthly_overview, offset)


@router.get("/monthly/available")
async def available_months():
    """列出有数据的月份，供月份切换器使用。"""
    return {"months": list_available_months()}


@router.get("/weekly/overview")
async def weekly_overview(week_start: str = Query(..., description="ISO 周起始日期, 如 2026-07-27")):
    """周报概览: 主线条 + 分类看点 + 精选文章 (每看点 3 篇, 最多 10 看点)."""
    return await asyncio.to_thread(generate_weekly_overview, week_start)


@router.get("/weekly/available")
async def available_weeks():
    """列出有数据的周，供周报切换器使用。"""
    return {"weeks": list_available_weeks()}


__all__ = ["router"]