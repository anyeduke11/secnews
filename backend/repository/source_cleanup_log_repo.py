"""源清理审计 (source_cleanup_log) 表仓储层。

数据源治理 T2: 删除/启停等破坏性动作的强制审计落点 —
先写本表再执行 DELETE/UPDATE (审计强制, 见设计稿 §3.2/§3.3)。
表结构见 migration 122_source_cleanup_log.sql。
"""
from __future__ import annotations

from backend.repository.db import get_connection


class SourceCleanupLogRepository:
    """source_cleanup_log 表写入与查询。"""

    def add(
        self,
        source_layer: str,
        source_ident: str,
        reason: str,
        executed_by: str = "system",
    ) -> int:
        """记录一条清理审计 (调用方须在真正 DELETE/UPDATE 之前调用)。

        Returns:
            新插入行的 id
        """
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO source_cleanup_log
                (source_layer, source_ident, reason, executed_by)
            VALUES (?, ?, ?, ?)
            """,
            (source_layer, source_ident, reason, executed_by),
        )
        return cur.lastrowid or 0

    def list_by_ident(self, source_layer: str, source_ident: str) -> list[dict]:
        """按层 + 标识查审计记录 (created_at 倒序), 供测试与追溯。"""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM source_cleanup_log
            WHERE source_layer = ? AND source_ident = ?
            ORDER BY executed_at DESC, id DESC
            """,
            (source_layer, source_ident),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self, source_layer: str | None = None) -> int:
        """审计行总数 (可选按层过滤)。"""
        conn = get_connection()
        if source_layer is None:
            row = conn.execute("SELECT COUNT(*) AS c FROM source_cleanup_log").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM source_cleanup_log WHERE source_layer = ?",
                (source_layer,),
            ).fetchone()
        return int(row["c"])


__all__ = ["SourceCleanupLogRepository"]
