"""Telegram collector 单元测试 (Phase 11)。

覆盖 5 个用例:
  1. ``test_telegram_returns_hotspot_items`` — mock fetch_source,验证返回 HotspotItem
  2. ``test_telegram_returns_empty_when_sources_fail`` — sources=[] 返回 []
  3. ``test_telegram_readable_id_format`` — 验证 ``telegram:post:{id}`` 格式
  4. ``test_telegram_category_correct`` — 验证 category 是 TECH
  5. ``test_telegram_source_config_valid`` — 验证源配置合法

Phase 13 硬约束 (SPEC §3):
* ``_fallback()`` 默认返回 []。
* sources=[] / 全部源失败 → collect() 直接返回 []。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.collectors.telegram_collector import (
    TELEGRAM_SOURCES,
    TelegramCollector,
)
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers (与 test_collectors.py 一致)
# ---------------------------------------------------------------------------
def _make_item(
    id_: str,
    *,
    category: Category = Category.TECH,
    title: str = "title",
    source: str = "Telegram",
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
# TelegramCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_telegram_returns_hotspot_items(monkeypatch):
    """mock fetch_source,验证返回 HotspotItem 列表且 category 匹配。"""
    c = TelegramCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.TECH),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.TECH for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_telegram_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = TelegramCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 [],"
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条合成数据"
    )


def test_telegram_readable_id_format():
    """验证 _parse_html 返回的 raw dict 中 id 为 telegram:post:{id} 格式。"""
    c = TelegramCollector()
    mock_html = """
    <div class="tgme_widget_message_wrap">
      <div class="tgme_widget_message" data-post="technews/12345">
        <div class="tgme_widget_message_text">Some text</div>
        <a class="tgme_widget_message_date"
           href="https://t.me/technews/12345">Yesterday</a>
      </div>
    </div>
    <div class="tgme_widget_message_wrap">
      <div class="tgme_widget_message" data-post="ai_updates/67890">
        <div class="tgme_widget_message_text">AI news</div>
        <a class="tgme_widget_message_date"
           href="https://t.me/ai_updates/67890">Today</a>
      </div>
    </div>
    """
    source = TELEGRAM_SOURCES[0]
    raw_items = c._parse_html(mock_html, source)

    assert len(raw_items) > 0
    for raw in raw_items:
        raw_id = raw.get("id", "")
        assert raw_id.startswith("telegram:post:"), (
            f"ID 应以 'telegram:post:' 开头, 实际: {raw_id!r}"
        )
        # 验证格式: telegram:post:<post_id> (post_id 是纯数字)
        parts = raw_id.split(":")
        assert len(parts) == 3, f"ID 应包含 3 部分, 实际: {parts}"
        assert parts[0] == "telegram"
        assert parts[1] == "post"
        assert parts[2].isdigit(), (
            f"ID 第三部分应为纯数字 post_id, 实际: {parts[2]!r}"
        )


def test_telegram_category_correct():
    """验证 category 是 TECH。"""
    c = TelegramCollector()
    assert c.category is Category.TECH, (
        f"TelegramCollector.category 应为 Category.TECH, "
        f"实际: {c.category}"
    )


def test_telegram_source_config_valid():
    """验证源配置合法 (url/name/score 完整)。"""
    c = TelegramCollector()
    assert len(c.sources) == 1
    src = c.sources[0]
    assert isinstance(src.get("name"), str) and len(src["name"]) > 0
    assert isinstance(src.get("url"), str) and len(src["url"]) > 0
    assert isinstance(src.get("score"), int) and 0 <= src["score"] <= 100
    # 模块级常量应与实例一致
    assert len(c.sources) == len(TELEGRAM_SOURCES)
    assert c.sources[0]["name"] == TELEGRAM_SOURCES[0]["name"]


# ---------------------------------------------------------------------------
# 继承自 BaseCollector + 不实现 _fallback
# ---------------------------------------------------------------------------
def test_telegram_collector_inherits_base():
    """TelegramCollector 应继承 BaseCollector。"""
    assert issubclass(TelegramCollector, BaseCollector)


def test_telegram_collector_does_not_implement_fallback():
    """Phase 13 硬约束: TelegramCollector 不实现 _fallback()。"""
    assert "_fallback" not in TelegramCollector.__dict__, (
        "TelegramCollector 重写了 _fallback(), 违反 Phase 13 硬约束。"
        "删除该方法, BaseCollector 默认 _fallback() 已返回 []。"
    )