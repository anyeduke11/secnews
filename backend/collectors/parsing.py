"""Module-level parsing helpers extracted from base.py.

- ``_now_utc()`` — tz-aware UTC now
- ``_PUBLISHED_AT_PATTERNS`` — 8 regex patterns for extracting timestamps from HTML
- ``_parse_iso_datetime(s)`` — ISO 8601 string → datetime
- ``_extract_published_at(html, source_url)`` — page-level time extraction
- ``_is_noise_title(title)`` — title noise filter
- ``_is_noise_url(url, source_url)`` — URL noise filter
- ``_resolve_url(href, base_url)`` — relative → absolute URL
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse


def _now_utc() -> datetime:
    """tz-aware UTC now。"""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Bug 2 修复 — 页面级发布时间提取
# ---------------------------------------------------------------------------
# 列表/索引页(主页、RSS 替代)通常没有"每篇文章"的发布时间,只有"页面
# 生成时间"。这里在 _parse_html 顶部抓取页面级时间,作为该页面所有
# 条目的默认 published_at,避免全部 = fetch time 导致排序无意义。
#
# 支持的常见模式(按可靠性排序):
#   1. JSON-LD ``datePublished``            (schema.org, 真实发布时间)
#   2. <meta property="article:published_time" content="ISO8601">
#   3. <meta itemprop="datePublished" content="ISO8601">
#   4. <meta name="pubdate" content="ISO8601">
#   5. <meta property="og:article:published_time" content="ISO8601">
#   6. <time datetime="ISO8601">            (HTML5)
#   7. URL slug 里的日期: /2026/07/05/...  (qbitai / thehackernews 等)
#   8. 页面顶部 ``Updated: 2026-07-05`` 文本
#
# 返回: tz-aware UTC datetime 或 None
_PUBLISHED_AT_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "jsonld_datePublished",
        re.compile(
            r'"datePublished"\s*:\s*"([^"]+)"',
            re.IGNORECASE,
        ),
    ),
    (
        "meta_article_published_time",
        re.compile(
            r'<meta[^>]+property=["\']article:published_time["\']'
            r'[^>]+content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "meta_og_article_published_time",
        re.compile(
            r'<meta[^>]+property=["\']og:article:published_time["\']'
            r'[^>]+content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "meta_itemprop_datePublished",
        re.compile(
            r'<meta[^>]+itemprop=["\']datePublished["\']'
            r'[^>]+content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "meta_pubdate",
        re.compile(
            r'<meta[^>]+name=["\']pubdate["\']'
            r'[^>]+content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "time_datetime",
        re.compile(
            r'<time[^>]+datetime=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
    ),
    # URL slug: qbitai.com/2026/07/442447.html (3 段,article_id)
    #         thehackernews.com/2026/07/05/... (4 段,有日)
    #         example.com/2026-07-04/news-12345
    # 注: qbitai 类 URL 只到月,使用月级精度(YYYY-MM-01)
    (
        "url_slug_yyyy_mm_dd",
        re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/"),
    ),
    (
        "url_slug_yyyy_mm_id",
        re.compile(
            r"/(20\d{2})/(\d{1,2})/([^/\s]{2,})/?(?:$|#|\?)"
        ),
    ),
    (
        "url_slug_yyyy_mm_dd_dash",
        re.compile(r"/(20\d{2})-(\d{2})-(\d{2})/"),
    ),
]


def _parse_iso_datetime(s: str) -> datetime | None:
    """从 ISO 8601 字符串解析为 tz-aware UTC datetime。

    容忍:
    - 带/不带 microseconds
    - 带/不带 timezone(naive 当作 UTC)
    - None / 空字符串 / 无效格式 → None
    - 年份超出 [2000, 2100] → None (防止 1970/2150 这类异常时间)
    """
    try:
        if s is None:
            return None
        s = s.strip().replace("T", " ")
        if "." in s:
            s = s.split(".")[0]
        if s.endswith("Z"):
            s = s[:-1]
        elif "+" in s or "-" in s[1:]:
            dt = datetime.fromisoformat(s).astimezone(timezone.utc)
            if not (2000 <= dt.year <= 2100):
                return None
            return dt
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        if not (2000 <= dt.year <= 2100):
            return None
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


def _extract_published_at(html: str, source_url: str) -> datetime | None:
    """从页面 HTML 提取发布时间 (仅页面级, 非逐条)。

    Returns
    -------
    tz-aware UTC datetime 或 None
    """
    for name, pattern in _PUBLISHED_AT_PATTERNS:
        m = pattern.search(html)
        if m:
            if name == "url_slug_yyyy_mm_dd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y, mo, d, tzinfo=timezone.utc)
            if name == "url_slug_yyyy_mm_id":
                y, mo = int(m.group(1)), int(m.group(2))
                return datetime(y, mo, 1, tzinfo=timezone.utc)
            if name == "url_slug_yyyy_mm_dd_dash":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y, mo, d, tzinfo=timezone.utc)
            dt = _parse_iso_datetime(m.group(1))
            if dt is not None:
                return dt
    # Fallback: URL slug 提取
    # 4 段: /2026/07/05/...
    slug_match = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", source_url)
    if slug_match:
        y, mo, d = int(slug_match.group(1)), int(slug_match.group(2)), int(slug_match.group(3))
        return datetime(y, mo, d, tzinfo=timezone.utc)
    # 3 段: /2026/07/article_id (qbitai 等只有月级精度)
    slug_match = re.search(
        r"/(20\d{2})/(\d{1,2})/[^/\s]{2,}/?(?:$|#|\?)", source_url
    )
    if slug_match:
        y, mo = int(slug_match.group(1)), int(slug_match.group(2))
        return datetime(y, mo, 1, tzinfo=timezone.utc)
    # dash 段: /2026-07-04/news-12345
    slug_match = re.search(r"/(20\d{2})-(\d{2})-(\d{2})/", source_url)
    if slug_match:
        y, mo, d = int(slug_match.group(1)), int(slug_match.group(2)), int(slug_match.group(3))
        return datetime(y, mo, d, tzinfo=timezone.utc)
    return None


def _is_noise_title(title: str) -> bool:
    """检查标题是否为导航/CTA/噪声内容。"""
    if not title:
        return True
    t = title.strip()
    if not t:
        return True
    low = t.lower()
    if re.fullmatch(r"\d+\s+comments?", low):
        return True
    if low.startswith("permalink to "):
        return True
    NAV_LOWER = {
        "skip to content", "skip to main content",
        "about", "about the author",
        "advertising", "advertising/speaking",
        "menu", "home", "search", "subscribe", "contact",
        "log in", "login", "sign up", "signup",
        "privacy policy", "terms of service",
        "read more", "continue reading", "older posts", "newer posts",
    }
    if low in NAV_LOWER:
        return True
    if low.startswith("about ") and len(t.split()) <= 4:
        return True
    if t[0].islower() and len(t) < 60:
        return True
    NAV_TITLE_LOWER = {
        "our mission", "contact us", "our team", "business", "press release",
        "submit press release", "laws & legalities", "zta gateways",
        "hacking news", "wikileaks", "anonymous",
        "technology", "microsoft",
        "artificial intelligence", "machine learning",
        "cyber crime", "phishing scam", "scams and fraud",
        "security", "censorship", "cyber attacks", "blockchain", "surveillance",
        "contact info", "newsletter", "more books", "more essays", "more tags",
        "archive by month", "homepage", "sitemap", "rss feed",
        "360网络安全周报",
    }
    if low in NAV_TITLE_LOWER:
        return True
    return False


def _is_noise_url(url: str, source_url: str) -> bool:
    """检查 URL 是否为评论/标签/分类/跨域导航等噪声内容。"""
    low = url.lower()
    if any(anchor in low for anchor in ("#comments", "#respond", "#comment-")):
        return True
    URL_PATH_BLOCKLIST = (
        r"/tag/", r"/category/", r"/tags\.html?", r"/tags\.htm",
        r"/about/", r"/about\.",
        r"/books(?:[?#]|$)",
        r"/essays(?:[?#]|$)",
        r"/submit-", r"/submit\.",
        r"/crypto-gram", r"/newsletter", r"/specials/",
        r"/blog/about/",
        r"/job/", r"/company/", r"/subject/id/", r"/week-list",
        r"pedaily\.cn/video/", r"pedaily\.cn/media/",
        r"pedaily\.cn/\d{4}investor/?", r"pedaily\.cn/\d{4}s50/?",
        r"pedaily\.cn/\d{4}f40/?", r"pedaily\.cn/uhk\d{4}/?",
        r"events\.pedaily\.cn",
    )
    if any(re.search(p, low) for p in URL_PATH_BLOCKLIST):
        return True
    if any(q in low for q in ("?author=", "&author=", "?tag=", "&tag=",
                              "?category=", "&category=")):
        return True
    try:
        src_host = urlparse(source_url).netloc.lower()
        url_host = urlparse(url).netloc.lower()
        if src_host and url_host and url_host != src_host:
            return True
    except Exception:
        pass
    return False


def _resolve_url(href: str, base_url: str) -> str:
    """相对路径 → 绝对 URL。"""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return base_url.rstrip("/") + "/" + href.lstrip("/")


__all__ = [
    "_now_utc", "_PUBLISHED_AT_PATTERNS",
    "_parse_iso_datetime", "_extract_published_at",
    "_is_noise_title", "_is_noise_url", "_resolve_url",
]