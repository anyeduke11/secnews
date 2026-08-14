"""URL 校验结果 (crawl_url_checks) 表仓储层。

Phase 2.2 (Crawler v2): 全量 URL 校验结果写入。
表结构见 migration 055_crawler_v2_phase0.sql。
"""
from __future__ import annotations

from backend.repository.db import get_connection


class CrawlUrlCheckRepo:
    """crawl_url_checks 表 CRUD。"""

    def insert(
        self,
        item_id: str,
        url: str,
        status_code: int | None = None,
        final_url: str = "",
        title_match_score: float | None = None,
    ) -> bool:
        """插入一条 URL 校验记录。

        Args:
            item_id: hotspots.id
            url: 被校验的 URL
            status_code: HTTP 状态码
            final_url: 最终重定向 URL
            title_match_score: 标题匹配度（0.0-1.0）

        Returns:
            True 表示插入成功
        """
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO crawl_url_checks
                    (item_id, url, final_url, status_code, title_match_score, checked_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (item_id, url, final_url, status_code, title_match_score),
            )
            return True
        except Exception:
            return False

    def get_unchecked(self, since_minutes: int = 5, limit: int = 100) -> list[dict]:
        """查询最近 N 分钟内入库且尚未校验的条目。

        通过检查 hotspots 表中 url_check_status IS NULL 且
        fetched_at 在最近 N 分钟内来确定。

        Args:
            since_minutes: 查询最近多少分钟内的条目
            limit: 最大返回条数

        Returns:
            list of dict，每个 dict 含 id, url, title
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT h.id, h.url, h.title
            FROM hotspots h
            LEFT JOIN crawl_url_checks cuc ON cuc.item_id = h.id
            WHERE h.url IS NOT NULL
              AND h.url != ''
              AND (h.url_check_status IS NULL OR h.url_check_status = '')
              AND cuc.id IS NULL
              AND h.fetched_at >= datetime('now', ?)
            ORDER BY h.fetched_at DESC
            LIMIT ?
            """,
            (f"-{since_minutes} minutes", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_status(
        self,
        item_id: str,
        status_code: int,
        title_match_score: float | None = None,
    ) -> bool:
        """更新校验状态。

        同时更新 crawl_url_checks 和 hotspots.url_check_status。

        Args:
            item_id: hotspots.id
            status_code: HTTP 状态码
            title_match_score: 标题匹配度

        Returns:
            True 表示更新成功
        """
        conn = get_connection()
        try:
            # 更新 url_check_status
            url_check_status = "verified" if 200 <= status_code < 400 else "unreachable"
            conn.execute(
                "UPDATE hotspots SET url_check_status = ?, updated_at = datetime('now') WHERE id = ?",
                (url_check_status, item_id),
            )
            # 更新 crawl_url_checks 中的 status_code
            conn.execute(
                "UPDATE crawl_url_checks SET status_code = ?, title_match_score = ? WHERE item_id = ?",
                (status_code, title_match_score, item_id),
            )
            return True
        except Exception:
            return False

    def get_stats(self) -> dict:
        """获取校验统计。

        Returns:
            dict 含 total, verified, unreachable, pending
        """
        conn = get_connection()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM crawl_url_checks"
        ).fetchone()["cnt"]
        verified = conn.execute(
            "SELECT COUNT(*) as cnt FROM crawl_url_checks WHERE status_code >= 200 AND status_code < 400"
        ).fetchone()["cnt"]
        unreachable = conn.execute(
            "SELECT COUNT(*) as cnt FROM crawl_url_checks WHERE status_code IS NOT NULL AND (status_code < 200 OR status_code >= 400)"
        ).fetchone()["cnt"]
        pending = conn.execute(
            "SELECT COUNT(*) as cnt FROM crawl_url_checks WHERE status_code IS NULL"
        ).fetchone()["cnt"]
        return {
            "total": total,
            "verified": verified,
            "unreachable": unreachable,
            "pending": pending,
        }


__all__ = ["CrawlUrlCheckRepo"]