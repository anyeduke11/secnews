"""Phase 4 v1.7 数据源健康趋势 API (green/yellow/red) — 拆自 sources.py (Batch 3 R3)。

- ``GET /api/sources/health/trend``          所有数据源产出趋势健康度
- ``GET /api/sources/health/trend/{source}`` 单个数据源产出趋势健康度

与 Phase 9 ``GET /health`` 的区别: Phase 9 基于 ``zero_yield_runs``
(liveness: active/stale/dead); Phase 4 基于 24h 产出 vs 7d 日均
(trend: green/yellow/red)。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ===========================================================================
# Phase 4 v1.7 数据源健康趋势 API (green/yellow/red)
# ===========================================================================
def _build_trend_payload(source: str | None) -> dict:
    """同步构建 Phase 4 健康趋势报告 (在 thread pool 中执行)。

    口径自述: 本端点只覆盖 ``hotspots.source`` 里**出现过**的源名 (实测 ~47 个)。
    注册表里一条都没采到的源根本不在结果集中 —— 这正是它与 ``/health`` 的
    dead 数不一致的原因, 而不是谁算错了。
    """
    from backend.services.source_census_service import (
        STATUS_EQUIVALENCE,
        registry_snapshot,
    )
    from backend.services.source_health_service import (
        check_all_health,
        check_health,
        health_summary,
    )

    reg = registry_snapshot()
    framing = {
        "metric": "phase4_throughput_trend",
        "measures": "24h 产出 vs 7d 日均偏离度 (green/yellow/red)",
        "registry_total": reg["registered_total"],
        "registry_enabled": reg["enabled_total"],
        "status_equivalence": STATUS_EQUIVALENCE,
    }

    if source:
        result = check_health(source)
        return {"version": API_VERSION, "item": result, **framing}
    items = check_all_health()
    summary = health_summary()
    return {
        "version": API_VERSION,
        "summary": summary,
        "items": items,
        **framing,
        # 有产出记录、因此本端点能判定的源数; 与 registry_enabled 的差 = 完全无产出信号源
        "covered": len(items),
        "uncovered_by_no_output": max(0, reg["enabled_total"] - len(items)),
    }


@router.get("/health/trend")
async def list_source_health_trend():
    """Phase 4: 所有数据源的产出趋势健康度 (green/yellow/red).

    与 Phase 9 ``GET /health`` 的区别:
    - Phase 9 基于 ``zero_yield_runs`` (liveness: active/stale/dead)
    - Phase 4 基于 24h 产出 vs 7d 日均 (trend: green/yellow/red)
    """
    return await asyncio.to_thread(_build_trend_payload, None)


@router.get("/health/trend/{source}")
async def get_source_health_trend(source: str):
    """Phase 4: 单个数据源的产出趋势健康度."""
    return await asyncio.to_thread(_build_trend_payload, source)
