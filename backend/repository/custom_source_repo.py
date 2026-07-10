"""Phase 8 Addendum 8.4: custom_sources 表 CRUD

字段语义
--------
- ``url``    用户输入的源地址（UNIQUE；重复插入 → 409）
- ``name``   用户起的别名（可空 → 默认用 url/title）
- ``category`` ai / security / finance / startup / bid / github
- ``enabled`` 0/1；下次采集时只读 enabled=1 的注入到 collector
- ``last_check_*``  最近一次 probe 的状态 / 延迟 / 抓取到的 <title>

写入路径
--------
- :meth:`add`           — 用户添加（probe 通过后调用）
- :meth:`delete`        — 用户删除
- :meth:`set_enabled`   — 用户 toggle enabled
- :meth:`update_probe_result` — 用户手动 re-probe 后回写

读取路径
--------
- :meth:`list`                — 前端列表展示
- :meth:`list_enabled_by_category` — collection_service 在 run_once 注入用
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.domain.enums import Category
from backend.repository.db import get_connection


class CustomSource:
    """custom_sources 表的单行内存表示。"""

    def __init__(
        self,
        id: int,
        url: str,
        name: str,
        category: str,
        enabled: bool,
        created_at: str,
        last_check_at: Optional[str],
        last_check_status: Optional[str],
        last_check_latency_ms: float,
        last_check_title: Optional[str],
        notes: str = "",
    ):
        self.id = id
        self.url = url
        self.name = name
        self.category = category
        self.enabled = enabled
        self.created_at = created_at
        self.last_check_at = last_check_at
        self.last_check_status = last_check_status
        self.last_check_latency_ms = last_check_latency_ms
        self.last_check_title = last_check_title
        self.notes = notes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "name": self.name,
            "category": self.category,
            "enabled": bool(self.enabled),
            "created_at": self.created_at,
            "last_check_at": self.last_check_at,
            "last_check_status": self.last_check_status,
            "last_check_latency_ms": self.last_check_latency_ms,
            "last_check_title": self.last_check_title,
            "notes": self.notes,
        }


class CustomSourceRepository:
    """custom_sources 表的 CRUD。"""

    def list(self) -> list[CustomSource]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM custom_sources ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_obj(r) for r in rows]

    def list_enabled_by_category(self, category: Category) -> list[dict]:
        """Phase 8: collection_service 用 — 列出某 category 启用的 source dict（与 collector.sources 兼容）

        返回 ``[{"name": ..., "url": ..., "score": 50}, ...]``，
        与 ``BaseCollector.sources`` 的契约一致（BaseCollector.fetch_source
        依赖 ``source["name"]`` 和 ``source["url"]``）。
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT url, name, category FROM custom_sources WHERE enabled=1 AND category=?",
            (category.value,),
        ).fetchall()
        return [
            {"name": r["name"] or r["url"], "url": r["url"], "score": 50}
            for r in rows
        ]

    def add(
        self,
        url: str,
        name: str,
        category: str,
        last_check_status: str = "ok",
        last_check_latency_ms: float = 0.0,
        last_check_title: Optional[str] = None,
    ) -> int:
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO custom_sources
            (url, name, category, enabled, created_at, last_check_at, last_check_status, last_check_latency_ms, last_check_title)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (
                url,
                name,
                category,
                now,
                now,
                last_check_status,
                last_check_latency_ms,
                last_check_title,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)

    def delete(self, id: int) -> bool:
        conn = get_connection()
        cur = conn.execute("DELETE FROM custom_sources WHERE id=?", (id,))
        conn.commit()
        return cur.rowcount > 0

    def update_probe_result(
        self, id: int, status: str, latency_ms: float, title: Optional[str] = None
    ) -> None:
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE custom_sources
            SET last_check_at=?, last_check_status=?, last_check_latency_ms=?, last_check_title=?
            WHERE id=?""",
            (now, status, latency_ms, title, id),
        )
        conn.commit()

    def set_enabled(self, id: int, enabled: bool) -> bool:
        conn = get_connection()
        cur = conn.execute(
            "UPDATE custom_sources SET enabled=? WHERE id=?",
            (1 if enabled else 0, id),
        )
        conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_obj(row: sqlite3.Row) -> CustomSource:
        return CustomSource(
            id=row["id"],
            url=row["url"],
            name=row["name"] or "",
            category=row["category"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            last_check_at=row["last_check_at"],
            last_check_status=row["last_check_status"],
            last_check_latency_ms=float(row["last_check_latency_ms"] or 0),
            last_check_title=row["last_check_title"],
            notes=row["notes"] or "",
        )


__all__ = ["CustomSourceRepository", "CustomSource"]
