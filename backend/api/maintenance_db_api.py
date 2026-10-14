"""Maintenance API 子模块 — DB 健康 / 维护 / 去重 (拆自 maintenance.py)。

端点: /health · /table-stats · /dirty-report · /index-health · /vacuum
      /cleanup · /orphans · /duplicates · /cleanup-duplicates
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/health")
async def maintenance_health():
    """DB health: size, page counts, fragmentation."""
    from backend.services.maintenance_service import db_health
    return db_health()


@router.get("/table-stats")
async def maintenance_table_stats():
    """Detailed per-table row count and estimated size."""
    from backend.services.maintenance_service import table_stats
    return {"tables": table_stats()}


@router.get("/dirty-report")
async def maintenance_dirty_report():
    """Comprehensive dirty-data report."""
    from backend.services.maintenance_service import dirty_data_report
    return dirty_data_report()


@router.get("/index-health")
async def maintenance_index_health(
    mode: str = Query("full", pattern="^(quick|full)$",
                     description="full=integrity_check (含索引内容一致性); quick=仅 B-tree 结构"),
):
    """DEV-0320: 索引健康探测 (逐 schema: 索引计数/integrity 检查/ANALYZE 统计覆盖)。

    默认 full — 实测三库合计 ~1s, 是"索引是否真的健康"的权威答案;
    integrity_check 属读侧长查询, to_thread 防阻塞事件循环。
    """
    from backend.services.maintenance_service import index_health
    return await asyncio.to_thread(index_health, mode)


@router.post("/vacuum")
async def maintenance_vacuum():
    """VACUUM + REINDEX + ANALYZE. Frees unused pages, rebuilds indexes."""
    from backend.services.maintenance_service import run_vacuum
    # DEV-0318: VACUUM 是长事务, async 端点内同步执行会冻结事件循环
    return await asyncio.to_thread(run_vacuum)


@router.post("/cleanup")
async def maintenance_cleanup(
    days: int = Query(90, ge=1, le=365, description="保留最近 N 天的记录"),
    dry_run: bool = Query(True, description="True=仅预览, False=实际删除"),
):
    """Delete historical data older than N days.

    Tables: sync_history, collection_history, export_cache.
    Dry-run by default — use ``?dry_run=false`` to actually delete.
    """
    from backend.services.maintenance_service import cleanup_history
    # DEV-0318: 清理+VACUUM 为长事务, 移出事件线程避免冻结事件循环
    result = await asyncio.to_thread(cleanup_history, days=days, dry_run=dry_run)
    if not dry_run:
        from backend.services.maintenance_service import run_vacuum
        vac = await asyncio.to_thread(run_vacuum)
        result["vacuum"] = vac
    return result


@router.get("/orphans")
async def maintenance_orphans():
    """Detect orphaned knowledge items (no domain, no concepts)."""
    from backend.services.maintenance_service import detect_orphan_items
    return detect_orphan_items()


@router.get("/duplicates")
async def maintenance_duplicates():
    """Detect duplicate hotspots by URL and duplicate knowledge items by title."""
    from backend.services.maintenance_service import (
        detect_duplicate_hotspots,
        detect_duplicate_knowledge_items,
    )
    return {
        "hotspots": detect_duplicate_hotspots(),
        "knowledge_items": detect_duplicate_knowledge_items(),
    }


@router.post("/cleanup-duplicates")
async def maintenance_cleanup_duplicates(
    dry_run: bool = Query(True, description="True=仅预览, False=实际删除"),
):
    """Deduplicate hotspots (by URL) and knowledge items (by title).

    Keeps the earliest-inserted row per unique URL/title.
    """
    from backend.services.maintenance_service import (
        cleanup_duplicate_hotspots,
        cleanup_duplicate_knowledge_items,
    )
    # DEV-0318: 去重 DELETE 为长事务, 移出事件线程
    hotspots = await asyncio.to_thread(cleanup_duplicate_hotspots, dry_run=dry_run)
    ki = await asyncio.to_thread(cleanup_duplicate_knowledge_items, dry_run=dry_run)
    return {
        "hotspots": hotspots,
        "knowledge_items": ki,
        "dry_run": dry_run,
        "total_deleted": hotspots["total_deleted"] + ki["total_deleted"],
    }


__all__ = ["router"]