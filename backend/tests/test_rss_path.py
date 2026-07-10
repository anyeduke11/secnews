"""Phase 22: BaseCollector._fetch_rss RSS 抓取路径测试"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from backend.collectors.security_collector import SecurityCollector
from backend.domain.collection import SourceResult
from backend.domain.models import HotspotItem


def _make_feedparser_mock(entries: list[dict[str, Any]], status: int = 200, bozo: bool = False):
    """构造 feedparser 返回值 stub"""
    d: dict[str, Any] = {
        "status": status,
        "bozo": bozo,
        "entries": entries,
    }
    return d


def test_rss_path_in_security_collector_sources():
    """SecWiki 必须以 rss_url 形式出现在 security 源清单里。"""
    src_names = {s["name"]: s for s in SecurityCollector.sources}
    assert "SecWiki" in src_names
    assert src_names["SecWiki"].get("rss_url") == "https://www.sec-wiki.com/news/rss"
    # FreeBuf 也必须走 RSS
    assert "FreeBuf" in src_names
    assert src_names["FreeBuf"].get("rss_url") == "https://www.freebuf.com/feed"


def test_rss_path_http_error_returns_error_result():
    """RSS 源 HTTP 4xx/5xx → 返回 ([], SourceResult(rss_http_*))"""
    src = {
        "name": "MockRSS",
        "url": "https://example.com/",
        "rss_url": "https://example.com/feed",
    }
    collector = SecurityCollector()
    with patch("feedparser.parse", return_value=_make_feedparser_mock([], status=404, bozo=True)):
        items, sr = __import__("asyncio").run(collector._fetch_rss(src))
    assert items == []
    assert sr.error_msg.startswith("rss_http_404")
    assert sr.item_count == 0


def test_rss_path_empty_entries_returns_error():
    """RSS 源无 entry → 返回 rss_empty"""
    src = {
        "name": "MockEmpty",
        "url": "https://example.com/",
        "rss_url": "https://example.com/feed",
    }
    collector = SecurityCollector()
    with patch("feedparser.parse", return_value=_make_feedparser_mock([], status=200, bozo=False)):
        items, sr = __import__("asyncio").run(collector._fetch_rss(src))
    assert items == []
    assert sr.error_msg.startswith("rss_empty")


def test_rss_path_happy_path():
    """RSS 源正常返回 → 输出 HotspotItem 列表。"""
    src = {
        "name": "MockGood",
        "url": "https://example.com/",
        "rss_url": "https://example.com/feed",
    }
    import time
    entries = [
        {
            "title": "First Article",
            "link": "https://example.com/a/1",
            "summary": "first summary",
            "published_parsed": (2026, 7, 6, 12, 0, 0, 0, 0, 0),
        },
        {
            "title": "Second Article",
            "link": "https://example.com/a/2",
            "summary": "second summary",
            "published_parsed": (2026, 7, 6, 11, 0, 0, 0, 0, 0),
        },
        # 缺 title → 跳过
        {"title": "", "link": "https://example.com/a/3", "summary": "x"},
        # 缺 link → 跳过
        {"title": "X", "link": "", "summary": "x"},
    ]
    collector = SecurityCollector()
    with patch("feedparser.parse", return_value=_make_feedparser_mock(entries)):
        items, sr = __import__("asyncio").run(collector._fetch_rss(src))
    assert len(items) == 2
    assert items[0].title == "First Article"
    assert str(items[0].url) == "https://example.com/a/1"
    assert items[0].source == "MockGood"
    assert items[0].published_at == datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    assert sr.item_count == 2


def test_rss_path_routes_before_html():
    """fetch_source 看到 rss_url 字段时直接走 _fetch_rss,不走 _parse_html。"""
    src = {
        "name": "SecWiki",
        "url": "https://www.sec-wiki.com/",
        "rss_url": "https://www.sec-wiki.com/news/rss",
    }
    collector = SecurityCollector()
    entries = [
        {
            "title": "SecWiki News 2026-07-06",
            "link": "http://www.sec-wiki.com/?2026-07-06",
            "summary": "",
            "published_parsed": (2026, 7, 6, 0, 0, 0, 0, 0, 0),
        }
    ]
    with patch("feedparser.parse", return_value=_make_feedparser_mock(entries)):
        items, sr = __import__("asyncio").run(collector.fetch_source(src))
    assert sr.error_msg is None or sr.error_msg == ""
    assert sr.item_count == 1
    assert items[0].title == "SecWiki News 2026-07-06"
    assert items[0].source == "SecWiki"


def test_rss_path_crash_handled():
    """feedparser 抛异常 → 返回 rss_crash。"""
    src = {
        "name": "MockCrash",
        "url": "https://example.com/",
        "rss_url": "https://example.com/feed",
    }
    collector = SecurityCollector()
    with patch("feedparser.parse", side_effect=RuntimeError("boom")):
        items, sr = __import__("asyncio").run(collector._fetch_rss(src))
    assert items == []
    assert sr.error_msg.startswith("rss_crash:")
    assert "boom" in sr.error_msg
