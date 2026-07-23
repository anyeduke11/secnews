"""v1.7 Phase 2 — TechStack 仓库 (个人技术栈管理).

对应迁移: 029_v1.7_tech_stack.sql
表结构: tech_stack(id, name, category, proficiency, notes, created_at, updated_at)

注意: 实际迁移 schema 与 plan 代码片段 (version/aliases) 不同,
以迁移文件为准 — 使用 proficiency (INTEGER) / notes (TEXT).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


class TechStackRepository:
    """tech_stack 表的 CRUD 仓库 (实例无状态, 跨线程共享)."""

    def add(
        self,
        id: str,
        name: str,
        category: str = "",
        proficiency: int = 1,
        notes: str = "",
    ) -> dict:
        """新建或替换一条技术栈记录 (INSERT OR REPLACE)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO tech_stack
                (id, name, category, proficiency, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, name, category, int(proficiency), notes, now, now),
        )
        return self.get(id)  # type: ignore[return-value]

    def get(self, id: str) -> Optional[dict]:
        row = get_connection().execute(
            "SELECT * FROM tech_stack WHERE id = ?", (id,)
        ).fetchone()
        return _row_to_tech(row) if row else None

    def list(self, category: Optional[str] = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM tech_stack"
        params: list = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [_row_to_tech(r) for r in rows]

    def update(
        self,
        id: str,
        name: Optional[str] = None,
        category: Optional[str] = None,
        proficiency: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        existing = self.get(id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        conn.execute(
            """
            UPDATE tech_stack
               SET name = ?, category = ?, proficiency = ?, notes = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                name if name is not None else existing["name"],
                category if category is not None else existing["category"],
                int(proficiency) if proficiency is not None else existing["proficiency"],
                notes if notes is not None else existing["notes"],
                now,
                id,
            ),
        )
        return self.get(id)

    def delete(self, id: str) -> int:
        cur = get_connection().execute("DELETE FROM tech_stack WHERE id = ?", (id,))
        return cur.rowcount or 0

    def find_by_name(self, name: str) -> Optional[dict]:
        """按 name 精确查找 (用于桥接: tag_id → tech_stack name)."""
        row = get_connection().execute(
            "SELECT * FROM tech_stack WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return _row_to_tech(row) if row else None

    def count(self) -> int:
        row = get_connection().execute("SELECT COUNT(*) AS c FROM tech_stack").fetchone()
        return int(row["c"] or 0)


def _row_to_tech(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "category": row["category"] or "",
        "proficiency": int(row["proficiency"] or 1),
        "notes": row["notes"] or "",
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
