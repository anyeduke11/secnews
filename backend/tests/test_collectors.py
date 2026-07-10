"""6 个 collector 单元测试 (Phase 13 更新)

每个 collector 覆盖两个用例:
  1. ``test_<name>_returns_hotspot_items`` — mock fetch_source 模拟成功抓取,
     验证返回的 items 全部是 HotspotItem、category 与 collector 自身一致。
  2. ``test_<name>_returns_empty_when_sources_fail`` — sources=[] 强制走空,
     验证 items 为空 (Phase 13 硬约束,不再有 fallback)。

外加 ``test_bid_collector_has_30_plus_sources`` 验证招标采集器配置 30+ 源。
``test_github_collector_returns_hotspot_items`` 单独覆盖 GitHub collector。

Phase 13 硬约束 (SPEC §3):
* BaseCollector._fallback() 默认返回 []。
* 6 个 collector 子类均不实现 _fallback()。
* collect() 在 sources=[] / 全部源失败 / items 不足时,**直接**返回 [],
  **不**调任何 fallback,**不**生成合成数据,**不**打 is_fallback=True。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.ai_collector import AICollector, AI_SOURCES
from backend.collectors.base import BaseCollector
from backend.collectors.bid_collector import (
    BID_SOURCES,
    BidCollector,
)
from backend.collectors.finance_collector import (
    FINANCE_SOURCES,
    FinanceCollector,
)
from backend.collectors.github_collector import GITHUB_SOURCES, GitHubCollector
from backend.collectors.security_collector import (
    SECURITY_SOURCES,
    SecurityCollector,
    _filter_blacklist,
)
from backend.collectors.startup_collector import (
    STARTUP_SOURCES,
    StartupCollector,
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
    category: Category = Category.AI,
    title: str = "title",
    source: str = "src",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=f"https://real-source.com/{id_}",  # Phase 13: 真实 URL,非 example.com
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _make_fake_fetch(items_per_source: int, category: Category = Category.AI):
    """构造一个 fetch_source 替身:返回固定 items + 成功 SourceResult。

    ``category`` 是 mock 出来的 items 的分类(与调用方 collector 的
    category 一致)——这样 collect() 透传下来的 items 才能匹配该分类。
    """
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
# AICollector
# ===========================================================================
@pytest.mark.asyncio
async def test_ai_collector_returns_hotspot_items(monkeypatch):
    c = AICollector()
    # mock fetch_source,模拟成功抓取
    monkeypatch.setattr(c, "fetch_source", _make_fake_fetch(items_per_source=3))

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.AI for it in items)
    # 成功抓取路径下不应是 fallback
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_ai_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = AICollector()
    # 强制 sources=[] 走空
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 [],"
        f"但 {c.__class__.__name__}.collect() 返回 {len(items)} 条合成数据"
    )


# ===========================================================================
# SecurityCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_security_collector_returns_hotspot_items(monkeypatch):
    c = SecurityCollector()
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
async def test_security_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = SecurityCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 []"
    )


# ===========================================================================
# FinanceCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_finance_collector_returns_hotspot_items(monkeypatch):
    c = FinanceCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.FINANCE),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.FINANCE for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_finance_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = FinanceCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 []"
    )


# ===========================================================================
# StartupCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_startup_collector_returns_hotspot_items(monkeypatch):
    c = StartupCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.STARTUP),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.STARTUP for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_startup_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = StartupCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 []"
    )


# ===========================================================================
# BidCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_bid_collector_returns_hotspot_items(monkeypatch):
    c = BidCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.BID),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.BID for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_bid_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback() (Phase 12 撤销的 Google 搜索 fallback)。"""
    c = BidCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 [],"
        "**不**得返回 Google 搜索 URL 兜底 (Phase 12 方案已撤销)"
    )


# ===========================================================================
# GitHubCollector
# ===========================================================================
@pytest.mark.asyncio
async def test_github_collector_returns_hotspot_items(monkeypatch):
    c = GitHubCollector()
    monkeypatch.setattr(
        c, "fetch_source",
        _make_fake_fetch(items_per_source=3, category=Category.GITHUB),
    )

    items = await c.collect()
    assert len(items) > 0
    assert all(isinstance(it, HotspotItem) for it in items)
    assert all(it.category is Category.GITHUB for it in items)
    assert not any(it.is_fallback for it in items)


@pytest.mark.asyncio
async def test_github_collector_returns_empty_when_sources_fail(monkeypatch):
    """Phase 13: sources=[] → collect() 返回 [],不调 _fallback()。"""
    c = GitHubCollector()
    monkeypatch.setattr(c, "sources", [])

    items = await c.collect()
    assert items == [], (
        "Phase 13 硬约束 (SPEC §3): sources=[] 时 collect() 必须返回 []"
    )


# ---------------------------------------------------------------------------
# 招标采集器特殊检查:sources 长度 ≥ 30 (Phase 9 扩充)
# ---------------------------------------------------------------------------
def test_bid_collector_has_30_plus_sources():
    """招标采集器应配置 30+ 源 (Phase 9 扩充:覆盖 skillhub 50+ 渠道)。"""
    c = BidCollector()
    assert len(c.sources) >= 30
    # 同样应等于模块级常量 BID_SOURCES
    assert len(c.sources) == len(BID_SOURCES)


# ---------------------------------------------------------------------------
# 其它 collector 的 sources 数量 sanity check
# ---------------------------------------------------------------------------
def test_other_collectors_have_sources():
    """AI / Security / Finance / Startup / GitHub 各自至少 4 个源。"""
    assert len(AICollector().sources) >= 4
    assert len(SecurityCollector().sources) >= 4
    assert len(FinanceCollector().sources) >= 4
    assert len(StartupCollector().sources) >= 4
    # sanity: AI_SOURCES / SECURITY_SOURCES / FINANCE_SOURCES / STARTUP_SOURCES
    # 与 instance.sources 数量一致
    # 注: SecurityCollector 应用了 SOURCE_BLACKLIST 过滤,
    # 所以 instance.sources 可能 < SECURITY_SOURCES(临时黑名单)
    assert len(AICollector().sources) == len(AI_SOURCES)
    assert len(SecurityCollector().sources) == len(_filter_blacklist(SECURITY_SOURCES))
    assert len(FinanceCollector().sources) == len(FINANCE_SOURCES)
    assert len(StartupCollector().sources) == len(STARTUP_SOURCES)


# ---------------------------------------------------------------------------
# Phase 26: 小互AI RSS 源 sanity (rss_url 路由 + domain 注册)
# ---------------------------------------------------------------------------
def test_phase26_xiaohu_rss_source_in_ai():
    """Phase 26: 小互AI 走 RSS 路由 (rss_url 字段),自动触发 _fetch_rss。"""
    src = next(
        (s for s in AI_SOURCES if s.get("name") == "小互AI"),
        None,
    )
    assert src is not None, "小互AI 不在 AI_SOURCES"
    assert src.get("rss_url") == "https://best.xiaohu.ai/rss.xml"
    # 不应使用 html renderer (走 RSS 路径)
    assert src.get("renderer") in (None, "aiohttp")


def test_phase26_xiaohu_in_publisher_registry():
    """Phase 26: best.xiaohu.ai 域名必须在 PUBLISHER_REGISTRY,避免 author_unknown。"""
    from backend.quality.publisher_registry import PUBLISHER_REGISTRY, resolve_publisher
    registry_map = {s: n for s, n in PUBLISHER_REGISTRY}
    assert "best.xiaohu.ai" in registry_map
    assert registry_map["best.xiaohu.ai"] == "小互AI"

    # resolve_publisher 应能识别
    canonical, is_match, _ = resolve_publisher(
        "https://best.xiaohu.ai/article/cloudflare-workers-cache/",
        "小互AI",
    )
    assert is_match is True
    assert canonical == "小互AI"


# ---------------------------------------------------------------------------
# 所有 6 个 collector 都继承自 BaseCollector
# ---------------------------------------------------------------------------
def test_all_collectors_inherit_base():
    """6 个 collector 都应继承 BaseCollector。"""
    assert issubclass(AICollector, BaseCollector)
    assert issubclass(SecurityCollector, BaseCollector)
    assert issubclass(FinanceCollector, BaseCollector)
    assert issubclass(StartupCollector, BaseCollector)
    assert issubclass(BidCollector, BaseCollector)
    assert issubclass(GitHubCollector, BaseCollector)


# ---------------------------------------------------------------------------
# Phase 13 硬约束: 6 个 collector 均不实现 _fallback
# ---------------------------------------------------------------------------
def test_collectors_do_not_implement_fallback():
    """Phase 13 硬约束 (SPEC §3.3.1): 6 个 collector 的 _fallback 必须继承
    BaseCollector 的默认实现 (返回 [])。子类不得重写。

    验证方法: 检查 cls.__dict__ 中**没有** '_fallback'。
    """
    for cls in (AICollector, SecurityCollector, FinanceCollector,
                StartupCollector, BidCollector, GitHubCollector):
        assert "_fallback" not in cls.__dict__, (
            f"{cls.__name__} 重写了 _fallback(),违反 Phase 13 硬约束。"
            f"删除该方法,BaseCollector 默认 _fallback() 已返回 []。"
        )
