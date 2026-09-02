"""Crawl4ai 详情页抓取包装器.

Phase 16 — Crawl4ai 高阶抓取集成。
gateway 方案 §3.1 改② — 复用 utils/crawl4ai_client 进程级单例,
不再每次抓取新建浏览器实例。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.services.proxy_pool import ProxyPool, proxy_pool

logger = logging.getLogger("hotspot.crawl4ai")

DEFAULT_CRAWL_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "collectors" / "crawl_config.yaml"
)


@dataclass
class CrawlResult:
    """Crawl4ai 抓取结果."""
    url: str
    title: str = ""
    content: str = ""
    markdown: str = ""
    success: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Crawl4aiParser:
    """Crawl4ai + Playwright 统一代理包装器.

    注意：crawl4ai 和 playwright 是可选依赖，未安装时 crawl() 返回空结果。
    """

    def __init__(
        self,
        crawl_config_path: Path | None = None,
        proxy_pool_instance: ProxyPool | None = None,
    ):
        cfg_path = crawl_config_path or DEFAULT_CRAWL_CONFIG_PATH
        self._config = self._load_config(cfg_path)
        self._proxy_pool = proxy_pool_instance or proxy_pool
        self._enabled = self._config.get("crawl4ai", {}).get("enabled", False)

    @staticmethod
    def _load_config(path: Path) -> dict:
        if not path.exists():
            return {"crawl4ai": {"enabled": False}}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    async def crawl(self, url: str) -> CrawlResult:
        """主调用：通过 Crawl4ai 抓取 URL.

        如果 crawl4ai 未安装或未启用，返回空 CrawlResult。
        """
        if not self._enabled:
            logger.debug("Crawl4ai disabled, skipping %s", url)
            return CrawlResult(url=url, success=False, error="Crawl4ai disabled")

        try:
            return await self._crawl_with_crawl4ai(url)
        except ImportError as e:
            logger.warning("Crawl4ai not installed: %s", e)
            return CrawlResult(url=url, success=False, error=str(e))
        except Exception as e:
            logger.error("Crawl4ai error for %s: %s", url, e)
            return CrawlResult(url=url, success=False, error=str(e))

    async def _crawl_with_crawl4ai(self, url: str) -> CrawlResult:
        """实际调用 Crawl4ai 进行抓取（延迟导入，避免可选依赖报错）。

        gateway 方案 §3.1 改②: 复用 ``utils/crawl4ai_client.get_client()``
        进程级单例, 删除每次 ``async with AsyncWebCrawler()`` 新建浏览器
        (Playwright 启动 5-10s)。浏览器生命周期与并发信号量统一由 client
        层管理; 每请求级代理轮换随单例架构移除（BrowserConfig 在启动时
        固定），``_proxy_pool`` 属性保留以兼容既有构造调用方。
        """
        # 延迟导入 crawl4ai
        from crawl4ai.async_configs import CrawlerRunConfig

        from backend.utils.crawl4ai_client import get_client

        client = await get_client()
        if client is None:
            return CrawlResult(
                url=url,
                success=False,
                error="crawl4ai client unavailable",
            )

        # crawl4ai 0.9 的 CrawlerRunConfig 用 page_timeout (ms), 与
        # utils/crawl4ai_client.fetch_html 同一语义; 旧 timeout kwarg 会
        # TypeError → 每次抓取必失败 (本次回归测试暴露的存量 bug)。
        run_cfg = CrawlerRunConfig(
            verbose=True,
            page_timeout=self._config["crawl4ai"].get("timeout_seconds", 30) * 1000,
        )
        result = await client.arun(url=url, config=run_cfg)

        if result.success:
            return CrawlResult(
                url=url,
                title=result.metadata.get("title", "") if result.metadata else "",
                content=result.markdown or "",
                markdown=result.markdown or "",
                success=True,
                metadata=result.metadata or {},
            )
        else:
            return CrawlResult(
                url=url,
                success=False,
                error=result.error_message or "Unknown crawl error",
            )


__all__ = ["Crawl4aiParser", "CrawlResult"]