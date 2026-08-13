"""Reddit collector 单元测试 (Phase 11)。

覆盖 5 个用例:

1. test_reddit_returns_hotspot_items — mock fetch_source, 验证返回 HotspotItem list
2. test_reddit_returns_empty_when_sources_fail — sources=[] 返回 []
3. test_reddit_readable_id_format — 验证 ``reddit:post:{id}`` 格式
4. test_reddit_category_correct — 验证 category 是 TECH
5. test_reddit_source_config_valid — 验证 source config 有必填字段
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.collectors.reddit_collector import REDDIT_SOURCES, RedditCollector
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str,
    *,
    category: Category = Category.TECH,
    title: str = "title",
    source: str = "Reddit",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=f"https://reddit.com/r/test/{id_}",
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _make_fake_fetch(items_per_source: int, category: Category = Category.TECH):
    """构造一个 fetch_source 替身:返回固定 items + 成功 SourceResult。"""
    async def fake_fetch(source: dict):
        items = [
            _make_item(
                f"{source['name']}_{i}",
                category=category,
                title=f"{source['name']} item {i}",
                source=source["name"],
            )
            for i in range(items_per_source)
        ]
        return items, SourceResult(
            source_name=source["name"],
            source_url=source["url"],
            item_count=items_per_source,
            duration_ms=10,
        )
    return fake_fetch


# ===========================================================================
# 1. mock fetch_source → 验证返回 HotspotItem list
# ===========================================================================
@pytest.mark.asyncio
async def test_reddit_returns_hotspot_items(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c, "fetch_source", _make_fake_fetch(items_per_source=3))

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.TECH for it in items)
    assert not any(it.is_fallback for it in items)


# ===========================================================================
# 2. sources=[] → collect() 返回 []
# ===========================================================================
@pytest.mark.asyncio
async def test_reddit_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [], 不调 _fallback()。"""
    c = RedditCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束: sources=[] 时 collect() 必须返回 [], "
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条数据"
    )


# ===========================================================================
# 3. readable ID 格式验证
# ===========================================================================
def test_reddit_readable_id_format():
    """验证 _parse_json 产出 reddit:post:{id} 格式的可读 ID。"""
    c = RedditCollector()
    # 使用当前时间戳确保通过 Phase 47 时效门禁 (published_at >= week_start)
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    mock_data = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "iPhone 17 Pro Max Review",
                        "url": "https://example.com/1",
                        "id": "abc123",
                        "score": 100,
                        "created_utc": now_ts,
                        "subreddit": "test",
                    }
                },
                {
                    "data": {
                        "title": "Python 3.14 Released",
                        # 注意: "Python" 在 _CAT_KEYWORDS["tech"] 中, 不会被过滤
                        "url": "https://example.com/2",
                        "id": "def456",
                        "score": 50,
                        "created_utc": now_ts - 1,
                        "subreddit": "test",
                    }
                },
            ]
        }
    }

    raw = c._parse_json(mock_data, c.sources[0])
    assert len(raw) == 2
    assert raw[0]["id"] == "reddit:post:abc123"
    assert raw[1]["id"] == "reddit:post:def456"
    # 验证 readable ID 通过 _build_items 传递到 HotspotItem
    # 使用 _build_items 内部构建, 确保 id 是 raw.get("id") 取到的
    items = c._build_items(raw, c.sources[0])
    assert len(items) > 0
    assert items[0].id == "reddit:post:abc123"
    assert items[1].id == "reddit:post:def456"


# ===========================================================================
# 4. category 验证
# ===========================================================================
def test_reddit_category_correct():
    """验证 category 是 Category.TECH。"""
    c = RedditCollector()
    assert c.category is Category.TECH
    assert c.category.value == "tech"


# ===========================================================================
# 5. source config 必填字段验证
# ===========================================================================
def test_reddit_source_config_valid():
    """验证 source config 有必填字段: name, url, score, keywords, headers。"""
    c = RedditCollector()
    assert len(c.sources) == 1
    src = c.sources[0]
    assert isinstance(src, dict)
    assert "name" in src and src["name"] == "Reddit"
    assert "url" in src
    assert src["url"] == "https://www.reddit.com/r/all/top.json"
    assert "score" in src and isinstance(src["score"], int)
    assert "keywords" in src and isinstance(src["keywords"], list)
    assert "headers" in src and isinstance(src["headers"], dict)
    # 验证模块级常量 REDDIT_SOURCES 与实例一致
    assert len(c.sources) == len(REDDIT_SOURCES)


# ===========================================================================
# 继承与 Phase 13 约束
# ===========================================================================
def test_reddit_collector_inherits_base():
    """RedditCollector 应继承 BaseCollector。"""
    assert issubclass(RedditCollector, BaseCollector)


def test_reddit_collector_does_not_implement_fallback():
    """Phase 13 硬约束: RedditCollector 不重写 _fallback()。"""
    assert "_fallback" not in RedditCollector.__dict__, (
        "RedditCollector 重写了 _fallback(), 违反 Phase 13 硬约束。"
        "删除该方法, BaseCollector 默认 _fallback() 已返回 []。"
    )