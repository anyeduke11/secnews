"""Maintenance API — DB health, vacuum, data cleanup, duplicate detection."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

log = logging.getLogger("hotspot.api.maintenance")
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


@router.post("/vacuum")
async def maintenance_vacuum():
    """VACUUM + REINDEX + ANALYZE. Frees unused pages, rebuilds indexes."""
    from backend.services.maintenance_service import run_vacuum
    return run_vacuum()


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
    result = cleanup_history(days=days, dry_run=dry_run)
    if not dry_run:
        from backend.services.maintenance_service import run_vacuum
        vac = run_vacuum()
        result["vacuum"] = vac
    return result


@router.get("/orphans")
async def maintenance_orphans():
    """Detect orphaned knowledge items (no domain, no concepts)."""
    from backend.services.maintenance_service import detect_orphan_items
    return detect_orphan_items()


@router.post("/cleanup-quality-logs")
async def maintenance_cleanup_quality_logs(
    days: int = Query(7, ge=1, le=365, description="保留最近 N 天的 quality 日志"),
    dry_run: bool = Query(True, description="True=仅预览, False=实际删除"),
):
    """Purge old quality_check_logs entries (main DB bloat culprit ~3M rows)."""
    from backend.services.maintenance_service import cleanup_quality_logs
    return cleanup_quality_logs(days=days, dry_run=dry_run)


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
    hotspots = cleanup_duplicate_hotspots(dry_run=dry_run)
    ki = cleanup_duplicate_knowledge_items(dry_run=dry_run)
    return {
        "hotspots": hotspots,
        "knowledge_items": ki,
        "dry_run": dry_run,
        "total_deleted": hotspots["total_deleted"] + ki["total_deleted"],
    }