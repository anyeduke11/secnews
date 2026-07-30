"""抓取路径 Mixin（v1.8 R3 从 base.py 拆出）。

``FetchersMixin`` 承载 BaseCollector 的 4 条抓取路径：

- ``fetch_source``       — 路由总入口 (RSS → JSON → disabled → sogou → crawl4ai → aiohttp)
- ``_fetch_rss``         — Phase 22: feedparser 路径 (source 含 ``rss_url``)
- ``_fetch_json_source`` — Phase 25 P1: JSON API 路径 (``renderer="json"``)
- ``_fetch_sogou_source``— Phase 51: sogou 搜索路径 (``renderer="sogou"``)

patch 兼容约定（重要）
----------------------
测试通过 ``backend.collectors.base`` 命名空间 monkeypatch 以下符号：
``_session_factory`` / ``fetch_html`` / ``crawl4ai_available`` / ``UA``。
因此本模块 **不直接 import 这些符号**，而是在方法体内延迟
``from backend.collectors import base`` 并经模块属性运行时查找，
保证 patch ``backend.collectors.base.X`` 依旧生效。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from backend.domain.collection import SourceResult
from backend.domain.models import HotspotItem


class FetchersMixin:
    """BaseCollector 的抓取路径实现（依赖宿主类的
    ``logger`` / ``timeout`` / ``max_items`` / ``_parse_html`` /
    ``_parse_json`` / ``_build_items``）。"""

    # ------------------------------------------------------------------
    # Phase 22: RSS 抓取 (feedparser) — 用于源 dict 含 ``rss_url`` 字段时
    # ------------------------------------------------------------------
    async def _fetch_rss(
        self, source: dict, start: datetime | None = None
    ) -> tuple[list[HotspotItem], SourceResult]:
        """Phase 22: 走 RSS feed 抓取,跳过 _parse_html。

        设计动机: FreeBuf/SecWiki 等媒体首页导航/备案/评论链接密集,
        用 HTML anchor 抓取会被噪声淹没(典型症状是抓到 ``beian.miit.gov.cn``
        备案链接)。直接走 RSS 拿 article 列表,标题/URL/时间都来自
        <item>/<entry>,质量高且结构稳定。

        约定:
        - source["rss_url"] 必填
        - source["url"] 保留为主站 URL(给 SourceResult 用,不影响抓取)
        - 抓取失败 → 返回 ([], SourceResult(error))
        - entry title/link/published 缺一即跳过该 entry
        """
        if start is None:
            start = datetime.now(timezone.utc)
        rss_url = source["rss_url"]
        source_name = source.get("name", "?")
        source_url = source.get("url", rss_url)

        # feedparser 是同步库;用 asyncio.to_thread 跑,避免阻塞事件循环
        def _parse() -> dict[str, Any]:
            import feedparser  # type: ignore
            return feedparser.parse(rss_url)

        try:
            d = await asyncio.to_thread(_parse)
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"rss fetch crashed for {source_name}: "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg=f"rss_crash: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        status = d.get("status")
        bozo = d.get("bozo")
        entries = d.get("entries", [])
        if status is not None and status >= 400:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg=f"rss_http_{status}",
                duration_ms=duration,
            )
        if not entries:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg=f"rss_empty bozo={bozo}",
                duration_ms=duration,
            )

        # RSS entry → raw_items (与 _parse_html 输出一致),后续 _build_items 复用
        raw_items: list[dict[str, Any]] = []
        for e in entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            published_at: datetime | None = None
            pp = e.get("published_parsed") or e.get("updated_parsed")
            if pp is not None:
                try:
                    published_at = datetime(*pp[:6], tzinfo=timezone.utc)
                except Exception:
                    published_at = None
            raw_items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": (e.get("summary") or "").strip(),
                    "published_at": published_at,
                }
            )

        items = self._build_items(raw_items, source)
        duration = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        return items, SourceResult(
            source_name=source_name,
            source_url=source_url,
            item_count=len(items),
            duration_ms=duration,
        )

    # ------------------------------------------------------------------
    # 抓取（默认实现；子类可整体覆盖）
    # ------------------------------------------------------------------
    async def fetch_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], SourceResult]:
        """抓单个源并构建 ``HotspotItem``。失败返回 ``([], SourceResult(error))``。

        Subclass 可整体覆盖（例如改走 JSON API）。

        Phase 11 抓取策略 (Phase 14 精细化路由)
        ---------------------------------------
        1. **按源 renderer 字段路由**:
           - ``renderer="crawl4ai"`` → 走 Playwright 渲染 (JS SPA / 反爬站点)
           - 无 ``renderer`` 字段或 ``renderer="aiohttp"`` → 走 aiohttp
           - crawl4ai 不可用时一律 fallback 到 aiohttp
        2. **crawl4ai 优先 + aiohttp fallback**: crawl4ai 失败/超时 → aiohttp
           适用于 ``renderer="crawl4ai"`` 的源 (政府站 / GitHub Trending / 36kr 等)
        3. **aiohttp 直连**: RSS / 静态 HTML / API 类源,不走 Playwright 提速
        4. **Phase 22 RSS 路由**: 源有 ``rss_url`` 字段 → 走 ``_fetch_rss``(feedparser),
           完全跳过 HTML 抓取和 _parse_html。FreeBuf / SecWiki 等用此路径,
           避免首页误抓备案/导航链接。
        """
        from backend.collectors import base as _base

        start = datetime.now(timezone.utc)
        html: str | None = None
        crawler_used: str = "none"  # "crawl4ai" / "aiohttp" / "rss" / "none"
        renderer = source.get("renderer", "aiohttp")

        # ---- Phase 22: RSS 路由 (优先) -----------------------------------
        if source.get("rss_url"):
            return await self._fetch_rss(source, start=start)

        # ---- Phase 25 P1: JSON API 路由 (提前返回,避免 HTML 抓取) ----
        if renderer == "json":
            return await self._fetch_json_source(source, start=start)

        # ---- Phase 25 P1: disabled 路由 (源接入受限,跳过抓取) ----
        if renderer == "disabled":
            return [], SourceResult(
                source_name=source["name"],
                source_url=source["url"],
                item_count=0,
                error_msg="source disabled (see source comment)",
                duration_ms=0,
            )

        # ---- Phase 51: sogou 搜索渲染 (走 sogou.com/web HTML 搜索 + site: 限定) ----
        # 用于 security_collector 的厂商漏洞/威胁情报公众号抓取,
        # 不直抓源站(可能被反爬), 用 sogou 索引抓真链接
        if renderer == "sogou":
            return await self._fetch_sogou_source(source, start=start)

        # ---- Phase 14: 按 renderer 字段决定是否走 crawl4ai ----------
        if renderer == "crawl4ai" and _base.crawl4ai_available():
            try:
                html = await _base.fetch_html(
                    source["url"], timeout=self.timeout
                )
                if html is not None:
                    crawler_used = "crawl4ai"
            except Exception as e:
                # 防御性 — fetch_html 自身已经 swallow 所有异常,这里是
                # 兜底;失败一律降级到 aiohttp
                self.logger.debug(
                    f"crawl4ai path raised (fallback aiohttp): "
                    f"{type(e).__name__}: {str(e)[:50]}"
                )
                html = None

        # ---- fallback 到 aiohttp (crawl4ai 不可用 / 失败 / 未配置) ----
        if html is None:
            session_cls = _base._session_factory()
            try:
                async with session_cls() as session:
                    async with session.get(
                        source["url"],
                        headers={"User-Agent": _base.UA},
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                        ssl=False,
                    ) as resp:
                        if resp.status != 200:
                            raise aiohttp.ClientError(f"HTTP {resp.status}")
                        html = await resp.text()
                        crawler_used = "aiohttp"
            except Exception as e:
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                self.logger.warning(
                    f"source {source['name']} failed: "
                    f"{type(e).__name__}: {str(e)[:50]}"
                )
                return [], SourceResult(
                    source_name=source["name"],
                    source_url=source["url"],
                    item_count=0,
                    error_msg=f"{type(e).__name__}: {str(e)[:100]}",
                    duration_ms=duration,
                )

        # ---- 解析 (无论 crawl4ai 还是 aiohttp 都走原 _parse_html) ----
        try:
            raw_items = self._parse_html(html, source)
            items = self._build_items(raw_items, source)
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"parse failed for {source['name']} "
                f"(crawler={crawler_used}): "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source["name"],
                source_url=source["url"],
                item_count=0,
                error_msg=f"parse_error: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        duration = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        # Phase 11: 在 source_url 后追加 #crawler=<crawler_used> 作为可
        # 观测性 trace(不影响主流程,debug 时方便定位 crawl4ai vs aiohttp)
        return items, SourceResult(
            source_name=source["name"],
            source_url=source["url"],
            item_count=len(items),
            duration_ms=duration,
        )

    async def _fetch_json_source(
        self, source: dict, start: datetime
    ) -> tuple[list[HotspotItem], SourceResult]:
        """Phase 25 P1: JSON API 路径,用于 ``renderer="json"`` 的源。

        1. 走 aiohttp GET ``api_url`` (或 fallback 到 ``url``)
        2. ``resp.json()`` 解析为 dict
        3. 调用 ``_parse_json(data, source)`` 由子类实现
        4. ``_build_items`` 走通用的 title/url/published_at 字段约定

        子类只需重写 ``_parse_json`` 把 API 响应转成
        ``[{"title":..., "url":..., "published_at":...}, ...]``。
        """
        from backend.collectors import base as _base

        api_url = source.get("api_url") or source["url"]
        # 允许 source 配置里 override headers (例如 AIhot 强制要求特定 UA)
        base_headers = {"User-Agent": _base.UA}
        extra_headers = source.get("headers") or {}
        if extra_headers:
            base_headers.update(extra_headers)
        try:
            session_cls = _base._session_factory()
            async with session_cls() as session:
                async with session.get(
                    api_url,
                    headers=base_headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"json fetch failed for {source['name']}: "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source["name"],
                source_url=api_url,
                item_count=0,
                error_msg=f"{type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        try:
            raw_items = self._parse_json(data, source)
            items = self._build_items(raw_items, source)
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"json parse failed for {source['name']}: "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source["name"],
                source_url=api_url,
                item_count=0,
                error_msg=f"parse_error: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        duration = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        return items, SourceResult(
            source_name=source["name"],
            source_url=api_url,
            item_count=len(items),
            duration_ms=duration,
        )

    async def _fetch_sogou_source(
        self, source: dict, start: datetime
    ) -> tuple[list[HotspotItem], SourceResult]:
        """Phase 51: sogou 搜索渲染路径, 用于 ``renderer="sogou"`` 的源。

        工作流程:
        1. 取 source['query'] 作为 sogou 搜索关键词 (含 ``site:`` 限定)
        2. 取 source['target_domain'] 作为 URL host 二次过滤 (可选)
        3. 走 ``sogou_search.search_sogou`` 一次性 fetch+parse
        4. ``_build_items`` 走通用的 title/url/published_at 字段约定
        5. 缺失 published_at 的 item 由 _build_items 兜底 (Phase 50 模式)

        子类无需重写 — sogou_search 解析已完成, 子类只配置 SECURITY_SOURCES
        时指定 ``renderer="sogou"`` + ``query`` + ``target_domain`` 即可。
        """
        from backend.collectors.sogou_search import search_sogou

        query = source.get("query") or source.get("url", "")
        target_domain = source.get("target_domain")
        max_items = source.get("max_items", 20) or 20

        try:
            raw_items = await search_sogou(
                query=query,
                target_domain=target_domain,
                max_items=max_items,
                timeout=self.timeout,
            )
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"sogou fetch failed for {source['name']}: "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source["name"],
                source_url=source["url"],
                item_count=0,
                error_msg=f"{type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        try:
            items = self._build_items(raw_items, source)
        except Exception as e:
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"sogou build_items failed for {source['name']}: "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source["name"],
                source_url=source["url"],
                item_count=0,
                error_msg=f"build_error: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        duration = int(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000
        )
        return items, SourceResult(
            source_name=source["name"],
            source_url=source["url"],
            item_count=len(items),
            duration_ms=duration,
        )


__all__ = ["FetchersMixin"]
