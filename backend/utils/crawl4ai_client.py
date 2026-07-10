"""Phase 11 — crawl4ai 适配层 (Playwright-based async crawler).

背景
----
项目原始 6 个 collector 全部走 ``BaseCollector.fetch_source`` 默认实现
(aiohttp + raw HTML + 正则解析)。问题:

- JS 渲染的 SPA 页面 (GitHub Trending) 拿不到真实数据
- 有 anti-bot 的中文站点 (36kr/量子位/雪球) 经常被拦
- 复杂页面噪声多,标题/链接容易抓错

crawl4ai (https://github.com/unclecode/crawl4ai) 提供
``AsyncWebCrawler().arun(url)`` 接口,内部跑 Playwright + Chromium,
返回 fully-rendered HTML / Markdown,可直接喂给 ``_parse_html``。

设计要点
--------
1. **可选依赖** — ``import crawl4ai`` 失败时 ``HAS_CRAWL4AI=False``,
   ``BaseCollector`` 走原始 aiohttp 路径 (向后兼容)。
2. **进程级单例** — Playwright 启动一次 5-10s,每个请求都新建 crawler
   会把 50+ 源跑成分钟级。``get_client()`` 返回全局单例。
3. **优雅降级** — ``fetch_html()`` 任何异常都返回 ``None``,调用方
   (collector) 决定 fallback 到 aiohttp 还是放弃该源。
4. **超时严格** — 用 ``asyncio.wait_for`` 包裹 arun,避免 Playwright
   内部 hang 死锁整个 collect 任务。
5. **环境变量开关** — ``USE_CRAWL4AI=1`` 才走 crawl4ai 路径 (默认关,
   单元测试环境无 Chromium 也能跑)。

Usage
-----
::

    from backend.utils.crawl4ai_client import fetch_html, close_client

    html = await fetch_html("https://news.ycombinator.com/", timeout=20)
    if html is None:
        # crawl4ai 失败 / 不可用 → caller 走 aiohttp 兜底
        ...
    await close_client()  # FastAPI shutdown 时调用
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from backend.logging_config import logger

# ----------------------------------------------------------------------
# Optional import — crawl4ai 是可选依赖
# ----------------------------------------------------------------------
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # type: ignore
    HAS_CRAWL4AI = True
except ImportError:  # pragma: no cover — 没装 crawl4ai 时
    AsyncWebCrawler = None  # type: ignore
    CrawlerRunConfig = None  # type: ignore
    HAS_CRAWL4AI = False

# 环境变量开关 — 默认关 (测试 / 无 Chromium 环境)
#   USE_CRAWL4AI=1 → 启用 crawl4ai
#
# 注: 这里只把开关字面量读出来作为 default;``is_available()`` 每次
# 调用时 re-read env,方便测试 monkeypatch 切换 + 生产环境热切换。
USE_CRAWL4AI_DEFAULT: bool = os.getenv("USE_CRAWL4AI", "0").lower() in (
    "1",
    "true",
    "yes",
)

# 并发控制 — Playwright 单浏览器实例同时处理多 tab 会内存爆炸,
# 限制最多 3 个并发渲染请求 (其余排队等待,避免 OOM)。
# 通过环境变量 CRAWL4AI_CONCURRENCY 可调。
_MAX_CONCURRENCY: int = int(os.getenv("CRAWL4AI_CONCURRENCY", "3"))
_concurrency_sem: Optional[asyncio.Semaphore] = None


# Phase 30: 真实浏览器 stealth 配置 (绕过 Playwright 自动化检测)
# 之前 ``_client = AsyncWebCrawler()`` 用了默认 BrowserConfig(enable_stealth=False),
# 导致 GitHub Trending / 政府站被反爬 (HTTP 403) → 抓取失败。
# 现在显式开启 stealth + 真实 Mac/Chrome 130 UA + 真实 viewport + 真实 args。
STEALTH_BROWSER_CONFIG: dict = {
    "browser_type": "chromium",
    "headless": True,
    # Phase 30: 不用 enable_stealth=True (crawl4ai 0.9.0 + stealth 组合导致
    # ERR_ABORTED 60s 抓取失败), 改用真实 UA + 真实 args 已能绕过大多数反爬
    "enable_stealth": False,
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "user_agent_mode": "real",  # 不随机化, 用真实 UA
    "viewport_width": 1440,
    "viewport_height": 900,
    "java_script_enabled": True,
    "ignore_https_errors": True,
    "extra_args": [
        "--disable-blink-features=AutomationControlled",  # 移除 navigator.webdriver
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-infobars",
    ],
}


def _get_semaphore() -> asyncio.Semaphore:
    """惰性创建 Semaphore (避免在模块加载时绑定错误的 event loop)。"""
    global _concurrency_sem
    if _concurrency_sem is None:
        _concurrency_sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    return _concurrency_sem


def is_available() -> bool:
    """crawl4ai 是否可用 (装了 + 开关打开)。

    每次重新读 env,便于测试 monkeypatch 和运行时切换。
    """
    use = os.getenv("USE_CRAWL4AI", "0").lower() in ("1", "true", "yes")
    return HAS_CRAWL4AI and use


# ----------------------------------------------------------------------
# 进程级单例
# ----------------------------------------------------------------------
_client: Optional["AsyncWebCrawler"] = None  # type: ignore[type-arg]
_client_lock = asyncio.Lock()


async def get_client() -> Optional["AsyncWebCrawler"]:  # type: ignore[type-arg]
    """获取 AsyncWebCrawler 单例,首次调用时启动 Playwright。

    Returns
    -------
    AsyncWebCrawler 实例,或 None (crawl4ai 不可用时)。
    """
    global _client
    if not is_available():
        return None
    if _client is not None:
        return _client
    async with _client_lock:
        # double-check (避免并发首次调用重复创建)
        if _client is None:
                try:
                    # Phase 30: 真实 Mac/Chrome 130 UA, 通过 CrawlerRunConfig 设置
                    # (BrowserConfig enable_stealth / user_agent_mode 跟 crawl4ai 0.9
                    # 兼容性有问题, 暂时用纯 CrawlerRunConfig 真实 UA 方案)
                    _client = AsyncWebCrawler()  # type: ignore[call-arg]
                    await _client.start()
                    logger.info("crawl4ai AsyncWebCrawler started (real UA via CrawlerRunConfig)")
                except Exception as e:
                    logger.warning(
                        f"crawl4ai client init failed: "
                        f"{type(e).__name__}: {str(e)[:100]}"
                    )
                    _client = None
        return _client


async def close_client() -> None:
    """关闭全局单例 (FastAPI shutdown / 测试 teardown)。"""
    global _client
    if _client is None:
        return
    try:
        await _client.close()
    except Exception as e:
        logger.warning(f"crawl4ai client close failed: {e}")
    finally:
        _client = None


# ----------------------------------------------------------------------
# Public API — 抓单个 URL 的 HTML
# ----------------------------------------------------------------------
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def fetch_html(
    url: str,
    *,
    timeout: int = 30,
    user_agent: str = DEFAULT_UA,
    use_stealth: bool = True,
) -> Optional[str]:
    """用 crawl4ai 抓取单个 URL 的 **fully-rendered HTML**。

    Returns
    -------
    HTML 字符串,或 ``None`` (crawl4ai 不可用 / 抓取失败)。

    失败原因覆盖:crawl4ai 未装 / 开关未开 / 启动失败 / 单次超时 /
    arun 内部异常 / 返回 success=False。**任何失败都返回 None**,
    caller 决定 fallback 到 aiohttp 还是放弃。
    """
    if not is_available():
        return None
    client = await get_client()
    if client is None:
        return None

    # 并发限制 — 多个源同时 arun 会让单例浏览器 OOM
    sem = _get_semaphore()
    async with sem:
        try:
            # CrawlerRunConfig 用来设置 UA / 等待策略 / 反爬绕过
            # 防御性: CrawlerRunConfig 可能在不同 crawl4ai 版本 API 略有差异
            config = None
            if CrawlerRunConfig is not None:
                try:
                    # crawl4ai 0.8.9: bypass_cache deprecated → cache_mode=CacheMode.BYPASS
                    cfg_kwargs = {
                        "user_agent": user_agent,
                        "page_timeout": timeout * 1000,  # ms
                    }
                    # 优先用 cache_mode (新 API)
                    try:
                        from crawl4ai import CacheMode  # type: ignore
                        cfg_kwargs["cache_mode"] = CacheMode.BYPASS
                    except ImportError:
                        cfg_kwargs["bypass_cache"] = True  # 老版本 fallback
                    config = CrawlerRunConfig(**cfg_kwargs)
                except Exception:
                    # 老版本 CrawlerRunConfig 字段不同时 fallback
                    config = None

            try:
                coro = client.arun(url=url, config=config) if config else client.arun(url=url)
                result = await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"crawl4ai fetch timeout ({timeout}s): {url}")
                return None
            except Exception as e:
                logger.warning(
                    f"crawl4ai fetch error: {url} - "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )
                return None

            # crawl4ai 返回 CrawlResult 对象
            success = getattr(result, "success", None)
            if success is False:
                err = getattr(result, "error_message", "") or "unknown"
                logger.warning(f"crawl4ai success=False for {url}: {err[:100]}")
                return None

            # 优先拿 .html (与现有 _parse_html 正则兼容);fallback 到 markdown
            html = getattr(result, "html", None) or getattr(result, "markdown", None)
            if not html:
                logger.warning(f"crawl4ai returned empty content for {url}")
                return None
            return str(html)
        except Exception as e:
            # 任何未预期的异常,统一降级
            logger.warning(
                f"crawl4ai fetch_html unhandled error: {url} - "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return None


__all__ = [
    "HAS_CRAWL4AI",
    "USE_CRAWL4AI_DEFAULT",
    "is_available",
    "get_client",
    "close_client",
    "fetch_html",
]
