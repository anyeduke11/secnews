"""v0.7 Batch ⑤ — feedback_events 表 Repository.

``feedback_events`` (migration 083) 记录用户的点赞/点踩原始事件,
供反馈分析 + 审计使用。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackRepository:
    """``feedback_events`` 表 CRUD。"""

    def record(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        signal: float,
        *,
        category: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        title: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """写入一条反馈事件。

        Returns
        -------
        dict
            刚插入的行 ``{"id", ...}``。
        """
        now = created_at or _now_iso()
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO feedback_events
                (entity_type, entity_id, action, signal,
                 category, source, tags, title, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                action,
                float(signal),
                category,
                source,
                _json_dumps(tags or []),
                title,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM feedback_events WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row) if row else {}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """返回最近 N 条反馈事件, 按时间倒序。"""
        rows = get_connection().execute(
            "SELECT * FROM feedback_events ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_entity(
        self, entity_type: str, entity_id: str
    ) -> list[dict[str, Any]]:
        """按实体查询反馈历史, 时间正序。"""
        rows = get_connection().execute(
            "SELECT * FROM feedback_events "
            "WHERE entity_type = ? AND entity_id = ? "
            "ORDER BY created_at ASC",
            (entity_type, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_by_action(self, action: str) -> int:
        """统计某 action 的总次数 (like 或 dislike)。"""
        row = get_connection().execute(
            "SELECT COUNT(*) AS n FROM feedback_events WHERE action = ?",
            (action,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def count_by_entity(self, entity_type: str, entity_id: str) -> int:
        """统计某实体收到的反馈总数。"""
        row = get_connection().execute(
            "SELECT COUNT(*) AS n FROM feedback_events "
            "WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchone()
        return int(row["n"]) if row else 0


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    import json
    return json.dumps(value, ensure_ascii=False)


__all__ = ["FeedbackRepository"]
