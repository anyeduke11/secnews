"""标讯信源搜索引擎采集器（Phase 19 + v1.6.3 整合）。

设计动机
--------
v1.6.3 skillhub 网安标讯助手的核心思路: 标讯信源（政府/银行/能源/电信/聚合）
普遍有 WAF / 强制 JS 渲染 / IP 黑白名单,直抓成功率近 0。v1.6.3 的解法是用
**搜索引擎**（Google / DDG）走 ``site:<domain> 关键词`` 间接采集,绕开源站反爬。

但项目 SPEC §3 硬约束: 卡片"原文链接"必须是用户点开就能直接读到该条资讯
真实正文的链接,禁止 example.com / google.com/search / bing.com/search 等
合成 URL（见 ``backend/scripts/purge_synthetic_urls.py`` 的
``FORBIDDEN_URL_PATTERNS``）。

本模块在两者之间架桥
--------------------
1. 用 cn.bing.com 搜索（DDG/Google/Brave 在本机网络不可达,
   cn.bing.com 是唯一可达的搜索入口;cn.bing.com 不遵守 ``site:`` 限定,
   所以搜的是纯关键词,**事后按目标域名过滤**结果）
2. **提取真实源 URL** — 拿到搜索结果后,只保留 target_domain 域名的链接
3. 关键词过滤走 :func:`is_security_bid`,只保留网安标讯
4. 标题/摘要用 Bing 结果的 h2 title + p 摘要 填充,作为 item 元数据

质量门禁对账
------------
- ``url_validity``: HEAD 请求的 URL 是源站 URL,不是搜索引擎 URL,真实可达就 PASS
- ``author_verification`` / ``source_reputation``: 已注册 16 域名到
  ``publisher_registry.PUBLISHER_REGISTRY``,不触发 author_unknown
- ``FORBIDDEN_URL_PATTERNS``: 提取后是源站 URL,**不**含 google.com/search /
  bing.com/search / duckduckgo.com/? 等 pattern
- ``url_content``（异步抽样）: title 用源站搜索结果标题,与源页 title 高度重叠
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp

from backend.collectors.bid_collector import is_security_bid
from backend.logging_config import logger

# ---------------------------------------------------------------------------
# cn.bing.com — 本机网络唯一可达的搜索引擎
# ---------------------------------------------------------------------------
BING_URL = "https://cn.bing.com/search"

# 简体中文 UA
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Bing 结果块: <li class="b_algo" ...> ... </li>
# 内部结构: <h2><a target="_blank" href="URL">TITLE</a></h2> <p>SNIPPET</p>
_B_ALGO_RE = re.compile(
    r'<li class="b_algo"[^>]*>(?P<block>.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
# 块内 h2 链接
_H2_LINK_RE = re.compile(
    r'<h2[^>]*>\s*<a[^>]+href="(?P<url>https?://[^"]+)"[^>]*>'
    r"(?P<title>[^<]+?)</a>",
    re.IGNORECASE | re.DOTALL,
)
# 块内摘要 - 多种 class name 都见过
_SNIPPET_RE = re.compile(
    r'<p[^>]*class="[^"]*(?:b_lineclamp|b_paractl|b_caption)[^"]*"[^>]*>'
    r"(?P<snippet>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
# 兜底: 找任何 <p>...</p> 在 h2 之后
_P_FALLBACK_RE = re.compile(
    r"</h2>\s*<p[^>]*>(?P<snippet>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)

# 简单 HTML 标签清理
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# 排除的搜索跟踪 / 站内 URL（这些不是源站 URL）
# - bing.com 自身
# - go.microsoft.com
# - r.bing.com (Bing 资源)
_EXCLUDE_HOSTS = {
    "cn.bing.com", "www.bing.com", "bing.com",
    "go.microsoft.com", "microsoft.com",
    "r.bing.com", "login.live.com", "account.microsoft.com",
}

# 搜索关键词（中文网安四线精简）
DEFAULT_QUERY_KEYWORDS: list[str] = [
    "网络安全 OR 数据安全 OR 防火墙 OR 密评 OR 等保",
]

# 单源搜索超时（秒）
DEFAULT_TIMEOUT = 20

# 单源最大返回条数
DEFAULT_MAX_RESULTS = 10

# 单源调用间隔（避开限流）
MIN_INTERVAL_SECONDS = 2.0

# 模块级限流锁
_search_lock = asyncio.Lock()


@dataclass
class SearchResult:
    """单条搜索结果。"""

    url: str  # 真实源 URL
    title: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title.strip(),
            "summary": _HTML_TAG_RE.sub("", self.snippet or "").strip(),
        }


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_target_domain(url: str, target_domain: str) -> bool:
    """判断 url 是否属于 target_domain（按 host 后缀匹配）。"""
    h = _host_of(url)
    if not h:
        return False
    if h in _EXCLUDE_HOSTS:
        return False
    target = target_domain.lower()
    return h == target or h.endswith("." + target)


def parse_bing_html(
    html: str,
    target_domain: str,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[SearchResult]:
    """从 Bing 搜索 HTML 解析出 ``[(url, title, snippet), ...]`` 列表。

    会按 ``target_domain`` 过滤（只保留该域名下的 URL）,
    这是因为 cn.bing.com 不遵守 ``site:`` 限定,只能用后置过滤。

    返回 URL 是真实源 URL,不是 bing.com 跳转 URL（cn.bing.com 的 h2 链接
    本来就是源 URL,不需要像 DDG 那样 uddg 解码）。
    """
    if not html:
        return []
    out: list[SearchResult] = []
    seen: set[str] = set()
    for m in _B_ALGO_RE.finditer(html):
        block = m.group("block")
        link_m = _H2_LINK_RE.search(block)
        if not link_m:
            continue
        url = link_m.group("url")
        if not _is_target_domain(url, target_domain):
            continue
        if url in seen:
            continue
        title = link_m.group("title").strip()
        if not title:
            continue
        # 摘要
        snip_m = _SNIPPET_RE.search(block) or _P_FALLBACK_RE.search(block)
        snippet = snip_m.group("snippet") if snip_m else ""
        seen.add(url)
        out.append(SearchResult(url=url, title=title, snippet=snippet))
        if len(out) >= max_results:
            break
    return out


def build_query(extra_keywords: list[str] | None = None) -> str:
    """构造 Bing 查询字符串（不用 site:，靠后置过滤）。

    Parameters
    ----------
    extra_keywords: 额外 OR 关键词组

    Returns
    -------
    完整查询字符串,如 ``网络安全 OR 数据安全 OR 防火墙 OR 密评 OR 等保``
    """
    kws = extra_keywords or DEFAULT_QUERY_KEYWORDS
    return " ".join(kws)


async def fetch_bing_html(
    query: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """对 cn.bing.com 发 GET,返回 HTML 文本。失败返回 None。"""
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.get(
                BING_URL,
                params={"q": query, "FORM": "QBLH"},
                headers={
                    "User-Agent": _UA,
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"bing_search non-200: status={resp.status} query={query[:60]}"
                    )
                    return None
                return await resp.text()
    except Exception as e:
        logger.warning(
            f"bing_search failed: {type(e).__name__}: {str(e)[:80]} query={query[:60]}"
        )
        return None


async def search_one_source(
    source: dict,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """对单个 BID_SOURCES 源跑 Bing 搜索,返回 ``[dict(url, title, summary), ...]``。

    会做关键词过滤（``is_security_bid``）、按源域名后置过滤和去重。

    Parameters
    ----------
    source: 形如 ``{"name": ..., "url": ..., "renderer": "search", ...}``
    max_results: 单源最大返回条数
    timeout: HTTP 超时（秒）

    Returns
    -------
    list of dict,每个 dict 含 ``url`` (真实源 URL) / ``title`` / ``summary``
    """
    parsed = urlparse(source["url"])
    domain = parsed.hostname or ""
    if not domain:
        logger.warning(f"search_one_source: invalid url {source['url']!r}")
        return []

    # 限流:多源并发时串行化
    async with _search_lock:
        query = build_query()
        html = await fetch_bing_html(query, timeout=timeout)
        await asyncio.sleep(MIN_INTERVAL_SECONDS)

    if not html:
        return []

    raw_results = parse_bing_html(html, target_domain=domain, max_results=max_results)
    out: list[dict] = []
    seen: set[str] = set()
    for r in raw_results:
        if r.url in seen:
            continue
        # Phase 19: 网安关键词过滤
        if not is_security_bid(r.title):
            continue
        seen.add(r.url)
        d = r.to_dict()
        # Phase 20: 标讯状态提取
        from backend.collectors.bid_status import extract_bid_status
        d["bid_status"] = extract_bid_status(d.get("title", ""), d.get("summary", ""))
        out.append(d)
        if len(out) >= max_results:
            break
    logger.info(
        f"search_one_source {source['name']!r} domain={domain}: "
        f"raw={len(raw_results)} kept={len(out)}"
    )
    return out


async def search_all_sources(
    sources: list[dict],
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """对一组 renderer="search" 源跑搜索,聚合去重后返回。

    返回 list of ``{"url", "title", "summary", "source"}``。
    """
    if not sources:
        return []
    tasks = [search_one_source(s, max_results=max_results, timeout=timeout) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict] = []
    seen: set[str] = set()
    for source, items in zip(sources, results):
        if isinstance(items, BaseException):
            logger.warning(
                f"search_all_sources task failed for {source['name']!r}: "
                f"{type(items).__name__}: {str(items)[:80]}"
            )
            continue
        for it in items:
            url = it.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            it["source"] = source["name"]
            out.append(it)
    return out


__all__ = [
    "SearchResult",
    "parse_bing_html",
    "build_query",
    "fetch_bing_html",
    "search_one_source",
    "search_all_sources",
    "DEFAULT_QUERY_KEYWORDS",
    "DEFAULT_MAX_RESULTS",
    "MIN_INTERVAL_SECONDS",
]
