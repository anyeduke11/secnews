"""GET /api/kl/compounding — 复利仪表盘聚合指标 (Phase 13).

返回每日/每周/每月摄入趋势、Top 概念、触发器健康度、生命周期阶段分布。
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection

router = APIRouter(prefix="/api/kl", tags=["kl"])


def _to_score(val: float | None) -> float:
    """Convert nullable AVG result to float."""
    return round(val, 4) if val is not None else 0.0


@router.get("/compounding")
def get_compounding() -> dict:
    """Return compounding metrics for the knowledge dashboard.

    Returns
    -------
    daily_trend
        items ingested per day (last 30d) with count and avg mastery score
    weekly_trend
        items per week (last 12w) with count and avg mastery score
    monthly_trend
        items per month (last 6m) with count and avg mastery score
    top_concepts
        top 10 concepts by link participation (name + score)
    trigger_health
        T1-T4 failed counts + dead_letter_count from in-process metrics
    stage_distribution
        count of items per lifecycle stage
    """
    conn = get_connection()

    # ── Daily trend (last 30 days) ──────────────────────────────
    daily = conn.execute(
        """
        SELECT DATE(ingested_at) AS day,
               COUNT(*) AS count,
               AVG(CAST(mastery AS REAL)) AS avg_score
        FROM knowledge_items
        WHERE ingested_at >= DATE('now', '-30 days')
        GROUP BY day
        ORDER BY day ASC
        """
    ).fetchall()

    # ── Weekly trend (last 12 weeks) ────────────────────────────
    weekly = conn.execute(
        """
        SELECT strftime('%Y-W%W', ingested_at) AS week,
               COUNT(*) AS count,
               AVG(CAST(mastery AS REAL)) AS avg_score
        FROM knowledge_items
        WHERE ingested_at >= DATE('now', '-84 days')
        GROUP BY week
        ORDER BY week ASC
        """
    ).fetchall()

    # ── Monthly trend (last 6 months) ───────────────────────────
    monthly = conn.execute(
        """
        SELECT strftime('%Y-%m', ingested_at) AS month,
               COUNT(*) AS count,
               AVG(CAST(mastery AS REAL)) AS avg_score
        FROM knowledge_items
        WHERE ingested_at >= DATE('now', '-6 months')
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()

    # ── Top 10 concepts by link participation ───────────────────
    # Counts how many links reference items that carry each concept.
    top_concepts = conn.execute(
        """
        SELECT c.value AS name, COUNT(*) AS score
        FROM (
            SELECT from_item_id AS item_id FROM knowledge_links
            UNION ALL
            SELECT to_item_id AS item_id FROM knowledge_links
        ) link_items
        JOIN knowledge_items ki ON link_items.item_id = ki.id
        CROSS JOIN json_each(ki.concepts) c
        WHERE c.value IS NOT NULL AND c.value != ''
        GROUP BY c.value
        ORDER BY score DESC
        LIMIT 10
        """
    ).fetchall()

    # ── Trigger health (in-process metrics) ─────────────────────
    counters = kl_metrics.snapshot()["counters"]
    trigger_health = {
        "t1_failed": counters.get("t1_failed", 0),
        "t2_failed": counters.get("t2_failed", 0),
        "t3_failed": counters.get("t3_failed", 0),
        "t4_failed": counters.get("t4_failed", 0),
        "dead_letter_count": sum(
            counters.get(k, 0)
            for k in ("t1_dead_letter", "t2_dead_letter",
                      "t3_dead_letter", "t4_dead_letter")
        ),
    }

    # ── Stage distribution ──────────────────────────────────────
    stage_rows = conn.execute(
        "SELECT lifecycle, COUNT(*) FROM knowledge_items "
        "WHERE lifecycle IS NOT NULL AND lifecycle != '' "
        "GROUP BY lifecycle ORDER BY COUNT(*) DESC"
    ).fetchall()

    return {
        "daily_trend": [
            {"day": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in daily
        ],
        "weekly_trend": [
            {"week": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in weekly
        ],
        "monthly_trend": [
            {"month": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in monthly
        ],
        "top_concepts": [
            {"name": r[0], "score": r[1]} for r in top_concepts
        ],
        "trigger_health": trigger_health,
        "stage_distribution": {r[0]: r[1] for r in stage_rows},
    }


__all__ = ["router"]