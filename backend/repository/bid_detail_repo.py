"""标讯详情 (bid_details) 表仓储层。

Phase 1.3 (Crawler v2): 写入 bid_details 表，结构化存储标讯字段。
表结构见 migration 055_crawler_v2_phase0.sql。
"""
from __future__ import annotations

from backend.repository.db import get_connection


class BidDetailRepo:
    """bid_details 表 CRUD。"""

    def upsert(self, item_id: str, fields: dict) -> bool:
        """插入或更新一条标讯详情。

        Args:
            item_id: hotspots.id
            fields: 标讯字段，支持 bid_no, buyer, region, budget,
                    deadline, bid_status, industry, published_at

        Returns:
            True 表示插入/更新成功
        """
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO bid_details
                    (item_id, bid_no, buyer, region, budget, deadline,
                     bid_status, industry, published_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(item_id) DO UPDATE SET
                    bid_no       = COALESCE(NULLIF(EXCLUDED.bid_no, ''), bid_no),
                    buyer        = COALESCE(NULLIF(EXCLUDED.buyer, ''), buyer),
                    region       = COALESCE(NULLIF(EXCLUDED.region, ''), region),
                    budget       = COALESCE(NULLIF(EXCLUDED.budget, ''), budget),
                    deadline     = COALESCE(EXCLUDED.deadline, deadline),
                    bid_status   = COALESCE(NULLIF(EXCLUDED.bid_status, ''), bid_status),
                    industry     = COALESCE(NULLIF(EXCLUDED.industry, ''), industry),
                    published_at = COALESCE(EXCLUDED.published_at, published_at),
                    updated_at   = datetime('now')
                """,
                (
                    item_id,
                    fields.get("bid_no", ""),
                    fields.get("buyer", ""),
                    fields.get("region", ""),
                    fields.get("budget", ""),
                    fields.get("deadline"),
                    fields.get("bid_status", ""),
                    fields.get("industry", ""),
                    fields.get("published_at"),
                ),
            )
            return True
        except Exception:
            return False

    def upsert_many(self, item_fields: list[tuple[str, dict]]) -> int:
        """批量插入或更新标讯详情。

        Args:
            item_fields: [(item_id, fields_dict), ...]

        Returns:
            成功写入的行数
        """
        count = 0
        for item_id, fields in item_fields:
            if self.upsert(item_id, fields):
                count += 1
        return count

    def get_by_item_id(self, item_id: str) -> dict | None:
        """按 item_id 查询标讯详情。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM bid_details WHERE item_id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_expired(self) -> list[dict]:
        """查询已过截止时间但未标记的标讯。

        deadline IS NOT NULL AND deadline < datetime('now')
        """
        conn = get_connection()
        rows = conn.execute(
            """SELECT bd.*, h.title, h.url
               FROM bid_details bd
               JOIN hotspots h ON h.id = bd.item_id
               WHERE bd.deadline IS NOT NULL
                 AND bd.deadline < datetime('now')
                 AND (h.bid_status IS NULL OR h.bid_status NOT IN ('终止', '废标', '流标'))
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_expired(self, item_id: str) -> bool:
        """标记标讯为过期状态。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE bid_details SET bid_status = '已过期', updated_at = datetime('now') WHERE item_id = ?",
                (item_id,),
            )
            return True
        except Exception:
            return False


__all__ = ["BidDetailRepo"]