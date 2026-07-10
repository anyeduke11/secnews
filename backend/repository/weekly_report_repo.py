"""v1.3.0 Phase 4: 周报数据仓库。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WeeklyReportRepository:
    def save(self, report: dict) -> int:
        conn = get_connection()
        try:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO weekly_reports (
                    week_start, week_end, category_summary, bid_summary,
                    trend_weekly, top_items, source_health, favorites_insight,
                    ai_insight, generated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(week_start) DO UPDATE SET
                    week_end = excluded.week_end,
                    category_summary = excluded.category_summary,
                    bid_summary = excluded.bid_summary,
                    trend_weekly = excluded.trend_weekly,
                    top_items = excluded.top_items,
                    source_health = excluded.source_health,
                    favorites_insight = excluded.favorites_insight,
                    ai_insight = excluded.ai_insight,
                    generated_at = excluded.generated_at,
                    version = excluded.version
                """,
                (
                    report["week_start"],
                    report["week_end"],
                    report["category_summary"],
                    report.get("bid_summary"),
                    report["trend_weekly"],
                    report["top_items"],
                    report.get("source_health"),
                    report.get("favorites_insight"),
                    report.get("ai_insight"),
                    report["generated_at"],
                    report.get("version", "1.0"),
                ),
            )
            conn.execute("COMMIT")
            return int(cur.lastrowid)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("weekly_report save failed", extra={"err": str(e)})
            raise InternalException(f"weekly_report save failed: {e}") from e

    def get_by_week(self, week_start: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM weekly_reports WHERE week_start = ? LIMIT 1",
            (week_start,),
        ).fetchone()
        return dict(row) if row else None

    def list_reports(self, limit: int = 12) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM weekly_reports ORDER BY week_start DESC LIMIT ?",
            (min(max(1, limit), 52),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest(self) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM weekly_reports ORDER BY week_start DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


class TrendDailyRepository:
    def save_snapshot(self, date: str, data: list[dict]) -> None:
        conn = get_connection()
        try:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            conn.execute("BEGIN")
            for entry in data:
                conn.execute(
                    """
                    INSERT INTO trend_daily_snapshots (snapshot_date, category, count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(snapshot_date, category) DO UPDATE SET count = excluded.count
                    """,
                    (date, entry["category"], int(entry["count"])),
                )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("trend_daily save failed", extra={"err": str(e)})
            raise InternalException(f"trend_daily save failed: {e}") from e

    def get_range(self, start: str, end: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM trend_daily_snapshots WHERE snapshot_date >= ? AND snapshot_date <= ? ORDER BY snapshot_date",
            (start, end),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["WeeklyReportRepository", "TrendDailyRepository"]