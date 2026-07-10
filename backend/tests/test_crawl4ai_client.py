"""crawl4ai 适配层测试 (Phase 11)

覆盖
----
- ``is_available()`` 反映 (USE_CRAWL4AI env + crawl4ai 是否安装) 两状态
- ``fetch_html`` 在 crawl4ai 不可用时返回 ``None`` (caller 走 fallback)
- ``fetch_html`` 内部异常 (timeout / arun error / success=False) 都
  返回 ``None`` 而不抛
- ``get_client`` 进程级单例:多次调用返回同一对象
- ``close_client`` 清空单例,后续 get_client 重新初始化
- ``fetch_html`` 拿到的 HTML 含 ``.html`` 字段
- ``BaseCollector.fetch_source`` 在 USE_CRAWL4AI 关闭时仍走 aiohttp
  路径 (向后兼容)
- ``BaseCollector.fetch_source`` 在 crawl4ai 不可用 / 失败时降级到
  aiohttp,产出正常 items
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils import crawl4ai_client
from backend.utils.crawl4ai_client import (
    close_client,
    fetch_html,
    is_available,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后重置 _client 单例,避免互相污染。"""
    crawl4ai_client._client = None
    yield
    crawl4ai_client._client = None


# ---------------------------------------------------------------------------
# 1. is_available 反映 env + import 状态
# ---------------------------------------------------------------------------
def test_is_available_false_when_env_unset(monkeypatch):
    """USE_CRAWL4AI 未设置 → is_available() = False。"""
    monkeypatch.delenv("USE_CRAWL4AI", raising=False)
    # 不管 crawl4ai 装没装,env 未开就 False
    assert is_available() is False


def test_is_available_false_when_env_true_but_no_module(monkeypatch):
    """env 开但 crawl4ai 未装 → False (graceful)。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    # 模拟 crawl4ai 未装
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", False):
        assert is_available() is False


def test_is_available_true_when_env_true_and_module_installed(monkeypatch):
    """env 开 + crawl4ai 装了 → True。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True):
        assert is_available() is True


# ---------------------------------------------------------------------------
# 2. fetch_html 在不可用时直接返回 None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_html_returns_none_when_unavailable(monkeypatch):
    """crawl4ai 不可用 → fetch_html 返回 None,不抛异常。"""
    monkeypatch.setenv("USE_CRAWL4AI", "0")
    result = await fetch_html("https://example.com", timeout=5)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_html_returns_none_when_module_missing(monkeypatch):
    """env 开但 crawl4ai 未装 → None。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", False):
        result = await fetch_html("https://example.com", timeout=5)
        assert result is None


# ---------------------------------------------------------------------------
# 3. fetch_html 内部异常 (timeout / arun error / success=False) 都返回 None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_html_timeout_returns_none(monkeypatch):
    """arun 超时 → fetch_html 返回 None,不抛 TimeoutError。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=1)
        assert result is None


@pytest.mark.asyncio
async def test_fetch_html_arun_exception_returns_none(monkeypatch):
    """arun 内部抛异常 → fetch_html 返回 None。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(side_effect=RuntimeError("chromium crashed"))

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=5)
        assert result is None


@pytest.mark.asyncio
async def test_fetch_html_success_false_returns_none(monkeypatch):
    """arun 返回 success=False → None。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    fake_result = MagicMock()
    fake_result.success = False
    fake_result.error_message = "blocked by cloudflare"

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(return_value=fake_result)

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=5)
        assert result is None


@pytest.mark.asyncio
async def test_fetch_html_empty_content_returns_none(monkeypatch):
    """arun 成功但 .html 和 .markdown 都为空 → None。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    fake_result = MagicMock()
    fake_result.success = True
    fake_result.html = ""
    fake_result.markdown = None

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(return_value=fake_result)

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=5)
        assert result is None


@pytest.mark.asyncio
async def test_fetch_html_returns_html_when_success(monkeypatch):
    """arun 成功 + .html 有内容 → 返回 HTML 字符串。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    expected_html = "<html><body><h1>Hello</h1></body></html>"
    fake_result = MagicMock()
    fake_result.success = True
    fake_result.html = expected_html

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(return_value=fake_result)

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=5)
        assert result == expected_html


@pytest.mark.asyncio
async def test_fetch_html_falls_back_to_markdown(monkeypatch):
    """.html 为空但 .markdown 有内容 → 返回 markdown。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    expected_md = "# Hello World\n\nLorem ipsum"
    fake_result = MagicMock()
    fake_result.success = True
    fake_result.html = None
    fake_result.markdown = expected_md

    fake_client = MagicMock()
    fake_client.arun = AsyncMock(return_value=fake_result)

    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "get_client", AsyncMock(return_value=fake_client)):
        result = await fetch_html("https://example.com", timeout=5)
        assert result == expected_md


# ---------------------------------------------------------------------------
# 4. 单例管理
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_client_singleton(monkeypatch):
    """多次 get_client() 返回同一对象 (Playwright 启动只一次)。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    fake_instance = MagicMock()
    fake_instance.start = AsyncMock()

    fake_class = MagicMock(return_value=fake_instance)
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "AsyncWebCrawler", fake_class):
        c1 = await crawl4ai_client.get_client()
        c2 = await crawl4ai_client.get_client()
        assert c1 is c2
        # AsyncWebCrawler() 构造只调一次
        assert fake_class.call_count == 1
        # start() 只调一次
        assert fake_instance.start.call_count == 1


@pytest.mark.asyncio
async def test_get_client_returns_none_when_unavailable(monkeypatch):
    """crawl4ai 不可用 → get_client() 返回 None。"""
    monkeypatch.setenv("USE_CRAWL4AI", "0")
    assert await crawl4ai_client.get_client() is None


@pytest.mark.asyncio
async def test_get_client_returns_none_on_init_failure(monkeypatch):
    """AsyncWebCrawler() 构造失败 → get_client 返回 None,不清空其他状态。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    fake_class = MagicMock(side_effect=RuntimeError("chromium missing"))
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "AsyncWebCrawler", fake_class):
        result = await crawl4ai_client.get_client()
        assert result is None


@pytest.mark.asyncio
async def test_close_client_releases_singleton(monkeypatch):
    """close_client() 后 _client=None,下次 get_client 重新构造。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")
    fake_instance = MagicMock()
    fake_instance.start = AsyncMock()
    fake_instance.close = AsyncMock()

    fake_class = MagicMock(return_value=fake_instance)
    with patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), \
         patch.object(crawl4ai_client, "AsyncWebCrawler", fake_class):
        c1 = await crawl4ai_client.get_client()
        await close_client()
        c2 = await crawl4ai_client.get_client()
        # 两次构造:close 后重新 start
        assert c1 is c2  # 同一 mock 对象
        assert fake_class.call_count == 2
        assert fake_instance.close.call_count == 1
        assert fake_instance.start.call_count == 2


# ---------------------------------------------------------------------------
# 5. BaseCollector.fetch_source 集成
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_base_collector_falls_back_to_aiohttp_when_crawl4ai_unavailable(
    monkeypatch,
):
    """crawl4ai 不可用 → BaseCollector 走原始 aiohttp 路径,产出 items。"""
    monkeypatch.setenv("USE_CRAWL4AI", "0")

    from backend.collectors.base import BaseCollector
    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem
    from datetime import datetime, timezone

    class StubCollector(BaseCollector):
        category = Category.AI
        sources = [
            {"name": "stub", "url": "https://example.com/", "score": 70}
        ]
        timeout = 5
        max_items = 5

        def _fallback(self) -> list[HotspotItem]:
            return []

    # mock aiohttp 响应,返回含 entry-title 的 HTML
    # Phase 25: 标题需命中 AI 关键词白名单 (避免 _title_relevant 拒绝)
    sample_html = """
    <html><body>
      <h2 class="entry-title">
        <a href="https://example.com/article-1" rel="bookmark">New GPT Model Release</a>
      </h2>
      <h2 class="entry-title">
        <a href="https://example.com/article-2" rel="bookmark">DeepSeek LLM Training Update</a>
      </h2>
    </body></html>
    """

    class FakeResp:
        status = 200
        async def text(self):
            return sample_html
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResp()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    c = StubCollector()
    # Bypass quality gates for test simplicity
    c._skip_quality = True
    monkeypatch.setattr(
        "backend.collectors.base._session_factory", lambda: FakeSession
    )

    items, sr = await c.fetch_source(c.sources[0])
    assert sr.error_msg is None
    assert len(items) == 2
    assert items[0].title == "New GPT Model Release"
    assert items[1].title == "DeepSeek LLM Training Update"


@pytest.mark.asyncio
async def test_base_collector_falls_back_to_aiohttp_when_crawl4ai_returns_none(
    monkeypatch,
):
    """crawl4ai 开关开但 fetch_html 返回 None → 降级 aiohttp,仍能产出 items。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    from backend.collectors.base import BaseCollector
    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem

    class StubCollector(BaseCollector):
        category = Category.AI
        sources = [
            {"name": "stub", "url": "https://example.com/", "score": 70,
             "renderer": "crawl4ai"},  # Phase 14: 显式声明走 crawl4ai
        ]
        timeout = 5
        max_items = 5

        def _fallback(self) -> list[HotspotItem]:
            return []

    sample_html = """
    <html><body>
      <h2 class="entry-title">
        <a href="https://example.com/a1" rel="bookmark">GPT-5 Article A1</a>
      </h2>
    </body></html>
    """

    class FakeResp:
        status = 200
        async def text(self):
            return sample_html
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResp()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    c = StubCollector()
    c._skip_quality = True

    # crawl4ai 标为可用,但 fetch_html 返回 None (模拟超时 / 失败)
    # 注: base.py 走的是它自己 import 的 fetch_html 引用,patch 那里
    with patch(
        "backend.collectors.base.fetch_html",
        AsyncMock(return_value=None),
    ), patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), patch(
        "backend.collectors.base.crawl4ai_available", return_value=True
    ), patch(
        "backend.collectors.base._session_factory", lambda: FakeSession
    ):
        items, sr = await c.fetch_source(c.sources[0])
        # 走 aiohttp 路径应该仍然能拿到 1 个 item
        assert sr.error_msg is None
        assert len(items) == 1
        assert items[0].title == "GPT-5 Article A1"


@pytest.mark.asyncio
async def test_base_collector_uses_crawl4ai_html_when_available(monkeypatch):
    """crawl4ai 可用且返回 HTML → 优先用 crawl4ai 的 HTML,不调 aiohttp。"""
    monkeypatch.setenv("USE_CRAWL4AI", "1")

    from backend.collectors.base import BaseCollector
    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem

    class StubCollector(BaseCollector):
        category = Category.AI
        sources = [
            {"name": "stub", "url": "https://example.com/", "score": 70,
             "renderer": "crawl4ai"},  # Phase 14: 显式声明走 crawl4ai
        ]
        timeout = 5
        max_items = 5

        def _fallback(self) -> list[HotspotItem]:
            return []

    js_rendered_html = """
    <html><body>
      <h2 class="entry-title">
        <a href="https://example.com/js1" rel="bookmark">JS Rendered GPT Article</a>
      </h2>
      <h2 class="entry-title">
        <a href="https://example.com/js2" rel="bookmark">JS LLM Article</a>
      </h2>
    </body></html>
    """

    c = StubCollector()
    c._skip_quality = True

    # mock aiohttp — 如果调用了应该 fail,证明没走 aiohttp
    aiohttp_called = {"count": 0}

    class BoomSession:
        def get(self, url, **kwargs):
            aiohttp_called["count"] += 1
            raise RuntimeError("aiohttp should NOT be called")
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    with patch(
        "backend.collectors.base.fetch_html",
        AsyncMock(return_value=js_rendered_html),
    ), patch.object(crawl4ai_client, "HAS_CRAWL4AI", True), patch(
        "backend.collectors.base.crawl4ai_available", return_value=True
    ), patch(
        "backend.collectors.base._session_factory", lambda: BoomSession
    ):
        items, sr = await c.fetch_source(c.sources[0])
        assert sr.error_msg is None
        assert len(items) == 2
        assert items[0].title == "JS Rendered GPT Article"
        assert aiohttp_called["count"] == 0  # 关键:crawl4ai 成功时 aiohttp 不调用


__all__ = [
    "test_is_available_false_when_env_unset",
    "test_is_available_false_when_env_true_but_no_module",
    "test_is_available_true_when_env_true_and_module_installed",
    "test_fetch_html_returns_none_when_unavailable",
    "test_fetch_html_returns_none_when_module_missing",
    "test_fetch_html_timeout_returns_none",
    "test_fetch_html_arun_exception_returns_none",
    "test_fetch_html_success_false_returns_none",
    "test_fetch_html_empty_content_returns_none",
    "test_fetch_html_returns_html_when_success",
    "test_fetch_html_falls_back_to_markdown",
    "test_get_client_singleton",
    "test_get_client_returns_none_when_unavailable",
    "test_get_client_returns_none_on_init_failure",
    "test_close_client_releases_singleton",
    "test_base_collector_falls_back_to_aiohttp_when_crawl4ai_unavailable",
    "test_base_collector_falls_back_to_aiohttp_when_crawl4ai_returns_none",
    "test_base_collector_uses_crawl4ai_html_when_available",
]
