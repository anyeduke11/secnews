"""OSS Insight collector 单元测试 (Phase 11)。

覆盖 5 个用例:
  1. ``test_ossinsight_returns_hotspot_items`` — mock fetch_source,
     验证返回 HotspotItem 列表且 category 为 TECH。
  2. ``test_ossinsight_returns_empty_when_sources_fail`` — sources=[] 返回 []。
  3. ``test_ossinsight_readable_id_format`` — 验证 _build_items 产出
     ``ossinsight:trend:{id}`` 格式的可读 ID。
  4. ``test_ossinsight_category_correct`` — 验证 category 是 TECH。
  5. ``test_ossinsight_source_config_valid`` — 验证 source 配置有必填字段。

Phase 13 硬约束 (SPEC §3):
* BaseCollector._fallback() 默认返回 []。
* collect() 在 sources=[] / 全部源失败时直接返回 []，
  不调 _fallback()，不生成合成数据。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.ossinsight_collector import (
    OSSINSIGHT_SOURCES,
    OSSInsightCollector,
)
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
    source: str = "OSSInsight",
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
    """构造一个 fetch_source 替身: 返回固定 items + 成功 SourceResult。"""
    async def fake_fetch(source: dict):
        items = [
            _make_item(
                f"ossinsight:trend:{i}",
                category=category,
                title=f"OSSInsight item {i}",
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
# OSSInsightCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_ossinsight_returns_hotspot_items(monkeypatch):
    """mock fetch_source, 验证返回 HotspotItem 列表且 category 为 TECH。"""
    c = OSSInsightCollector()
    monkeypatch.setattr(c, "fetch_source", _make_fake_fetch(items_per_source=3))

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.TECH for it in items)
    # 成功抓取路径下不应是 fallback
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_ossinsight_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [], 不调 _fallback()。"""
    c = OSSInsightCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 [],"
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条数据"
    )


def test_ossinsight_readable_id_format():
    """验证 _build_items 产出 ossinsight:trend:{id} 格式的可读 ID。"""
    c = OSSInsightCollector()
    raw_items = [
        {"title": "Project Alpha", "url": "https://ossinsight.io/project/alpha"},
        {"title": "Project Beta", "url": "https://ossinsight.io/project/beta"},
    ]
    source = {"name": "OSSInsight", "url": "https://ossinsight.io/", "score": 77}
    items = c._build_items(raw_items, source)
    assert len(items) == 2
    for i, item in enumerate(items):
        assert item.id == f"ossinsight:trend:{i}", (
            f"预期 ID 为 ossinsight:trend:{i}, 实际为 {item.id!r}"
        )
    # 验证 source 字段
    assert all(it.source == "OSSInsight" for it in items)


def test_ossinsight_category_correct():
    """验证 category 是 TECH。"""
    c = OSSInsightCollector()
    assert c.category is Category.TECH


def test_ossinsight_source_config_valid():
    """验证 source 配置有必填字段 (name, url, score)。"""
    assert len(OSSINSIGHT_SOURCES) >= 1
    for src in OSSINSIGHT_SOURCES:
        assert "name" in src, "source 缺少 name 字段"
        assert "url" in src, "source 缺少 url 字段"
        assert "score" in src, "source 缺少 score 字段"
        assert isinstance(src["name"], str) and src["name"], "name 必须是非空字符串"
        assert isinstance(src["url"], str) and src["url"], "url 必须是非空字符串"
        assert isinstance(src["score"], int) and 0 <= src["score"] <= 100, (
            "score 必须是 0-100 的整数"
        )