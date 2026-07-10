"""Phase 10 收藏仓库：favorites 表 CRUD

设计要点
--------
- 单 user 本地系统（无 user_id 字段）
- 同一 ``hotspot_id`` 重复收藏等价于 no-op（``UNIQUE(hotspot_id)``）
- 收藏时把 title/source/url/category 快照进表，避免 hotspots 表更新后
  收藏列表里看到错乱数据
- 删除是软操作（返回删除行数），无级联到 hotspots 表
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.domain.enums import Category
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
class FavoriteItem:
    """收藏条目的内存模型（不直接用 HotspotItem 是为了表独立）。"""

    __slots__ = (
        "id",
        "hotspot_id",
        "category",
        "title",
        "source",
        "url",
        "favorited_at",
    )

    def __init__(
        self,
        *,
        id: int,
        hotspot_id: str,
        category: str,
        title: str,
        source: str,
        url: str,
        favorited_at: str,
    ):
        self.id = id
        self.hotspot_id = hotspot_id
        self.category = category
        self.title = title
        self.source = source
        self.url = url
        self.favorited_at = favorited_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hotspot_id": self.hotspot_id,
            "category": self.category,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "favorited_at": self.favorited_at,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_favorite(row: sqlite3.Row) -> FavoriteItem:
    return FavoriteItem(
        id=int(row["id"]),
        hotspot_id=str(row["hotspot_id"]),
        category=str(row["category"]),
        title=str(row["title"]),
        source=str(row["source"]),
        url=str(row["url"]),
        favorited_at=str(row["favorited_at"]),
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class FavoriteRepository:
    """对 ``favorites`` 表的 CRUD + 简单聚合。"""

    def add(
        self,
        *,
        hotspot_id: str,
        category: str,
        title: str,
        source: str,
        url: str,
    ) -> tuple[bool, FavoriteItem]:
        """收藏一条资讯/标讯。

        Returns
        -------
        (created, item)
            ``created=True`` 表示新增成功；``False`` 表示已存在（不抛异常）
        """
        if not hotspot_id or not hotspot_id.strip():
            raise InternalException("hotspot_id is required")
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO favorites
                    (hotspot_id, category, title, source, url, favorited_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (hotspot_id, category, title, source, url, now),
            )
            if cur.rowcount == 0:
                # 已存在 → 查出来返回
                conn.execute("COMMIT")
                row = conn.execute(
                    "SELECT * FROM favorites WHERE hotspot_id = ?",
                    (hotspot_id,),
                ).fetchone()
                return False, _row_to_favorite(row)
            conn.execute("COMMIT")
            # 写统计表
            self._bump_stats(conn, category, now)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("favorite add failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"favorite add failed: {e}") from e
        new_id = int(cur.lastrowid)
        item = FavoriteItem(
            id=new_id,
            hotspot_id=hotspot_id,
            category=category,
            title=title,
            source=source,
            url=url,
            favorited_at=now,
        )
        return True, item

    def remove(self, hotspot_id: str) -> int:
        """取消收藏。返回被删除的行数（0=本来就没收藏）。"""
        if not hotspot_id:
            return 0
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM favorites WHERE hotspot_id = ?",
                (hotspot_id,),
            )
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            if n > 0:
                self._refresh_all_stats(conn)
            return n
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("favorite remove failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"favorite remove failed: {e}") from e

    def list(
        self,
        *,
        category: Optional[str] = None,
        limit: int = 200,
    ) -> list[FavoriteItem]:
        """按收藏时间倒序列出收藏项。``category=None`` 表示全部分类。"""
        conn = get_connection()
        limit = max(1, min(int(limit or 200), 1000))
        if category:
            try:
                cat_value = Category(category).value
            except ValueError:
                cat_value = category
            rows = conn.execute(
                """
                SELECT * FROM favorites
                WHERE category = ?
                ORDER BY favorited_at DESC
                LIMIT ?
                """,
                (cat_value, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM favorites
                ORDER BY favorited_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_favorite(r) for r in rows]

    def is_favorited(self, hotspot_id: str) -> bool:
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE hotspot_id = ? LIMIT 1",
            (hotspot_id,),
        ).fetchone()
        return row is not None

    def list_favorited_ids(self) -> set[str]:
        """返回所有已收藏 hotspot_id 集合（用于卡片批量标星）。"""
        conn = get_connection()
        rows = conn.execute("SELECT hotspot_id FROM favorites").fetchall()
        return {str(r["hotspot_id"]) for r in rows}

    def count_by_category(self) -> dict[str, int]:
        """按分类统计收藏数（全 6 大分类都有，0 也要返回）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM favorites GROUP BY category"
        ).fetchall()
        out: dict[str, int] = {c.value: 0 for c in Category}
        for r in rows:
            out[str(r["category"])] = int(r["n"])
        return out

    def total(self) -> int:
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) AS n FROM favorites").fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # 内部：favorites_stats 维护
    # ------------------------------------------------------------------
    def _bump_stats(self, conn: sqlite3.Connection, category: str, now: str) -> None:
        """在收藏后增量更新 favorites_stats。"""
        try:
            conn.execute(
                """
                INSERT INTO favorites_stats (category, total_favorites, last_favorited_at, updated_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(category) DO UPDATE SET
                    total_favorites = total_favorites + 1,
                    last_favorited_at = excluded.last_favorited_at,
                    updated_at = excluded.updated_at
                """,
                (category, now, now),
            )
        except Exception:
            # stats 表是辅助表，失败不影响主表
            logger.warning(
                "bump favorites_stats failed", extra={"trace_id": "", "category": category}
            )

    def _refresh_all_stats(self, conn: sqlite3.Connection) -> None:
        """删除收藏后刷新全表聚合（确保准确，避免漏算）。"""
        try:
            conn.execute("DELETE FROM favorites_stats")
            conn.execute(
                """
                INSERT INTO favorites_stats (category, total_favorites, last_favorited_at, updated_at)
                SELECT category, COUNT(*), MAX(favorited_at), ? FROM favorites GROUP BY category
                """,
                (_now_iso(),),
            )
        except Exception:
            logger.warning("refresh favorites_stats failed", extra={"trace_id": ""})


__all__ = ["FavoriteRepository", "FavoriteItem"]
