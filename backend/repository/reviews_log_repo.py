"""复习评分流水仓库 (migration 120 ``review_log`` 表)。

review_log 是撤销 (undo) 与保留率/评分分布统计的唯一真数据源:
每次 ``submit_grade`` 写一条 旧→新 全量快照, undo 恢复最新一条活跃
log 的 prev 状态并标记 ``reverted=1`` (保留痕迹, 不物理删行)。

设计
----
- 遵守 R2 写路径唯一: review_log 的全部写入收敛在本仓库。
- 连接由 ``get_connection()`` 提供 (thread-local, autocommit)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.repository.db import get_connection


class ReviewLogRepository:
    """review_log 表的写入与查询。"""

    def insert(
        self,
        entity_type: str,
        entity_id: str,
        grade: int,
        prev: dict | None,
        new_easiness: float,
        new_interval: int,
        new_repetitions: int,
        new_due_at: str,
    ) -> int:
        """写入一条评分快照 (旧→新)。``prev`` 为评分前的 sm2_reviews 行,
        无历史记录 (首评) 时传 None。返回新 log id。"""
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO review_log (
                entity_type, entity_id, grade,
                prev_easiness, prev_interval, prev_repetitions,
                prev_due_at, prev_last_reviewed_at, prev_last_grade,
                new_easiness, new_interval, new_repetitions, new_due_at,
                reverted, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                entity_type, entity_id, grade,
                prev["easiness"] if prev else None,
                prev["interval"] if prev else None,
                prev["repetitions"] if prev else None,
                prev["due_at"] if prev else None,
                prev["last_reviewed_at"] if prev else None,
                prev["last_grade"] if prev else None,
                new_easiness, new_interval, new_repetitions, new_due_at,
                now,
            ),
        )
        return cur.lastrowid

    def latest_active(self, entity_type: str, entity_id: str) -> dict | None:
        """该实体最新一条 ``reverted=0`` 的评分 log, 无则 None。"""
        conn = get_connection()
        row = conn.execute(
            """
            SELECT * FROM review_log
            WHERE entity_type=? AND entity_id=? AND reverted=0
            ORDER BY id DESC LIMIT 1
            """,
            (entity_type, entity_id),
        ).fetchone()
        return dict(row) if row else None

    def mark_reverted(self, log_id: int) -> int:
        """标记 log 已撤销 (保留痕迹), 返回更新行数。"""
        conn = get_connection()
        cur = conn.execute(
            "UPDATE review_log SET reverted=1 WHERE id=?", (log_id,)
        )
        return cur.rowcount

    def list_recent(self, limit: int = 50) -> list[dict]:
        """全部评分流水倒序 (含 reverted 标记), 供历史视图。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM review_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def retention(self, days: int = 30) -> float | None:
        """近 N 天 grade>=3 占比 (保留率); 窗口内无评分返回 None。"""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        conn = get_connection()
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN grade >= 3 THEN 1 ELSE 0 END) AS passed
            FROM review_log WHERE created_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        total = row["total"] or 0
        if total == 0:
            return None
        return (row["passed"] or 0) / total

    def grade_distribution(self, days: int = 30) -> dict[int, int]:
        """近 N 天各 grade 的评分次数 (0-5 → 次数), 供分布图。"""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT grade, COUNT(*) AS n FROM review_log
            WHERE created_at >= ? GROUP BY grade ORDER BY grade
            """,
            (cutoff,),
        ).fetchall()
        return {r["grade"]: r["n"] for r in rows}


__all__ = ["ReviewLogRepository"]
