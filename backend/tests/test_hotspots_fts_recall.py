"""v0.8.8 P2.5 M5: 关键词召回不降级 — ``hotspots_fts`` 必须同时索引 title 与 summary。

测试意图 (WHY):
- 方案 v2 §3 P2 曾提出「去掉 summary 索引换空间」——实测重建后仅再省 ≤3.4 MB,
  但 ``MATCH`` 调用方 (``search_service`` / ``hotspot_repo``) 都是裸 ``MATCH``
  不带列过滤 → 一旦 summary 移出索引, 只出现在摘要里的关键词会**静默**搜不到。
- 因此本用例把「summary 里的词能被搜到」钉成回归护栏: 若有人改动 migration
  124 的 ``hotspots_fts`` 列定义 (去 summary / 换 tokenizer), 本用例立刻失败。

用 ``temp_db`` (跑全套 migration) 而非手写 DDL: 断言的是**生产 schema**,
避免测试自带副本与真实定义漂移。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _insert(conn: sqlite3.Connection, *, hid: str, title: str, summary: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO hotspots (id, title, summary, source, url, category, "
        "published_at, fetched_at) VALUES (?,?,?,?,?,'ai',?,?)",
        (hid, title, summary, "test", f"https://example.com/{hid}", now, now),
    )
    conn.commit()
    return conn.execute("SELECT rowid FROM hotspots WHERE id = ?", (hid,)).fetchone()[0]


def _match_ids(conn: sqlite3.Connection, term: str) -> list[str]:
    rows = conn.execute(
        "SELECT h.id FROM hotspots_fts f JOIN hotspots h ON h.rowid = f.rowid "
        "WHERE hotspots_fts MATCH ? ORDER BY h.id",
        (term,),
    ).fetchall()
    return [r[0] for r in rows]


def test_summary_only_keyword_is_searchable(temp_db: Path) -> None:
    """只出现在 summary、title 里没有的关键词必须命中 (防 summary 索引被去掉)。"""
    conn = sqlite3.connect(str(temp_db))
    try:
        _insert(
            conn, hid="h-summary-only",
            title="Model release notes",
            summary="Mitigations for prompt injection in agent pipelines",
        )
        _insert(
            conn, hid="h-control",
            title="Unrelated report",
            summary="Quarterly revenue figures",
        )
        assert _match_ids(conn, "injection") == ["h-summary-only"]
    finally:
        conn.close()


def test_title_keyword_still_searchable(temp_db: Path) -> None:
    """title 命中是既有能力, 防止修复召回时把另一列弄丢。"""
    conn = sqlite3.connect(str(temp_db))
    try:
        _insert(
            conn, hid="h-title-only",
            title="Zero trust architecture guide",
            summary="no relevant vocabulary here",
        )
        assert _match_ids(conn, "trust") == ["h-title-only"]
    finally:
        conn.close()