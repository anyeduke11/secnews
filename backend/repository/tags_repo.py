"""v1.7 Phase 1 标签仓库 — tags 层级表 + hotspot_tags 多对多.

PRD §3.2.1 / §6.2 / §6.3

职责:
- Tag CRUD (层级, type 索引)
- hotspot_tags 关联 (attach/detach + 按 tag 查热点)
- suggest 模糊搜索 (id/label)
- list_by_hotspot 反查热点所有标签
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


@dataclass
class Tag:
    id: str
    label: str
    type: str
    parent_id: Optional[str] = None
    weight: float = 1.0
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "parent_id": self.parent_id,
            "weight": self.weight,
            "created_at": self.created_at,
        }


class TagRepository:
    """tags + hotspot_tags 仓库 (singleton 风格, 复用 thread-local conn)."""

    def add(
        self,
        id: str,
        label: str,
        type: str,
        parent_id: Optional[str] = None,
        weight: float = 1.0,
    ) -> Tag:
        """插入或替换标签, 返回完整 Tag."""
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "INSERT OR REPLACE INTO tags (id, label, type, parent_id, weight, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id, label, type, parent_id, weight, now),
        )
        result = self.get(id)
        assert result is not None, f"tag {id} not found after add"
        return result

    def get(self, id: str) -> Optional[Tag]:
        row = (
            get_connection()
            .execute("SELECT * FROM tags WHERE id=?", (id,))
            .fetchone()
        )
        if not row:
            return None
        return Tag(**dict(row))

    def list(
        self,
        type: Optional[str] = None,
        parent_id: Optional[str] = None,
        limit: int = 1000,
    ) -> list[Tag]:
        sql = "SELECT * FROM tags WHERE 1=1"
        params: list = []
        if type:
            sql += " AND type=?"
            params.append(type)
        if parent_id is not None:
            sql += " AND parent_id=?"
            params.append(parent_id)
        sql += " ORDER BY weight DESC, label LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [Tag(**dict(r)) for r in rows]

    def suggest(self, q: str, limit: int = 10) -> list[Tag]:
        rows = (
            get_connection()
            .execute(
                "SELECT * FROM tags WHERE id LIKE ? OR label LIKE ? "
                "ORDER BY weight DESC, label LIMIT ?",
                (f"%{q}%", f"%{q}%", limit),
            )
            .fetchall()
        )
        return [Tag(**dict(r)) for r in rows]

    def delete(self, id: str) -> bool:
        """删除标签 (hotspot_tags 因 ON DELETE CASCADE 自动清理)."""
        cur = get_connection().execute("DELETE FROM tags WHERE id=?", (id,))
        return cur.rowcount > 0

    # ---- hotspot_tags 关联 ----

    def attach(
        self,
        hotspot_id: str,
        tag_id: str,
        confidence: float = 1.0,
    ) -> None:
        """关联热点与标签 (幂等, 冲突时更新 confidence)."""
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "INSERT INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(hotspot_id, tag_id) DO UPDATE SET confidence=excluded.confidence",
            (hotspot_id, tag_id, confidence, now),
        )

    def detach(self, hotspot_id: str, tag_id: str) -> None:
        get_connection().execute(
            "DELETE FROM hotspot_tags WHERE hotspot_id=? AND tag_id=?",
            (hotspot_id, tag_id),
        )

    def list_by_hotspot(self, hotspot_id: str) -> list[Tag]:
        rows = (
            get_connection()
            .execute(
                "SELECT t.* FROM tags t "
                "JOIN hotspot_tags ht ON t.id = ht.tag_id "
                "WHERE ht.hotspot_id=? ORDER BY t.weight DESC, t.label",
                (hotspot_id,),
            )
            .fetchall()
        )
        return [Tag(**dict(r)) for r in rows]

    def list_hotspot_ids_by_tags(
        self,
        tag_ids: list[str],
        mode: str = "or",
        limit: int = 50,
    ) -> list[str]:
        """按标签筛选热点 id.

        mode='and': 热点必须拥有全部 tag_ids
        mode='or':  热点拥有任一 tag_ids
        """
        if not tag_ids:
            return []
        placeholders = ",".join("?" * len(tag_ids))
        if mode == "and":
            sql = f"""
            SELECT h.id FROM hotspots h
            JOIN hotspot_tags ht ON h.id = ht.hotspot_id
            WHERE ht.tag_id IN ({placeholders})
            GROUP BY h.id
            HAVING COUNT(DISTINCT ht.tag_id) = ?
            ORDER BY h.ingested_at DESC
            LIMIT ?
            """
            params = tag_ids + [len(tag_ids), limit]
        else:
            sql = f"""
            SELECT DISTINCT h.id FROM hotspots h
            JOIN hotspot_tags ht ON h.id = ht.hotspot_id
            WHERE ht.tag_id IN ({placeholders})
            ORDER BY h.ingested_at DESC
            LIMIT ?
            """
            params = tag_ids + [limit]
        rows = get_connection().execute(sql, params).fetchall()
        return [r[0] for r in rows]
