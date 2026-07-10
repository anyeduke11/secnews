"""Settings KV repository.

Wraps the ``settings`` table behind a small typed API. Values are
persisted as JSON strings (so we can store arbitrary scalars, lists
and dicts) and deserialised transparently on read.

Design notes
------------
- Stateless: the class holds no connection of its own; every method
  calls ``get_connection()`` and uses the per-thread connection
  managed by ``db.py``.
- All write paths catch ``sqlite3.Error`` and re-raise as
  ``InternalException`` to honour the project-wide error contract
  (never leak a raw ``sqlite3.Error`` to callers).
- Read paths return ``default`` on miss; they do not raise
  ``NotFoundException`` because "key not set" is a normal outcome
  (e.g. feature flags default to off).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """ISO-8601 UTC string used to stamp ``settings.updated_at``."""
    return datetime.now(timezone.utc).isoformat()


def _serialize(value: Any) -> str:
    """Encode ``value`` as a JSON string for storage.

    ``ensure_ascii=False`` keeps Chinese / CJK strings readable when
    someone peeks at the DB with ``sqlite3`` CLI.
    """
    return json.dumps(value, ensure_ascii=False)


def _deserialize(raw: str) -> Any:
    """Decode a JSON string back into the original Python object."""
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class SettingsRepository:
    """Typed KV access to the ``settings`` table.

    Example
    -------
    >>> repo = SettingsRepository()
    >>> repo.set("theme", "dark")
    >>> repo.get("theme")
    'dark'
    >>> repo.get("missing", "fallback")
    'fallback'
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Return the JSON-deserialised value for ``key``, or ``default``.

        On a miss (no row) or a corrupt JSON payload, ``default`` is
        returned. A corrupt value is also logged at WARNING so an
        operator can investigate without crashing the request path.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.Error as e:
            logger.error(
                "settings get failed",
                extra={"trace_id": "", "key": key, "error": str(e)},
            )
            raise InternalException(f"settings get failed: {e}") from e

        if row is None:
            return default

        try:
            return _deserialize(row["value"])
        except (TypeError, ValueError) as e:
            logger.warning(
                "settings value not valid JSON, returning default",
                extra={"trace_id": "", "key": key, "error": str(e)},
            )
            return default

    def list_all(self) -> dict[str, Any]:
        """Return every (key, value) pair as a ``{key: deserialised}`` dict.

        Corrupt values are silently skipped (and logged) so a single
        bad row cannot break the whole snapshot. The returned dict
        preserves no particular key order — callers must not depend
        on it.
        """
        conn = get_connection()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        except sqlite3.Error as e:
            logger.error(
                "settings list_all failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"settings list_all failed: {e}") from e

        out: dict[str, Any] = {}
        for row in rows:
            try:
                out[row["key"]] = _deserialize(row["value"])
            except (TypeError, ValueError) as e:
                logger.warning(
                    "settings row has invalid JSON, skipping",
                    extra={"trace_id": "", "key": row["key"], "error": str(e)},
                )
        return out

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def set(self, key: str, value: Any) -> None:
        """Insert or upsert ``key`` = ``value`` (JSON-encoded).

        Uses ``ON CONFLICT(key) DO UPDATE`` so the call is idempotent
        and can be used to mutate an existing flag.
        """
        conn = get_connection()
        payload = _serialize(value)
        try:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, payload, _now_iso()),
            )
        except sqlite3.Error as e:
            logger.error(
                "settings set failed",
                extra={"trace_id": "", "key": key, "error": str(e)},
            )
            raise InternalException(f"settings set failed: {e}") from e

    def delete(self, key: str) -> bool:
        """Remove ``key``; return ``True`` iff a row was actually removed."""
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        except sqlite3.Error as e:
            logger.error(
                "settings delete failed",
                extra={"trace_id": "", "key": key, "error": str(e)},
            )
            raise InternalException(f"settings delete failed: {e}") from e
        return cur.rowcount > 0


__all__ = ["SettingsRepository"]
