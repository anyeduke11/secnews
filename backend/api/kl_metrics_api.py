"""GET /api/kl/metrics — read-only JSON snapshot of the KL trigger metrics.

Phase 10 — exposes :class:`backend.metrics.kl_metrics.KLMetrics` over
HTTP so the dashboard and external observability tools can read counters,
gauges, and histogram summaries without scraping Prometheus.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection
from backend.services.kl_state_machine import ALL_STAGES, LIFECYCLE_RAW

router = APIRouter(prefix="/api/kl", tags=["kl"])


def _refresh_stage_counts() -> None:
    """Read the live count of items per lifecycle stage into the gauge."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT lifecycle, COUNT(*) FROM knowledge_items "
            "WHERE lifecycle IN ({}) "
            "GROUP BY lifecycle".format(",".join("?" for _ in ALL_STAGES)),
            tuple(ALL_STAGES),
        ).fetchall()
        counts = {stage: 0 for stage in ALL_STAGES}
        for stage, n in rows:
            if stage in counts:
                counts[stage] = int(n)
        kl_metrics.set_stage_counts(counts)
    except Exception:
        # The gauge is best-effort; never fail the snapshot.
        pass


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
