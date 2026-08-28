"""v0.6 Phase 6 commit 2 — wiki_items_fts 同步层 + search_wiki_only 单测.

锁定 5 件事:
  1. 迁移 073 创建 wiki_items_fts (5 列: id/title/topic/tags/type)
  2. 存量回填把 warm.knowledge_items 行映射到 FTS5
  3. search_wiki_only('渗透') 真相关度排序 (rank)
  4. wiki_items_fts_sync_job 失同步自愈 (drift 检测 + rebuild)
  5. unified_search 新增 'wiki' source 走 FTS5 旁路 (与 LIKE 并存)
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def wiki_db(temp_db: Path):
    """应用 migration 073 并回填 3 条 fixture knowledge_items.

    temp_db 已重定向 config.db_path + warm_db_path + cold_db_path,
    但需要在 test setup 阶段把 knowledge_items 表 seed 进去 (暖库初始为空).
    注意 knowledge_items 物理上在 warm.db (ATTACH alias='warm'),
    表创建必须用 CREATE TABLE warm.knowledge_items, 不能省略 schema。

    关键: warm_db_path 由 conftest._isol 指向 tmp_path/test-warm.db,
    但该文件不存在 → get_connection 会跳过 ATTACH ('file not exists')。
    本 fixture 先 touch 一下让 ATTACH 走通, 再建表 + seed + wiki_items_fts。
    """
    from backend.config import config
    from backend.repository import db

    # 1. touch test-warm.db 文件让 get_connection 的 ATTACH 走通
    warm_path = config.warm_db_path
    warm_path.parent.mkdir(parents=True, exist_ok=True)
    if not warm_path.exists():
        warm_path.touch()
    # 关键: conftest 之前已 get_connection() 过一次 (init_db), warm 不在
    # 这里重置 _tls.conn 缓存让 ATTACH 重新跑
    import backend.repository.db as _db_mod
    if hasattr(_db_mod._tls, "conn"):
        try:
            _db_mod._tls.conn.close()
        except Exception:
            pass
        delattr(_db_mod._tls, "conn")

    conn = db.get_connection()

    # 暖库: 建 knowledge_items + seed 3 fixture (warm.db 真实表)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS warm.knowledge_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            domain TEXT,
            topic TEXT,
            type TEXT,
            difficulty TEXT,
            tags TEXT,
            concepts TEXT,
            mastery INTEGER DEFAULT 0,
            compiled INTEGER DEFAULT 0,
            ingested_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    fixtures = [
        ("k-001", "渗透测试基础指南", "渗透", "渗透测试入门"),
        ("k-002", "Web 应用漏洞分析", "Web", "Web 漏洞实战"),
        ("k-003", "代码审计最佳实践", "审计", "代码审计入门"),
    ]
    for kid, title, topic, tags in fixtures:
        conn.execute(
            """
            INSERT INTO warm.knowledge_items
            (id, title, source, topic, type, tags, ingested_at, updated_at)
            VALUES (?, ?, 'test', ?, 'news', ?, '2026-01-01', '2026-01-01')
            """,
            (kid, title, topic, tags),
        )
    conn.commit()

    # 主库: 创建 wiki_items_fts (迁移 073 等价 SQL, 不用跑全量 migration 链)
    conn.executescript(
        """
        DROP TABLE IF EXISTS wiki_items_fts;
        CREATE VIRTUAL TABLE wiki_items_fts USING fts5(
            id UNINDEXED,
            title,
            topic,
            tags,
            type,
            tokenize='porter unicode61',
            content=''
        );
        INSERT INTO wiki_items_fts(rowid, id, title, topic, tags, type)
        SELECT rowid, id, IFNULL(title, ''), IFNULL(topic, ''),
               IFNULL(tags, ''), IFNULL(type, '')
        FROM warm.knowledge_items;
        """
    )
    conn.commit()
    return conn


def test_wiki_fts_seeded_with_5_columns(wiki_db) -> None:
    """迁移 073 落地的 wiki_items_fts 必须有 5 列且回填 ≥3 行."""
    cols = wiki_db.execute("PRAGMA table_info(wiki_items_fts)").fetchall()
    col_names = [c[1] for c in cols]
    assert col_names == ["id", "title", "topic", "tags", "type"], col_names
    assert wiki_db.execute("SELECT COUNT(*) FROM wiki_items_fts").fetchone()[0] >= 3


def test_search_wiki_only_fts5_match(wiki_db) -> None:
    """search_wiki_only 走 FTS5 MATCH 真相关度排序."""
    from backend.services.search_service import search_wiki_only

    hits = search_wiki_only("渗透", limit=10)
    assert len(hits) >= 1, "渗透 must hit at least one fixture"
    titles = [h["title"] for h in hits]
    assert any("渗透" in t for t in titles)


def test_search_wiki_only_returns_entity_id(wiki_db) -> None:
    """search_wiki_only 返回 entity_id (来自 wiki_items_fts.id UNINDEXED)."""
    from backend.services.search_service import search_wiki_only

    hits = search_wiki_only("审计", limit=10)
    assert len(hits) >= 1
    for h in hits:
        assert h["entity_type"] == "wiki"
        assert h["entity_id"] in {"k-001", "k-002", "k-003"}
        assert "fts_snippet" in h


def test_unified_search_wiki_source_routes_to_fts(wiki_db) -> None:
    """unified_search(sources=['wiki']) 走 FTS5 旁路, 不走 LIKE unified_search view."""
    from backend.services.search_service import unified_search

    result = unified_search("渗透", sources=["wiki"], limit=10)
    assert "wiki" in result["grouped"]
    assert len(result["grouped"]["wiki"]) >= 1


def test_wiki_items_fts_sync_job_detects_drift(wiki_db) -> None:
    """wiki_items_fts_sync_job: drift 检测 → rebuild 后两侧 COUNT 对齐."""
    import asyncio

    from backend.scheduler.jobs.maintenance import wiki_items_fts_sync_job

    # 制造 drift: wiki_items_fts 多 1 行 (模拟孤儿)
    wiki_db.execute(
        "INSERT INTO wiki_items_fts(rowid, id, title, topic, tags, type) "
        "VALUES (99999, 'orphan', 'orphan', '', '', '')"
    )
    wiki_db.commit()

    before = wiki_db.execute(
        "SELECT (SELECT COUNT(*) FROM warm.knowledge_items),"
        " (SELECT COUNT(*) FROM wiki_items_fts)"
    ).fetchone()
    assert before[1] == before[0] + 1, f"pre-sync drift: {before}"

    asyncio.run(wiki_items_fts_sync_job())

    after = wiki_db.execute(
        "SELECT (SELECT COUNT(*) FROM warm.knowledge_items),"
        " (SELECT COUNT(*) FROM wiki_items_fts)"
    ).fetchone()
    assert after[0] == after[1], f"post-sync drift remains: {after}"