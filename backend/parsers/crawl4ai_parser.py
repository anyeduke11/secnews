"""Crawl4ai + Playwright 统一代理包装器.

Phase 16 — Crawl4ai 高阶抓取集成。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Crawl4aiParser:
    """Crawl4ai + Playwright 统一代理包装器.

    注意：crawl4ai 和 playwright 是可选依赖，未安装时 crawl() 返回空结果。
    """

    def __init__(
        self,
        crawl_config_path: Optional[Path] = None,
        proxy_pool_instance: Optional[ProxyPool] = None,
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
        """实际调用 Crawl4ai 进行抓取（延迟导入，避免可选依赖报错）。"""
        # 延迟导入 crawl4ai
        from crawl4ai import AsyncWebCrawler
        from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

        proxy = self._proxy_pool.get_next()
        browser_cfg = BrowserConfig(
            browser_type=self._config["crawl4ai"].get("browser", "chromium"),
            headless=self._config["crawl4ai"].get("headless", True),
            proxy=proxy if proxy else None,
        )
        run_cfg = CrawlerRunConfig(
            verbose=True,
            timeout=self._config["crawl4ai"].get("timeout_seconds", 30),
        )

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

        if result.success:
            self._proxy_pool.mark_success(proxy)
            return CrawlResult(
                url=url,
                title=result.metadata.get("title", "") if result.metadata else "",
                content=result.markdown or "",
                markdown=result.markdown or "",
                success=True,
                metadata=result.metadata or {},
            )
        else:
            self._proxy_pool.mark_failed(proxy)
            return CrawlResult(
                url=url,
                success=False,
                error=result.error_message or "Unknown crawl error",
            )


__all__ = ["Crawl4aiParser", "CrawlResult"]