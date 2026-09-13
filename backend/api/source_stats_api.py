"""Phase 3 源级调度健康 API — 拆自 ``backend/api/sources.py`` (Batch 3 R3 行数收缩)。

- ``GET  /api/sources/health/v2``          调度器状态机健康状态 (crawler_sources)
- ``GET  /api/sources/stats``              源健康状态聚合统计
- ``GET  /api/sources/alerts``             源告警列表 (分页)
- ``POST /api/sources/{source_id}/probe``  手动触发单源探活
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ===========================================================================
# Phase 3: 源级调度 + 健康状态 API
# ===========================================================================
@router.get("/health/v2")
async def get_source_health_v2():
    """Phase 3: 返回所有源的详细健康状态（crawler_sources 表）。

    返回字段: id, name, category, status, health_score, consecutive_failures,
    cooldown_until, last_success_at, last_yield_at, last_error, grace_rounds。

    口径: ``status`` 来自 Phase 3 **调度器状态机** (含 ``unknown`` / 停用源),
    既不是 Phase 9 的 liveness (``/health``), 也不是 Phase 4 的产出趋势
    (``/health/trend``) —— 三者度量不同事实, 用 ``status_equivalence`` 对照。
    """
    from backend.repository.source_scheduler_repo import SourceSchedulerRepository
    from backend.services.source_census_service import STATUS_EQUIVALENCE

    repo = SourceSchedulerRepository()
    sources = repo.list_all()
    statuses = [str(s.get("status", "unknown")) for s in sources]
    return {
        "version": API_VERSION,
        "metric": "phase3_scheduler_state",
        "measures": "调度器连续失败 / 冷却 / 健康分 (crawler_sources.status)",
        "registry_total": len(sources),
        "enabled_total": sum(1 for s in sources if bool(s.get("enabled", 1))),
        # unknown 通常是"注册了但从没被调度过"的源 —— 三个端点数字对不上的主因之一
        "unknown_status_count": sum(1 for x in statuses if x == "unknown"),
        "status_equivalence": STATUS_EQUIVALENCE,
        "sources": [
            {
                "id": s["id"],
                "name": s.get("name", ""),
                "category": s.get("category", ""),
                "status": s.get("status", "unknown"),
                "health_score": float(s.get("health_score", 0.0)),
                "consecutive_failures": int(s.get("consecutive_failures", 0)),
                "cooldown_until": s.get("cooldown_until"),
                "last_success_at": s.get("last_success_at"),
                "last_yield_at": s.get("last_yield_at"),
                "last_error": s.get("last_error"),
                "grace_rounds": int(s.get("grace_rounds", 0)),
                "priority": int(s.get("priority", 50)),
                "network_zone": str(s.get("network_zone") or "domestic"),
                "enabled": bool(s.get("enabled", 1)),
            }
            for s in sources
        ],
    }


@router.get("/stats")
async def get_source_stats():
    """Phase 3: 返回源健康状态聚合统计。

    返回: total, active, grace, stale, dead, disabled, active_rate.
    """
    from backend.repository.source_scheduler_repo import SourceSchedulerRepository
    repo = SourceSchedulerRepository()
    stats = repo.get_stats_summary()
    return {
        "version": API_VERSION,
        **stats,
    }


@router.get("/alerts")
async def get_source_alerts(
    source_id: str | None = None,
    level: str | None = None,
    since: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """Phase 3: 返回源告警列表（分页）。

    - source_id: 按来源筛选
    - level: 按告警级别筛选 (P1/P2)
    - since: 按 created_at >= since 筛选 (ISO 时间字符串)
    - page: 页码 (从 1 开始)
    - page_size: 每页条数 (默认 50)
    """
    from backend.repository.source_alert_repo import SourceAlertRepository
    repo = SourceAlertRepository()
    result = repo.list(
        source_id=source_id,
        level=level,
        since=since,
        page=page,
        page_size=page_size,
    )
    return {
        "version": API_VERSION,
        **result,
    }


@router.post("/{source_id}/probe")
async def probe_source_manual(source_id: str):
    """Phase 3: 手动触发单源探活。

    对指定源执行 HEAD/GET 探测，返回探测结果。
    """
    try:
        from backend.services.source_prober import probe_one
        result = await asyncio.to_thread(probe_one, source_id)
        return {
            "version": API_VERSION,
            **result.to_dict(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": f"probe failed: {str(e)[:200]}"},
        )
