"""Bug 1 + Bug 2 修复回归测试 (2026-07-05), Phase 13 硬约束重写。

Phase 12 修 Bug 1 时,bid fallback URL 从 ``example.com`` 改为 Google
搜索 URL,看似"真实可访问"。

Phase 13 复盘后撤销该方案。用户明确反对"把搜索工作推给用户":

    资讯的原文链接必须是原文真实链接,如果没有真实链接说明资讯和
    标讯有问题,**禁止** 提供搜索字眼让用户自己搜索资讯。

因此 Phase 13 重写:

- ``BaseCollector._fallback()`` 默认返回 ``[]``
- 6 个 collector 子类 **不再** 实现 ``_fallback()``(子类不实现继承
  默认空列表,占位 fallback 接口留作未来真实离线数据源场景)
- ``BaseCollector.collect()`` 全部源失败 / items 不足时,直接返回 ``[]``
- UI 显示"该分类暂无可用资讯"

Bug 2 修复保留: ``_parse_html`` 仍提取页面级发布时间,``_build_items``
优先用 raw 时间,24h 趋势图 / 按发布时间排序正常工作。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.parsing import (
    _extract_published_at,
    _parse_iso_datetime,
)
from backend.collectors.bid_collector import BidCollector
from backend.collectors.ai_collector import AICollector
from backend.collectors.security_collector import SecurityCollector
from backend.collectors.finance_collector import FinanceCollector
from backend.collectors.startup_collector import StartupCollector
from backend.collectors.github_collector import GitHubCollector
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ===========================================================================
# Phase 13 硬约束: 所有 collector 的 _fallback 必须返回空列表
# (禁止 example.com 占位 / 禁止 Google 搜索 / 禁止任何合成 URL)
# ===========================================================================
class TestFallbackReturnsEmpty:
    """Phase 13: 任何 _fallback 调用都不得返回合成数据,必须返回空列表。"""

    @pytest.mark.parametrize("collector_cls", [
        AICollector,
        SecurityCollector,
        FinanceCollector,
        StartupCollector,
        BidCollector,
        GitHubCollector,
    ])
    def test_fallback_returns_empty_list(self, collector_cls):
        """所有 6 个 collector 的 _fallback 必须返回空列表。"""
        items = collector_cls()._fallback()
        assert items == [], (
            f"{collector_cls.__name__}._fallback() 返回 {len(items)} 条 "
            f"合成数据,违反 Phase 13 硬约束 (SPEC §3)"
        )

    @pytest.mark.parametrize("collector_cls", [
        AICollector,
        SecurityCollector,
        FinanceCollector,
        StartupCollector,
        BidCollector,
        GitHubCollector,
    ])
    def test_fallback_no_synthetic_urls(self, collector_cls):
        """fallback 不得返回任何 URL,包括 example.com / google.com / 任何域。"""
        items = collector_cls()._fallback()
        for it in items:
            url = str(getattr(it, "url", "") or "")
            assert url == "", (
                f"{collector_cls.__name__}._fallback() 返回了带 URL 的合成 "
                f"item: {url}"
            )
            # 任何含 example.com / google.com / baidu.com 的 URL 都是禁止的
            assert "example.com" not in url
            assert "google.com" not in url
            assert "baidu.com" not in url

    def test_base_collector_fallback_default_empty(self):
        """BaseCollector._fallback() 默认实现必须是空列表。"""
        from backend.collectors.base import BaseCollector
        items = BaseCollector()._fallback()
        assert items == []


class TestCollectReturnsEmptyOnAllSourcesFailed:
    """Phase 13: 所有源失败时 collect() 直接返回空列表,不调 _fallback。"""

    @pytest.mark.asyncio
    async def test_collect_no_sources_returns_empty(self):
        """无 sources → return []。"""
        from backend.collectors.base import BaseCollector
        from backend.domain.enums import Category

        class EmptyCollector(BaseCollector):
            category = Category.AI
            sources = []
            name = "empty_test"

        items = await EmptyCollector().collect()
        assert items == []


# ===========================================================================
# Bug 2: _parse_iso_datetime 健壮性
# ===========================================================================
class TestParseIsoDatetime:
    """_parse_iso_datetime 容忍各种 ISO 8601 格式。"""

    def test_standard_iso_with_z(self):
        dt = _parse_iso_datetime("2026-07-05T10:35:17Z")
        assert dt == datetime(2026, 7, 5, 10, 35, 17, tzinfo=timezone.utc)

    def test_iso_with_offset(self):
        dt = _parse_iso_datetime("2026-07-05T18:35:17+08:00")
        # 转换为 UTC
        assert dt == datetime(2026, 7, 5, 10, 35, 17, tzinfo=timezone.utc)

    def test_naive_assumed_utc(self):
        dt = _parse_iso_datetime("2026-07-05 10:35:17")
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2026 and dt.month == 7 and dt.day == 5

    def test_invalid_returns_none(self):
        assert _parse_iso_datetime("not a date") is None
        assert _parse_iso_datetime("") is None
        assert _parse_iso_datetime(None) is None  # type: ignore

    def test_out_of_range_year_returns_none(self):
        # 1990 或 2100 之外返回 None
        assert _parse_iso_datetime("1995-01-01T00:00:00Z") is None
        assert _parse_iso_datetime("2150-01-01T00:00:00Z") is None


# ===========================================================================
# Bug 2: _extract_published_at 多种 HTML 模式
# ===========================================================================
class TestExtractPublishedAt:
    """_extract_published_at 从 HTML/URL 提取发布时间。"""

    def test_jsonld_datePublished(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","datePublished":"2026-07-05T10:00:00Z"}
        </script>
        </head></html>
        """
        dt = _extract_published_at(html, "https://example.com/")
        assert dt == datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc)

    def test_meta_article_published_time(self):
        html = """
        <html><head>
        <meta property="article:published_time" content="2026-07-04T08:30:00+00:00">
        </head></html>
        """
        dt = _extract_published_at(html, "https://example.com/")
        assert dt == datetime(2026, 7, 4, 8, 30, tzinfo=timezone.utc)

    def test_meta_itemprop_datePublished(self):
        html = """
        <html><head>
        <meta itemprop="datePublished" content="2026-07-03T15:45:00Z">
        </head></html>
        """
        dt = _extract_published_at(html, "https://example.com/")
        assert dt == datetime(2026, 7, 3, 15, 45, tzinfo=timezone.utc)

    def test_meta_pubdate(self):
        html = """
        <html><head>
        <meta name="pubdate" content="2026-07-02T12:00:00Z">
        </head></html>
        """
        dt = _extract_published_at(html, "https://example.com/")
        assert dt == datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    def test_time_datetime(self):
        html = """
        <html><body>
        <time datetime="2026-07-01T09:00:00Z">July 1, 2026</time>
        </body></html>
        """
        dt = _extract_published_at(html, "https://example.com/")
        assert dt == datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)

    def test_url_slug_yyyy_mm_dd(self):
        """无 meta,fallback 到 URL slug(常见于 qbitai / thehackernews)。"""
        html = "<html><body>nothing here</body></html>"
        dt = _extract_published_at(
            html, "https://www.qbitai.com/2026/07/05/442447.html"
        )
        assert dt == datetime(2026, 7, 5, tzinfo=timezone.utc)

    def test_url_slug_yyyy_mm_id(self):
        """qbitai 类 URL 只有 /2026/07/article_id.html (3 段,无日),
        fallback 到月级精度 (YYYY-MM-01)。"""
        html = "<html></html>"
        dt = _extract_published_at(
            html, "https://www.qbitai.com/2026/07/442447.html"
        )
        assert dt == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_url_slug_with_dashes(self):
        html = "<html></html>"
        dt = _extract_published_at(
            html, "https://www.example.com/2026-07-04/news-12345"
        )
        assert dt == datetime(2026, 7, 4, tzinfo=timezone.utc)

    def test_url_slug_wordpress_no_html(self):
        """WordPress 类 URL /2026/06/scattered-spider-hackers(无 .html),
        第 3 段是 slug,使用月级精度。"""
        html = "<html></html>"
        dt = _extract_published_at(
            html,
            "https://krebsonsecurity.com/2026/06/scattered-spider-hackers",
        )
        assert dt == datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_url_slug_with_query_and_hash(self):
        """URL 带 ?query 或 #anchor 也能匹配。"""
        html = "<html></html>"
        dt = _extract_published_at(
            html,
            "https://www.qbitai.com/2026/07/442447.html#comments",
        )
        assert dt == datetime(2026, 7, 1, tzinfo=timezone.utc)

    def test_returns_none_when_no_signal(self):
        html = "<html><body>just text</body></html>"
        url = "https://www.example.com/news/latest"
        assert _extract_published_at(html, url) is None

    def test_meta_takes_priority_over_url(self):
        """HTML meta 优先于 URL slug(meta 更可靠)。"""
        html = """
        <meta property="article:published_time" content="2026-07-01T05:00:00Z">
        """
        url = "https://www.qbitai.com/2026/07/05/442447.html"
        dt = _extract_published_at(html, url)
        assert dt == datetime(2026, 7, 1, 5, 0, tzinfo=timezone.utc)


# ===========================================================================
# Bug 2: 端到端 — _parse_html → _build_items 把页面时间传到 HotspotItem
# ===========================================================================
class TestEndToEndPublishedAt:
    """_parse_html 提取的时间必须能传到 HotspotItem.published_at。"""

    def test_parsed_items_have_real_published_at(self):
        """HTML 含 <meta> 时间,parse 后 published_at 应是页面时间。"""
        from backend.collectors.ai_collector import AICollector
        c = AICollector()
        # 找一个简单源做测试
        source = c.sources[0]
        # Phase 27 BL-07 同源校验: mock URL 必须与 source.url 同 host
        src_host = source["url"].split("//", 1)[-1].split("/", 1)[0]
        html = f"""
        <html><head>
        <meta property="article:published_time" content="2026-07-21T08:00:00Z">
        </head><body>
        <h2 class="entry-title">
          <a href="https://{src_host}/article-1" rel="bookmark">New GPT Model Release Article One</a>
        </h2>
        <h2 class="entry-title">
          <a href="https://{src_host}/article-2" rel="bookmark">DeepSeek LLM Training Update Article Two</a>
        </h2>
        </body></html>
        """
        raw_items = c._parse_html(html, source)
        assert len(raw_items) == 2
        for raw in raw_items:
            assert raw["published_at"] == datetime(
                2026, 7, 21, 8, 0, tzinfo=timezone.utc
            )

        # 进一步验证 _build_items 把它传到 HotspotItem
        items = c._build_items(raw_items, source)
        assert len(items) == 2
        for it in items:
            assert it.published_at == datetime(
                2026, 7, 21, 8, 0, tzinfo=timezone.utc
            )
            # fetched_at 仍然是 now
            assert it.fetched_at is not None

    def test_parsed_items_dropped_when_no_published_at(self):
        """无 meta/无 URL slug → published_at=None → Phase 47 设计拒收。

        Phase 47 之前 fallback 到 now (fetch time) 会污染首页(让历史
        资讯被当作"当周新资讯"入库)。当前设计: 缺发布时间 = 无法
        验证时效性 = 拒收 (宁缺毋滥)。"""
        from backend.collectors.ai_collector import AICollector
        c = AICollector()
        source = c.sources[0]
        # Phase 27 BL-07 同源校验: mock URL 必须与 source.url 同 host
        src_host = source["url"].split("//", 1)[-1].split("/", 1)[0]
        html = f"""
        <html><body>
        <h2 class="entry-title">
          <a href="https://{src_host}/news-1" rel="bookmark">GPT Article Without Time Meta Information</a>
        </h2>
        </body></html>
        """
        raw_items = c._parse_html(html, source)
        assert len(raw_items) == 1
        assert raw_items[0]["published_at"] is None

        # Phase 47: 缺 published_at → drop, 不 fallback
        items = c._build_items(raw_items, source)
        assert items == []

    def test_url_slug_published_at_per_item(self):
        """每个 item 的 URL slug 时间戳独立提取(优先级高于页面级)。"""
        from backend.collectors.ai_collector import AICollector
        c = AICollector()
        source = c.sources[0]
        # Phase 27 BL-07 同源校验: mock URL 必须与 source.url 同 host
        src_host = source["url"].split("//", 1)[-1].split("/", 1)[0]
        # 页面 meta 是 7/5,但 article URL 是 7/1
        html = f"""
        <html><head>
        <meta property="article:published_time" content="2026-07-05T00:00:00Z">
        </head><body>
        <h2 class="entry-title">
          <a href="https://{src_host}/2026/07/01/12345.html" rel="bookmark">Article With Earlier URL Date Information</a>
        </h2>
        </body></html>
        """
        raw_items = c._parse_html(html, source)
        assert len(raw_items) == 1
        # URL slug 2026/07/01 优先于 meta 2026-07-05
        assert raw_items[0]["published_at"] == datetime(
            2026, 7, 1, tzinfo=timezone.utc
        )


__all__ = [
    # Bug 1
    "TestBidFallbackUrl",
    # Bug 2
    "TestParseIsoDatetime",
    "TestExtractPublishedAt",
    "TestEndToEndPublishedAt",
]
