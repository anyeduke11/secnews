"""Repository for the ``hotspots`` table + FTS5 mirror.

Design notes
------------
- All datetime columns are stored as ISO-8601 UTC strings; we serialize
  with ``datetime.isoformat()`` and parse with ``datetime.fromisoformat()``
  so tz information round-trips cleanly.
- ``HttpUrl`` (pydantic v2 ``Url``) → ``str(item.url)`` on write,
  ``HttpUrl(value)`` on read. Same field name in DB (``url TEXT``).
- ``Category`` enum → ``item.category.value`` on write, ``Category(value)``
  on read. The DB column has a CHECK constraint matching the enum values.
- Booleans: SQLite has no native boolean — use INTEGER 0/1 and convert
  with ``1 if item.is_fallback else 0`` / ``bool(row["is_fallback"])``.
- ``quality_flags`` is a JSON array — stored as TEXT, parsed with
  ``json.loads``.
- FTS5: ``hotspots_fts`` is kept in sync with ``hotspots`` via the
  triggers defined in ``001_init.sql``, so the repository only needs
  to write to the main table.
- Transactions are explicit (``conn.execute("BEGIN")`` /
  ``"COMMIT"`` / ``"ROLLBACK"``) because the connection is opened in
  autocommit mode (``isolation_level=None``).
- Every failure is logged with ``logger.error(...)`` (no ``print``)
  and re-raised as ``InternalException`` so the API layer can return
  a uniform error envelope.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from pydantic import HttpUrl

from backend.domain.enums import Category, TimeRange
from backend.domain.models import HotspotItem
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Cap the requested limit at 200 to avoid pathological full-table scans.
_MAX_LIMIT = 200
_DEFAULT_LIMIT = 100
_SEARCH_DEFAULT_LIMIT = 50

# All categories are always present in count_by_category() results, even
# when their count is zero (frontend depends on a stable key set).
_ALL_CATEGORIES: tuple[Category, ...] = tuple(Category)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class HotspotRepository:
    """All reads/writes against the ``hotspots`` table.

    The instance is stateless — every method pulls the calling thread's
    connection via :func:`backend.repository.db.get_connection`. You can
    therefore share a single ``HotspotRepository()`` across threads.
    """

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> HotspotItem:
        """Deserialize a SQLite ``Row`` into a :class:`HotspotItem`.

        Handles the cross-type conversions listed in the module docstring:
        category string → enum, is_fallback int → bool, quality_flags
        JSON string → list, url string → HttpUrl, datetime string → tz-aware
        datetime.
        """
        quality_flags_raw = row["quality_flags"]
        if quality_flags_raw is None or quality_flags_raw == "":
            flags: list[str] = []
        else:
            flags = json.loads(quality_flags_raw)

        quality_checked_at = row["quality_checked_at"]
        if quality_checked_at is not None:
            quality_checked_at = datetime.fromisoformat(quality_checked_at)

        # Phase 15: ingested_at 可能为 NULL(理论上迁移后不会,防御性处理)
        ingested_at_raw = row["ingested_at"] if "ingested_at" in row.keys() else None
        ingested_at = (
            datetime.fromisoformat(ingested_at_raw) if ingested_at_raw else None
        )

        return HotspotItem(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            source=row["source"],
            url=HttpUrl(row["url"]),
            category=Category(row["category"]),
            published_at=datetime.fromisoformat(row["published_at"]),
            score=row["score"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            is_fallback=bool(row["is_fallback"]),
            quality_score=row["quality_score"],
            quality_flags=flags,
            quality_checked_at=quality_checked_at,
            url_check_status=row["url_check_status"],
            ingested_at=ingested_at,
            bid_status=row["bid_status"] if "bid_status" in row.keys() else None,
        )

    @staticmethod
    def _item_to_params(item: HotspotItem) -> tuple:
        """Serialize a :class:`HotspotItem` to a tuple of SQLite parameters."""
        return (
            item.id,
            item.title,
            item.summary,
            item.source,
            str(item.url),
            item.category.value,
            item.published_at.isoformat(),
            item.score,
            item.fetched_at.isoformat(),
            1 if item.is_fallback else 0,
            item.quality_score,
            json.dumps(item.quality_flags),
            item.quality_checked_at.isoformat() if item.quality_checked_at else None,
            item.url_check_status,
            # Phase 15: ingested_at 缺失时回退到 fetched_at(防御性,正常路径
            # collector 会显式设置 ingested_at = now())
            (item.ingested_at or item.fetched_at).isoformat(),
            # Phase 20: 标讯状态
            item.bid_status,
        )

    @staticmethod
    def _make_cursor(item: HotspotItem) -> str:
        """Build a pagination cursor from a :class:`HotspotItem`.

        Phase 15: cursor 基于 ingested_at(列表排序字段),而非 published_at。
        """
        ts = item.ingested_at or item.fetched_at
        return f"{int(ts.timestamp())}_{item.id}"

    @staticmethod
    def _parse_cursor(cursor: str) -> tuple[int, str]:
        """Parse ``<unix_ts>_<id>`` cursor. Raises ``InvalidParamException``
        on malformed input — but we translate to ``InternalException`` here
        because cursors are an internal contract, not user input.
        """
        try:
            ts_str, _, cid = cursor.partition("_")
            return int(ts_str), cid
        except (ValueError, AttributeError) as e:
            raise InternalException(f"invalid cursor: {cursor!r}") from e

    # ---- writes -----------------------------------------------------------
    def upsert_many(self, items: list[HotspotItem]) -> int:
        """Insert or update many hotspots in a single transaction.

        On conflict (``id`` already exists) all mutable columns are
        overwritten by the new values — this matches the upstream
        collector's "latest-wins" semantics.

        Returns the sum of affected row counts (inserts + updates).
        On any error the transaction is rolled back and an
        :class:`InternalException` is raised.
        """
        if not items:
            return 0

        conn = get_connection()
        sql = """
            INSERT INTO hotspots (
                id, title, summary, source, url, category,
                published_at, score, fetched_at, is_fallback,
                quality_score, quality_flags, quality_checked_at, url_check_status,
                ingested_at, bid_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title            = excluded.title,
                summary          = excluded.summary,
                source           = excluded.source,
                url              = excluded.url,
                category         = excluded.category,
                published_at     = excluded.published_at,
                score            = excluded.score,
                fetched_at       = excluded.fetched_at,
                is_fallback      = excluded.is_fallback,
                quality_score    = excluded.quality_score,
                quality_flags    = excluded.quality_flags,
                quality_checked_at = excluded.quality_checked_at,
                url_check_status = excluded.url_check_status,
                ingested_at      = excluded.ingested_at,
                bid_status       = excluded.bid_status
        """

        total_affected = 0
        try:
            conn.execute("BEGIN")
            for item in items:
                params = self._item_to_params(item)
                cur = conn.execute(sql, params)
                total_affected += cur.rowcount
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                # Best-effort rollback; surface the original error regardless.
                pass
            logger.error(
                "upsert_many failed",
                extra={"trace_id": "", "count": len(items), "error": str(e)},
            )
            raise InternalException(f"upsert_many failed: {e}") from e

        logger.info(
            "upsert_many ok",
            extra={"trace_id": "", "count": len(items), "affected": total_affected},
        )
        return total_affected

    # ---- reads ------------------------------------------------------------
    def query(
        self,
        category: Optional[Category],
        time_range: TimeRange = TimeRange.D7,
        keyword: str = "",
        cursor: Optional[str] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> tuple[list[HotspotItem], Optional[str]]:
        """List hotspots with category / time / keyword / cursor filters.

        Returns ``(items, next_cursor)``. ``next_cursor`` is ``None`` when
        the result is fully exhausted within the requested ``limit``.
        The caller is expected to pass the returned ``next_cursor`` back
        as the ``cursor`` argument on the next page.
        """
        effective_limit = max(1, min(limit, _MAX_LIMIT))
        # Phase 35: 改用 start_datetime() 替代 to_hours()
        # D7 起点从 now-7d 改为「本周周一 00:00 UTC」(calendar week 语义)。
        # 其余窗口保持相对 hours 语义。返回 tz-aware UTC datetime,这里
        # 用 .isoformat() 转字符串与 ingested_at 列直接比较。
        start_dt = time_range.start_datetime()
        conn = get_connection()

        # Phase 15: 列表过滤/排序/cursor 全部改用 ingested_at(录入时间),
        # 避免历史老旧资讯(published_at 是历史时间)出现在最新列表里。
        # COALESCE 兜底:迁移前的旧数据可能 ingested_at IS NULL,回退到 published_at。
        # Phase 20+: 排除带 historical_bid flag 的标讯(时效门禁拒绝,不应出现在列表里)。
        # Phase 47+: 排除带 historical_published / no_published_at flag 的资讯
        #   (RecencyGate 拒绝, 不应出现在列表里)。
        where_clauses: list[str] = [
            "COALESCE(ingested_at, published_at) >= ?",
            "(quality_flags IS NULL OR ("
            "  quality_flags NOT LIKE '%historical_bid%' AND"
            "  quality_flags NOT LIKE '%historical_published%' AND"
            "  quality_flags NOT LIKE '%no_published_at%'"
            "))",
        ]
        params: list = [start_dt.isoformat()]

        if category is not None:
            # Phase 35: ai 分类在 SQL 层合并 tech, 与 count_by_category() 对齐
            # (前端的「科技/AI」tab 计数 = ai + tech, 列表也要返回两者)
            if category == Category.AI:
                where_clauses.append("category IN ('ai', 'tech')")
            else:
                where_clauses.append("category = ?")
                params.append(category.value)

        if keyword:
            # Use FTS5 to pre-resolve the matching rowid set, then JOIN
            # by rowid. We use a subquery (rather than JOIN) so the
            # parameter list stays flat. The keyword is wrapped in
            # double quotes as a single phrase so FTS5 tokenises the
            # entire string literally.
            where_clauses.append(
                "id IN ("
                "SELECT h2.id FROM hotspots h2 "
                "JOIN hotspots_fts f2 ON f2.rowid = h2.rowid "
                "WHERE hotspots_fts MATCH ?"
                ")"
            )
            # Escape any embedded double quotes inside the keyword.
            safe_keyword = keyword.replace('"', '""')
            params.append(f'"{safe_keyword}"')

        if cursor:
            cursor_ts, cursor_id = self._parse_cursor(cursor)
            # The stored ingested_at is an ISO-8601 string
            # (e.g. "2026-07-04T11:10:20.624479+00:00") which is not
            # byte-comparable to datetime(?, 'unixepoch'). We convert
            # the column to a unix timestamp with strftime('%s', ...)
            # so the comparison is purely numeric.
            where_clauses.append(
                "(CAST(strftime('%s', COALESCE(ingested_at, published_at)) AS INTEGER) < ? "
                "OR (CAST(strftime('%s', COALESCE(ingested_at, published_at)) AS INTEGER) = ? AND id < ?))"
            )
            params.extend([cursor_ts, cursor_ts, cursor_id])

        # Phase 24 bug fix: tiebreaker 用 rowid DESC 替代 id DESC
        # 原因: id 是 TEXT 主键, 字典序 security_xxx > finance_xxx > ai_xxx
        #       (s > f > b > a), security 一次写 313 条同毫秒时把 ai/finance 挤掉
        # 解决: rowid 是 SQLite 隐式 integer 自增, 不受 TEXT 字典序影响
        sql = (
            "SELECT id, title, summary, source, url, category, "
            "published_at, score, fetched_at, is_fallback, quality_score, "
            "quality_flags, quality_checked_at, url_check_status, ingested_at, "
            "bid_status "
            "FROM hotspots "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY COALESCE(ingested_at, published_at) DESC, rowid DESC "
            "LIMIT ?"
        )
        params.append(effective_limit + 1)

        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error(
                "query failed",
                extra={
                    "trace_id": "",
                    "category": category.value if category else None,
                    "time_range": time_range.value,
                    "keyword": keyword,
                    "cursor": cursor,
                    "limit": effective_limit,
                    "error": str(e),
                },
            )
            raise InternalException(f"query failed: {e}") from e

        has_more = len(rows) > effective_limit
        page_rows = rows[:effective_limit]
        items = [self._row_to_item(r) for r in page_rows]
        next_cursor = self._make_cursor(items[-1]) if has_more and items else None
        return items, next_cursor

    def query_in_range(
        self,
        start: datetime,
        end: datetime,
        category: Optional[str] = None,
        keyword: str = "",
        cursor: Optional[str] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> tuple[list[HotspotItem], Optional[str]]:
        """Phase 28: 按 ingest_at 范围查询(用于历史资讯批次内查询).

        与 query() 区别: time_range 用绝对 [start, end) 区间,而不是相对 now-7d.

        Returns ``(items, next_cursor)``.
        """
        effective_limit = max(1, min(limit, _MAX_LIMIT))
        conn = get_connection()

        where_clauses: list[str] = [
            "COALESCE(ingested_at, published_at) >= ?",
            "COALESCE(ingested_at, published_at) < ?",
            "(quality_flags IS NULL OR ("
            "  quality_flags NOT LIKE '%historical_bid%' AND"
            "  quality_flags NOT LIKE '%historical_published%' AND"
            "  quality_flags NOT LIKE '%no_published_at%'"
            "))",
        ]
        params: list = [start.isoformat(), end.isoformat()]

        if category and category != "all":
            # Phase 35: ai 分类合并 tech, 与 query() / count_by_category() 一致
            if category == "ai":
                where_clauses.append("category IN ('ai', 'tech')")
            else:
                where_clauses.append("category = ?")
                params.append(category)

        if keyword:
            safe_keyword = keyword.replace('"', '""')
            where_clauses.append(
                "id IN ("
                "SELECT h2.id FROM hotspots h2 "
                "JOIN hotspots_fts f2 ON f2.rowid = h2.rowid "
                "WHERE hotspots_fts MATCH ?"
                ")"
            )
            params.append(f'"{safe_keyword}"')

        if cursor:
            cursor_ts, cursor_id = self._parse_cursor(cursor)
            where_clauses.append(
                "(CAST(strftime('%s', COALESCE(ingested_at, published_at)) AS INTEGER) < ? "
                "OR (CAST(strftime('%s', COALESCE(ingested_at, published_at)) AS INTEGER) = ? AND id < ?))"
            )
            params.extend([cursor_ts, cursor_ts, cursor_id])

        sql = (
            "SELECT id, title, summary, source, url, category, "
            "published_at, score, fetched_at, is_fallback, quality_score, "
            "quality_flags, quality_checked_at, url_check_status, ingested_at, "
            "bid_status "
            "FROM hotspots "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY COALESCE(ingested_at, published_at) DESC, rowid DESC "
            "LIMIT ?"
        )
        params.append(effective_limit + 1)

        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error(
                "query_in_range failed",
                extra={
                    "trace_id": "",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "category": category,
                    "keyword": keyword,
                    "error": str(e),
                },
            )
            raise InternalException(f"query_in_range failed: {e}") from e

        has_more = len(rows) > effective_limit
        page_rows = rows[:effective_limit]
        items = [self._row_to_item(r) for r in page_rows]
        next_cursor = self._make_cursor(items[-1]) if has_more and items else None
        return items, next_cursor

    def search(
        self,
        keyword: str,
        limit: int = _SEARCH_DEFAULT_LIMIT,
    ) -> list[HotspotItem]:
        """Pure FTS5 search across ``title`` and ``summary``.

        The keyword is wrapped in double quotes so FTS5 treats it as one
        literal phrase; any embedded double quotes are doubled per the
        FTS5 escaping rules. Newest matches come first.
        """
        if not keyword:
            return []

        effective_limit = max(1, min(limit, _MAX_LIMIT))
        conn = get_connection()

        safe_keyword = keyword.replace('"', '""')
        fts_query = f'"{safe_keyword}"'

        sql = (
            "SELECT h.id, h.title, h.summary, h.source, h.url, h.category, "
            "h.published_at, h.score, h.fetched_at, h.is_fallback, "
            "h.quality_score, h.quality_flags, h.quality_checked_at, "
            "h.url_check_status, h.ingested_at, h.bid_status "
            "FROM hotspots h "
            "JOIN hotspots_fts f ON f.rowid = h.rowid "
            "WHERE hotspots_fts MATCH ? "
            "AND (h.quality_flags IS NULL OR h.quality_flags NOT LIKE '%historical_bid%') "
            "ORDER BY COALESCE(h.ingested_at, h.published_at) DESC "
            "LIMIT ?"
        )
        try:
            rows = conn.execute(sql, (fts_query, effective_limit)).fetchall()
        except Exception as e:
            logger.error(
                "search failed",
                extra={"trace_id": "", "keyword": keyword, "limit": effective_limit, "error": str(e)},
            )
            raise InternalException(f"search failed: {e}") from e

        return [self._row_to_item(r) for r in rows]

    def get_by_id(self, id: str) -> Optional[HotspotItem]:
        """Fetch a single hotspot by primary key, or ``None`` if absent."""
        conn = get_connection()
        sql = (
            "SELECT id, title, summary, source, url, category, "
            "published_at, score, fetched_at, is_fallback, quality_score, "
            "quality_flags, quality_checked_at, url_check_status, ingested_at, "
            "bid_status "
            "FROM hotspots WHERE id = ?"
        )
        try:
            row = conn.execute(sql, (id,)).fetchone()
        except Exception as e:
            logger.error(
                "get_by_id failed",
                extra={"trace_id": "", "id": id, "error": str(e)},
            )
            raise InternalException(f"get_by_id failed: {e}") from e

        if row is None:
            return None
        return self._row_to_item(row)

    def count_in_range(
        self,
        time_range: TimeRange,
        category: Optional[str] = None,
    ) -> int:
        """Phase 39: 统计时间窗口内的真实总数 (不依赖 cursor, 不分页)。

        用于:
        - ``list_hotspots()`` 的 ``total`` 字段 (前端分页 "X / Y" 的分母)
        - 顶栏 / StatsPanel 之外的"当前窗口总数"展示

        与 ``query()`` 走相同的 ingested_at 窗口语义 (Phase 39 起 H24/D3 改为
        基于日历日, D7 仍为本周周一 00:00 UTC)。

        Phase 42 修复: 排除 ``historical_bid`` 标记行, 与 ``query()`` 口径一致。
        """
        if not isinstance(time_range, TimeRange):
            raise InternalException(f"time_range must be TimeRange, got {type(time_range).__name__}")
        conn = get_connection()
        start_iso = time_range.start_datetime().isoformat()
        where_clauses = [
            "ingested_at >= ?",
            "(quality_flags IS NULL OR ("
            "  quality_flags NOT LIKE '%historical_bid%' AND"
            "  quality_flags NOT LIKE '%historical_published%' AND"
            "  quality_flags NOT LIKE '%no_published_at%'"
            "))",
        ]
        params: list = [start_iso]
        if category and category != "all":
            if category == "ai":
                where_clauses.append("category IN ('ai', 'tech')")
            else:
                where_clauses.append("category = ?")
                params.append(category)
        sql = f"SELECT COUNT(*) AS n FROM hotspots WHERE {' AND '.join(where_clauses)}"
        try:
            row = conn.execute(sql, params).fetchone()
        except Exception as e:
            logger.error(
                "count_in_range failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"count_in_range failed: {e}") from e
        return int(row["n"])

    def count_unique_urls_in_range(
        self,
        time_range: TimeRange,
        category: Optional[str] = None,
    ) -> int:
        """Phase 42 修复: 统计时间窗口内的 **去重 url 数** (供 list 翻页 total)。

        与 :meth:`count_in_range` 区别:
        - ``count_in_range`` 按行数 (同 url 多次重复入库会算多次)
        - 本方法按 ``COUNT(DISTINCT url)`` — 与 ``HotspotService._dedupe_by_url``
          后的 ``items`` 口径一致, 避免前端 "X / Y" 出现 X 远大于 Y 的显示问题
          (用户反馈: "已显示 83 / 841 条, 已是最后一页" 但 841 实际包含大量
          重复 url, 真正唯一 url 只有 83 条)
        """
        if not isinstance(time_range, TimeRange):
            raise InternalException(f"time_range must be TimeRange, got {type(time_range).__name__}")
        conn = get_connection()
        start_iso = time_range.start_datetime().isoformat()
        where_clauses = [
            "ingested_at >= ?",
            "(quality_flags IS NULL OR ("
            "  quality_flags NOT LIKE '%historical_bid%' AND"
            "  quality_flags NOT LIKE '%historical_published%' AND"
            "  quality_flags NOT LIKE '%no_published_at%'"
            "))",
        ]
        params: list = [start_iso]
        if category and category != "all":
            if category == "ai":
                where_clauses.append("category IN ('ai', 'tech')")
            else:
                where_clauses.append("category = ?")
                params.append(category)
        sql = f"SELECT COUNT(DISTINCT url) AS n FROM hotspots WHERE {' AND '.join(where_clauses)}"
        try:
            row = conn.execute(sql, params).fetchone()
        except Exception as e:
            logger.error(
                "count_unique_urls_in_range failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"count_unique_urls_in_range failed: {e}") from e
        return int(row["n"])

    def count_by_category(
        self,
        time_range: Optional[TimeRange] = None,
    ) -> dict[str, int]:
        """Return ``{category_value: count}`` for every known category.

        Phase 35: ``tech`` 类别在 SQL 层合并到 ``ai``(CASE WHEN),
        输出 dict 中不再包含 ``tech`` key,与 UI「科技/AI」合并展示对齐。
        其余 6 个分类 (ai/security/finance/startup/bid/github) 始终存在,
        0 条时返回 0,前端可稳定渲染。

        Phase 39 新增 time_range 参数: 传入时按 ingested_at >= start 过滤,
        用于「StatsPanel / TopNav 总按本周口径」等场景 (与 Grid 的
        time_range 无关, 独立计算)。
        """
        conn = get_connection()
        sql = (
            "SELECT CASE WHEN category = 'tech' THEN 'ai' ELSE category END AS cat, "
            "COUNT(*) AS n FROM hotspots"
        )
        params: tuple = ()
        if time_range is not None:
            # 始终用 ingested_at (而非 published_at) 做窗口过滤, 与
            # ``query()`` 内部一致 (HomeGrid 是按 ingested_at 排序的)
            start_iso = time_range.start_datetime().isoformat()
            sql += " WHERE ingested_at >= ?"
            params = (start_iso,)
        sql += " GROUP BY cat"
        try:
            rows = conn.execute(sql, params).fetchall() if params else conn.execute(sql).fetchall()
        except Exception as e:
            logger.error(
                "count_by_category failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"count_by_category failed: {e}") from e

        # 默认 dict 不再包含 tech key (tech 已并入 ai)
        counts: dict[str, int] = {
            c.value: 0 for c in _ALL_CATEGORIES if c.value != "tech"
        }
        for row in rows:
            cat = str(row["cat"])
            counts[cat] = int(row["n"])
        return counts

    def count_by_category_db(self) -> dict[str, int]:
        """Alias for :meth:`count_by_category` — direct DB count, no caching.

        Phase 6 数据一致性校验 (``/api/stats.consistency_check``) 用
        此方法拉取「DB 真实条数」与缓存中的列表条数比对，检测
        缓存与 DB 之间的漂移 (drift)。
        """
        return self.count_by_category()

    def cleanup_older_than(self, days: int) -> int:
        """Delete hotspots whose ``published_at`` is older than ``days`` days.

        Returns the number of rows deleted. The default data-retention
        policy is "keep everything", so this is exposed for a manual
        maintenance CLI rather than for scheduled cleanup.
        """
        if days <= 0:
            raise InternalException(f"days must be positive, got {days}")

        conn = get_connection()
        sql = (
            "DELETE FROM hotspots "
            "WHERE published_at < datetime('now', ?)"
        )
        try:
            cur = conn.execute(sql, (f"-{days} days",))
            deleted = cur.rowcount
        except Exception as e:
            logger.error(
                "cleanup_older_than failed",
                extra={"trace_id": "", "days": days, "error": str(e)},
            )
            raise InternalException(f"cleanup_older_than failed: {e}") from e

        logger.info(
            "cleanup_older_than ok",
            extra={"trace_id": "", "days": days, "deleted": deleted},
        )
        return deleted


__all__ = ["HotspotRepository"]
