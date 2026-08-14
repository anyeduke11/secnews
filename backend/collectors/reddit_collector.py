"""Reddit 热点数据采集器 (Phase 11).

继承 :class:`BaseCollector`：

- ``category``  : ``Category.TECH``
- ``sources``   : Reddit r/all/top JSON API
- ``max_items`` : 25 (限制 top 25 条)

Reddit JSON API 响应格式::

    {"data": {"children": [{"data": {"title", "url", "id",
                                     "score", "created_utc",
                                     "subreddit"}}]}}

走 ``renderer="json"`` 路由, 通过 ``_parse_json`` 解析。

Phase 13 硬约束: 所有源失败时返回空列表, 不生成合成 fallback 数据。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.collectors.id_factory import make_readable_id
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.parsers.crawl4ai_parser import CrawlResult

REDDIT_SOURCES: list[dict] = [
    {
        "name": "Reddit",
        "url": "https://www.reddit.com/r/all/top.json",
        "score": 80,
        "keywords": ["tech", "trending"],
        "headers": {"User-Agent": "hotspot-collector/1.0"},
        "renderer": "json",
    },
]


class RedditCollector(BaseCollector):
    """Reddit 热点数据采集器 (r/all/top JSON API)。"""

    category = Category.TECH
    sources = REDDIT_SOURCES
    max_items = 25

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """Reddit JSON API 解析。

        响应格式::

            {"data": {"children": [
                {"data": {"title": "...", "url": "...", "id": "...",
                          "score": 1234, "created_utc": 1234567890.0,
                          "subreddit": "..."}},
            ]}}
        """
        children = ((data or {}).get("data") or {}).get("children") or []
        out: list[dict[str, Any]] = []
        for entry in children:
            if not isinstance(entry, dict):
                continue
            post = entry.get("data") or {}
            title = (post.get("title") or "").strip()
            url = (post.get("url") or "").strip()
            post_id = post.get("id") or ""
            created_utc = post.get("created_utc")
            if not title or not url or not post_id or created_utc is None:
                continue

            readable_id = make_readable_id("reddit", "post", post_id)
            published = datetime.fromtimestamp(
                created_utc, tz=timezone.utc
            )

            out.append(
                {
                    "id": readable_id,
                    "title": title,
                    "url": url,
                    "published_at": published,
                    "source": "Reddit",
                }
            )
            if len(out) >= self.max_items:
                break
        return out

    # Phase 13 硬约束: 不实现 _fallback(), 所有源失败时 collect()
    # 直接返回 []。

    async def fetch_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], SourceResult]:
        """Override: 先走父类标准流程, 失败时通过 Crawl4ai 兜底抓取 Reddit 详情页."""
        from datetime import datetime
        from datetime import timezone as _tz

        start = datetime.now(_tz.utc)
        source_name = source.get("name", "Reddit")
        source_url = source["url"]

        # 第 1 步: 父类标准流程 (JSON API)
        items, result = await super().fetch_source(source)

        # 如果拿到了数据, 直接返回
        if items:
            return items, result

        # 第 2 步: 父类失败, 走 Crawl4ai 兜底 (适合 Reddit 详情页等需要 JS 渲染的页面)
        self.logger.info("Reddit fetch_source returned empty, trying Crawl4ai fallback for %s", source_url)
        crawl4ai_result = await self._fetch_with_crawl4ai(source_url)
        if crawl4ai_result.success:
            raw_items = self._parse_crawl4ai_result(crawl4ai_result, source)
            items = self._build_items(raw_items, source)
            duration = int((datetime.now(_tz.utc) - start).total_seconds() * 1000)
            return items, SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=len(items),
                duration_ms=duration,
            )

        return items, result

    async def _fetch_with_crawl4ai(self, url: str) -> CrawlResult:
        """Phase 16: Crawl4ai fallback for Reddit detail pages."""
        try:
            from backend.parsers.crawl4ai_parser import Crawl4aiParser
            parser = Crawl4aiParser()
            return await parser.crawl(url)
        except ImportError:
            return CrawlResult(url=url, success=False, error="Crawl4aiParser not available")
        except Exception as e:
            self.logger.warning(f"crawl4ai fallback failed: {e}")
            return CrawlResult(url=url, success=False, error=str(e))

    def _parse_crawl4ai_result(self, result: CrawlResult, source: dict) -> list[dict]:
        """将 Crawl4ai 抓取结果解析为 raw item dict 列表。"""
        if not result.success or not result.title:
            return []
        readable_id = make_readable_id("reddit", "crawl", str(hash(result.url)))
        return [{
            "id": readable_id,
            "title": result.title[:500],
            "url": result.url,
            "published_at": None,
            "source": "Reddit",
        }]


__all__ = ["REDDIT_SOURCES", "RedditCollector"]