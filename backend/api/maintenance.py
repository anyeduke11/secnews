"""Maintenance API — DB health, vacuum, data cleanup."""

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
        # Also vacuum after cleanup
        from backend.services.maintenance_service import run_vacuum
        vac = run_vacuum()
        result["vacuum"] = vac
    return result


@router.get("/orphans")
async def maintenance_orphans():
    """Detect orphaned knowledge items (no domain, no concepts)."""
    from backend.services.maintenance_service import detect_orphan_items
    return detect_orphan_items()