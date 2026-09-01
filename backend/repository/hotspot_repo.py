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
from datetime import datetime, timezone

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

# v0.5 M1-Task1: 与迁移 064 对齐 — quality_flags 命中任一 → 列表隐藏(is_hidden=1)。
# 与离线回填脚本 backend/scripts/backfill_ingested_at.py 口径一致。
_HIDDEN_FLAGS: frozenset[str] = frozenset(
    {
        "historical_bid",
        "historical_published",
        "no_published_at",
        "landing_page_unresolvable",
    }
)


def _derive_is_hidden(quality_flags: list[str]) -> int:
    """由 quality_flags 推导 is_hidden(1=隐藏)。与迁移 064 / 回填脚本口径一致。"""
    return 1 if any(f in _HIDDEN_FLAGS for f in (quality_flags or [])) else 0


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
            region=row["region"] if "region" in row.keys() else None,
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
            # v0.5: is_hidden 由 quality_flags 推导(μ工艺与迁移 064 一致)
            _derive_is_hidden(item.quality_flags),
            # Phase 8 标讯地区 (migration 023) — 此前 INSERT 漏列导致 region 恒 NULL,
            # 地区筛选 / list_regions() 整条链静默失效
            getattr(item, "region", None),
        )

    @staticmethod
    def _make_cursor(item: HotspotItem) -> str:
        """Build a pagination cursor from a :class:`HotspotItem`.

        Phase 15: cursor 基于 ingested_at(列表排序字段),而非 published_at。
        v0.5 M1-Task1: 精度提升到微秒浮点, 使 cursor 边界能走 ingested_at
        ISO 字符串直接比较(索引可用)。旧整数秒格式仍可被 _parse_cursor
        解析(float() 兼容)。
        """
        ts = item.ingested_at or item.fetched_at
        return f"{ts.timestamp():.6f}_{item.id}"

    @staticmethod
    def _parse_cursor(cursor: str) -> tuple[float, str]:
        """Parse ``<unix_ts>_<id>`` cursor. Raises ``InvalidParamException``
        on malformed input — but we translate to ``InternalException`` here
        because cursors are an internal contract, not user input.

        v0.5: ts 段接受旧整数秒与新微秒浮点(float() 兼容两者)。
        """
        try:
            ts_str, _, cid = cursor.partition("_")
            return float(ts_str), cid
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
                ingested_at, bid_status, is_hidden, region
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                -- P2-7: 不再刷新 ingested_at — 保留首次入库时间,
                -- 重采同 ID 条目不再"浮顶"并虚增"新增 X 条"计数。
                bid_status       = excluded.bid_status,
                -- v0.5: 最新 quality_flags 决定最新隐藏状态
                is_hidden        = excluded.is_hidden,
                region           = excluded.region
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
        category: Category | None,
        time_range: TimeRange = TimeRange.D7,
        keyword: str = "",
        cursor: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        region: str | None = None,  # Phase 8: 标讯地区筛选
        source: str | None = None,  # v1.9.1: 来源筛选 (头条/条目行来源可点击)
    ) -> tuple[list[HotspotItem], str | None]:
        """List hotspots with category / time / keyword / cursor / region
        / source filters.

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
        # v0.5 M1-Task1: COALESCE + NOT LIKE 逐行过滤 → ingested_at 直接比较
        # + is_hidden 列(迁移 064 + 离线回填脚本维护), 使 idx_list_visible
        # 部分索引被利用, 消除 TEMP B-TREE。回填前置条件: ingested_at 非 NULL
        # (backfill_ingested_at.py 补齐) — 迁移注释明确禁止启动时全量回填。
        where_clauses: list[str] = [
            "ingested_at >= ?",
            "is_hidden = 0",
            "(url_check_status IS NULL OR url_check_status NOT IN ('mismatch', 'unreachable'))",
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

        if region:
            where_clauses.append("region = ?")
            params.append(region)

        if source:
            where_clauses.append("source = ?")
            params.append(source)

        kw_sql, kw_params = self._keyword_condition(keyword)
        if kw_sql:
            where_clauses.append(kw_sql)
            params.extend(kw_params)

        if cursor:
            cursor_ts, cursor_id = self._parse_cursor(cursor)
            # v0.5 M1-Task1: 把 unix 秒(微秒浮点) 转回 ISO 字符串,
            # 与 ingested_at 列(ISO) 直接字符串比较 — 不再 strftime 转换
            # 到整数秒(会使索引失效 + 丢弃微秒, cursor 精度丢失)。
            # 旧整数秒 cursor 同样可用(float 解析 → fromtimestamp 补零)。
            cursor_iso = datetime.fromtimestamp(
                cursor_ts, timezone.utc
            ).isoformat()
            where_clauses.append(
                "(ingested_at < ? OR (ingested_at = ? AND id < ?))"
            )
            params.extend([cursor_iso, cursor_iso, cursor_id])

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
            "ORDER BY ingested_at DESC, rowid DESC "
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
        category: str | None = None,
        keyword: str = "",
        cursor: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> tuple[list[HotspotItem], str | None]:
        """Phase 28: 按 ingest_at 范围查询(用于历史资讯批次内查询).

        与 query() 区别: time_range 用绝对 [start, end) 区间,而不是相对 now-7d.

        Returns ``(items, next_cursor)``.
        """
        effective_limit = max(1, min(limit, _MAX_LIMIT))
        conn = get_connection()

        where_clauses: list[str] = [
            "ingested_at >= ?",
            "ingested_at < ?",
            "is_hidden = 0",
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
            cursor_iso = datetime.fromtimestamp(
                cursor_ts, timezone.utc
            ).isoformat()
            where_clauses.append(
                "(ingested_at < ? OR (ingested_at = ? AND id < ?))"
            )
            params.extend([cursor_iso, cursor_iso, cursor_id])

        sql = (
            "SELECT id, title, summary, source, url, category, "
            "published_at, score, fetched_at, is_fallback, quality_score, "
            "quality_flags, quality_checked_at, url_check_status, ingested_at, "
            "bid_status "
            "FROM hotspots "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY ingested_at DESC, rowid DESC "
            "LIMIT ?"
        )
        params.append(effective_limit + 1)

        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error(
                "query_in_range failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"query_in_range failed: {e}") from e
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
            "AND h.is_hidden = 0 "
            "ORDER BY h.ingested_at DESC "
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

    def get_by_id(self, id: str) -> HotspotItem | None:
        """Fetch a single hotspot by primary key, or ``None`` if absent."""
        conn = get_connection()
        sql = (
            "SELECT id, title, summary, source, url, category, "
            "published_at, score, fetched_at, is_fallback, quality_score, "
            "quality_flags, quality_checked_at, url_check_status, ingested_at, "
            "bid_status, region "
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
        category: str | None = None,
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
            "is_hidden = 0",
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

    def _keyword_condition(self, keyword: str) -> tuple[str, list[str]]:
        """关键词检索的 SQL 片段 + 绑定参数 (供 query 与计数共用同一口径)。

        ``hotspots_fts`` 用 ``tokenize='unicode61'``, 它按空白/标点切 token, 不切
        中日韩连写 —— 实测 "漏洞" LIKE 140 / MATCH 10, "勒索" LIKE 18 / MATCH 0。
        故含非 ASCII 的关键词走 LIKE (与 search_service.py 当年放弃 FTS5 改用
        LIKE 的取舍一致); 纯 ASCII 仍走 FTS5 索引 (CVE 召回 40/44 且更快)。
        两个分支匹配范围一致, 都只覆盖 title + summary —— FTS 索引里没有 source。
        """
        if not keyword:
            return "", []
        if any(ord(ch) > 127 for ch in keyword):
            escaped = (
                keyword.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pat = f"%{escaped}%"
            return "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')", [pat, pat]
        safe = keyword.replace('"', '""')
        return (
            "id IN ("
            "SELECT h2.id FROM hotspots h2 "
            "JOIN hotspots_fts f2 ON f2.rowid = h2.rowid "
            "WHERE hotspots_fts MATCH ?"
            ")",
            [f'"{safe}"'],
        )

    def count_unique_urls_in_range(
        self,
        time_range: TimeRange,
        category: str | None = None,
        keyword: str = "",
    ) -> int:
        """Phase 42 修复: 统计时间窗口内的 **去重 url 数** (供 list 翻页 total)。

        与 :meth:`count_in_range` 区别:
        - ``count_in_range`` 按行数 (同 url 多次重复入库会算多次)
        - 本方法按 ``COUNT(DISTINCT url)`` — 与 ``HotspotService._dedupe_by_url``
          后的 ``items`` 口径一致, 避免前端 "X / Y" 出现 X 远大于 Y 的显示问题
          (用户反馈: "已显示 83 / 841 条, 已是最后一页" 但 841 实际包含大量
          重复 url, 真正唯一 url 只有 83 条)

        ``keyword`` 必须与 :meth:`query` 同口径, 否则搜索时 "X / Y" 的分母会
        退回全窗口总数。
        """
        if not isinstance(time_range, TimeRange):
            raise InternalException(f"time_range must be TimeRange, got {type(time_range).__name__}")
        conn = get_connection()
        start_iso = time_range.start_datetime().isoformat()
        where_clauses = [
            "ingested_at >= ?",
            "is_hidden = 0",
        ]
        params: list = [start_iso]
        if category and category != "all":
            if category == "ai":
                where_clauses.append("category IN ('ai', 'tech')")
            else:
                where_clauses.append("category = ?")
                params.append(category)
        kw_sql, kw_params = self._keyword_condition(keyword)
        if kw_sql:
            where_clauses.append(kw_sql)
            params.extend(kw_params)
        sql = (
            f"SELECT COUNT(DISTINCT url) AS n FROM hotspots "
            f"WHERE {' AND '.join(where_clauses)}"
        )
        try:
            row = conn.execute(sql, params).fetchone()
        except Exception as e:
            logger.error(
                "count_unique_urls_in_range failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"count_unique_urls_in_range failed: {e}") from e
        return int(row["n"])

    def list_recent_urls_by_source(
        self,
        source_name: str,
        since_iso: str,
    ) -> set[str]:
        """返回 ``source`` 列匹配 ``source_name`` 且 ``ingested_at >= since_iso`` 的去重 URL 集合。

        2026-08-04 新增: 公众号 wechat renderer 抓取前预查询, 跳过 DB 中已
        存在的 URL, 避免每次 scheduler tick 都重复 fetch + parse + quality
        pipeline 同一批老文章。

        Args:
            source_name: 源名称(与 ``hotspots.source`` 列严格匹配)。
            since_iso: ISO 8601 起点字符串(由调用方计算, 通常为
                ``(now - max_age_days).isoformat()``)。

        Returns:
            去重 URL 集合(空集合当 source_name 为空)。
        """
        if not source_name or not since_iso:
            return set()
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT DISTINCT url FROM hotspots "
                "WHERE source = ? AND ingested_at >= ?",
                (source_name, since_iso),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error(
                "list_recent_urls_by_source failed",
                extra={"trace_id": "", "source": source_name, "error": str(e)},
            )
            raise InternalException(
                f"list_recent_urls_by_source failed: {e}"
            ) from e
        return {str(r["url"]) for r in rows if r["url"]}

    def count_by_category(
        self,
        time_range: TimeRange | None = None,
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
        base_where = (
            "(url_check_status IS NULL OR url_check_status NOT IN ('mismatch', 'unreachable')) "
            "AND is_hidden = 0"
        )
        sql = (
            "SELECT CASE WHEN category = 'tech' THEN 'ai' ELSE category END AS cat, "
            "COUNT(*) AS n FROM hotspots"
        )
        params: tuple = ()
        if time_range is not None:
            # 始终用 ingested_at (而非 published_at) 做窗口过滤, 与
            # ``query()`` 内部一致 (HomeGrid 是按 ingested_at 排序的)
            start_iso = time_range.start_datetime().isoformat()
            sql += f" WHERE ingested_at >= ? AND {base_where}"
            params = (start_iso,)
        else:
            sql += f" WHERE {base_where}"
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

    def list_regions(self) -> list[str]:
        """列出所有标讯地区（仅 category=bid 且 region 非空）。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT region FROM hotspots WHERE category = 'bid' AND region IS NOT NULL AND region != '' ORDER BY region ASC"
        ).fetchall()
        return [str(r["region"]) for r in rows]

    def list_by_tags(
        self,
        tag_ids: list[str],
        mode: str = "or",
        limit: int = 50,
    ) -> list[HotspotItem]:
        """v1.7 Phase 1: 按 tag_id 列表筛选热点 (AND/OR)。

        - ``mode='and'``: 热点须拥有 ``tag_ids`` 中的**全部**标签
          (HAVING COUNT(DISTINCT tag_id) = len(tag_ids))。
        - ``mode='or'``: 热点拥有 ``tag_ids`` 中**任一**标签即可。
        - 空tag_ids → 返回空列表 (不报错)。
        - 结果按 ingested_at DESC 排序, 与列表页口径一致。
        """
        if not tag_ids:
            return []
        limit = min(max(1, limit), _MAX_LIMIT)
        placeholders = ",".join("?" * len(tag_ids))
        conn = get_connection()
        if mode == "and":
            sql = f"""
                SELECT h.id, h.title, h.summary, h.source, h.url, h.category,
                       h.published_at, h.score, h.fetched_at, h.is_fallback,
                       h.quality_score, h.quality_flags, h.quality_checked_at,
                       h.url_check_status, h.ingested_at, h.bid_status
                FROM hotspots h
                JOIN hotspot_tags ht ON h.id = ht.hotspot_id
                WHERE ht.tag_id IN ({placeholders})
                GROUP BY h.id
                HAVING COUNT(DISTINCT ht.tag_id) = ?
                ORDER BY h.ingested_at DESC
                LIMIT ?
            """
            params = [*tag_ids, len(tag_ids), limit]
        else:
            sql = f"""
                SELECT DISTINCT h.id, h.title, h.summary, h.source, h.url, h.category,
                       h.published_at, h.score, h.fetched_at, h.is_fallback,
                       h.quality_score, h.quality_flags, h.quality_checked_at,
                       h.url_check_status, h.ingested_at, h.bid_status
                FROM hotspots h
                JOIN hotspot_tags ht ON h.id = ht.hotspot_id
                WHERE ht.tag_id IN ({placeholders})
                ORDER BY h.ingested_at DESC
                LIMIT ?
            """
            params = [*tag_ids, limit]
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_item(r) for r in rows]


__all__ = ["HotspotRepository"]
