"""v1.7 Phase 5 — KV Cache Repository.

表 kv_cache (migration 032):
    key         TEXT PRIMARY KEY
    value       TEXT NOT NULL       -- JSON 序列化
    expires_at  TEXT                 -- ISO 时间, NULL 表示永不过期
    created_at  TEXT NOT NULL
    updated_at  TEXT NOT NULL
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KVCacheRepository:
    """KV 缓存数据访问层."""

    def get(self, key: str) -> Optional[dict]:
        """获取缓存值, 自动过滤过期项. 返回解析后的 dict 或 None."""
        now = _now_iso()
        row = get_connection().execute(
            "SELECT value FROM kv_cache "
            "WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)",
            (key, now),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set(
        self,
        key: str,
        value: dict,
        expires_seconds: Optional[int] = 60,
    ) -> None:
        """写入缓存. expires_seconds=None 表示永不过期."""
        now = _now_iso()
        if expires_seconds is not None:
            expires = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .timestamp()
            )
            from datetime import timedelta
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
            ).isoformat()
        else:
            expires_at = None
        get_connection().execute(
            """INSERT INTO kv_cache (key, value, expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   expires_at = excluded.expires_at,
                   updated_at = excluded.updated_at""",
            (key, json.dumps(value, ensure_ascii=False), expires_at, now, now),
        )

    def delete(self, key: str) -> None:
        get_connection().execute("DELETE FROM kv_cache WHERE key = ?", (key,))

    def invalidate_prefix(self, prefix: str) -> int:
        """按前缀批量失效, 返回删除行数."""
        cursor = get_connection().execute(
            "DELETE FROM kv_cache WHERE key LIKE ?", (f"{prefix}%",)
        )
        return cursor.rowcount or 0

    def cleanup_expired(self) -> int:
        """清理已过期项, 返回删除行数."""
        now = _now_iso()
        cursor = get_connection().execute(
            "DELETE FROM kv_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        return cursor.rowcount or 0

    def count(self) -> int:
        """当前有效缓存项数 (含未过期)."""
        now = _now_iso()
        row = get_connection().execute(
            "SELECT COUNT(*) AS c FROM kv_cache "
            "WHERE expires_at IS NULL OR expires_at > ?",
            (now,),
        ).fetchone()
        return row["c"] if row else 0


kv_cache_repo = KVCacheRepository()
