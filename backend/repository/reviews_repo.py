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

from datetime import datetime, timedelta, timezone

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

    def get(self, entity_type: str, entity_id: str) -> dict | None:
        """读取一条复习记录, 不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM sm2_reviews WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        return dict(row) if row else None

    def list_due(self, limit: int = 20) -> list[dict]:
        """列出到期 (due_at <= now) 的复习记录, 按 due_at 升序。

        migration 120: 暂停卡 (suspended=1) 不进队列。
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM sm2_reviews WHERE due_at <= ? AND suspended=0 "
            "ORDER BY due_at LIMIT ?",
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

    def count_suspended(self) -> int:
        """暂停中的复习记录数 (migration 120)。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM sm2_reviews WHERE suspended=1"
        ).fetchone()
        return row[0] if row else 0

    def set_suspended(self, entity_type: str, entity_id: str, suspended: bool) -> int:
        """暂停/恢复一张卡, 返回更新行数 (0 = 卡不存在)。"""
        conn = get_connection()
        cur = conn.execute(
            "UPDATE sm2_reviews SET suspended=?, updated_at=? "
            "WHERE entity_type=? AND entity_id=?",
            (1 if suspended else 0,
             datetime.now(timezone.utc).isoformat(),
             entity_type, entity_id),
        )
        return cur.rowcount

    def restore_state(
        self,
        entity_type: str,
        entity_id: str,
        easiness: float,
        interval: int,
        repetitions: int,
        due_at: str,
        last_grade: int,
        last_reviewed_at: str | None,
    ) -> None:
        """undo 专用: 精确恢复评分前状态 (含 last_reviewed_at/last_grade)。

        与 ``upsert`` 的区别: 不把 last_reviewed_at 盖成 now。
        记录不存在则插入 (suspended 取默认 0)。
        """
        now = datetime.now(timezone.utc).isoformat()
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
                last_reviewed_at, now, now,
            ),
        )

    def forecast(self, days: int = 7) -> list[dict]:
        """未来 N 天逐日到期计数 (排除 suspended, 含今日), 空缺日补 0。

        返回 ``[{"date": "YYYY-MM-DD", "count": n}, ...]`` 恒为 N 条。
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT date(due_at) AS d, COUNT(*) AS n FROM sm2_reviews
            WHERE suspended=0
              AND date(due_at) BETWEEN date('now') AND date('now', ?)
            GROUP BY d ORDER BY d
            """,
            (f"+{max(0, days - 1)} days",),
        ).fetchall()
        by_date = {r["d"]: r["n"] for r in rows}
        out: list[dict] = []
        today = datetime.now(timezone.utc).date()
        for i in range(max(0, days)):
            key = (today + timedelta(days=i)).isoformat()
            out.append({"date": key, "count": by_date.get(key, 0)})
        return out


__all__ = ["ReviewRepository"]
