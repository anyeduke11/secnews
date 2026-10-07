"""kpi_api.py — GET /api/ops/kpi: P3-C 新口径 KPI 观测 (分诊时延 + 产物产出率)。

口径裁决 (DEV-0289, PLAN_P3 C): signals/hotspots 转化率带退场 (结构性不可达
+ 行业对标量「分诊时延」), 主指标 = triage_latency + artifact_yield;
signals_ratio 降级参考值仍可查。

- GET /api/ops/kpi?latency_days=30&yield_days=7
返回 { version, triage_latency, artifact_yield, signals_ratio_reference }。
只读; SQL 在 KpiService (R3)。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.services.kpi_service import KpiService
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/kpi")
def get_kpi(
    latency_days: int = Query(30, ge=1, le=365),
    yield_days: int = Query(7, ge=1, le=90),
) -> dict:
    """P3-C 新口径 KPI: 分诊时延 (P50/P90) + artifact 产出率 + 比率参考值。"""
    svc = KpiService()
    return {
        "version": API_VERSION,
        "triage_latency": svc.triage_latency(days=latency_days),
        "artifact_yield": svc.artifact_yield(days=yield_days),
        "signals_ratio_reference": svc.signals_ratio(days=yield_days),
    }


__all__ = ["router"]
