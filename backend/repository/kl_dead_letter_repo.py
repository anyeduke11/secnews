"""KLDeadLetterRepository — CRUD for the ``kl_dead_letters`` table.

Phase 10 — backing store for the KL trigger dead-letter queue.

Design
------
- One row per (trigger_name, item_id) for unresolved failures. Re-failures
  bump the ``attempts`` counter; on the 3rd attempt a new row is created
  (or an existing unresolved row is replaced) with ``resolved=0``.
- The repository is the single source of truth — :class:`RetryPolicy` in
  :mod:`backend.services.retry_policy` is the business logic that calls
  into this module.

Conventions
-----------
- The class follows the singleton pattern used elsewhere in the repo
  layer (see :data:`knowledge_repo`).
- All public methods are synchronous and rely on
  :func:`backend.repository.db.get_connection`.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from backend.repository.db import get_connection


@dataclass
class DeadLetterEntry:
    """Snapshot of a single ``kl_dead_letters`` row."""
    id: int
    trigger_name: str
    item_id: str
    error_msg: str
    attempts: int
    payload: Optional[str]
    created_at: str
    last_retry_at: Optional[str]
    resolved: bool

    @property
    def is_resolved(self) -> bool:
        return bool(self.resolved)


def _row_to_entry(row: sqlite3.Row) -> DeadLetterEntry:
    d = dict(row)
    return DeadLetterEntry(
        id=d["id"],
        trigger_name=d["trigger_name"],
        item_id=d["item_id"],
        error_msg=d["error_msg"],
        attempts=d["attempts"],
        payload=d.get("payload"),
        created_at=d["created_at"],
        last_retry_at=d.get("last_retry_at"),
        resolved=bool(d.get("resolved", 0)),
    )


class KLDeadLetterRepository:
    """CRUD over ``kl_dead_letters``.

    Public methods
    --------------
    - :meth:`add` — insert a new dead letter (used on the 3rd attempt)
    - :meth:`get_active` — return the unresolved row for a (trigger, item)
    - :meth:`update_attempts` — bump attempts + error message on retry
    - :meth:`list_active_count` — how many unresolved dead letters exist
    - :meth:`list_active` — return up to N active entries
    - :meth:`resolve` — mark a row as resolved
    """

    # ── Write ────────────────────────────────────────────────────

    def add(
        self,
        trigger_name: str,
        item_id: str,
        error_msg: str,
        attempts: int,
        payload: Optional[dict] = None,
    ) -> int:
        """Insert a new dead letter. Returns the new row id.

        If an unresolved row for the same (trigger_name, item_id) already
        exists, it is replaced (so the latest error message is preserved
        and a new id is generated).
        """
        conn = get_connection()
        # Resolve any prior unresolved row for the same (trigger, item).
        conn.execute(
            "UPDATE kl_dead_letters SET resolved = 1 "
            "WHERE trigger_name = ? AND item_id = ? AND resolved = 0",
            (trigger_name, item_id),
        )
        cur = conn.execute(
            """
            INSERT INTO kl_dead_letters
                (trigger_name, item_id, error_msg, attempts, payload, resolved)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                trigger_name,
                item_id,
                error_msg,
                attempts,
                json.dumps(payload) if payload else None,
            ),
        )
        return int(cur.lastrowid)

    def update_attempts(
        self,
        trigger_name: str,
        item_id: str,
        error_msg: str,
        attempts: int,
    ) -> None:
        """Bump the attempts counter for the active dead letter.

        If no active row exists yet (first failure) a new row is inserted
        with ``resolved=0``. This is the "still retrying" path.
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM kl_dead_letters "
            "WHERE trigger_name = ? AND item_id = ? AND resolved = 0",
            (trigger_name, item_id),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO kl_dead_letters
                    (trigger_name, item_id, error_msg, attempts, resolved)
                VALUES (?, ?, ?, ?, 0)
                """,
                (trigger_name, item_id, error_msg, attempts),
            )
        else:
            conn.execute(
                """
                UPDATE kl_dead_letters
                SET error_msg = ?, attempts = ?, last_retry_at = datetime('now')
                WHERE id = ?
                """,
                (error_msg, attempts, row["id"]),
            )

    def resolve(self, entry_id: int) -> None:
        """Mark a dead letter as resolved (manual cleanup)."""
        conn = get_connection()
        conn.execute(
            "UPDATE kl_dead_letters SET resolved = 1 WHERE id = ?",
            (entry_id,),
        )

    # ── Read ─────────────────────────────────────────────────────

    def get_active(
        self,
        trigger_name: str,
        item_id: str,
    ) -> Optional[DeadLetterEntry]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM kl_dead_letters "
            "WHERE trigger_name = ? AND item_id = ? AND resolved = 0 "
            "ORDER BY id DESC LIMIT 1",
            (trigger_name, item_id),
        ).fetchone()
        return _row_to_entry(row) if row else None

    def get_by_id(self, entry_id: int) -> Optional[DeadLetterEntry]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM kl_dead_letters WHERE id = ?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def list_active(
        self,
        trigger_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[DeadLetterEntry]:
        conn = get_connection()
        if trigger_name:
            rows = conn.execute(
                "SELECT * FROM kl_dead_letters "
                "WHERE trigger_name = ? AND resolved = 0 "
                "ORDER BY id DESC LIMIT ?",
                (trigger_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kl_dead_letters "
                "WHERE resolved = 0 "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def list_active_count(
        self,
        trigger_name: Optional[str] = None,
    ) -> int:
        conn = get_connection()
        if trigger_name:
            row = conn.execute(
                "SELECT COUNT(*) FROM kl_dead_letters "
                "WHERE trigger_name = ? AND resolved = 0",
                (trigger_name,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM kl_dead_letters WHERE resolved = 0"
            ).fetchone()
        return int(row[0]) if row else 0


# Singleton
kl_dead_letter_repo = KLDeadLetterRepository()


__all__ = [
    "DeadLetterEntry",
    "KLDeadLetterRepository",
    "kl_dead_letter_repo",
]
