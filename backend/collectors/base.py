"""Collector 抽象基类（Phase 3 重构; v1.8 R3 拆分）。

所有 collector 都继承 ``BaseCollector``，子类必须实现：

- ``category`` ClassVar （指明采集哪一类）
- ``_fallback() -> list[HotspotItem]`` （硬编码备用数据）

子类可按需覆盖：

- ``sources`` / ``timeout`` / ``max_items`` / ``min_items_threshold``
- ``_parse_html()`` 适配特定站点结构
- ``fetch_source()`` 整体替换抓取逻辑（例如走 API 而非 HTML）

v1.8 R3 拆分
------------
``BaseCollector`` 的实现按职责拆为 3 个 Mixin（本模块只保留
HTML 解析 + collect 编排）：

- :class:`backend.collectors.fetchers.FetchersMixin` — 4 条抓取路径
  (fetch_source / _fetch_rss / _fetch_json_source / _fetch_sogou_source)
- :class:`backend.collectors.item_builder.ItemBuilderMixin` — raw dict →
  HotspotItem (_build_items / _title_relevant / _mark_fallback)
- :class:`backend.collectors.quality_hook.QualityGatesMixin` — 质量门禁
  (_skip_quality / _run_quality_gates)

patch 兼容: ``UA`` / ``_session_factory`` / ``fetch_html`` /
``crawl4ai_available`` 等模块级符号保留在本模块（测试 monkeypatch
``backend.collectors.base.X`` 的路径不变），fetchers.py 经
``base`` 模块属性运行时查找这些符号。

约定
----
- 所有 ``datetime`` 字段 tz-aware UTC
- 所有异常用 ``logger.warning/error``，不 ``print``
- 任何 source 的异常隔离到 ``SourceResult.error_msg``，不向上抛
- 任何 collector 异常隔离到 ``CollectionResult.error``，不向上抛
"""
from __future__ import annotations

import asyncio
import re
from abc import ABC
from typing import Any, ClassVar, Optional
from urllib.parse import urlparse

import aiohttp

from backend.collectors.fetchers import FetchersMixin
from backend.collectors.item_builder import ItemBuilderMixin
from backend.collectors.keywords import (
    _CAT_KEYWORDS,
    _is_title_relevant_to_category,
)
from backend.collectors.parsing import (
    _extract_published_at,
    _is_noise_title,
    _is_noise_url,
)
from backend.collectors.quality_hook import QualityGatesMixin
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.observability import log_event
from backend.quality.config import NOISE_URL_REGEX

# Phase 11: crawl4ai 适配层 (Playwright-based 抓取)。
#   - 可选依赖: 没装 crawl4ai 时 ``is_available()`` 返回 False
#   - 开关来自 crawl_config.yaml ``enabled`` (默认关);打开后
#     BaseCollector.fetch_source 优先用 crawl4ai 拿 fully-rendered
#     HTML,失败 fallback 到 aiohttp
# patch 兼容: fetch_html / crawl4ai_available 模块级符号保留在本模块
# (测试 monkeypatch backend.collectors.base.X 的路径不变) — F401 re-export
from backend.utils.crawl4ai_client import (
    fetch_html,
    is_available as crawl4ai_available,
)

# ProxySession 保留导入，供 fetchers 直连失败后做代理兜底。
# 代理不主动使用 — 直连失败 + 需要代理的源才走代理。
try:
    from backend.proxy_session import ProxySession  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from proxy_session import ProxySession  # type: ignore
    except ImportError:  # pragma: no cover
        ProxySession = None  # type: ignore


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _session_factory() -> type:
    """始终返回 aiohttp.ClientSession（直连优先）。

    代理不主动使用 — 直连失败 + 需要代理的源由调用方自行用
    ProxySession 重试。
    """
    return aiohttp.ClientSession


class BaseCollector(FetchersMixin, ItemBuilderMixin, QualityGatesMixin, ABC):
    """所有 collector 的抽象基类。

    Class-level defaults (subclass overrides):

    ======================  ====  ===========================================
    Field                    Default  Meaning
    ======================  ====  ===========================================
    ``name``                ""    Lower-case identifier; auto-derived from
                                   the class name when empty.
    ``category``            ``Category.AI``  Subclass MUST override.
    ``sources``             ``[]`` List of source config dicts:
                                   ``{"name", "url", "score"?}``
    ``timeout``             30    Per-request timeout in seconds.
    ``max_items``           50    Hard cap on returned items.
    ``min_items_threshold`` 3     If total < this (or all sources failed),
                                   trigger ``_fallback``.
    ======================  ====  ===========================================
    """

    # ---- 子类可覆盖的 ClassVar -----------------------------------------
    name: str = ""
    category: Category = Category.AI  # subclass 必须覆盖
    sources: ClassVar[list[dict]] = []  # 子类覆盖的源清单
    timeout: int = 30
    max_items: int = 50
    min_items_threshold: int = 3

    def __init__(self) -> None:
        if not self.name:
            self.name = (
                self.__class__.__name__.lower().replace("collector", "")
            )
        # 绑定 collector name 到 logger，所有子类日志自动带上
        self.logger = logger.bind(collector=self.name)
        # Phase 9 招标源质量门禁：上一次 collect 的每源产出结果，
        # CollectionService 跑完 collect() 后读此属性评估源覆盖度。
        self.last_source_results: list[SourceResult] = []

    # ------------------------------------------------------------------
    # 必须实现（Phase 13: 硬约束 - 不允许合成假数据）
    # ------------------------------------------------------------------
    def _fallback(self) -> list[HotspotItem]:
        """返回硬编码备用数据。

        Phase 13 硬约束 (写进 SPEC §3) — 原文链接必须是真实链接,
        **禁止** 生成合成 / 占位 / 搜索 URL 让用户自己点开去搜。

        因此 base 默认返回空,subclass **不应** 再实现 (除非有真实
        离线数据源)。所有源失败时 collect() 直接返回 [],UI 显示
        "该分类暂无可用资讯" — 真实优先于"假装有数据"。
        """
        return []

    # ------------------------------------------------------------------
    # 可选覆盖
    # ------------------------------------------------------------------
    def _parse_html(self, html: str, source: dict) -> list[dict[str, Any]]:
        """从 HTML 抓 ``<a>`` 标签中的 (title, url)。

        v1.3.0: 优先使用 lxml CSS Selector 解析，正则作为 fallback。
        解析策略降级链：lxml CSS Selector → 正则匹配

        噪声过滤规则不变（标题/URL 黑名单、长度限制、去重等）。
        v1.8 R3: 噪声判定改用 :mod:`backend.collectors.parsing` 的
        模块级 ``_is_noise_title`` / ``_is_noise_url``（与原嵌套版逐字相同）。
        """
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        page_published_at = _extract_published_at(html, source["url"])

        def _add_item(title: str, url: str) -> None:
            title = (title or "").strip()
            url = (url or "").strip()
            if _is_noise_title(title) or _is_noise_url(url, source["url"]):
                return
            try:
                import html as _html
                title = _html.unescape(title)
            except Exception:
                pass
            if len(title) < 8 or len(title) > 200:
                return
            key = title[:30]
            if key in seen:
                return
            seen.add(key)
            resolved_url = self._resolve_url(url, source["url"])
            item_published_at = _extract_published_at("", resolved_url)
            if item_published_at is None:
                item_published_at = page_published_at
            items.append(
                {
                    "title": title,
                    "summary": "",
                    "url": resolved_url,
                    "published_at": item_published_at,
                }
            )
            if len(items) >= self.max_items:
                return

        # ---- v1.3.0: lxml CSS Selector 优先解析 ----
        lxml_ok = False
        try:
            from lxml import html as lxml_html

            tree = lxml_html.fromstring(html)
            lxml_ok = True

            CSS_SELECTORS = [
                "h1.entry-title a[rel='bookmark']",
                "h2.entry-title a[rel='bookmark']",
                "h1.entry-title a",
                "h2.entry-title a",
                "a[rel='bookmark']",
                ".post-title a",
                ".article-title a",
                ".entry-title a",
                "h2 a",
                "h3 a",
            ]

            for selector in CSS_SELECTORS:
                try:
                    links = tree.cssselect(selector)
                except Exception:
                    continue
                if not links:
                    continue
                for el in links:
                    href = el.get("href", "").strip()
                    text = el.text_content().strip()
                    if href and text:
                        if NOISE_URL_REGEX.match(href):
                            continue
                        _add_item(text, href)
                    if len(items) >= self.max_items:
                        return items
                if items:
                    return items
        except Exception:
            lxml_ok = False

        # ---- Fallback: 正则匹配 ----
        if not lxml_ok or not items:
            entry_title_pat = re.compile(
                r'<h[12][^>]*class="entry-title"[^>]*>\s*'
                r'<a[^>]+href="([^"]+)"[^>]*rel="bookmark"[^>]*>([^<]+)</a>',
                re.IGNORECASE | re.DOTALL,
            )
            for m in entry_title_pat.finditer(html):
                href, title = m.group(1), m.group(2)
                if NOISE_URL_REGEX.match(href):
                    continue
                _add_item(title, href)
                if len(items) >= self.max_items:
                    return items

            patterns = [
                r'<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*>([^<]{8,80})</a>',
                r'<a[^>]*href="([^"]+)"[^>]*>([^<]{8,80})</a>',
            ]
            for pat in patterns:
                for m in re.findall(pat, html):
                    if len(m) == 3:
                        href, title, text = m
                    else:
                        href, text = m
                        title = text
                    if NOISE_URL_REGEX.match(href):
                        continue
                    _add_item(title or text, href)
                    if len(items) >= self.max_items:
                        return items
        return items

    def _resolve_url(self, href: str, base_url: str) -> str:
        """相对路径 → 绝对 URL。"""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        return base_url.rstrip("/") + "/" + href.lstrip("/")

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """Phase 25 P1: JSON 解析。子类重写, 默认返回空 (renderer=json 源必须实现)。"""
        return []

    # ------------------------------------------------------------------
    # 编排
    # ------------------------------------------------------------------

    # P0 SSRF 副作用根除 (Layer 3): 全局 name→renderer 查表缓存。
    # 跨 collector 共享 (e.g. SecurityCollector + GDELTCollector 同 category),
    # 避免次 collector 拿 wechat 源时 const 查表失败导致 renderer 静默
    # 降级为 "aiohttp" → fetch_source 走 aiohttp fallback → session.get("")
    # 抛 InvalidUrlClientError。
    _RENDERER_BY_NAME: dict[str, str] | None = None

    @classmethod
    def _get_renderer_by_name(cls) -> dict[str, str]:
        """扫描所有 Collector 子类的 SOURCES 常量, 缓存 name→renderer.

        类加载时一次性建, 跨实例共享, 不在 hot path。
        """
        if cls._RENDERER_BY_NAME is not None:
            return cls._RENDERER_BY_NAME
        out: dict[str, str] = {}
        try:
            import backend.collectors as _c
        except ImportError:
            return out
        for name in dir(_c):
            obj = getattr(_c, name, None)
            if not isinstance(obj, type):
                continue
            srcs = getattr(obj, "sources", None)
            if not isinstance(srcs, list):
                continue
            for s in srcs:
                if (
                    isinstance(s, dict)
                    and s.get("name")
                    and s.get("renderer")
                    and s.get("renderer") != "disabled"
                ):
                    out[s["name"]] = s["renderer"]
        cls._RENDERER_BY_NAME = out
        return out

    def _load_sources_from_registry(self) -> list[dict] | None:
        """P1 crawler-v2 Phase 1 切流: 从 crawler_sources 表读本分类源.

        Strangler 迁移的「切流」阶段: 源注册表 (055 建表, seed_crawler_
        sources 已注册 132 条) 成为源数据源, 替代硬编码类常量。

        映射: feed_url→rss_url, priority→score; renderer 与 keywords 从
        类常量同名源补充 (常量保留了 renderer=disabled/crawl4ai/sogou/
        wechat 等语义与分类关键词; disabled 源已在注册时 enabled=0, 不会
        被读出, 与常量语义等价)。

        P0 SSRF 副作用根除 (Layer 3):
        - 顶层过滤 url/feed_url/api_url 全空行 (wechat 源不应入 registry
          表, 但 Layer 1 migration 清理后仍可能有漏网)
        - renderer 字段优先用类常量同名片查 (const), fallback 到全局
          _get_renderer_by_name 查表 (跨 collector 共享); 都查不到再
          fallback 到 "aiohttp" (有 url 的普通 HTML 源)

        返回语义:
        - 表无本 category 记录 (未 seed / 非主分类如 ai_security) → None,
          调用方回退类常量 (渐进切流, 未注册分类不受影响)。
        - 表有记录但 0 个 enabled (用户全禁用) → [] (不回退常量)。
        """
        try:
            from backend.repository.db import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT name, url, feed_url, api_url, priority FROM crawler_sources "
                "WHERE category = ? AND enabled = 1 ORDER BY priority DESC",
                (self.category.value,),
            ).fetchall()
            has_cat = conn.execute(
                "SELECT 1 FROM crawler_sources WHERE category = ? LIMIT 1",
                (self.category.value,),
            ).fetchone()
        except Exception as e:
            self.logger.warning(
                f"crawler_sources load failed (fallback to class constants): {e}"
            )
            return None
        if not has_cat:
            return None  # 分类未注册 → 回退常量
        if not rows:
            return []  # 已注册但全禁用

        by_name = {s["name"]: s for s in self.sources}
        renderer_by_name = self._get_renderer_by_name()
        out: list[dict] = []
        for r in rows:
            name = r["name"]
            url = r["url"] or ""
            feed_url = r["feed_url"] or ""
            api_url = r["api_url"] or ""

            # P0 SSRF 副作用根除 (Layer 3 兜底): url/feed_url/api_url 全空
            # 的行 (wechat/sogou 源误入) 直接跳过, 避免 fetch_source
            # 走 aiohttp fallback 抛 InvalidUrlClientError。
            if not (url or feed_url or api_url):
                self.logger.debug(
                    f"skip registry row {name!r}: url/feed_url/api_url all empty"
                )
                continue

            # renderer 解析: const (本 collector SOURCES) > 全局查表 > aiohttp
            const = next(
                (s for s in self.sources
                 if s["name"] == name and s.get("renderer") != "disabled"),
                None,
            )
            renderer = (
                (const or {}).get("renderer")
                or renderer_by_name.get(name)
                or "aiohttp"
            )
            out.append({
                "name": name,
                "url": url,
                "rss_url": feed_url,
                "api_url": api_url,
                "score": r["priority"],
                "renderer": renderer,
                "keywords": (const or by_name.get(name, {})).get("keywords", []),
            })
        return out

    async def collect(self, only_source: str | None = None, since: str | None = None) -> list[HotspotItem]:
        """默认编排：

        1. 无 sources → 强制 fallback
        2. 并发抓所有 source，合并 items
        3. 全部失败 **或** items 不足 → fallback
        4. 截断到 ``max_items``
        5. **Phase 3.5**：跑同步质量门禁（fallback 跳过）

        Phase 5: 入口打 ``collect_start`` 事件，出口打 ``collect_end`` 事件

        P1 切流: 优先用 crawler_sources 表源 (若本分类已注册), 否则类常量。

        P2-0: ``only_source`` 参数 — 源级调度 (run_one_source) 传入目标源名,
        只抓该源, 不再整分类抓取 (此前单源调度实为整分类采集, 健康状态机
        归因全部失真)。

        P2-3: ``since`` 参数 — catchup 追抓窗口真正生效: 抓取后按
        ``published_at >= since`` 过滤, 只保留窗口内条目 (此前 since/until
        仅用于日志/校验, 抓取仍是全量当前内容)。增量历史回填受 RSS 等
        源能力限制, 本实现保证"窗口过滤"语义真实生效。
        """
        import time as _time
        from uuid import uuid4 as _uuid4

        # P1 crawler-v2 Phase 1: 源注册表驱动 (strangler 切流)
        registry = self._load_sources_from_registry()
        if registry is not None:
            self.sources = registry
        if only_source is not None:
            # P2-0: 过滤到目标源 (按 name 匹配)
            self.sources = [s for s in self.sources if s.get("name") == only_source]

        run_id = _uuid4().hex[:8]
        start = _time.time()
        log_event(
            "collect_start",
            collector=self.name,
            category=self.category.value,
            run_id=run_id,
            n_sources=len(self.sources),
        )

        if not self.sources:
            self.logger.warning("no sources configured, returning []")
            # Phase 13: 不调 _fallback,直接返回空。避免合成假数据。
            duration_ms = int((_time.time() - start) * 1000)
            self.last_source_results = []
            log_event(
                "collect_end",
                collector=self.name,
                category=self.category.value,
                run_id=run_id,
                item_count=0,
                fallback_count=0,
                duration_ms=duration_ms,
                status="no_sources",
            )
            return []

        tasks = [self.fetch_source(s) for s in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[HotspotItem] = []
        successful_sources = 0
        # Phase 9 招标源质量门禁：收集每源结果
        collected_source_results: list[SourceResult] = []
        # Phase 23: 名称→source 配置索引,用于 per-source cap
        _src_by_name = {s["name"]: s for s in self.sources}
        for r in results:
            if isinstance(r, BaseException):
                self.logger.error(f"task crashed: {r}")
                continue
            items, sr = r
            # Phase 23: per-source max_items 配额 — 防止单源(如证监会 94 条)
            # 挤掉末位 RSS 源(启明星辰)
            src_cfg = _src_by_name.get(sr.source_name, {})
            per_src_cap = src_cfg.get("max_items")
            if per_src_cap and len(items) > per_src_cap:
                self.logger.debug(
                    f"per-source cap: {sr.source_name} {len(items)}→{per_src_cap}"
                )
                items = items[:per_src_cap]
            all_items.extend(items)
            collected_source_results.append(sr)
            if sr.error_msg is None and sr.item_count > 0:
                successful_sources += 1

        # Phase 13 硬约束: 所有源失败 / items 不足 → 不调 _fallback。
        # 原文链接必须真实,不允许合成/搜索 URL 兜底。
        if successful_sources == 0:
            self.logger.warning(
                f"all {len(self.sources)} sources failed, returning [] "
                f"(Phase 13: no synthetic fallback allowed)"
            )
            return []
        elif len(all_items) < self.min_items_threshold:
            self.logger.warning(
                f"insufficient items ({len(all_items)} < "
                f"{self.min_items_threshold}), returning [] "
                f"(Phase 13: no synthetic fallback allowed)"
            )
            return []

        used_fallback = False  # Phase 13: 永远 False
        all_items = all_items[: self.max_items]
        # P2-3: catchup since 窗口过滤 — published_at >= since 才保留
        # (增量追抓语义: 只处理窗口内条目, 防止重复摄入更早内容)
        if since:
            try:
                from datetime import datetime, timezone
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=timezone.utc)
                all_items = [
                    it for it in all_items
                    if it.published_at is None or it.published_at >= since_dt
                ]
            except (ValueError, TypeError) as _e:
                self.logger.warning(f"since filter parse failed: {_e}")
        # Phase 3.5: 跑同步门禁（fallback 数据跳过）
        if not self._skip_quality:
            all_items = await self._run_quality_gates(all_items)

        duration_ms = int((_time.time() - start) * 1000)
        fallback_count = sum(1 for it in all_items if it.is_fallback)
        # Phase 9: 把收集到的 source_results 暴露给 CollectionService
        self.last_source_results = collected_source_results
        log_event(
            "collect_end",
            collector=self.name,
            category=self.category.value,
            run_id=run_id,
            item_count=len(all_items),
            fallback_count=fallback_count,
            duration_ms=duration_ms,
            status="fallback" if used_fallback else "success",
        )
        return all_items


__all__ = ["BaseCollector"]
