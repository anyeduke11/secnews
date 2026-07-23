"""v1.7 Phase 4 — Digest repository.

数据模型 (migration 031)
------------------------
::

    digests (
        id           TEXT PRIMARY KEY,   -- e.g. "digest-2026-07-24"
        period       TEXT NOT NULL,      -- "daily" / "weekly" / ...
        summary      TEXT NOT NULL,      -- 简报摘要文本
        item_ids     TEXT DEFAULT '[]',  -- JSON 数组, 关联 hotspot/knowledge id
        created_at   TEXT NOT NULL       -- ISO 8601 UTC
    )

设计决策
--------
- 表无 ``start_at`` / ``end_at`` / ``read`` 列 (与 PRD §3.2.10 简化版对齐),
  时间窗口通过 ``id`` (含日期) 隐含, 读取状态用 ``kv_cache`` 表记录
  (见 digest_service.mark_digest_read).
- ``add`` 用 ``ON CONFLICT(id) DO UPDATE`` 实现 upsert, 同 id 重复生成时覆盖.
- ``list_recent`` 按 created_at DESC 排序, 用于仪表盘展示历史简报.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DigestRepository:
    """``digests`` 表的数据访问层."""

    def add(
        self,
        digest_id: str,
        period: str,
        summary: str,
        item_ids: Optional[list[str]] = None,
        created_at: Optional[str] = None,
    ) -> dict:
        """插入或覆盖一条简报.

        Parameters
        ----------
        digest_id:
            简报唯一 ID (建议 ``"digest-YYYY-MM-DD"``).
        period:
            周期类型 (``"daily"`` / ``"weekly"`` / ...).
        summary:
            简报摘要文本.
        item_ids:
            关联的 hotspot/knowledge id 列表, 存为 JSON.
        created_at:
            创建时间 (ISO 8601), 默认当前 UTC.

        Returns
        -------
        dict
            插入后的完整记录.
        """
        ts = created_at or _now_iso()
        ids_json = json.dumps(item_ids or [])
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO digests (id, period, summary, item_ids, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                period = excluded.period,
                summary = excluded.summary,
                item_ids = excluded.item_ids,
                created_at = excluded.created_at
            """,
            (digest_id, period, summary, ids_json, ts),
        )
        return self.get(digest_id) or {
            "id": digest_id,
            "period": period,
            "summary": summary,
            "item_ids": ids_json,
            "created_at": ts,
        }

    def get(self, digest_id: str) -> Optional[dict]:
        """读取一条简报. 不存在返回 None."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM digests WHERE id = ?", (digest_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        # 解析 item_ids JSON 为 list
        try:
            d["item_ids"] = json.loads(d.get("item_ids") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["item_ids"] = []
        return d

    def list_by_period(
        self, period: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """列出简报, 按 created_at DESC 排序.

        Parameters
        ----------
        period:
            可选, 按周期过滤 (``"daily"`` / ``"weekly"``). None = 全部.
        limit:
            最多返回条数 (1..100).
        """
        effective_limit = max(1, min(limit, 100))
        conn = get_connection()
        if period:
            rows = conn.execute(
                "SELECT * FROM digests WHERE period = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (period, effective_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM digests ORDER BY created_at DESC LIMIT ?",
                (effective_limit,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            try:
                d["item_ids"] = json.loads(d.get("item_ids") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["item_ids"] = []
            out.append(d)
        return out

    def list_recent(self, limit: int = 10) -> list[dict]:
        """列出最近 N 条简报 (不限 period)."""
        return self.list_by_period(period=None, limit=limit)

    def get_latest(self, period: Optional[str] = None) -> Optional[dict]:
        """获取最新一条简报, 无则返回 None."""
        items = self.list_by_period(period=period, limit=1)
        return items[0] if items else None

    def delete(self, digest_id: str) -> bool:
        """删除一条简报. 返回是否删除成功."""
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM digests WHERE id = ?", (digest_id,)
        )
        return cur.rowcount > 0

    def count(self, period: Optional[str] = None) -> int:
        """简报总数, 可按 period 过滤."""
        conn = get_connection()
        if period:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM digests WHERE period = ?",
                (period,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM digests").fetchone()
        return int(row["n"]) if row else 0


# 单例 (与 codebase 约定一致)
digest_repo = DigestRepository()


__all__ = ["DigestRepository", "digest_repo"]
