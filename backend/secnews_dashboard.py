"""SecNews Dashboard — aggregated data service for the security dashboard.

Combines feed data, pipeline stats, and knowledge metrics into a
single service that the API layer can query.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.kl_pipeline.obs.funnel import funnel_stats
from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.repository.db import get_connection
from backend.wiki_fs.contract import get_lifecycle


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
        """Pipeline observability: funnel + queue + dead-letter + token ledger."""
        funnel = funnel_stats(self.wiki_fs)

        queue_stats = {"pending": 0, "running": 0, "error": 0}
        errors: list[dict] = []
        if self.pipeline:
            queue_stats = self.pipeline.queue.stats()
            errors = self.pipeline.queue.errors(limit=10)

        ledger = self._ledger.summary()

        return {
            "funnel": funnel,
            "queue": queue_stats,
            "errors": errors,
            "ledger": ledger,
        }

    def get_knowledge_stats(self) -> dict:
        """Knowledge base statistics: items, concepts, lifecycle distribution."""
        items_count = 0
        concepts_count = 0
        stage_dist: dict[str, int] = {}

        if self.wiki_fs:
            ids = self.wiki_fs.list_ids()
            items_count = len(ids)
            for item_id in ids:
                doc = self.wiki_fs.read_item(item_id)
                if doc:
                    stage = get_lifecycle(doc["fm"])
                    stage_dist[stage] = stage_dist.get(stage, 0) + 1
            concepts_count = len(self.wiki_fs.list_concepts())

        return {
            "items": items_count,
            "concepts": concepts_count,
            "stage_distribution": stage_dist,
        }

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
