"""Cache API — clear/reset in-memory caches for troubleshooting."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.cache import list_cache, detail_cache

log = logging.getLogger("hotspot.api.cache")
router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.post("/clear")
async def clear_cache():
    """Clear all in-memory caches (list, detail, URL resolver)."""
    from backend.quality.final_url_resolver import clear_cache as clear_url_cache

    list_cache.clear()
    detail_cache.clear()
    clear_url_cache()

    log.info("All caches cleared")
    return {"status": "ok", "message": "All caches cleared"}


@router.get("/stats")
async def cache_stats():
    """Get current cache statistics."""
    from backend.cache import hit_rate, stats as cache_stats_fn

    return {
        "list_cache": {
            "size": list_cache.size(),
            **list_cache.stats(),
        },
        "detail_cache": {
            "size": detail_cache.size(),
            **detail_cache.stats(),
        },
        "hit_rate": hit_rate(),
        "overall": cache_stats_fn(),
    }