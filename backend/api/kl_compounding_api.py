"""GET /api/kl/compounding — 复利仪表盘聚合指标 (Phase 13, P3-5 修复)。

P3-5 (2026-08-16): 修复三处空转数据源 —
1. avg_score 原取 AVG(mastery) (全 0) → 改为 AVG(attention_score)
   (注意力事件经 P3-2 前端埋点流入, attention_aggregate job 聚合)
2. trigger_health 原读进程内内存计数器 (重启清零) → 改为读 kl_dead_letters
   表 (持久化) + 进程内计数合并
3. top_concepts 原 join knowledge_links×concepts (links/concepts 稀疏)
   → 改为直接聚合 knowledge_items.concepts 列
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
        items ingested per day (last 30d) with count and avg attention score
    weekly_trend
        items per week (last 12w) with count and avg attention score
    monthly_trend
        items per month (last 6m) with count and avg attention score
    top_concepts
        top 10 concepts by item participation (name + score)
    trigger_health
        T1-T4 dead-letter counts (persisted in kl_dead_letters) + 进程内计数
    stage_distribution
        count of items per lifecycle stage
    """
    conn = get_connection()

    # ── Daily trend (last 30 days) ──────────────────────────────
    # P3-5: avg_score 改用 attention_score (真实注意力数据), 不再用 mastery (全 0)
    daily = conn.execute(
        """
        SELECT DATE(ingested_at) AS day,
               COUNT(*) AS count,
               AVG(CAST(attention_score AS REAL)) AS avg_score
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
               AVG(CAST(attention_score AS REAL)) AS avg_score
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
               AVG(CAST(attention_score AS REAL)) AS avg_score
        FROM knowledge_items
        WHERE ingested_at >= DATE('now', '-6 months')
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()

    # ── Top 10 concepts by item participation ───────────────────
    # P3-5: 直接聚合 knowledge_items.concepts (不再依赖稀疏的 knowledge_links)
    top_concepts = conn.execute(
        """
        SELECT c.value AS name, COUNT(*) AS score
        FROM knowledge_items ki
        CROSS JOIN json_each(ki.concepts) c
        WHERE c.value IS NOT NULL AND c.value != ''
        GROUP BY c.value
        ORDER BY score DESC
        LIMIT 10
        """
    ).fetchall()

    # ── Trigger health ──────────────────────────────────────────
    # P3-5: 死信从 kl_dead_letters 表读 (持久化, 重启不丢), 进程内计数仅补充
    try:
        dl_rows = conn.execute(
            "SELECT trigger_name, COUNT(*) AS n FROM kl_dead_letters "
            "WHERE status = 'active' GROUP BY trigger_name"
        ).fetchall()
        dead_letter_db = {r[0]: r[1] for r in dl_rows}
    except Exception:
        dead_letter_db = {}
    counters = kl_metrics.snapshot()["counters"]
    trigger_health = {
        "t1_failed": counters.get("t1_failed", 0),
        "t2_failed": counters.get("t2_failed", 0),
        "t3_failed": counters.get("t3_failed", 0),
        "t4_failed": counters.get("t4_failed", 0),
        "dead_letter_count": sum(dead_letter_db.values()),
        "dead_letter_by_trigger": dead_letter_db,
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