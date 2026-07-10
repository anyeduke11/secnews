"""Phase 42 sync_states 仓库: 上次同步的 merged bundle (3-way merge base)。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncStateRepository:
    def get(self, config_id: int) -> Optional[dict]:
        """返回 {bundle_json, merged_at} 或 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT bundle_json, merged_at FROM sync_states WHERE config_id = ? LIMIT 1",
            (int(config_id),),
        ).fetchone()
        if row is None:
            return None
        return {
            "bundle_json": str(row["bundle_json"]),
            "merged_at": str(row["merged_at"]),
        }

    def get_by_config(self, config_id: int) -> Optional[dict]:
        """返回完整行 (含 id) 或 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM sync_states WHERE config_id = ? LIMIT 1",
            (int(config_id),),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def update_merged_bundle(self, config_id: int, bundle_json: str) -> None:
        """更新 merged bundle (冲突裁决后)。"""
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute(
                "UPDATE sync_states SET bundle_json = ?, merged_at = ? WHERE config_id = ?",
                (bundle_json, now, int(config_id)),
            )
        except Exception as e:
            logger.error("sync_state update_merged_bundle failed", extra={"err": str(e)})
            raise InternalException(f"sync_state update_merged_bundle failed: {e}") from e

    def upsert(self, config_id: int, bundle_json: str) -> None:
        conn = get_connection()
        now = _now_iso()
        try:
            # autocommit 模式下先 ROLLBACK 任何残留事务 (防御)
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO sync_states (config_id, bundle_json, merged_at)
                VALUES (?, ?, ?)
                ON CONFLICT(config_id) DO UPDATE SET
                    bundle_json = excluded.bundle_json,
                    merged_at   = excluded.merged_at
                """,
                (int(config_id), bundle_json, now),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_state upsert failed", extra={"err": str(e)})
            raise InternalException(f"sync_state upsert failed: {e}") from e

    def clear(self, config_id: int) -> bool:
        conn = get_connection()
        try:
            cur = conn.execute(
                "DELETE FROM sync_states WHERE config_id = ?", (int(config_id),)
            )
            return int(cur.rowcount) > 0
        except Exception as e:
            logger.error("sync_state clear failed", extra={"err": str(e)})
            raise InternalException(f"sync_state clear failed: {e}") from e

    def clear_all(self) -> int:
        """清空所有 sync_states (admin reset 用)。"""
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM sync_states")
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_state clear_all failed", extra={"err": str(e)})
            raise InternalException(f"sync_state clear_all failed: {e}") from e


__all__ = ["SyncStateRepository"]
