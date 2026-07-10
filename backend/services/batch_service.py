"""Phase 28 BatchService — 历史资讯批次计算与查询.

设计
----
- **批次 (Batch)**: 按自然周边界 (每周一 00:00 UTC) 的 7 天窗口
- **批次号 (Batch No)**: 从 HISTORY_START_DATE (2026-07-06, 项目启动后第一个周一) 起 1/2/3/...
- **当前批次**: 本周一至今 — 仍是首页展示范围
- **历史批次**: 上周及更早 — 历史资讯页
- 批次边界是查询时计算, **不需要 cron / 归档**

计算规则
--------
batch_no = (ingested_date - HISTORY_START_DATE).days // 7 + 1
batch_start = HISTORY_START_DATE + timedelta(days=(batch_no-1) * 7)
batch_end = batch_start + timedelta(days=7)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from backend.logging_config import logger
from backend.repository.db import get_connection

# 项目启动后第一个周一 (UTC)
HISTORY_START_DATE: date = date(2026, 7, 6)

# 单批次 7 天
_BATCH_DAYS = 7


def _to_utc_date(ts: datetime) -> date:
    """将任意 tz-aware 或 naive datetime 转为 UTC date."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date()


def get_batch_no(ts: datetime) -> int:
    """计算指定时间所属批次号.

    Examples
    --------
    >>> get_batch_no(datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))
    1
    >>> get_batch_no(datetime(2026, 7, 12, 23, 59, tzinfo=timezone.utc))
    1
    >>> get_batch_no(datetime(2026, 7, 13, 0, 0, tzinfo=timezone.utc))
    2
    """
    d = _to_utc_date(ts)
    if d < HISTORY_START_DATE:
        # 历史开始日期之前的数据归到 1 号批次 (兜底)
        return 1
    delta_days = (d - HISTORY_START_DATE).days
    return (delta_days // _BATCH_DAYS) + 1


def get_batch_range(batch_no: int) -> tuple[datetime, datetime]:
    """返回指定批次的 [start, end) 时间区间 (UTC, tz-aware).

    Examples
    --------
    >>> s, e = get_batch_range(1)
    >>> s.isoformat()
    '2026-07-06T00:00:00+00:00'
    >>> e.isoformat()
    '2026-07-13T00:00:00+00:00'
    """
    if batch_no < 1:
        raise ValueError(f"batch_no must be >= 1, got {batch_no}")
    start_date = HISTORY_START_DATE + timedelta(days=(batch_no - 1) * _BATCH_DAYS)
    end_date = start_date + timedelta(days=_BATCH_DAYS)
    return (
        datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc),
    )


def get_current_batch_no() -> int:
    """返回当前时间所属批次号."""
    return get_batch_no(datetime.now(timezone.utc))


class BatchService:
    """历史资讯批次查询服务."""

    def list_batches(
        self,
        cursor: Optional[int] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """列出所有有数据的批次 (按 batch_no DESC, 不含当前批次).

        Parameters
        ----------
        cursor : int, optional
            上次返回的最小 batch_no; 首次传 None
        limit : int
            每页返回的批次数 (1-200)

        Returns
        -------
        dict with keys:
            - batches: list[{batch_no, start, end, item_count, favorite_count}]
            - total: int (所有批次的 item_count 总和, 仅本次返回页)
            - next_cursor: int or None
            - has_more: bool
        """
        limit = max(1, min(limit, 200))
        current_batch = get_current_batch_no()

        # 1) 找出所有有数据的批次 (用 ingested_at 范围 group by batch_no)
        # 用 CTE 算 batch_no 然后 group by, 避免 N+1
        # 注: 用 strftime('%s', ...) 拿 unix epoch, 整数除法; julianday 对带
        #     timezone 的 ISO 8601 字符串解析可能因 SQL 版本不同而不一致
        cte = """
            WITH batch_items AS (
                SELECT
                    CASE
                        WHEN COALESCE(ingested_at, published_at) < ? THEN 1
                        ELSE CAST(
                            (CAST(strftime('%s', COALESCE(ingested_at, published_at)) AS INTEGER)
                             - CAST(strftime('%s', ?) AS INTEGER)) / 86400 / 7 AS INTEGER) + 1
                    END AS batch_no
                FROM hotspots
                WHERE is_fallback = 0
            )
            SELECT batch_no, COUNT(*) AS item_count
            FROM batch_items
            WHERE batch_no < ?
        """
        params: list[Any] = [
            HISTORY_START_DATE.isoformat(),
            HISTORY_START_DATE.isoformat(),
            current_batch,
        ]
        if cursor is not None:
            cte += " AND batch_no < ?"
            params.append(cursor)
        cte += " GROUP BY batch_no ORDER BY batch_no DESC LIMIT ?"
        params.append(limit + 1)

        conn = get_connection()
        try:
            rows = conn.execute(cte, params).fetchall()
        except sqlite3.Error as e:
            logger.error(f"BatchService.list_batches query failed: {e}")
            return {
                "batches": [],
                "total": 0,
                "next_cursor": None,
                "has_more": False,
            }

        has_more = len(rows) > limit
        rows = rows[:limit]

        batches: list[dict[str, Any]] = []
        for r in rows:
            bn = int(r["batch_no"])
            start, end = get_batch_range(bn)
            fav_count = self._favorite_count_for_batch(bn, start, end)
            batches.append(
                {
                    "batch_no": bn,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "item_count": int(r["item_count"] or 0),
                    "favorite_count": fav_count,
                }
            )

        next_cursor = batches[-1]["batch_no"] if has_more and batches else None
        total = sum(b["item_count"] for b in batches)
        return {
            "batches": batches,
            "total": total,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def get_batch_items(
        self,
        batch_no: int,
        category: str = "all",
        keyword: str = "",
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """列出指定批次内的所有 hotspots.

        Returns
        -------
        dict with keys:
            - items: list[HotspotItem]
            - cursor: str or None
            - has_more: bool
        """
        from backend.repository.hotspot_repo import HotspotRepository

        if batch_no < 1:
            raise ValueError(f"batch_no must be >= 1, got {batch_no}")
        start, end = get_batch_range(batch_no)
        items, next_cursor = HotspotRepository().query_in_range(
            start=start,
            end=end,
            category=category,
            keyword=keyword,
            cursor=cursor or None,
            limit=limit,
        )
        # HotspotItem -> dict
        item_dicts = []
        for it in items:
            item_dicts.append(
                {
                    "id": it.id,
                    "title": it.title,
                    "summary": it.summary,
                    "source": it.source,
                    "url": it.url,
                    "category": it.category.value if it.category else None,
                    "published_at": it.published_at.isoformat() if it.published_at else None,
                    "ingested_at": it.ingested_at.isoformat() if it.ingested_at else None,
                    "score": it.score,
                    "quality_score": it.quality_score,
                    "quality_flags": it.quality_flags,
                    "bid_status": it.bid_status,
                }
            )
        return {
            "items": item_dicts,
            "cursor": next_cursor,
            "has_more": next_cursor is not None,
        }

    def get_batch_summary(self, batch_no: int) -> dict[str, Any]:
        """返回指定批次的统计摘要."""
        if batch_no < 1:
            raise ValueError(f"batch_no must be >= 1, got {batch_no}")
        start, end = get_batch_range(batch_no)
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(DISTINCT source) AS source_count
                FROM hotspots
                WHERE ingested_at >= ? AND ingested_at < ?
                  AND is_fallback = 0
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            cat_rows = conn.execute(
                """
                SELECT category, COUNT(*) AS n
                FROM hotspots
                WHERE ingested_at >= ? AND ingested_at < ?
                  AND is_fallback = 0
                GROUP BY category
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            src_rows = conn.execute(
                """
                SELECT source, COUNT(*) AS n
                FROM hotspots
                WHERE ingested_at >= ? AND ingested_at < ?
                  AND is_fallback = 0
                GROUP BY source
                ORDER BY n DESC
                LIMIT 5
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error(f"BatchService.get_batch_summary query failed: {e}")
            return {
                "batch_no": batch_no,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "total": 0,
                "source_count": 0,
                "category_breakdown": {},
                "top_sources": [],
            }

        return {
            "batch_no": batch_no,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total": int(row["total"] or 0),
            "source_count": int(row["source_count"] or 0),
            "category_breakdown": {r["category"]: int(r["n"]) for r in cat_rows},
            "top_sources": [{"source": r["source"], "count": int(r["n"])} for r in src_rows],
        }

    # ---- internal ---------------------------------------------------------
    def _favorite_count_for_batch(self, batch_no: int, start: datetime, end: datetime) -> int:
        """统计指定批次内被收藏的 item 数 (join favorites + hotspots)."""
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM favorites f
                JOIN hotspots h ON h.id = f.hotspot_id
                WHERE h.ingested_at >= ? AND h.ingested_at < ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            return int(row["n"] or 0)
        except sqlite3.Error as e:
            logger.warning(f"BatchService._favorite_count_for_batch failed: {e}")
            return 0


__all__ = [
    "BatchService",
    "HISTORY_START_DATE",
    "get_batch_no",
    "get_batch_range",
    "get_current_batch_no",
]
