"""HackerNews collector 单元测试 (Phase 11)。

覆盖 5 个用例:

1. ``test_hn_returns_hotspot_items`` — mock fetch_source, 验证返回 HotspotItem list
2. ``test_hn_returns_empty_when_sources_fail`` — sources=[] 返回 []
3. ``test_hn_readable_id_format`` — 验证 ``hn:item:{id}`` 格式
4. ``test_hn_category_correct`` — 验证 category 是 TECH
5. ``test_hn_source_config_valid`` — 验证 source config 有必填字段

Phase 13 硬约束 (SPEC §3):
* BaseCollector._fallback() 默认返回 []。
* collect() 在 sources=[] / 全部源失败时直接返回 [],
  不调 _fallback(), 不生成合成数据。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.collectors.hn_collector import HN_SOURCES, HNCollector
from backend.collectors.id_factory import make_readable_id
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
    source: str = "HackerNews",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=f"https://real-source.com/{id_}",
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _make_fake_fetch(items_per_source: int, category: Category = Category.TECH):
    """构造一个 fetch_source 替身:返回固定 items + 成功 SourceResult。"""
    async def fake_fetch(source: dict):
        items = [
            _make_item(
                f"hn:item:{i}",
                category=category,
                title=f"HackerNews item {i}",
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
async def test_hn_returns_hotspot_items(monkeypatch):
    c = HNCollector()
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
async def test_hn_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [], 不调 _fallback()。"""
    c = HNCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束: sources=[] 时 collect() 必须返回 [], "
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条数据"
    )


# ===========================================================================
# 3. readable ID 格式验证
# ===========================================================================
def test_hn_readable_id_format():
    """验证 _parse_json 产出 ``hn:item:{story_id}`` 格式的可读 ID。"""
    c = HNCollector()
    # 模拟 HN API 响应: list of story dicts
    mock_data = [
        {
            "id": 12345678,
            "title": "Test Story 1",
            "url": "https://example.com/1",
            "time": 1720000000,
            "score": 100,
            "by": "author1",
        },
        {
            "id": 87654321,
            "title": "Test Story 2",
            "url": "https://example.com/2",
            "time": 1720000001,
            "score": 50,
            "by": "author2",
        },
    ]

    raw = c._parse_json(mock_data, c.sources[0])
    assert len(raw) == 2
    # _parse_json 返回 numeric story_id
    assert raw[0]["id"] == 12345678
    assert raw[1]["id"] == 87654321

    # make_readable_id 生成 hn:item:{id} 格式
    readable_0 = make_readable_id("hn", "item", str(raw[0]["id"]))
    readable_1 = make_readable_id("hn", "item", str(raw[1]["id"]))
    assert readable_0 == "hn:item:12345678"
    assert readable_1 == "hn:item:87654321"


# ===========================================================================
# 4. category 验证
# ===========================================================================
def test_hn_category_correct():
    """验证 category 是 Category.TECH。"""
    c = HNCollector()
    assert c.category is Category.TECH
    assert c.category.value == "tech"


# ===========================================================================
# 5. source config 必填字段验证
# ===========================================================================
def test_hn_source_config_valid():
    """验证 source config 有必填字段: name, url, api_url, score, keywords。"""
    c = HNCollector()
    assert len(c.sources) == 1
    src = c.sources[0]
    assert isinstance(src, dict)
    assert "name" in src and src["name"] == "HackerNews"
    assert "url" in src
    assert "api_url" in src
    assert src["api_url"] == "https://hacker-news.firebaseio.com/v0/topstories.json"
    assert "score" in src and isinstance(src["score"], int)
    assert 0 <= src["score"] <= 100
    assert "keywords" in src and isinstance(src["keywords"], list)
    assert len(src["keywords"]) >= 1
    # 验证模块级常量 HN_SOURCES 与实例一致
    assert len(c.sources) == len(HN_SOURCES)


# ===========================================================================
# 继承与 Phase 13 约束
# ===========================================================================
def test_hn_collector_inherits_base():
    """HNCollector 应继承 BaseCollector。"""
    assert issubclass(HNCollector, BaseCollector)


def test_hn_collector_does_not_implement_fallback():
    """Phase 13 硬约束: HNCollector 不重写 _fallback()。"""
    assert "_fallback" not in HNCollector.__dict__, (
        "HNCollector 重写了 _fallback(), 违反 Phase 13 硬约束。"
        "删除该方法, BaseCollector 默认 _fallback() 已返回 []。"
    )