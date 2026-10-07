"""quality_rejection_api.py — /api/quality 拒绝统计与信源信誉查询 (DEV-0287 D5 拆分)。

R3 行数守卫: quality.py 306>300 (+6, 注册增长漂移) — 拆出三个只读查询端点:
- ``GET /api/quality/source-reputation``  信源信誉表
- ``GET /api/quality/rejection-log``      分页拒绝日志
- ``GET /api/quality/rejection-stats``    按 gate 聚合拒绝统计
URL/method 逐字不变 (router 同 prefix, 由 _registry 经 quality.py 聚合挂载)。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/quality", tags=["quality"])


# ---------------------------------------------------------------------------
# GET /api/quality/source-reputation
# ---------------------------------------------------------------------------
def _build_source_reputation() -> dict:
    """同步构建 source-reputation payload（在 thread pool 中执行）。"""
    from backend.services.quality_query_service import list_source_reputation

    return {
        "version": API_VERSION,
        "sources": list_source_reputation(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/source-reputation")
async def source_reputation():
    """返回 source 信誉表。

    Phase 9 修复：同步 DB query 放 thread pool。
    """
    return await asyncio.to_thread(_build_source_reputation)


# ---------------------------------------------------------------------------
# GET /api/quality/rejection-log
# ---------------------------------------------------------------------------
def _build_rejection_log(
    gate_name: str | None = None,
    source_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """同步构建 rejection-log payload（在 thread pool 中执行）。"""
    from backend.services.quality_query_service import query_rejection_log

    return query_rejection_log(
        gate_name=gate_name,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/rejection-log")
async def quality_rejection_log(
    gate_name: str | None = None,
    source_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """分页查询 quality_rejection_log。"""
    return await asyncio.to_thread(
        _build_rejection_log,
        gate_name, source_id, date_from, date_to, page, page_size,
    )


# ---------------------------------------------------------------------------
# GET /api/quality/rejection-stats
# ---------------------------------------------------------------------------
def _build_rejection_stats(
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """同步构建 rejection-stats payload（在 thread pool 中执行）。"""
    from backend.services.quality_query_service import rejection_stats

    return rejection_stats(date_from=date_from, date_to=date_to)


@router.get("/rejection-stats")
async def quality_rejection_stats(
    date_from: str | None = None,
    date_to: str | None = None,
):
    """按 gate 名称聚合统计拒绝次数。"""
    return await asyncio.to_thread(_build_rejection_stats, date_from, date_to)


__all__ = ["router"]
