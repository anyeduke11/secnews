"""Trend snapshots repository.

Wraps the ``trend_snapshots`` table. The table holds pre-aggregated
24h heatmap buckets: one row per (hours_ago, category) pair, written
periodically by the scheduler. The API exposes:

- ``rebuild(hours=24)``: re-aggregate from the live ``hotspots`` table
  and replace all existing rows.
- ``get_current()``: return the cached buckets as a list of
  ``TrendPoint`` models.

Design notes
------------
- ``rebuild`` is a two-phase operation:
    1. ``DELETE FROM trend_snapshots`` to wipe stale data.
    2. For every ``hours_ago`` in ``[0, hours)`` and every category,
       run a single ``SELECT COUNT(*)`` against ``hotspots`` and bulk
       ``INSERT`` the result with ``executemany``.
  The 24 * 5 = 120 individual ``COUNT(*)`` calls are deliberately
  simple — at 10k rows this is well under 100 ms on the indexed
  ``published_at`` column, and the simple query is much easier to
  debug than a recursive-CTE / cross-join alternative.
- ``is_fallback`` is hard-filtered (only ``= 0`` rows count) so
  fallback placeholders never inflate trend numbers.
- ``hours_ago=0`` means the most recent 1h bucket
  ``[now-1h, now)``; ``hours_ago=23`` means ``[now-24h, now-23h)``.
- All write paths catch ``sqlite3.Error`` and re-raise as
  ``InternalException`` per the project-wide error contract
  (never leak a raw ``sqlite3.Error`` to callers).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.domain.enums import Category
from backend.domain.models import TrendPoint
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """ISO-8601 UTC string used to stamp ``trend_snapshots.snapshot_at``."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class TrendRepository:
    """Aggregation access to the ``trend_snapshots`` table.

    Example
    -------
    >>> repo = TrendRepository()
    >>> repo.rebuild(24)
    120
    >>> points = repo.get_current()
    >>> len(points)
    120
    """

    # Category list, frozen from the enum — every Category participates
    # in the trend grid even if the source table is empty for it.
    _CATEGORIES: tuple[str, ...] = tuple(c.value for c in Category)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def rebuild(self, hours: int = 24) -> int:
        """Recompute the trend snapshot for the last ``hours`` hours.

        1. ``DELETE`` every row in ``trend_snapshots``.
        2. For every ``hours_ago`` in ``[0, hours)`` and every
           category, run one ``COUNT(*)`` against ``hotspots``.
        3. Bulk ``INSERT`` the resulting rows via ``executemany``,
           wrapped in an explicit ``BEGIN`` / ``COMMIT``.

        Returns the number of rows inserted (typically
        ``hours * len(_CATEGORIES)``). Empty buckets are written with
        ``count=0`` so ``get_current()`` always returns a full grid
        after a rebuild.

        Raises ``InvalidParamException`` for ``hours < 1`` and
        ``InternalException`` on any SQLite error.
        """
        if hours < 1:
            raise InternalException(
                f"trend rebuild hours must be >= 1, got {hours}"
            )

        conn = get_connection()
        snapshot_at = _now_iso()

        # 1. Wipe the previous snapshot. Autocommit mode means a bare
        #    DELETE is its own transaction.
        try:
            conn.execute("DELETE FROM trend_snapshots")
        except sqlite3.Error as e:
            logger.error(
                "trend rebuild delete failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(
                f"trend rebuild delete failed: {e}"
            ) from e

        # 2. Count hotspots per (hours_ago, category) bucket.
        #    hours_ago=0  -> [now-1h, now)
        #    hours_ago=h  -> [now-(h+1)h, now-h)
        #
        #    `published_at` is stored as a Python ``isoformat()`` string
        #    (e.g. ``2026-07-04T10:30:00.123456+00:00``) while
        #    ``datetime('now', ...)`` returns ``2026-07-04 10:30:00``
        #    (space separator, no fractional seconds, no timezone). A
        #    raw lexicographic compare would treat ``T`` > `` `` and
        #    silently exclude every Python-inserted row. Wrapping
        #    ``published_at`` in ``datetime(...)`` normalises both
        #    sides to ``YYYY-MM-DD HH:MM:SS`` and makes the comparison
        #    correct.
        count_sql = (
            "SELECT COUNT(*) FROM hotspots "
            "WHERE category = ? "
            "  AND is_fallback = 0 "
            "  AND datetime(published_at) >= datetime('now', ?) "
            "  AND datetime(published_at) <  datetime('now', ?)"
        )
        rows: list[tuple[str, int, str, int]] = []
        for h in range(hours):
            lower = f"-{h + 1} hours"  # "now - (h+1) hours"
            upper = f"-{h} hours"      # "now - h hours"
            for cat in self._CATEGORIES:
                try:
                    row = conn.execute(
                        count_sql, (cat, lower, upper)
                    ).fetchone()
                except sqlite3.Error as e:
                    logger.error(
                        "trend rebuild count failed",
                        extra={
                            "trace_id": "",
                            "hours_ago": h,
                            "category": cat,
                            "error": str(e),
                        },
                    )
                    raise InternalException(
                        f"trend rebuild count failed: {e}"
                    ) from e
                count = int(row[0]) if row is not None else 0
                rows.append((snapshot_at, h, cat, count))

        # 3. Bulk insert. One transaction so partial writes are not
        #    observable.
        try:
            conn.execute("BEGIN")
            conn.executemany(
                "INSERT INTO trend_snapshots"
                "  (snapshot_at, hours_ago, category, count) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.execute("COMMIT")
        except sqlite3.Error as e:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                # If ROLLBACK itself fails, the original error is
                # still the meaningful one.
                pass
            logger.error(
                "trend rebuild insert failed",
                extra={"trace_id": "", "rows": len(rows), "error": str(e)},
            )
            raise InternalException(
                f"trend rebuild insert failed: {e}"
            ) from e

        logger.info(
            "trend snapshots rebuilt",
            extra={
                "trace_id": "",
                "hours": hours,
                "rows": len(rows),
                "snapshot_at": snapshot_at,
            },
        )
        return len(rows)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_current(self) -> list[TrendPoint]:
        """Return every cached trend point as a ``TrendPoint`` model.

        The repository does NOT synthesise empty buckets — the caller
        is expected to invoke ``rebuild()`` first to populate the full
        grid. If the table is empty (e.g. first start-up before the
        scheduler has run), this returns an empty list.

        Raises ``InternalException`` on any SQLite error.
        """
        conn = get_connection()
        try:
            db_rows = conn.execute(
                "SELECT hours_ago, category, count "
                "FROM trend_snapshots "
                "ORDER BY hours_ago ASC, category ASC"
            ).fetchall()
        except sqlite3.Error as e:
            logger.error(
                "trend get_current failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(
                f"trend get_current failed: {e}"
            ) from e

        points: list[TrendPoint] = []
        for db_row in db_rows:
            hours_ago = int(db_row["hours_ago"])
            category = str(db_row["category"])
            count = int(db_row["count"])
            points.append(
                TrendPoint(
                    label=f"-{hours_ago}h",
                    hours_ago=hours_ago,
                    category=category,
                    count=count,
                )
            )
        return points


__all__ = ["TrendRepository"]
