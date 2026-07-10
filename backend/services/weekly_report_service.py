"""v1.3.0 Phase 4: WeeklyReportService — 周报生成 + 日级快照。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.domain.enums import Category
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.weekly_report_repo import (
    TrendDailyRepository,
    WeeklyReportRepository,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _week_range(reference: Optional[datetime] = None) -> tuple[str, str]:
    """Return (week_start, week_end) ISO strings for the ISO week containing *reference*.

    week_start = Monday 00:00 UTC, week_end = Sunday 23:59:59 UTC.
    """
    ref = reference or datetime.now(timezone.utc)
    monday = ref - timedelta(days=ref.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return week_start.isoformat(), week_end.isoformat()


def _count_hotspots_since(since: str) -> dict[str, int]:
    """Count hotspots per category ingested after *since*."""
    conn = get_connection()
    cats = [c.value for c in Category]
    result: dict[str, int] = {}
    for cat in cats:
        row = conn.execute(
            "SELECT COUNT(*) FROM hotspots WHERE category = ? AND is_fallback = 0 AND ingested_at > ?",
            (cat, since),
        ).fetchone()
        result[cat] = int(row[0]) if row else 0
    total = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE is_fallback = 0 AND ingested_at > ?",
        (since,),
    ).fetchone()
    result["total"] = int(total[0]) if total else 0
    return result


def _top_items_since(since: str, limit: int = 20) -> list[dict]:
    """Return top *limit* hotspots by score ingested after *since*."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, source, url, category, score, published_at "
        "FROM hotspots WHERE is_fallback = 0 AND ingested_at > ? "
        "ORDER BY COALESCE(score, 0) DESC LIMIT ?",
        (since, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _source_health_since(since: str) -> list[dict]:
    """Per-source success/failure counts since *since*."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT source, COUNT(*) as total, "
        "SUM(CASE WHEN quality_score >= 50 THEN 1 ELSE 0 END) as pass "
        "FROM hotspots WHERE ingested_at > ? GROUP BY source ORDER BY total DESC",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def _favorites_insight() -> dict:
    """Favorites summary for the report."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()
    by_cat_rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM favorites GROUP BY category"
    ).fetchall()
    by_category = {r["category"]: r["cnt"] for r in by_cat_rows}
    return {
        "total": int(total[0]) if total else 0,
        "by_category": by_category,
    }


class WeeklyReportService:
    def generate_report(self, reference: Optional[datetime] = None) -> dict:
        """Generate a weekly report for the ISO week containing *reference*.

        Returns the saved report dict.
        """
        week_start, week_end = _week_range(reference)

        category_summary = _count_hotspots_since(week_start)
        top_items = _top_items_since(week_start)
        source_health = _source_health_since(week_start)
        favorites = _favorites_insight()

        trend_repo = TrendDailyRepository()
        trend_data = trend_repo.get_range(week_start[:10], week_end[:10])

        bid_summary = None
        if category_summary.get("bid", 0) > 0:
            bid_summary = {"total": category_summary["bid"]}

        report = {
            "week_start": week_start,
            "week_end": week_end,
            "category_summary": json.dumps(category_summary, ensure_ascii=False),
            "bid_summary": json.dumps(bid_summary, ensure_ascii=False) if bid_summary else None,
            "trend_weekly": json.dumps(trend_data, ensure_ascii=False),
            "top_items": json.dumps(top_items, ensure_ascii=False),
            "source_health": json.dumps(source_health, ensure_ascii=False),
            "favorites_insight": json.dumps(favorites, ensure_ascii=False),
            "ai_insight": None,
            "generated_at": _now_iso(),
            "version": "1.3.0",
        }

        repo = WeeklyReportRepository()
        repo.save(report)
        logger.info(
            "weekly report generated",
            extra={"week_start": week_start, "total": category_summary.get("total", 0)},
        )
        return report

    def take_daily_snapshot(self) -> int:
        """Take a daily snapshot of per-category hotspot counts.

        Returns the number of categories snapshotted.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = get_connection()
        cats = [c.value for c in Category]
        data: list[dict] = []
        for cat in cats:
            row = conn.execute(
                "SELECT COUNT(*) FROM hotspots WHERE category = ? AND is_fallback = 0",
                (cat,),
            ).fetchone()
            data.append({"category": cat, "count": int(row[0]) if row else 0})

        repo = TrendDailyRepository()
        repo.save_snapshot(today, data)
        logger.info("daily trend snapshot taken", extra={"date": today, "categories": len(data)})
        return len(data)

    def get_report(self, week_start: str) -> Optional[dict]:
        """Get a specific week's report."""
        repo = WeeklyReportRepository()
        row = repo.get_by_week(week_start)
        if row is None:
            return None
        return self._enrich_report(row)

    def get_latest_report(self) -> Optional[dict]:
        """Get the most recent weekly report."""
        repo = WeeklyReportRepository()
        row = repo.get_latest()
        if row is None:
            return None
        return self._enrich_report(row)

    def list_reports(self, limit: int = 12) -> list[dict]:
        """List recent weekly reports."""
        repo = WeeklyReportRepository()
        rows = repo.list_reports(limit)
        return [self._enrich_report(r) for r in rows]

    def _enrich_report(self, row: dict) -> dict:
        """Parse JSON fields back to objects for API response."""
        for key in ("category_summary", "bid_summary", "trend_weekly",
                     "top_items", "source_health", "favorites_insight", "ai_insight"):
            val = row.get(key)
            if isinstance(val, str):
                try:
                    row[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        return row


__all__ = ["WeeklyReportService"]