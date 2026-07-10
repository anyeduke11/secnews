"""Phase 9.2 最终 URL 下钻：tag/landing 页面 → 真实文章 URL

业务背景
--------
用户反馈：量子位 (qbitai.com) 的 RSS 抓取常把 ``/tag/xxx`` 标签页当成文章
收录，点击卡片打开的是 "WorldClaw" 标签聚合页，而不是具体的文章页
``https://www.qbitai.com/2026/07/442447.html``。

解决策略
--------
1. :func:`is_landing_page(url)` — 用 URL 模式识别 "标签/聚合/landing 页"：
   - 域名已知 + path 是 ``/tag/xxx``、``/tags/xxx``、``/topics/xxx``、``/author/xxx``、``/category/xxx``
   - 域名已知 + path 是 ``/?s=...``、``/search?...``（搜索结果页）
   - 整个 URL 是 ``mailto:``（邮箱链接）
2. :func:`resolve_final_url(url)` — 抓 landing 页 HTML，从页面里挑出第一个
   真实文章链接，匹配模式：``/YYYY/MM/NNNNN.html`` 或 ``/p/NNNNN`` 等
3. 缓存：避免对同一 landing URL 重复抓取（30 分钟 TTL）

设计取舍
--------
- 抓取走同步 urllib（与 url_validity_gate 一致），最多 3 秒超时
- 已 fallback 数据跳过（fallback 路径下 URL 通常是 example.com 占位）
- 失败 → flag ``url_drilldown_failed``，item.url 保留原值，扣 5 分
- 成功 → 替换 ``item.url`` + 写 ``url_final=<new>`` flag 供溯源
"""
from __future__ import annotations

import re
import time
import urllib.request
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Landing page 模式识别
# ---------------------------------------------------------------------------
# 通用 path 模式（域名无关）：tag/tags/author/category/topic/search/label
LANDING_PATH_PATTERNS: tuple[str, ...] = (
    r"^/tag/[^/]+/?$",
    r"^/tags/[^/]+/?$",
    r"^/topic/[^/]+/?$",
    r"^/topics/[^/]+/?$",
    r"^/author/[^/]+/?$",
    r"^/authors/[^/]+/?$",
    r"^/category/[^/]+/?$",
    r"^/categories/[^/]+/?$",
    r"^/label/[^/]+/?$",
    r"^/labels/[^/]+/?$",
    r"^/search/?$",
    r"^/\?s=.+$",  # ?s=xxx WordPress 搜索
    r"^/search/\?q=.+$",
)

# 已知域名 → 文章 path 模式（用于从 tag 页面 HTML 抽取第一个真实文章 URL）
# 顺序：列表中前者优先匹配
DOMAIN_ARTICLE_PATTERNS: dict[str, tuple[str, ...]] = {
    # 量子位：/2026/07/442447.html
    "qbitai.com": (
        r"href=[\"'](/\d{4}/\d{2}/\d+\.html)[\"']",
        r"href=[\"'](https?://www\.qbitai\.com/\d{4}/\d{2}/\d+\.html)[\"']",
    ),
    # 36 氪：/p/3882258709180678
    "36kr.com": (
        r"href=[\"'](/p/\d+)[\"']",
        r"href=[\"'](https?://36kr\.com/p/\d+)[\"']",
    ),
    # 机器之心：/articles/yyyy-mm-dd-xxx
    "jiqizhixin.com": (
        r"href=[\"'](/articles/\d{4}/\d{2}/\d{2}/[^/]+/?)[\"']",
    ),
    # KrebsOnSecurity: /YYYY/MM/slug/
    "krebsonsecurity.com": (
        r"href=[\"'](/\d{4}/\d{2}/[^/]+/?)[\"']",
    ),
    # The Hacker News: /YYYY/MM/slug.html
    "thehackernews.com": (
        r"href=[\"'](/\d{4}/\d{2}/[^/]+\.html)[\"']",
    ),
    # BleepingComputer: /YYYY/MM/slug
    "bleepingcomputer.com": (
        r"href=[\"'](/\d{4}/\d{2}/[^/]+/?)[\"']",
    ),
}

# 抓取超时（秒）
_FETCH_TIMEOUT = 3.0
# 缓存 TTL（秒）
_CACHE_TTL = 30 * 60
# User-Agent
_UA = "hotspot-urldrill/1.0 (Mozilla/5.0 compatible)"


# ---------------------------------------------------------------------------
# 简单内存缓存
# ---------------------------------------------------------------------------
_drilldown_cache: dict[str, tuple[float, Optional[str]]] = {}


def _is_mailto(url: str) -> bool:
    return url.startswith("mailto:")


def is_landing_page(url: str) -> bool:
    """判断 URL 是否为 "标签/聚合/landing 页"（非真实文章）。

    Examples
    --------
    >>> is_landing_page("https://www.qbitai.com/tag/worldclaw")
    True
    >>> is_landing_page("https://www.qbitai.com/2026/07/442447.html")
    False
    >>> is_landing_page("mailto:foo@bar.com")
    True
    """
    if not url:
        return False
    if _is_mailto(url):
        return True
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return False
    path = parsed.path or "/"
    # 已知域名（domain_article_patterns 里有）→ 走 path 模式
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # 整段 path + 通用模式匹配
    test = path + ("?" + parsed.query if parsed.query else "")
    for pat in LANDING_PATH_PATTERNS:
        if re.search(pat, test):
            return True
    return False


def _extract_first_article_url(html: str, host: str) -> Optional[str]:
    """从 tag 页面 HTML 抽取第一个真实文章 URL。

    匹配 :data:`DOMAIN_ARTICLE_PATTERNS` 中 ``host`` 对应的 pattern。
    找不到返回 None。
    """
    # 用 host 的主域做查找
    primary = host
    if host.startswith("www."):
        primary = host[4:]
    patterns = DOMAIN_ARTICLE_PATTERNS.get(primary)
    if not patterns:
        # 尝试二级域匹配
        parts = primary.split(".")
        if len(parts) >= 2:
            short = ".".join(parts[-2:])
            patterns = DOMAIN_ARTICLE_PATTERNS.get(short)
    if not patterns:
        return None
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            href = m.group(1)
            # 绝对化
            if href.startswith("http"):
                return href
            return f"https://{host}{href}"
    return None


def _fetch_html(url: str, timeout: float = _FETCH_TIMEOUT) -> Optional[str]:
    """同步抓取 HTML（最多 timeout 秒），出错返回 None。"""
    try:
        req = urllib.request.Request(
            url, method="GET",
            headers={"User-Agent": _UA, "Accept": "text/html"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def resolve_final_url(url: str) -> Optional[str]:
    """下钻 landing 页 → 抓 HTML → 抽取第一个真实文章 URL。

    Returns
    -------
    - 真实文章 URL（如果成功）
    - 原始 URL（如果 URL 已经是文章页 / 已知无可下钻路径）
    - None（如果抓取失败，调用方需处理）

    Notes
    -----
    - 30 分钟内存缓存，避免对同一 landing URL 重复抓取
    - 同步实现，调用方负责放到 thread pool 避免阻塞 event loop
    """
    if not url:
        return None
    # mailto: 无法下钻 → 返回 None
    if _is_mailto(url):
        return None
    # 已不是 landing 页 → 直接返回原 URL（不抓取）
    if not is_landing_page(url):
        return url
    # 查缓存
    now = time.time()
    if url in _drilldown_cache:
        ts, cached = _drilldown_cache[url]
        if now - ts < _CACHE_TTL:
            return cached
    # 抓取 + 抽取
    html = _fetch_html(url)
    if not html:
        _drilldown_cache[url] = (now, None)
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    resolved = _extract_first_article_url(html, host)
    _drilldown_cache[url] = (now, resolved)
    return resolved


def clear_cache() -> None:
    """清空下钻缓存（运维/测试用）。"""
    _drilldown_cache.clear()


__all__ = [
    "is_landing_page",
    "resolve_final_url",
    "clear_cache",
    "DOMAIN_ARTICLE_PATTERNS",
    "LANDING_PATH_PATTERNS",
]
