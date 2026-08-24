"""SecNews Dashboard API — aggregated data for the security dashboard.

Four read-only endpoints: feed, pipeline, knowledge, stats.
All delegate to SecNewsDashboard for data aggregation.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.repository.db import get_connection
from backend.secnews_dashboard import SecNewsDashboard

router = APIRouter(prefix="/api/secnews", tags=["secnews"])

_dashboard: SecNewsDashboard | None = None


def _get_dashboard() -> SecNewsDashboard:
    global _dashboard
    if _dashboard is None:
        from backend.wiki_fs import WikiFs
        from backend.wiki_fs.root import resolve_wiki_root
        _dashboard = SecNewsDashboard(
            db=get_connection(),
            wiki_fs=WikiFs(resolve_wiki_root()),
        )
    return _dashboard


@router.get("/feed")
async def secnews_feed(
    category: str = Query("", description="Filter by category"),
    keyword: str = Query("", description="Search keyword"),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    """Newspaper-style feed data."""
    return _get_dashboard().get_feed(category=category, keyword=keyword, limit=limit)


@router.get("/pipeline")
async def secnews_pipeline() -> dict:
    """Pipeline observability data (funnel + queue + ledger)."""
    return _get_dashboard().get_pipeline_stats()


@router.get("/knowledge")
async def secnews_knowledge() -> dict:
    """Knowledge base statistics."""
    return _get_dashboard().get_knowledge_stats()


@router.get("/stats")
async def secnews_stats() -> dict:
    """Dashboard overview statistics."""
    return _get_dashboard().get_dashboard_stats()
