"""v1.3.0 Phase 4: /api/weekly-report router."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.services.weekly_report_service import WeeklyReportService

router = APIRouter(prefix="/api/weekly-report", tags=["weekly-report"])
_service = WeeklyReportService()


@router.get("")
async def list_reports(
    limit: int = Query(12, ge=1, le=52, description="返回周数"),
):
    """列出最近的周报。"""
    return await asyncio.to_thread(_service.list_reports, limit=limit)


@router.get("/latest")
async def get_latest_report():
    """获取最新一期周报。"""
    return await asyncio.to_thread(_service.get_latest_report)


@router.get("/{week_start}")
async def get_report(week_start: str):
    """获取指定周的周报（week_start 格式: ISO datetime）。"""
    return await asyncio.to_thread(_service.get_report, week_start)


@router.post("/generate")
async def generate_report():
    """手动触发当前周的周报生成。"""
    return await asyncio.to_thread(_service.generate_report)


@router.post("/snapshot")
async def take_snapshot():
    """手动触发日级趋势快照。"""
    count = await asyncio.to_thread(_service.take_daily_snapshot)
    return {"status": "ok", "categories": count}