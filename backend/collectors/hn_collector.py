"""HackerNews 热点数据采集器 (Phase 11)。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.TECH``
- ``sources``   : HackerNews Firestore API
- ``timeout``   : 20s
- ``max_items`` : 30 (HN top stories 截取)

HN API 是两阶段请求：
1. GET /v0/topstories.json → 返回 500 个 story ID 数组
2. 取前 30 个 ID，并发 GET /v0/item/{id}.json → 返回 story 详情

每个 story 使用可读 ID ``hn:item:{story_id}`` (Phase 11 约定)。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from backend.collectors.base import BaseCollector
from backend.collectors.id_factory import make_readable_id
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.parsers.crawl4ai_parser import CrawlResult

HN_SOURCES: list[dict] = [
    {
        "name": "HackerNews",
        "url": "https://hacker-news.firebaseio.com/v0/",
        "api_url": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "score": 85,
        "keywords": ["tech", "startup", "programming"],
    },
]


class HNCollector(BaseCollector):
    """HackerNews 热点数据采集器。

    HN Firestore API 是两阶段请求:
    1. GET /v0/topstories.json → 获取 top story ID 列表
    2. 并发 GET /v0/item/{id}.json → 获取 story 详情
    """

    category = Category.TECH
    sources = HN_SOURCES
    timeout = 20
    max_items = 30
    min_items_threshold = 3

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """Parse HN story dicts into raw items.

        ``data`` 是 ``list[dict]``，每个 dict 对应一个 story 详情
        (来自 GET /v0/item/{id}.json 响应)。

        返回 ``[{"id": ..., "title": ..., "url": ...,
                  "published_at": datetime|None}, ...]``
        """
        out: list[dict[str, Any]] = []
        for story in data or []:
            if not isinstance(story, dict):
                continue
            title = (story.get("title") or "").strip()
            url = (story.get("url") or "").strip()
            if not title or not url:
                continue
            story_id = story.get("id")
            if story_id is None:
                continue
            # HN API 返回的 time 是 Unix timestamp
            published_ts = story.get("time")
            published_at: datetime | None = None
            if published_ts:
                try:
                    published_at = datetime.fromtimestamp(
                        int(published_ts), tz=timezone.utc
                    )
                except (ValueError, OSError):
                    published_at = None
            out.append(
                {
                    "id": story_id,
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                }
            )
        return out

    async def fetch_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], SourceResult]:
        """Override: 两阶段 HN API 抓取。

        1. GET /v0/topstories.json → 取前 ``max_items`` 个 story ID
        2. 并发 GET /v0/item/{id}.json → 构建 HotspotItem

        Phase 13 硬约束: 失败时返回空列表,不生成合成 fallback 数据。
        """
        from backend.collectors import base as _base

        start = datetime.now(timezone.utc)
        api_url = source.get("api_url") or source["url"]
        source_name = source.get("name", "?")
        source_url = source.get("url", api_url)

        try:
            session_cls = _base._session_factory()

            # ---- Step 1: fetch top story IDs ----
            async with session_cls() as session:  # type: ignore
                async with session.get(
                    api_url,
                    headers={"User-Agent": _base.UA},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(
                            f"topstories HTTP {resp.status}"
                        )
                    story_ids: list[Any] = await resp.json(content_type=None)

            story_ids = [int(sid) for sid in (story_ids or [])]
            if not story_ids:
                raise ValueError("no story IDs returned from HN API")

            # 取前 max_items 个
            story_ids = story_ids[: self.max_items]

            # ---- Step 2: 并发 fetch story details ----
            async def fetch_story(
                sid: int,
            ) -> dict[str, Any] | None:
                item_url = (
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                )
                try:
                    async with session_cls() as s:  # type: ignore
                        async with s.get(
                            item_url,
                            headers={"User-Agent": _base.UA},
                            timeout=aiohttp.ClientTimeout(
                                total=self.timeout
                            ),
                            ssl=False,
                        ) as resp2:
                            if resp2.status != 200:
                                return None
                            return await resp2.json(content_type=None)
                except Exception:
                    return None

            tasks = [fetch_story(sid) for sid in story_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # ---- Step 3: _parse_json → raw items ----
            valid_stories = [
                r for r in results if isinstance(r, dict)
            ]
            raw_items = self._parse_json(valid_stories, source)

            # ---- Step 4: 构建 HotspotItem (用 readable ID) ----
            now = datetime.now(timezone.utc)
            items: list[HotspotItem] = []
            for raw in raw_items:
                readable_id = make_readable_id(
                    "hn", "item", str(raw["id"])
                )
                published_at = raw.get("published_at") or now
                items.append(
                    HotspotItem(
                        id=readable_id,
                        title=raw["title"][:500],
                        source="HackerNews",
                        url=raw["url"],
                        category=self.category,
                        published_at=published_at,
                        fetched_at=now,
                        ingested_at=now,
                        score=source.get("score", 85),
                    )
                )

            if not items:
                raise ValueError("no valid items from HN stories")

            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            return items, SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=len(items),
                duration_ms=duration,
            )

        except Exception as e:
            self.logger.warning(
                f"hn fetch failed: {type(e).__name__}: {str(e)[:100]}"
            )
            # Phase 16: Crawl4ai fallback for thread/comment pages
            crawl4ai_result = await self._fetch_with_crawl4ai(source_url)
            if crawl4ai_result.success:
                items = [HotspotItem(
                    id=make_readable_id("hn", "crawl", str(hash(crawl4ai_result.url))),
                    title=crawl4ai_result.title[:500] or "HN: " + source_url,
                    source="HackerNews",
                    url=source_url,
                    category=self.category,
                    published_at=datetime.now(timezone.utc),
                    fetched_at=datetime.now(timezone.utc),
                    ingested_at=datetime.now(timezone.utc),
                    score=source.get("score", 85),
                )]
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                return items, SourceResult(
                    source_name=source_name,
                    source_url=source_url,
                    item_count=1,
                    duration_ms=duration,
                )
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg=f"{type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

    async def _fetch_with_crawl4ai(self, url: str) -> CrawlResult:
        """Phase 16: Crawl4ai fallback for comment/thread pages."""
        try:
            from backend.parsers.crawl4ai_parser import Crawl4aiParser
            parser = Crawl4aiParser()
            return await parser.crawl(url)
        except ImportError:
            return CrawlResult(url=url, success=False, error="Crawl4aiParser not available")
        except Exception as e:
            self.logger.warning(f"crawl4ai fallback failed: {e}")
            return CrawlResult(url=url, success=False, error=str(e))


__all__ = ["HN_SOURCES", "HNCollector"]