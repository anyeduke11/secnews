"""SecNews Dashboard — aggregated data service for the security dashboard.

Combines feed data, pipeline stats, and knowledge metrics into a
single service that the API layer can query.

v0.6.3 P0-1 卡顿根治: pipeline/knowledge 统计从"全量扫描 4149 个 wiki md"
切换到 DB 投影 (warm.knowledge_items.lifecycle / knowledge_concepts),
liveness 走 30s TTL 缓存 — 调用方 (api 层) 仍需以 asyncio.to_thread 调用。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.repository.db import get_connection
from backend.services.wiki_stats_service import (
    funnel_from_db,
    knowledge_stats_from_db,
    liveness_from_md_cached,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# v0.6.3 P3-1: feed 关键词搜索惰性 FTS 化 (卡顿审计 2026-08-30 裁决的落地)。
#
# 实测 4.5k 行 LIKE 全扫 <1ms, 无需索引; 数据到 5 万行起 (扫描 ~10ms/次 ×
# StatusBar/SSE 轮询频率) 才值得切换。本机制把"到 5 万行再 FTS 化"从备忘
# 变成自执行: 带关键词的请求经 TTL 缓存的行数探针发现达标后, 在 worker 线程
# 内一次性建 trigram FTS (contentless, 与 001_init.sql 的 hotspots_fts 同构)
# + 全量回填 + AFTER INSERT/DELETE/UPDATE 触发器保持同步, 之后关键词查询走
# MATCH。达标前行为与旧 LIKE 路径完全一致 (零语义漂移)。
#
# 选 trigram 而非既有 unicode61 的原因: unicode61 按空白/标点切 token 不切
# 中日韩连写 (hotspot_repo 实测 "勒索" MATCH 0 / LIKE 18), 而 trigram 的
# 引号短语查询就是子串匹配 — 与 LIKE %kw% 语义等价 (ASCII 大小写不敏感,
# CJK 逐字), ≥3 字符的查询词零召回损失; <3 字符 trigram 无 trigram 可用,
# 继续 LIKE (5 万行量级 ~10ms 且已脱事件循环, 可接受)。
# ----------------------------------------------------------------------------
_FEED_FTS_ROW_THRESHOLD = 50_000
_FEED_ROW_PROBE_TTL_S = 600.0
_feed_fts_state: dict[str, Any] = {"rows": 0, "checked_at": 0.0, "activated": False}
_feed_fts_lock = threading.Lock()

# 与 001_init.sql 的 hotspots_ai/ad/au 同构。注意 contentless 'delete' 必须
# 提供**旧值**才能移除词条 — 只给 rowid 不报错但词条残留 (P3-1 实证, SQLite
# 3.53), 会造成假阳性; 旧触发的这一缺陷由 migration 078 修复。
# 触发器创建放在回填之后: 回填期间无触发器, 不会双重索引导入脏数据。
_FEED_TRIGRAM_TRIGGER_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS hotspots_tft_ai AFTER INSERT ON hotspots BEGIN
        INSERT INTO hotspots_trigram_fts(rowid, title, summary)
            VALUES (new.rowid, new.title, IFNULL(new.summary, ''));
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS hotspots_tft_ad AFTER DELETE ON hotspots BEGIN
        INSERT INTO hotspots_trigram_fts(hotspots_trigram_fts, rowid, title, summary)
            VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, ''));
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS hotspots_tft_au AFTER UPDATE ON hotspots BEGIN
        INSERT INTO hotspots_trigram_fts(hotspots_trigram_fts, rowid, title, summary)
            VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, ''));
        INSERT INTO hotspots_trigram_fts(rowid, title, summary)
            VALUES (new.rowid, new.title, IFNULL(new.summary, ''));
    END
    """,
)


def _probe_feed_rows(db: Any) -> int:
    """TTL 缓存的 hotspots 行数探针 (仅在带关键词的 get_feed 里调用)。"""
    now = time.monotonic()
    state = _feed_fts_state
    if now - state["checked_at"] < _FEED_ROW_PROBE_TTL_S:
        return int(state["rows"])
    row = db.execute("SELECT COUNT(*) FROM hotspots").fetchone()
    rows = int(row[0]) if row else 0
    state["rows"] = rows
    state["checked_at"] = now
    return rows


def _ensure_feed_fts(db: Any) -> None:
    """行数达标后的一次性激活: 建 trigram FTS + 回填 + 同步触发器。

    幂等且崩溃可续: 触发器未齐即视为未完成, 回填以 ``rowid NOT IN``
    守卫, autocommit 下任一步中断后下次调用从断点继续。调用方必须处于
    worker 线程 (get_feed 经 to_thread 进入, 满足)。
    """
    with _feed_fts_lock:
        if _feed_fts_state["activated"]:
            return
        have_triggers = db.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='trigger' AND name IN "
            "('hotspots_tft_ai','hotspots_tft_ad','hotspots_tft_au')"
        ).fetchone()[0]
        if int(have_triggers) == 3:
            # 之前进程已激活过 (表与触发器持久在 DB), 仅恢复进程内标记。
            _feed_fts_state["activated"] = True
            return
        t0 = time.monotonic()
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS hotspots_trigram_fts "
            "USING fts5(title, summary, content='', tokenize='trigram')"
        )
        db.execute(
            "INSERT INTO hotspots_trigram_fts(rowid, title, summary) "
            "SELECT rowid, title, IFNULL(summary, '') FROM hotspots "
            "WHERE rowid NOT IN "
            "(SELECT rowid FROM hotspots_trigram_fts)"
        )
        for ddl in _FEED_TRIGRAM_TRIGGER_SQL:
            db.execute(ddl)
        _feed_fts_state["activated"] = True
        logger.info(
            "get_feed: hotspots crossed %d rows — trigram FTS activated "
            "(backfill+triggers took %.0fms), keyword search switched from LIKE",
            _FEED_FTS_ROW_THRESHOLD,
            (time.monotonic() - t0) * 1000,
        )


class SecNewsDashboard:
    """Aggregation service for the SecNews security dashboard."""

    def __init__(
        self,
        db: Any = None,
        wiki_fs: Any = None,
        pipeline: Any = None,
    ) -> None:
        self.db = db or get_connection()
        self.wiki_fs = wiki_fs
        self.pipeline = pipeline
        self._ledger = TokenLedger(self.db)

    def get_feed(self, category: str = "", keyword: str = "", limit: int = 30) -> dict:
        """Newspaper-style feed sorted by ingested_at DESC.

        Returns items from the hotspots table filtered by category/keyword.

        v0.6.3 P3-1: 带关键词时先经 TTL 探针看 hotspots 行数 — 达到
        ``_FEED_FTS_ROW_THRESHOLD`` (5 万) 惰性激活 trigram FTS 并把
        ≥3 字符查询词切到 MATCH (子串语义 = LIKE 等价, 见模块头注释);
        短查询词与未达标时维持 LIKE。响应以 ``search_engine`` /
        ``feed_rows`` 标注实际口径 (沿用 funnel_source 模式)。
        """
        conditions = []
        params: list = []

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category)

        search_engine = ""
        if keyword:
            feed_rows = _probe_feed_rows(self.db)
            if feed_rows >= _FEED_FTS_ROW_THRESHOLD:
                _ensure_feed_fts(self.db)
            if _feed_fts_state["activated"] and len(keyword) >= 3:
                phrase = '"' + keyword.replace('"', '""') + '"'
                conditions.append(
                    "rowid IN (SELECT rowid FROM hotspots_trigram_fts "
                    "WHERE hotspots_trigram_fts MATCH ?)"
                )
                params.append(phrase)
                search_engine = "fts5_trigram"
            else:
                conditions.append("(title LIKE ? OR summary LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])
                search_engine = "like"

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT id, title, url, source, category, summary, "
            f"published_at, ingested_at "
            f"FROM hotspots WHERE {where} "
            f"ORDER BY ingested_at DESC LIMIT ?"
        )
        params.append(limit)

        rows = self.db.execute(sql, params).fetchall()
        total_row = self.db.execute(
            f"SELECT COUNT(*) FROM hotspots WHERE {where}", params[:-1]
        ).fetchone()

        items = [dict(r) for r in rows]
        total = total_row[0] if total_row else 0

        result: dict[str, Any] = {"items": items, "total": total, "limit": limit}
        if keyword:
            result["search_engine"] = search_engine
            result["feed_rows"] = _feed_fts_state["rows"]
        return result

    def get_pipeline_stats(self) -> dict:
        """Pipeline observability: funnel + queue + dead-letter + alive + ledger.

        v0.6.3 P0-1: funnel 走 DB 投影 (真实管线口径); liveness 走 md + 30s
        TTL 缓存。调用方必须以 asyncio.to_thread 包本方法 (liveness 缓存
        miss 时仍有一次全量 md 扫描)。
        """
        funnel = funnel_from_db(self.db)

        queue_stats = {"pending": 0, "running": 0, "error": 0}
        errors: list[dict] = []
        if self.pipeline:
            queue_stats = self.pipeline.queue.stats()
            errors = self.pipeline.queue.errors(limit=10)

        ledger = self._ledger.summary()

        return {
            "funnel": funnel,
            "funnel_source": "db_knowledge_items_lifecycle",
            "funnel_note": "按 DB warm.knowledge_items.lifecycle 统计 (T1-T5 管线真实口径)",
            "queue": queue_stats,
            "errors": errors,
            "alive": liveness_from_md_cached(self.wiki_fs) if self.wiki_fs else {
                "total": 0, "alive": 0, "dead": 0, "unknown": 0,
            },
            "ledger": ledger,
        }

    def get_knowledge_stats(self) -> dict:
        """Knowledge base statistics: items, concepts, lifecycle distribution.

        v0.6.3 P0-1: 全量 md 扫描 (4149 read_text+YAML) → DB 投影单查询。
        """
        return knowledge_stats_from_db(self.db)

    def get_dashboard_stats(self) -> dict:
        """Dashboard overview: today's new items, pipeline health, top categories."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Today's new items.
        new_today = self.db.execute(
            "SELECT COUNT(*) FROM hotspots WHERE ingested_at LIKE ?",
            (f"{today}%",),
        ).fetchone()

        # Top categories by count.
        top_cats = self.db.execute(
            "SELECT category, COUNT(*) as cnt FROM hotspots "
            "GROUP BY category ORDER BY cnt DESC LIMIT 5"
        ).fetchall()

        # Pipeline health.
        pipeline_health = "unknown"
        if self.pipeline:
            stats = self.pipeline.queue.stats()
            total = sum(stats.values())
            if total == 0:
                pipeline_health = "idle"
            elif stats.get("error", 0) / max(total, 1) < 0.1:
                pipeline_health = "healthy"
            else:
                pipeline_health = "degraded"

        return {
            "new_today": new_today[0] if new_today else 0,
            "pipeline_health": pipeline_health,
            "top_categories": [dict(r) for r in top_cats],
            "date": today,
        }
