"""Phase 42 sync_history 仓库: 同步审计日志。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncHistoryRepository:
    def write(
        self,
        *,
        config_id: int,
        direction: str,
        status: str,
        records_count: Optional[int] = None,
        conflict_count: int = 0,
        error_message: Optional[str] = None,
        started_at: str,
        finished_at: str,
    ) -> int:
        conn = get_connection()
        try:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO sync_history (
                    config_id, direction, status, records_count,
                    conflict_count, error_message, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(config_id),
                    direction,
                    status,
                    records_count,
                    int(conflict_count),
                    error_message,
                    started_at,
                    finished_at,
                ),
            )
            conn.execute("COMMIT")
            return int(cur.lastrowid)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_history write failed", extra={"err": str(e)})
            raise InternalException(f"sync_history write failed: {e}") from e

    def list_recent(self, config_id: int, limit: int = 50) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM sync_history
            WHERE config_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (int(config_id), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, config_id: int, keep: int = 50) -> int:
        """保留最近 N 条, 删多余。"""
        conn = get_connection()
        try:
            cur = conn.execute(
                """
                DELETE FROM sync_history
                WHERE config_id = ? AND id NOT IN (
                    SELECT id FROM sync_history
                    WHERE config_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                )
                """,
                (int(config_id), int(config_id), int(keep)),
            )
            return int(cur.rowcount)
        except Exception as e:
            logger.error("sync_history prune failed", extra={"err": str(e)})
            raise InternalException(f"sync_history prune failed: {e}") from e

    def prune_all(self) -> int:
        """清空所有 sync_history (admin reset 用, 配对 delete_all sync_configs)。"""
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM sync_history")
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_history prune_all failed", extra={"err": str(e)})
            raise InternalException(f"sync_history prune_all failed: {e}") from e


__all__ = ["SyncHistoryRepository"]
