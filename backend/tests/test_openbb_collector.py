"""OpenBB collector 单元测试 (Phase 11)。

覆盖 5 个用例:
  1. test_openbb_returns_hotspot_items — mock 成功抓取,返回 HotspotItem 列表
  2. test_openbb_returns_empty_when_sources_fail — sources=[] 返回空列表
  3. test_openbb_category_correct — 验证 category 为 FINANCE
  4. test_openbb_source_config_valid — 验证源配置（V1.9: 无 rss_url, 走 aiohttp 抓取）
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.collectors.openbb_collector import OPENBB_SOURCES, OpenBBCollector
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers (匹配 test_collectors.py 的 _make_item / _make_fake_fetch 模式)
# ---------------------------------------------------------------------------
def _make_item(
    id_: str,
    *,
    category: Category = Category.FINANCE,
    title: str = "title",
    source: str = "OpenBB",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=f"https://openbb.co/article/{id_}",
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _make_fake_fetch(items_per_source: int):
    """构造一个 fetch_source 替身:返回固定 items + 成功 SourceResult。"""

    async def fake_fetch(source: dict):
        items = [
            _make_item(
                f"{source['name']}_{i}",
                category=Category.FINANCE,
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
# 用例 1: 成功抓取返回 HotspotItem
# ===========================================================================
@pytest.mark.asyncio
async def test_openbb_returns_hotspot_items(monkeypatch):
    c = OpenBBCollector()
    monkeypatch.setattr(c, "fetch_source", _make_fake_fetch(items_per_source=3))

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.FINANCE for it in items)
    assert not any(it.is_fallback for it in items)


# ===========================================================================
# 用例 2: sources=[] 返回空 (Phase 13 硬约束)
# ===========================================================================
@pytest.mark.asyncio
async def test_openbb_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = OpenBBCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 [],"
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条数据"
    )


# ===========================================================================
# 用例 3: Category 验证
# ===========================================================================
def test_openbb_category_correct():
    c = OpenBBCollector()
    assert c.category is Category.FINANCE, (
        f"OpenBBCollector.category 应为 FINANCE, 实际为 {c.category}"
    )


# ===========================================================================
# 用例 4: 源配置验证 (V1.9: 无 rss_url, 走 aiohttp 抓取)
# ===========================================================================
def test_openbb_source_config_valid():
    c = OpenBBCollector()
    assert len(c.sources) >= 1
    assert len(c.sources) == len(OPENBB_SOURCES)
    src = c.sources[0]
    assert "rss_url" not in src, "V1.9: OpenBB RSS 已失效, 不应有 rss_url 字段"
    assert src["name"] == "OpenBB"
    assert src["url"] == "https://openbb.co/blog"
    assert isinstance(src.get("score"), int)
    assert 0 <= src["score"] <= 100