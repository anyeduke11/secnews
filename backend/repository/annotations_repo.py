"""v1.7 Phase 2 — Annotations (笔记) 仓库。

对应 migration ``027_v1.7_annotations.sql``:
    annotations(id, entity_type, entity_id, content,
                range_start, range_end, created_at, updated_at)

设计
----
- ``entity_type`` / ``entity_id`` 标注被笔记的对象 (concept/knowledge/hotspot/...)。
- ``range_start`` / ``range_end`` 可选, 用于标注正文内的字符区间 (未来前端高亮)。
- id 用 uuid4 派生, 不复用 entity 派生 (一条 entity 可有多条笔记)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from backend.repository.db import get_connection


class AnnotationRepository:
    """annotations 表的 CRUD。"""

    def add(
        self,
        entity_type: str,
        entity_id: str,
        content: str,
        range_start: Optional[int] = None,
        range_end: Optional[int] = None,
    ) -> dict:
        """新增一条笔记, 返回创建后的完整记录。"""
        aid = f"{entity_type}-{entity_id}-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO annotations (id, entity_type, entity_id, content,
                range_start, range_end, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (aid, entity_type, entity_id, content, range_start, range_end, now, now),
        )
        return self.get(aid)

    def get(self, annotation_id: str) -> Optional[dict]:
        """按 id 读取一条笔记, 不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM annotations WHERE id = ?",
            (annotation_id,),
        ).fetchone()
        return dict(row) if row else None

    def list(self, entity_type: str, entity_id: str) -> list[dict]:
        """列出某对象的所有笔记, 按创建时间倒序。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM annotations WHERE entity_type=? AND entity_id=? "
            "ORDER BY created_at DESC",
            (entity_type, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(
        self,
        annotation_id: str,
        content: Optional[str] = None,
        range_start: Optional[int] = None,
        range_end: Optional[int] = None,
    ) -> Optional[dict]:
        """更新笔记内容/区间。至少更新一个字段。返回更新后的记录或 None。"""
        existing = self.get(annotation_id)
        if existing is None:
            return None
        new_content = content if content is not None else existing["content"]
        new_start = range_start if range_start is not None else existing["range_start"]
        new_end = range_end if range_end is not None else existing["range_end"]
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        conn.execute(
            """
            UPDATE annotations SET content=?, range_start=?, range_end=?, updated_at=?
            WHERE id=?
            """,
            (new_content, new_start, new_end, now, annotation_id),
        )
        return self.get(annotation_id)

    def delete(self, annotation_id: str) -> int:
        """删除一条笔记, 返回删除行数 (0=不存在)。"""
        conn = get_connection()
        cur = conn.execute("DELETE FROM annotations WHERE id=?", (annotation_id,))
        return cur.rowcount

    def count(self, entity_type: Optional[str] = None) -> int:
        """笔记总数, 可按 entity_type 过滤。"""
        conn = get_connection()
        if entity_type:
            row = conn.execute(
                "SELECT COUNT(*) FROM annotations WHERE entity_type=?",
                (entity_type,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM annotations").fetchone()
        return row[0] if row else 0


__all__ = ["AnnotationRepository"]
