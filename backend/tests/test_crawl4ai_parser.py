"""Crawl4aiParser 单元测试.

覆盖 Crawl4aiParser 的配置加载、启用/禁用状态、错误处理、成功/失败路径、
以及 CrawlResult 数据类。

crawl4ai 是可选依赖，所有测试均通过 mock 隔离，无需安装 crawl4ai。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from backend.parsers.crawl4ai_parser import Crawl4aiParser, CrawlResult

# ---------------------------------------------------------------------------
# 1. CrawlResult 数据类
# ---------------------------------------------------------------------------


def test_crawl_result_defaults():
    """CrawlResult 默认值：success=False, 字符串字段为空, error=None, metadata={}。"""
    r = CrawlResult(url="https://example.com")
    assert r.url == "https://example.com"
    assert r.title == ""
    assert r.content == ""
    assert r.markdown == ""
    assert r.success is False
    assert r.error is None
    assert r.metadata == {}


def test_crawl_result_full_fields():
    """CrawlResult 全字段赋值后取值正确。"""
    r = CrawlResult(
        url="https://example.com/article",
        title="Test Title",
        content="<p>html content</p>",
        markdown="# Markdown",
        success=True,
        error=None,
        metadata={"source": "test", "cached": True},
    )
    assert r.title == "Test Title"
    assert r.content == "<p>html content</p>"
    assert r.markdown == "# Markdown"
    assert r.success is True
    assert r.error is None
    assert r.metadata == {"source": "test", "cached": True}


# ---------------------------------------------------------------------------
# 2. 配置加载
# ---------------------------------------------------------------------------


def test_load_config_missing_file(tmp_path):
    """_load_config 在文件不存在时返回默认配置 {crawl4ai: {enabled: False}}。"""
    missing = tmp_path / "nonexistent.yaml"
    config = Crawl4aiParser._load_config(missing)
    assert config == {"crawl4ai": {"enabled": False}}


def test_load_config_from_yaml(tmp_path):
    """_load_config 正确解析 YAML 配置。"""
    config_data = {
        "crawl4ai": {
            "enabled": True,
            "browser": "firefox",
            "headless": False,
            "timeout_seconds": 60,
        }
    }
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config_data, f)

    config = Crawl4aiParser._load_config(p)
    assert config["crawl4ai"]["enabled"] is True
    assert config["crawl4ai"]["browser"] == "firefox"
    assert config["crawl4ai"]["headless"] is False
    assert config["crawl4ai"]["timeout_seconds"] == 60


def test_load_config_empty_yaml(tmp_path):
    """_load_config 遇到空 YAML 文件返回空 dict。"""
    p = tmp_path / "empty.yaml"
    p.touch()
    config = Crawl4aiParser._load_config(p)
    assert config == {}


# ---------------------------------------------------------------------------
# 3. 构造函数与默认代理池
# ---------------------------------------------------------------------------


def test_constructor_default_proxy_pool():
    """未传入 proxy_pool_instance 时使用全局 proxy_pool 单例。"""
    from backend.parsers.crawl4ai_parser import proxy_pool as default_pool

    parser = Crawl4aiParser(crawl_config_path=Path("/nonexistent"))
    assert parser._proxy_pool is default_pool


def test_constructor_custom_proxy_pool():
    """传入自定义 proxy_pool_instance 后优先使用。"""
    mock_pool = MagicMock()
    parser = Crawl4aiParser(
        crawl_config_path=Path("/nonexistent"),
        proxy_pool_instance=mock_pool,
    )
    assert parser._proxy_pool is mock_pool


# ---------------------------------------------------------------------------
# 4. 禁用状态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_disabled(tmp_path):
    """crawl4ai.enabled=False → crawl() 直接返回 CrawlResult(success=False, error='Crawl4ai disabled')。"""
    config = {"crawl4ai": {"enabled": False}}
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    parser = Crawl4aiParser(crawl_config_path=p)
    result = await parser.crawl("https://example.com")

    assert result.success is False
    assert result.error == "Crawl4ai disabled"
    assert result.url == "https://example.com"
    # 确保未调用 _crawl_with_crawl4ai
    assert parser._enabled is False


# ---------------------------------------------------------------------------
# 5. 错误处理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_importerror(tmp_path):
    """crawl4ai 未安装 → _crawl_with_crawl4ai 抛出 ImportError → crawl() 捕获并返回 CrawlResult(success=False)。"""
    config = {"crawl4ai": {"enabled": True}}
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    parser = Crawl4aiParser(crawl_config_path=p)
    with patch.object(
        parser,
        "_crawl_with_crawl4ai",
        AsyncMock(side_effect=ImportError("No module named crawl4ai")),
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is False
    assert "No module named crawl4ai" in result.error


@pytest.mark.asyncio
async def test_crawl_general_error(tmp_path):
    """_crawl_with_crawl4ai 抛出任意 Exception → crawl() 捕获并返回 CrawlResult(success=False)。"""
    config = {"crawl4ai": {"enabled": True}}
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    parser = Crawl4aiParser(crawl_config_path=p)
    with patch.object(
        parser,
        "_crawl_with_crawl4ai",
        AsyncMock(side_effect=RuntimeError("chromium crashed")),
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is False
    assert "chromium crashed" in result.error


# ---------------------------------------------------------------------------
# 6. _crawl_with_crawl4ai 成功 / 失败路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_success(tmp_path):
    """_crawl_with_crawl4ai 成功 → mark_success 被调用, CrawlResult 含完整内容。"""
    config = {
        "crawl4ai": {
            "enabled": True,
            "browser": "chromium",
            "headless": True,
            "timeout_seconds": 30,
        }
    }
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    mock_pool = MagicMock()
    mock_pool.get_next.return_value = "http://proxy:8080"

    parser = Crawl4aiParser(crawl_config_path=p, proxy_pool_instance=mock_pool)

    # 模拟 crawl4ai 返回结果
    mock_crawl_result = MagicMock()
    mock_crawl_result.success = True
    mock_crawl_result.markdown = "# Hello World\n\nThis is content."
    mock_crawl_result.metadata = {"title": "Test Page"}

    mock_crawler = AsyncMock()
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.arun.return_value = mock_crawl_result

    mock_async_web_crawler = MagicMock(return_value=mock_crawler)

    # 模拟 crawl4ai 模块（延迟导入，需要 patch sys.modules）
    crawl4ai_mod = MagicMock()
    crawl4ai_mod.AsyncWebCrawler = mock_async_web_crawler
    async_configs_mod = MagicMock()
    async_configs_mod.BrowserConfig = MagicMock()
    async_configs_mod.CrawlerRunConfig = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "crawl4ai": crawl4ai_mod,
            "crawl4ai.async_configs": async_configs_mod,
        },
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is True
    assert result.title == "Test Page"
    assert result.content == "# Hello World\n\nThis is content."
    assert result.markdown == "# Hello World\n\nThis is content."
    assert result.metadata == {"title": "Test Page"}
    mock_pool.mark_success.assert_called_once_with("http://proxy:8080")
    mock_pool.mark_failed.assert_not_called()


@pytest.mark.asyncio
async def test_crawl_result_failure(tmp_path):
    """_crawl_with_crawl4ai 返回 success=False → mark_failed 被调用, CrawlResult 含错误信息。"""
    config = {
        "crawl4ai": {
            "enabled": True,
            "browser": "chromium",
            "headless": True,
            "timeout_seconds": 30,
        }
    }
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    mock_pool = MagicMock()
    mock_pool.get_next.return_value = "http://proxy:8080"

    parser = Crawl4aiParser(crawl_config_path=p, proxy_pool_instance=mock_pool)

    mock_crawl_result = MagicMock()
    mock_crawl_result.success = False
    mock_crawl_result.error_message = "Blocked by Cloudflare"

    mock_crawler = AsyncMock()
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.arun.return_value = mock_crawl_result

    mock_async_web_crawler = MagicMock(return_value=mock_crawler)

    crawl4ai_mod = MagicMock()
    crawl4ai_mod.AsyncWebCrawler = mock_async_web_crawler
    async_configs_mod = MagicMock()
    async_configs_mod.BrowserConfig = MagicMock()
    async_configs_mod.CrawlerRunConfig = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "crawl4ai": crawl4ai_mod,
            "crawl4ai.async_configs": async_configs_mod,
        },
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is False
    assert result.error == "Blocked by Cloudflare"
    mock_pool.mark_failed.assert_called_once_with("http://proxy:8080")
    mock_pool.mark_success.assert_not_called()


@pytest.mark.asyncio
async def test_crawl_success_no_proxy(tmp_path):
    """无代理配置时 get_next 返回空字符串 → crawl 仍正常执行。"""
    config = {"crawl4ai": {"enabled": True}}
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    mock_pool = MagicMock()
    mock_pool.get_next.return_value = ""  # 无代理

    parser = Crawl4aiParser(crawl_config_path=p, proxy_pool_instance=mock_pool)

    mock_crawl_result = MagicMock()
    mock_crawl_result.success = True
    mock_crawl_result.markdown = "content"
    mock_crawl_result.metadata = {"title": "No Proxy"}

    mock_crawler = AsyncMock()
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.arun.return_value = mock_crawl_result

    mock_async_web_crawler = MagicMock(return_value=mock_crawler)

    crawl4ai_mod = MagicMock()
    crawl4ai_mod.AsyncWebCrawler = mock_async_web_crawler
    async_configs_mod = MagicMock()
    async_configs_mod.BrowserConfig = MagicMock()
    async_configs_mod.CrawlerRunConfig = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "crawl4ai": crawl4ai_mod,
            "crawl4ai.async_configs": async_configs_mod,
        },
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is True
    assert result.title == "No Proxy"


@pytest.mark.asyncio
async def test_crawl_failure_unknown_error(tmp_path):
    """crawl4ai 返回 success=False 且 error_message 为空 → 使用默认错误信息。"""
    config = {"crawl4ai": {"enabled": True}}
    p = tmp_path / "crawl_config.yaml"
    with open(p, "w") as f:
        yaml.dump(config, f)

    mock_pool = MagicMock()
    mock_pool.get_next.return_value = "http://proxy:8080"

    parser = Crawl4aiParser(crawl_config_path=p, proxy_pool_instance=mock_pool)

    mock_crawl_result = MagicMock()
    mock_crawl_result.success = False
    mock_crawl_result.error_message = None  # 无错误信息

    mock_crawler = AsyncMock()
    mock_crawler.__aenter__.return_value = mock_crawler
    mock_crawler.arun.return_value = mock_crawl_result

    mock_async_web_crawler = MagicMock(return_value=mock_crawler)

    crawl4ai_mod = MagicMock()
    crawl4ai_mod.AsyncWebCrawler = mock_async_web_crawler
    async_configs_mod = MagicMock()
    async_configs_mod.BrowserConfig = MagicMock()
    async_configs_mod.CrawlerRunConfig = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "crawl4ai": crawl4ai_mod,
            "crawl4ai.async_configs": async_configs_mod,
        },
    ):
        result = await parser.crawl("https://example.com")

    assert result.success is False
    assert result.error == "Unknown crawl error"


__all__ = [
    "test_constructor_custom_proxy_pool",
    "test_constructor_default_proxy_pool",
    "test_crawl_disabled",
    "test_crawl_failure_unknown_error",
    "test_crawl_general_error",
    "test_crawl_importerror",
    "test_crawl_result_defaults",
    "test_crawl_result_failure",
    "test_crawl_result_full_fields",
    "test_crawl_success",
    "test_crawl_success_no_proxy",
    "test_load_config_empty_yaml",
    "test_load_config_from_yaml",
    "test_load_config_missing_file",
]