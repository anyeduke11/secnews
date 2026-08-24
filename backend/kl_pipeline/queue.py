"""KL Queue DAO — kl_queue table operations.

Design notes:
- ISO-8601 UTC strings for datetime columns (matches hotspot_repo pattern).
- Autocommit mode: explicit BEGIN/COMMIT/ROLLBACK.
- enqueue_unique is idempotent via UNIQUE(item_id, stage).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.repository.db import get_connection

# Stage ordering for advancement.
STAGES = ("kl:raw", "kl:refine", "kl:link", "kl:structure", "kl:publish")


class KLQueue:
    """DAO for the ``kl_queue`` table."""

    def __init__(self, db: sqlite3.Connection | None = None) -> None:
        self._db = db

    @property
    def db(self) -> sqlite3.Connection:
        return self._db if self._db is not None else get_connection()

    def enqueue_unique(self, item_id: str, stage: str, next_run: datetime) -> bool:
        """Idempotent enqueue — returns True if a new row was inserted."""
        next_run_iso = next_run.isoformat()
        try:
            self.db.execute(
                "INSERT INTO kl_queue (item_id, stage, next_run_at) VALUES (?, ?, ?)",
                (item_id, stage, next_run_iso),
            )
            return True
        except sqlite3.IntegrityError:
            # (item_id, stage) already exists — update next_run if pending.
            self.db.execute(
                "UPDATE kl_queue SET next_run_at = ?, updated_at = datetime('now') "
                "WHERE item_id = ? AND stage = ? AND status = 'pending'",
                (next_run_iso, item_id, stage),
            )
            return False

    def due(self, limit: int = 20) -> list[dict]:
        """Return tasks where status=pending AND next_run_at <= now."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self.db.execute(
            "SELECT id, item_id, stage, attempts, max_attempts, next_run_at "
            "FROM kl_queue "
            "WHERE status = 'pending' AND next_run_at <= ? "
            "ORDER BY priority DESC, next_run_at ASC "
            "LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_run(self, queue_id: int) -> None:
        self.db.execute(
            "UPDATE kl_queue SET status = 'running', attempts = attempts + 1, "
            "updated_at = datetime('now') WHERE id = ?",
            (queue_id,),
        )

    def mark_done(self, queue_id: int) -> None:
        """Completed — delete the row."""
        self.db.execute("DELETE FROM kl_queue WHERE id = ?", (queue_id,))

    def mark_error(self, queue_id: int, error: str) -> None:
        self.db.execute(
            "UPDATE kl_queue SET status = 'error', last_error = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (error, queue_id),
        )

    def stats(self) -> dict:
        """Count by status."""
        rows = self.db.execute(
            "SELECT status, COUNT(*) as cnt FROM kl_queue GROUP BY status"
        ).fetchall()
        result = {"pending": 0, "running": 0, "error": 0}
        for r in rows:
            result[r["status"]] = r["cnt"]
        return result

    def errors(self, limit: int = 50) -> list[dict]:
        """Return error tasks for the dead-letter view."""
        rows = self.db.execute(
            "SELECT id, item_id, stage, attempts, last_error, updated_at "
            "FROM kl_queue WHERE status = 'error' "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def reset_errors(self, wiki_id: str | None = None) -> int:
        """Reset error tasks to pending — returns count reset."""
        if wiki_id:
            cur = self.db.execute(
                "UPDATE kl_queue SET status = 'pending', last_error = NULL, "
                "next_run_at = datetime('now'), updated_at = datetime('now') "
                "WHERE status = 'error' AND item_id = ?",
                (wiki_id,),
            )
        else:
            cur = self.db.execute(
                "UPDATE kl_queue SET status = 'pending', last_error = NULL, "
                "next_run_at = datetime('now'), updated_at = datetime('now') "
                "WHERE status = 'error'"
            )
        return cur.rowcount
