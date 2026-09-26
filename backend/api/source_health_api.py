"""Phase 9 招标源质量门禁 API — 拆自 ``backend/api/sources.py`` (Batch 3 R3 行数收缩)。

- ``GET  /api/sources/health``  所有 / 指定分类的源健康度报告 (运维盯盘)
- ``GET  /api/sources/health/by-source/{category}/{source_name}``  单源累计统计
- ``POST /api/sources/health/by-source/{category}/{source_name}/reset``  手动重置 (清 zero_yield)
- ``POST /api/sources/health/by-source/{category}/{source_name}/dead``   手动标 dead
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from backend.repository.source_stats_repo import SourceStatsRepository
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ===========================================================================
# Phase 9 招标源质量门禁 API
# ===========================================================================
def _build_health_payload(category: str | None) -> dict:
    """同步构建 health 报告（在 thread pool 中执行）。"""
    from backend.services.source_census_service import build_census, registry_snapshot

    repo = SourceStatsRepository()
    rows = repo.list_by_category(category) if category else repo.list_all()
    summary = repo.summary_by_category()
    reg = registry_snapshot()
    census = build_census(reg)
    reg_keys, live_keys = reg["keys"], reg["enabled_keys"]

    def _key(r: dict) -> tuple[str, str]:
        return (str(r["category"]), str(r["source_name"]))

    # 只有"注册且启用"的源才该进分母: 旧口径把 source_stats 历史行全数计入,
    # 实测 152 行含 22 个已无 collector 抓取的孤儿行 + 2 个跨 category 重名。
    live = [r for r in rows if _key(r) in live_keys]

    def _count(status: str) -> int:
        return sum(1 for r in live if str(r["status"] or "") == status)

    return {
        "version": API_VERSION,
        "category": category or "all",
        "summary": summary,
        "sources": [
            {
                "category": r["category"],
                "source_name": r["source_name"],
                "source_url": r["source_url"],
                "last_seen_at": r["last_seen_at"],
                "last_checked_at": r["last_checked_at"],
                "total_runs": int(r["total_runs"] or 0),
                "zero_yield_runs": int(r["zero_yield_runs"] or 0),
                "total_items": int(r["total_items"] or 0),
                "last_error": r["last_error"],
                "status": r["status"],
                # 治理 T3: 介质维度 (migration 121), 前端矩阵按它分组
                "media_kind": r["media_kind"] or "web",
                # false = 历史遗留行, 已不再被任何 collector 抓取 (不该计入分母)
                "registered": _key(r) in reg_keys,
            }
            for r in rows
        ],
        "dead_count": sum(1 for r in rows if r["status"] == "dead"),
        "stale_count": sum(1 for r in rows if r["status"] == "stale"),
        "active_count": sum(1 for r in rows if r["status"] == "active"),
        # ↓ 新口径: 仅统计注册且启用的源 (前端心跳条应改用这一组)
        "registered_total": len(live),
        "registered_active": _count("active"),
        "registered_stale": _count("stale"),
        "registered_dead": _count("dead"),
        "census": census,
    }


@router.get("/health")
async def list_source_health(category: str | None = None):
    """返回所有 / 指定分类的源健康度报告（用于运维盯盘）。

    Phase 9 招标源质量门禁：
    - ``active``: 最近 1 次 collect 有产出
    - ``stale``: 连续 N 次零产出 (默认 3)
    - ``dead``: 连续 N 次零产出 (默认 6)

    ``summary`` 字段按 category 聚合 active / stale / dead / total 计数。
    """
    return await asyncio.to_thread(_build_health_payload, category)


@router.get("/health/by-source/{category}/{source_name}")
async def get_source_health(category: str, source_name: str):
    """返回单条 source 的累计统计。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    return {
        "version": API_VERSION,
        **{
            "category": row["category"],
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "last_seen_at": row["last_seen_at"],
            "last_checked_at": row["last_checked_at"],
            "total_runs": int(row["total_runs"] or 0),
            "zero_yield_runs": int(row["zero_yield_runs"] or 0),
            "total_items": int(row["total_items"] or 0),
            "last_error": row["last_error"],
            "status": row["status"],
        },
    }


@router.post("/health/by-source/{category}/{source_name}/reset")
async def reset_source(category: str, source_name: str):
    """手动重置 zero_yield_runs（运维工具，确认源已恢复时调用）。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    repo.reset(category, source_name)
    return {"status": "ok", "category": category, "source_name": source_name}


@router.post("/health/by-source/{category}/{source_name}/dead")
async def mark_dead_source(category: str, source_name: str):
    """手动标 dead（运维工具，确认源已下线时调用）。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    repo.mark_dead(category, source_name)
    return {"status": "ok", "category": category, "source_name": source_name}
