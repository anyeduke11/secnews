"""GDELT collector 单元测试（Phase 11 延迟实现）。

覆盖 5 个用例:
  1. test_gdelt_returns_hotspot_items — mock fetch_source, 验证返回 HotspotItem list
  2. test_gdelt_returns_empty_when_sources_fail — sources=[] 返回 []
  3. test_gdelt_readable_id_format — 验证 gdelt:article:{id} 格式
  4. test_gdelt_category_correct — 验证 category 是 SECURITY
  5. test_gdelt_source_config_valid — 验证 source config 有 api_url
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.collectors.gdelt_collector import GDELTCollector, GDELT_SOURCES
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str,
    *,
    category: Category = Category.SECURITY,
    title: str = "title",
    source: str = "GDELT",
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


def _make_fake_fetch(items_per_source: int, category: Category = Category.SECURITY):
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
# GDELTCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_gdelt_returns_hotspot_items(monkeypatch):
    """mock fetch_source, 验证返回 HotspotItem list。"""
    c = GDELTCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.SECURITY),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.SECURITY for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_gdelt_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [], 不调 _fallback()。"""
    c = GDELTCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 []"
    )


def test_gdelt_readable_id_format():
    """验证 _parse_json 输出的 readable ID 为 gdelt:article:{id} 格式。"""
    c = GDELTCollector()
    fake_data = {
        "articles": [
            {
                "url": "https://example.com/1",
                "title": "Cyber news 1",
                "seendate": "20260629T050000Z",
            },
            {
                "url": "https://example.com/2",
                "title": "Cyber news 2",
                "seendate": "20260629T060000Z",
            },
        ]
    }
    source = GDELT_SOURCES[0]
    raw_items = c._parse_json(fake_data, source)
    assert len(raw_items) == 2
    assert raw_items[0]["id"] == "gdelt:article:0"
    assert raw_items[1]["id"] == "gdelt:article:1"


def test_gdelt_category_correct():
    """验证 category 是 SECURITY。"""
    c = GDELTCollector()
    assert c.category is Category.SECURITY


def test_gdelt_source_config_valid():
    """验证 source config 有 api_url 且配置正确。"""
    c = GDELTCollector()
    assert len(c.sources) == 1
    src = c.sources[0]
    assert src.get("name") == "GDELT"
    assert "api_url" in src
    assert "cyber+security" in src["api_url"]
    assert "format=json" in src["api_url"]
    assert "max=25" in src["api_url"]
    assert src.get("renderer") == "json"