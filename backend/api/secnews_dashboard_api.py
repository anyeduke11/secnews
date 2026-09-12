"""SecNews Dashboard API — aggregated data for the security dashboard.

Four read-only endpoints: feed, pipeline, knowledge, stats.
All delegate to SecNewsDashboard for data aggregation.

v0.6.3 P0-1 卡顿根治: 所有 handler 一律 asyncio.to_thread 包同步聚合
(此前 async def 里直接跑同步 SQLite/文件扫描, 阻塞事件循环拖垮全站)。

Batch 2 D (api 层 SQL 下沉): 连接/聚合器装配在
``backend/services/secnews_dashboard_service.build_dashboard`` —
get_connection 是 thread-local, 必须在 to_thread 工作线程内调用。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/secnews", tags=["secnews"])


def _get_dashboard():
    from backend.services.secnews_dashboard_service import build_dashboard

    return build_dashboard()


@router.get("/feed")
async def secnews_feed(
    category: str = Query("", description="Filter by category"),
    keyword: str = Query("", description="Search keyword"),
    limit: int = Query(30, ge=1, le=100),
    profile_boost: bool = Query(False, description="Apply personalization boost"),
) -> dict:
    """Newspaper-style feed data."""
    def _run():
        return _get_dashboard().get_feed(
            category=category,
            keyword=keyword,
            limit=limit,
            profile_boost=profile_boost,
        )

    return await asyncio.to_thread(_run)


@router.get("/pipeline")
async def secnews_pipeline() -> dict:
    """Pipeline observability data (funnel + queue + ledger)."""
    return await asyncio.to_thread(lambda: _get_dashboard().get_pipeline_stats())


@router.get("/knowledge")
async def secnews_knowledge() -> dict:
    """Knowledge base statistics."""
    return await asyncio.to_thread(lambda: _get_dashboard().get_knowledge_stats())


@router.get("/stats")
async def secnews_stats() -> dict:
    """Dashboard overview statistics."""
    return await asyncio.to_thread(lambda: _get_dashboard().get_dashboard_stats())
