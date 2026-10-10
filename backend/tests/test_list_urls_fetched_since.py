"""list_urls_fetched_since — F4 预去重窗口根治 (2026-09-27 校对室刷屏)。

背景: quality_hook F4 原走 query_in_range(limit=2000), 被 repo 层
_MAX_LIMIT=200 钳制 → known_urls 只覆盖最近几小时 → RSS 旧文每轮漏过
预去重 → duplicate/strict 拒 → quality_rejection_log 每轮刷上千条
(实测 24h 1595 条)。

契约:
- 返回窗口内全源去重 URL 集合 (fetched_at 维度, 不受 _MAX_LIMIT 钳制)
- since_iso 为空 → 空集合 (调用方退化为不去重)
- 窗口外 URL 不返回
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.repository.db import get_connection
from backend.repository.hotspot_repo import _MAX_LIMIT, HotspotRepository


def _insert(url: str, fetched_at_iso: str, title: str = "t") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO hotspots (id, title, url, source, category,"
        " published_at, quality_score, fetched_at, ingested_at)"
        " VALUES (?, ?, ?, 'src', 'security', ?, 80, ?, ?)",
        (
            f"id_{abs(hash(url))}", title, url,
            fetched_at_iso,  # published_at NOT NULL 无默认
            fetched_at_iso, fetched_at_iso,
        ),
    )


@pytest.fixture
def repo(temp_db):
    return HotspotRepository()


def test_returns_urls_within_window(repo):
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=30)).isoformat()
    _insert("https://a.com/1", fresh)
    _insert("https://a.com/2", old)
    since = (now - timedelta(days=7)).isoformat()
    result = repo.list_urls_fetched_since(since)
    assert "https://a.com/1" in result
    assert "https://a.com/2" not in result  # 窗口外不返回


def test_dedups_urls(repo):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=1)).isoformat()
    _insert("https://b.com/x", ts, "t1")
    _insert("https://b.com/x", ts, "t2")  # 同 URL 重复入库
    result = repo.list_urls_fetched_since(
        (now - timedelta(days=7)).isoformat()
    )
    assert result == {"https://b.com/x"}  # set 语义: 去重后唯一


def test_no_row_limit_beats_max_limit(repo):
    """核心契约: 结果集不受 _MAX_LIMIT(200) 钳制 — 这是本次根治点。"""
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=1)).isoformat()
    conn = get_connection()
    n = _MAX_LIMIT + 50  # 250 行 > 200
    for i in range(n):
        conn.execute(
            "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
            " category, published_at, quality_score, fetched_at, ingested_at)"
            " VALUES (?, ?, ?, 'src', 'security', ?, 80, ?, ?)",
            (f"bulk_{i}", f"t{i}", f"https://bulk.com/{i}", ts, ts, ts),
        )
    result = repo.list_urls_fetched_since(
        (now - timedelta(days=7)).isoformat()
    )
    bulk = {u for u in result if u.startswith("https://bulk.com/")}
    assert len(bulk) == n  # 全量返回, 未被钳制到 200


def test_empty_since_returns_empty_set(repo):
    assert repo.list_urls_fetched_since("") == set()
