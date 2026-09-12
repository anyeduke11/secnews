"""GET /api/kl/metrics — read-only JSON snapshot of the KL trigger metrics.

Phase 10 — exposes :class:`backend.metrics.kl_metrics.KLMetrics` over
HTTP so the dashboard and external observability tools can read counters,
gauges, and histogram summaries without scraping Prometheus.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.metrics.kl_metrics import kl_metrics

router = APIRouter(prefix="/api/kl", tags=["kl"])


def _refresh_stage_counts() -> None:
    """Read the live count of items per lifecycle stage into the gauge.

    SQL 在 wiki_stats_service.kl_stage_counts (Batch 2 D 下沉);
    查询失败时 service 返回 None, gauge 保持旧值 (best-effort, 不阻断快照)。
    """
    from backend.services.wiki_stats_service import kl_stage_counts

    counts = kl_stage_counts()
    if counts is not None:
        kl_metrics.set_stage_counts(counts)


@router.get("/metrics")
def get_metrics() -> dict:
    """Return a snapshot of all KL metrics (counters, gauges, histograms)."""
    _refresh_stage_counts()
    return kl_metrics.snapshot()


@router.get("/metrics/counters")
def get_counters() -> dict:
    """Return just the counter block (smaller payload, no DB call)."""
    return kl_metrics.snapshot()["counters"]


@router.get("/metrics/stage-counts")
def get_stage_counts() -> dict:
    """Return the current per-stage item counts."""
    _refresh_stage_counts()
    return kl_metrics.snapshot()["gauges"].get("by_stage_count", {})


@router.get("/health")
def health() -> dict:
    """Cheap liveness probe for the KL subsystem."""
    snap = kl_metrics.snapshot()
    return {
        "ok": True,
        "counters": snap["counters"],
        "stages": snap["gauges"].get("by_stage_count", {}),
    }


__all__ = ["router"]
