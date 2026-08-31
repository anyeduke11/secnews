"""SecNews Dashboard API — aggregated data for the security dashboard.

Four read-only endpoints: feed, pipeline, knowledge, stats.
All delegate to SecNewsDashboard for data aggregation.

v0.6.3 P0-1 卡顿根治: 所有 handler 一律 asyncio.to_thread 包同步聚合
(此前 async def 里直接跑同步 SQLite/文件扫描, 阻塞事件循环拖垮全站)。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.repository.db import get_connection
from backend.secnews_dashboard import SecNewsDashboard

router = APIRouter(prefix="/api/secnews", tags=["secnews"])

_wiki_fs = None


def _get_dashboard() -> SecNewsDashboard:
    """每次调用新建聚合器 (轻量, 无状态)。

    db 必须在**当前线程**取 (get_connection 是 thread-local, SQLite 连接
    默认 check_same_thread=True); P0-1 起 handler 跑在 to_thread 工作线程,
    缓存整个 dashboard 会把首个线程的连接带进别的线程 → ProgrammingError。
    wiki_fs 是进程级单例, 只取一次。
    """
    global _wiki_fs
    if _wiki_fs is None:
        from backend.kl_pipeline.runtime import get_production_wiki_fs
        _wiki_fs = get_production_wiki_fs()
    return SecNewsDashboard(db=get_connection(), wiki_fs=_wiki_fs)


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
