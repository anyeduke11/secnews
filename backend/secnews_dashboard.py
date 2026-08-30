"""SecNews Dashboard — aggregated data service for the security dashboard.

Combines feed data, pipeline stats, and knowledge metrics into a
single service that the API layer can query.

v0.6.3 P0-1 卡顿根治: pipeline/knowledge 统计从"全量扫描 4149 个 wiki md"
切换到 DB 投影 (warm.knowledge_items.lifecycle / knowledge_concepts),
liveness 走 30s TTL 缓存 — 调用方 (api 层) 仍需以 asyncio.to_thread 调用。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.repository.db import get_connection
from backend.services.wiki_stats_service import (
    funnel_from_db,
    knowledge_stats_from_db,
    liveness_from_md_cached,
)


class SecNewsDashboard:
    """Aggregation service for the SecNews security dashboard."""

    def __init__(
        self,
        db: Any = None,
        wiki_fs: Any = None,
        pipeline: Any = None,
    ) -> None:
        self.db = db or get_connection()
        self.wiki_fs = wiki_fs
        self.pipeline = pipeline
        self._ledger = TokenLedger(self.db)

    def get_feed(self, category: str = "", keyword: str = "", limit: int = 30) -> dict:
        """Newspaper-style feed sorted by ingested_at DESC.

        Returns items from the hotspots table filtered by category/keyword.
        """
        conditions = []
        params: list = []

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category)
        if keyword:
            conditions.append("(title LIKE ? OR summary LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT id, title, url, source, category, summary, "
            f"published_at, ingested_at "
            f"FROM hotspots WHERE {where} "
            f"ORDER BY ingested_at DESC LIMIT ?"
        )
        params.append(limit)

        rows = self.db.execute(sql, params).fetchall()
        total_row = self.db.execute(
            f"SELECT COUNT(*) FROM hotspots WHERE {where}", params[:-1]
        ).fetchone()

        items = [dict(r) for r in rows]
        total = total_row[0] if total_row else 0

        return {"items": items, "total": total, "limit": limit}

    def get_pipeline_stats(self) -> dict:
        """Pipeline observability: funnel + queue + dead-letter + alive + ledger.

        v0.6.3 P0-1: funnel 走 DB 投影 (真实管线口径); liveness 走 md + 30s
        TTL 缓存。调用方必须以 asyncio.to_thread 包本方法 (liveness 缓存
        miss 时仍有一次全量 md 扫描)。
        """
        funnel = funnel_from_db(self.db)

        queue_stats = {"pending": 0, "running": 0, "error": 0}
        errors: list[dict] = []
        if self.pipeline:
            queue_stats = self.pipeline.queue.stats()
            errors = self.pipeline.queue.errors(limit=10)

        ledger = self._ledger.summary()

        return {
            "funnel": funnel,
            "funnel_source": "db_knowledge_items_lifecycle",
            "funnel_note": "按 DB warm.knowledge_items.lifecycle 统计 (T1-T5 管线真实口径)",
            "queue": queue_stats,
            "errors": errors,
            "alive": liveness_from_md_cached(self.wiki_fs) if self.wiki_fs else {
                "total": 0, "alive": 0, "dead": 0, "unknown": 0,
            },
            "ledger": ledger,
        }

    def get_knowledge_stats(self) -> dict:
        """Knowledge base statistics: items, concepts, lifecycle distribution.

        v0.6.3 P0-1: 全量 md 扫描 (4149 read_text+YAML) → DB 投影单查询。
        """
        return knowledge_stats_from_db(self.db)

    def get_dashboard_stats(self) -> dict:
        """Dashboard overview: today's new items, pipeline health, top categories."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Today's new items.
        new_today = self.db.execute(
            "SELECT COUNT(*) FROM hotspots WHERE ingested_at LIKE ?",
            (f"{today}%",),
        ).fetchone()

        # Top categories by count.
        top_cats = self.db.execute(
            "SELECT category, COUNT(*) as cnt FROM hotspots "
            "GROUP BY category ORDER BY cnt DESC LIMIT 5"
        ).fetchall()

        # Pipeline health.
        pipeline_health = "unknown"
        if self.pipeline:
            stats = self.pipeline.queue.stats()
            total = sum(stats.values())
            if total == 0:
                pipeline_health = "idle"
            elif stats.get("error", 0) / max(total, 1) < 0.1:
                pipeline_health = "healthy"
            else:
                pipeline_health = "degraded"

        return {
            "new_today": new_today[0] if new_today else 0,
            "pipeline_health": pipeline_health,
            "top_categories": [dict(r) for r in top_cats],
            "date": today,
        }
