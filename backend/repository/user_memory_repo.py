"""v0.7 Batch ⑤ — user_memory 表 Repository.

``user_memory`` (migration 084) 存储 AI 分析结果 (interest/dislike/source_pref/
reading_style/topic), 供 user_memory_service 读取形成用户上下文。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserMemoryRepository:
    """``user_memory`` 表 CRUD。"""

    def upsert(
        self,
        memory_type: str,
        key: str,
        value: str,
        source: str = "feedback_analyzer",
    ) -> dict[str, Any]:
        """幂等写入记忆: 同一 (memory_type, key) 更新 value + updated_at。

        Returns
        -------
        dict
            写入后的行。
        """
        now = _now_iso()
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO user_memory (memory_type, key, value, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_type, key) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (memory_type, key, value, source, now, now),
        )
        row = conn.execute(
            "SELECT * FROM user_memory WHERE memory_type = ? AND key = ?",
            (memory_type, key),
        ).fetchone()
        return dict(row) if row else {}

    def get(self, memory_type: str, key: str) -> dict | None:
        """读取单条记忆。"""
        row = get_connection().execute(
            "SELECT * FROM user_memory WHERE memory_type = ? AND key = ?",
            (memory_type, key),
        ).fetchone()
        return dict(row) if row else None

    def list_by_type(self, memory_type: str) -> list[dict[str, Any]]:
        """按 memory_type 列出所有记忆, 按 updated_at 倒序。"""
        rows = get_connection().execute(
            "SELECT * FROM user_memory WHERE memory_type = ? ORDER BY updated_at DESC",
            (memory_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        """列出全部记忆。"""
        rows = get_connection().execute(
            "SELECT * FROM user_memory ORDER BY memory_type, updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, memory_type: str, key: str) -> bool:
        """删除单条记忆。返回是否实际删除。"""
        cur = get_connection().execute(
            "DELETE FROM user_memory WHERE memory_type = ? AND key = ?",
            (memory_type, key),
        )
        return cur.rowcount > 0


__all__ = ["UserMemoryRepository"]
