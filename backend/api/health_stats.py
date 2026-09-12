"""Phase 5 /api/stats router — 内部统计 (自 health.py 拆出, URL 不变)。

Phase 5 扩展字段:
- /api/stats: collect_runs_24h, success_rate_24h, avg_collect_duration_ms,
              last_fallback_at

Batch 2 SQL 下沉: stats 三查询 (hotspots 总数 / 24h 采集统计 / 末次
fallback) + 一致性校验迁至 backend.services.health_query_service。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from backend.api.health import _now_iso
from backend.cache import hit_rate
from backend.cache import stats as cache_stats
from backend.observability import uptime_s
from backend.services.health_query_service import (
    collect_stats_24h,
    consistency_check,
    db_size_mb,
    db_wal,
    last_fallback_at,
    stats_hotspots_total,
)

# 项目版本 (单一来源 backend/version.py)
from backend.version import APP_VERSION as VERSION

router = APIRouter(prefix="/api", tags=["health"])


def _build_stats_payload() -> dict:
    """同步构建 stats payload（在 thread pool 中执行）。"""
    total_hotspots = stats_hotspots_total()
    stats_24h = collect_stats_24h()

    return {
        "version": VERSION,
        "cache": {
            "stats": cache_stats(),
            "hit_rate": hit_rate(),
        },
        "db": {
            "hotspots_total": total_hotspots,
            "size_mb": db_size_mb(),
            "wal": db_wal(),
        },
        "uptime_s": round(uptime_s(), 2),
        "collect_runs_24h": stats_24h["collect_runs_24h"],
        "success_rate_24h": stats_24h["success_rate_24h"],
        "avg_collect_duration_ms": stats_24h["avg_collect_duration_ms"],
        "last_fallback_at": last_fallback_at(),
        "consistency_check": consistency_check(),
        "time": _now_iso(),
    }


@router.get("/stats")
async def stats():
    """内部统计（Phase 5 扩展）。

    Phase 9 修复：整体 payload 构建放 thread pool，避免 collect 期间阻塞 event loop。
    """
    return await asyncio.to_thread(_build_stats_payload)


__all__ = ["router"]
