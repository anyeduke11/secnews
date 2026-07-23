"""v1.7 Phase 2 — SM-2 复习仓库。

对应 migration ``026_v1.7_sm2_reviews.sql`` 的表结构:
    sm2_reviews(
        id, entity_type, entity_id, easiness, interval, repetitions,
        due_at, last_grade, last_reviewed_at, created_at, updated_at
    )

设计
----
- ``entity_type`` / ``entity_id`` 复合唯一 (一个被复习对象一条记录),
  用 ``ON CONFLICT(entity_type, entity_id) DO UPDATE`` upsert。
- ``due_at`` 存 ISO-8601 UTC 字符串; ``list_due`` 用 ``due_at <= now`` 过滤。
- 连接由 ``get_connection()`` 提供 (thread-local, autocommit)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


class ReviewRepository:
    """sm2_reviews 表的 CRUD + 查询。"""

    def upsert(
        self,
        entity_type: str,
        entity_id: str,
        easiness: float,
        interval: int,
        repetitions: int,
        due_at: str,
        last_grade: int,
    ) -> None:
        """插入或更新一条复习记录 (按 id 唯一, id = entity_type-entity_id)。"""
        now = datetime.now(timezone.utc).isoformat()
        # id 用 entity_type-entity_id 派生, 保证 upsert 幂等 (migration 026
        # 只把 id 设为 PK, (entity_type, entity_id) 无 UNIQUE 约束, 故用
        # ON CONFLICT(id))
        rid = f"{entity_type}-{entity_id}"
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO sm2_reviews (id, entity_type, entity_id, easiness,
                interval, repetitions, due_at, last_grade,
                last_reviewed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                easiness=excluded.easiness,
                interval=excluded.interval,
                repetitions=excluded.repetitions,
                due_at=excluded.due_at,
                last_grade=excluded.last_grade,
                last_reviewed_at=excluded.last_reviewed_at,
                updated_at=excluded.updated_at
            """,
            (
                rid, entity_type, entity_id, easiness,
                interval, repetitions, due_at, last_grade,
                now, now, now,
            ),
        )

    def get(self, entity_type: str, entity_id: str) -> Optional[dict]:
        """读取一条复习记录, 不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM sm2_reviews WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        return dict(row) if row else None

    def list_due(self, limit: int = 20) -> list[dict]:
        """列出到期 (due_at <= now) 的复习记录, 按 due_at 升序。"""
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM sm2_reviews WHERE due_at <= ? ORDER BY due_at LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, limit: int = 100) -> list[dict]:
        """列出全部复习记录 (调试/统计用)。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM sm2_reviews ORDER BY due_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, entity_type: str, entity_id: str) -> int:
        """删除一条复习记录, 返回删除行数。"""
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM sm2_reviews WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        )
        return cur.rowcount

    def count(self) -> int:
        """总复习记录数。"""
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) FROM sm2_reviews").fetchone()
        return row[0] if row else 0


__all__ = ["ReviewRepository"]
