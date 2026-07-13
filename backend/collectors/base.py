"""Collector 抽象基类（Phase 3 重构）。

所有 collector 都继承 ``BaseCollector``，子类必须实现：

- ``category`` ClassVar （指明采集哪一类）
- ``_fallback() -> list[HotspotItem]`` （硬编码备用数据）

子类可按需覆盖：

- ``sources`` / ``timeout`` / ``max_items`` / ``min_items_threshold``
- ``_parse_html()`` 适配特定站点结构
- ``fetch_source()`` 整体替换抓取逻辑（例如走 API 而非 HTML）

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
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp

from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.observability import log_event

# Phase 11: crawl4ai 适配层 (Playwright-based 抓取)。
#   - 可选依赖: 没装 crawl4ai 时 ``is_available()`` 返回 False
#   - 默认关闭 (USE_CRAWL4AI=0);打开后 BaseCollector.fetch_source
#     优先用 crawl4ai 拿 fully-rendered HTML,失败 fallback 到 aiohttp
from backend.utils.crawl4ai_client import fetch_html, is_available as crawl4ai_available

# ----------------------------------------------------------------------
# 可选：项目内的代理感知 aiohttp 包装（``backend.proxy_session``）。
# 老 collector 直接 ``from proxy_session import ProxySession``（依赖
# ``sys.path`` 注入）；新代码优先走 ``backend.`` 命名空间导入，
# 失败时回退到顶层 ``proxy_session``，最终回退到 ``aiohttp.ClientSession``。
# ----------------------------------------------------------------------
try:
    from backend.proxy_session import ProxySession  # type: ignore
    HAS_PROXY = True
except ImportError:  # pragma: no cover
    try:
        from proxy_session import ProxySession  # type: ignore
        HAS_PROXY = True
    except ImportError:  # pragma: no cover
        ProxySession = None  # type: ignore
        HAS_PROXY = False


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _now_utc() -> datetime:
    """tz-aware UTC now。供 Phase 3.5 门禁回写 ``quality_checked_at``。"""
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Bug 2 修复 — 页面级发布时间提取
# ----------------------------------------------------------------------
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
        # /2026/07/442447.html  (article_id 是数字)
        # /2026/06/scattered-spider-hackers  (slug 不带 .html)
        # /2026/05/cisa-admin-leaked  (WordPress slug 形式)
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
    - 'Z' 后缀
    - 含空格日期时间分隔(部分 RSS 格式)
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # 替换空格分隔的日期时间 + 去掉 Z
    s_norm = s.replace(" ", "T").rstrip("Z")
    # 去掉 fractional seconds >6 位
    try:
        # Python 3.11+ 接受 fromisoformat 含 'Z' (3.11+)
        if sys.version_info >= (3, 11):
            dt = datetime.fromisoformat(s_norm)
        else:
            # 旧版本:手动剥 Z
            dt = datetime.fromisoformat(s_norm.rstrip("Z"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # 合理性检查:不能是 1990 年前或 2100 年后
    if dt.year < 2000 or dt.year > 2100:
        return None
    return dt


def _extract_published_at(html: str, source_url: str) -> datetime | None:
    """从 HTML + source URL 提取页面级发布时间。

    按 ``_PUBLISHED_AT_PATTERNS`` 顺序尝试,首个成功匹配的返回。
    失败返回 ``None``(caller fallback 到 fetch time)。

    URL slug 时间精度说明:
    - ``/2026/07/05/...`` (4 段,有日) → YYYY-MM-DD
    - ``/2026/07/442447.html`` (3 段,article_id) → YYYY-MM-01 (月级)
    - ``/2026-07-04/...`` (dash 形式) → YYYY-MM-DD
    """
    # 1) meta / JSON-LD / <time>
    for name, pat in _PUBLISHED_AT_PATTERNS[:6]:
        m = pat.search(html)
        if not m:
            continue
        raw = m.group(1)
        dt = _parse_iso_datetime(raw)
        if dt is not None:
            return dt

    # 2) URL slug 日期
    # 优先尝试 4 段(有日)
    m = _PUBLISHED_AT_PATTERNS[6][1].search(source_url)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return datetime(y, mo, d, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # 月级精度(3 段 /YYYY/MM/article_id.html)
    m = _PUBLISHED_AT_PATTERNS[7][1].search(source_url)
    if m:
        try:
            y, mo = int(m.group(1)), int(m.group(2))
            if 2000 <= y <= 2100 and 1 <= mo <= 12:
                return datetime(y, mo, 1, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # dash 形式
    m = _PUBLISHED_AT_PATTERNS[8][1].search(source_url)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return datetime(y, mo, d, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    return None


# Phase 25: 分类相关度关键词白名单 (module-level 常量)
# 防止综合媒体 (投资界/新浪/36kr) 把无关内容 (旅行社/演唱会/餐饮) 误归类
# 没命中关键词的标题直接 drop, 避免噪声入库
#
# 没列的 category (security / bid / github) 默认放行——它们用领域专用
# 关键词过滤 (security_collector / bid_collector 内部已处理),
# 不需要通用白名单。
_CAT_KEYWORDS: dict[str, list[str]] = {
    "ai": [
        # AI / 大模型
        "AI", "GPT", "LLM", "大模型", "人工智能", "机器学习", "深度学习",
        "神经网络", "AGI", "AIGC", "扩散模型", "推理", "智能体", "Agent",
        "机器人", "具身", "世界模型", "WAIC", "Transformer", "LLama",
        "Claude", "Gemini", "Qwen", "DeepSeek", "豆包", "文心", "通义",
        "Sora", "HBM", "多模态", "RAG", "MoE", "训练",
    ],
    "finance": [
        # 金融 / 投资
        "经济", "股市", "A股", "港股", "美股", "上证", "深证", "创业板",
        "纳斯达克", "标普", "道指", "期货", "外汇", "汇率", "美元", "人民币",
        "黄金", "原油", "大宗", "央行", "美联储", "加息", "降息", "利率",
        "通胀", "GDP", "PMI", "非农", "财报", "营收", "利润", "市值",
        "上市公司", "IPO", "并购", "重组", "证券", "基金", "ETF",
        "宁德", "比亚迪", "苹果", "微软", "英伟达", "台积电", "三星",
        "LG", "SK", "现代", "丰田", "大众", "Meta", "Google",
        "阿里", "腾讯", "字节", "百度", "拼多多", "美团", "京东",
        "高盛", "摩根", "巴菲特", "木头姐", "ARK", "对冲基金",
    ],
    "startup": [
        # 创业 / 融资 / 公司动态
        "融资", "天使轮", "种子轮", "Pre-A", "A轮", "B轮", "C轮", "D轮",
        "Pre-IPO", "估值", "领投", "跟投", "投资人", "创投", "VC",
        "PE", "FA", "路演", "创投号", "新青年", "融资轮", "数千万",
        "数亿", "亿元", "万元", "美元", "完成", "获投", "完成融资",
        "创业", "创始人", "CEO", "90后", "00后", "85后", "95后",
        "独角兽", "上市公司", "并购", "战略投资", "红杉", "IDG",
        "经纬", "源码", "真格", "启明", "DCM", "GGV", "五源",
        "高瓴", "弘毅", "鼎晖", "复星", "软银", "愿景", "老虎",
        "创业公司", "初创", "联合创始人", "孵化", "加速器",
        "YC", "Y Combinator",
    ],
    "tech": [
        # IT / 科技 / 数码
        "科技", "数码", "手机", "iPhone", "Android", "iOS", "HarmonyOS",
        "鸿蒙", "小米", "华为", "OPPO", "vivo", "荣耀", "三星", "苹果",
        "Mac", "MacBook", "iPad", "iMac", "AirPods", "Apple Watch",
        "Windows", "Linux", "Ubuntu", "Chromebook", "Surface",
        "Intel", "AMD", "高通", "联发科", "骁龙", "天玑", "麒麟",
        "显卡", "GPU", "RTX", "处理器", "芯片", "主板", "内存",
        "SSD", "硬盘", "显示器", "笔记本", "台式机", "服务器",
        "Docker", "Kubernetes", "K8s", "开源", "GitHub", "代码",
        "程序员", "开发者", "开发", "前端", "后端", "全栈", "DevOps",
        "数据库", "SQL", "NoSQL", "Redis", "MongoDB", "PostgreSQL",
        "Python", "Java", "Go", "Rust", "C++", "TypeScript", "JavaScript",
        "Solidot", "IT之家", "ithome", "稀土", "掘金", "酷安",
        "发布会", "系统更新", "版本", "升级", "推送",
        "上架", "下架", "App Store", "Play Store", "应用商店",
        "5G", "6G", "Wi-Fi", "蓝牙", "NFC", "USB-C", "Type-C",
        "折叠屏", "全面屏", "曲面屏", "OLED", "LCD", "Mini LED",
        "相机", "摄像", "像素", "光圈", "长焦", "广角", "夜景",
        "AI", "大模型", "LLM", "GPT", "Claude", "Gemini", "DeepSeek",
        "机器人", "无人机", "智能", "自动化", "算法",
    ],
}


def _is_title_relevant_to_category(title: str, category_value: str) -> bool:
    """Phase 25: 分类相关度过滤 (module-level helper)。

    检查 ``title`` 是否命中 ``category_value`` 对应的关键词白名单。
    没在白名单的 category (security/bid/github) 一律放行。
    """
    keywords = _CAT_KEYWORDS.get(category_value)
    if not keywords:
        return True
    return any(kw in title for kw in keywords)


def _session_factory() -> type:
    """Return a session context-manager **class** (not yet instantiated).

    Usage::

        async with _session_factory()() as session:   # type: ignore
            ...
    """
    if HAS_PROXY:
        return ProxySession  # type: ignore
    return aiohttp.ClientSession


class BaseCollector(ABC):
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
    sources: list[dict] = []
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
        """
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        page_published_at = _extract_published_at(html, source["url"])

        def _is_noise_title(title: str) -> bool:
            if not title:
                return True
            t = title.strip()
            if not t:
                return True
            low = t.lower()
            import re as _re
            if _re.fullmatch(r"\d+\s+comments?", low):
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

        def _is_noise_url(url: str) -> bool:
            from urllib.parse import urlparse
            low = url.lower()
            if any(anchor in low for anchor in ("#comments", "#respond", "#comment-")):
                return True
            import re as _url_re
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
            if any(_url_re.search(p, low) for p in URL_PATH_BLOCKLIST):
                return True
            if any(q in low for q in ("?author=", "&author=", "?tag=", "&tag=",
                                      "?category=", "&category=")):
                return True
            try:
                src_host = urlparse(source["url"]).netloc.lower()
                url_host = urlparse(url).netloc.lower()
                if src_host and url_host and url_host != src_host:
                    return True
            except Exception:
                pass
            return False

        def _add_item(title: str, url: str) -> None:
            title = (title or "").strip()
            url = (url or "").strip()
            if _is_noise_title(title) or _is_noise_url(url):
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
                    _add_item(title or text, href)
                    if len(items) >= self.max_items:
                        return items
        return items

        # ---- Stage 2: 常规 <a> 模式（带 title= / 不带）兜底 ----
        patterns = [
            r'<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*>([^<]{8,80})</a>',
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]{8,80})</a>',
        ]
        for pat in patterns:
            for m in re.findall(pat, html):
                if len(m) == 3:
                    href, title, text = m
                else:  # len == 2
                    href, text = m
                    title = text
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

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """raw dicts (``_parse_html`` 输出) → ``HotspotItem`` list。

        Bug 2 修复: ``raw["published_at"]`` 优先(由 ``_parse_html`` 从
        meta / JSON-LD / URL slug 提取);缺失时回退到 fetch time。

        Phase 15: ``ingested_at`` = 录入时间(= now),列表按此字段排序。
        ``published_at`` 保留为文章真实发布时间(可能比 ingested_at 早很多,
        当源页面显示历史内容时)。

        Phase 20: ``bid_status`` 字段(仅 category=bid)从标题正则提取。

        Phase 25: title 通用过滤 (导航 CTA / 超短标题 / 纯标点)
        — 修复部门信源(如投资界、新浪财经)抓到"查看更多 >" / "入驻创投号>>>"
        / "今年暑期旅行社" 等与分类无关的标题。
        """
        from backend.domain.enums import Category as _Cat

        # Phase 20: 标讯状态提取器(惰性导入,避免循环)
        _extract_bid_status = None
        if self.category == _Cat.BID:
            from backend.collectors.bid_status import extract_bid_status
            _extract_bid_status = extract_bid_status

        # Phase 25: 通用 title 导航/CTA 黑名单 (所有 category 共用)
        # 防止投资界 / 新浪财经 / 36kr 等综合媒体把侧栏链接误当标题
        _NAV_CTA = re.compile(
            r"查看更多|更多\s*>>|更多\s*>|立即查看|立即申请|"
            r"立即报名|马上了解|点击查看|>>>|>>>\s*$|>>\s*$|"
            r"入驻\s*\S{0,4}$|注册\s*\S{0,4}$|"
            r"查看全部|点击进入|关注我们|关于我们|"
            r"^\s*[Aa][Bb][Oo][Uu][Tt]\s*$|"
            r"^\s*[Cc][Oo][Nn][Tt][Aa][Cc][Tt]\s*$|"
            r"^更多$|^首页$|^登录$|^注册$"
        )
        _MIN_TITLE_LEN = 8  # 短于 8 字符基本都是 nav / breadcrumb
        _MAX_TITLE_LEN = 200  # 长于 200 通常是把段落当标题

        now = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        skipped = 0
        # Phase 47: 资讯/标讯时效硬门禁 — 本周一 00:00 Asia/Shanghai
        from backend.utils.business_days import current_week_start
        week_start = current_week_start()
        for i, raw in enumerate(raw_items[: self.max_items * 2]):  # 多取些再过滤
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            # Phase 25: 通用 title 过滤
            if not title or len(title) < _MIN_TITLE_LEN:
                skipped += 1
                continue
            if len(title) > _MAX_TITLE_LEN:
                skipped += 1
                continue
            if _NAV_CTA.search(title):
                skipped += 1
                continue
            # Phase 25: 分类相关度过滤 (子类可重写 _title_relevant)
            if not self._title_relevant(title, url, source):
                skipped += 1
                continue
            # Bug 2: 优先用 _parse_html 提取的文章发布时间
            # Phase 47: 不再 fallback 到 now — 缺失 published_at 一律拒绝
            #   原因: 嘶吼等 HTML 抓取源偶尔提取不到发布时间, fallback 到
            #   fetch time 会让历史资讯被当作"当周新资讯"入库, 污染首页。
            #   缺失发布时间 = 无法验证时效性 = 拒收 (宁缺毋滥)。
            published_at = raw.get("published_at")
            if published_at is None:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop no-published_at item {i}: "
                    f"title={title[:40]!r}"
                )
                continue
            # Phase 47: 早于本周一 00:00 Shanghai → 拒收 (历史资讯)
            # type 兜底: 如果上游传了非 datetime (eg 字符串), 拒收
            if not isinstance(published_at, datetime) or published_at.tzinfo is None:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop bad-published_at item {i}: "
                    f"title={title[:40]!r} type={type(published_at).__name__}"
                )
                continue
            if published_at < week_start:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop historical item {i}: "
                    f"pub={published_at.isoformat()} < "
                    f"week_start={week_start.isoformat()}"
                )
                continue
            # Phase 20: 标讯状态提取
            bid_status_val = None
            if _extract_bid_status is not None:
                bid_status_val = _extract_bid_status(
                    title,
                    raw.get("summary", "") or "",
                )
            try:
                items.append(
                    HotspotItem(
                        id=f"{self.name}_{source['name']}_{i}",
                        title=title[:500],
                        summary=(raw.get("summary") or "")[:500] or None,
                        source=source["name"][:50],
                        url=raw["url"],
                        category=self.category,
                        published_at=published_at,
                        fetched_at=now,
                        ingested_at=now,
                        bid_status=bid_status_val,
                        score=source.get("score", 75),
                        is_fallback=False,
                        quality_score=100,
                        quality_flags=[],
                        url_check_status="pending",
                    )
                )
                if len(items) >= self.max_items:
                    break
            except Exception as e:
                self.logger.warning(
                    f"skip item {i}: {type(e).__name__}: {str(e)[:50]}"
                )
        if skipped:
            self.logger.debug(
                f"{source['name']} filtered {skipped} nav/cta/short/irrelevant/no-pub/historical titles"
            )
        return items

    def _title_relevant(
        self, title: str, url: str, source: dict
    ) -> bool:
        """Phase 25: 分类相关度过滤。子类可重写此方法,
        注入自定义过滤逻辑(例如按 source 加白/黑名单)。

        默认实现: 走 ``_CAT_KEYWORDS`` 关键词白名单。
        - ai / finance / startup: 必须命中至少一个关键词才放行
          (阻挡 "查看更多 >" / "演唱会" / "旅行社" 等无关内容)
        - security / bid / github: 默认放行(这些分类用领域专用关键词
          在 collector 内部或 quality gate 里处理)
        """
        return _is_title_relevant_to_category(title, self.category.value)

    def _mark_fallback(
        self, items: list[HotspotItem]
    ) -> list[HotspotItem]:
        """复制 items 并打上 ``is_fallback=True`` + ``"fallback"`` flag。"""
        out: list[HotspotItem] = []
        for item in items:
            flags = list(item.quality_flags)
            if "fallback" not in flags:
                flags.append("fallback")
            out.append(
                item.model_copy(
                    update={"is_fallback": True, "quality_flags": flags}
                )
            )
        return out

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
        if renderer == "crawl4ai" and crawl4ai_available():
            try:
                html = await fetch_html(
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
            session_cls = _session_factory()
            try:
                async with session_cls() as session:
                    async with session.get(
                        source["url"],
                        headers={"User-Agent": UA},
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
        api_url = source.get("api_url") or source["url"]
        # 允许 source 配置里 override headers (例如 AIhot 强制要求特定 UA)
        base_headers = {"User-Agent": UA}
        extra_headers = source.get("headers") or {}
        if extra_headers:
            base_headers.update(extra_headers)
        try:
            session_cls = _session_factory()
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

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """Phase 25 P1: JSON 解析。子类重写, 默认返回空 (renderer=json 源必须实现)。"""
        return []

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

    # ------------------------------------------------------------------
    # 编排
    # ------------------------------------------------------------------
    async def collect(self) -> list[HotspotItem]:
        """默认编排：

        1. 无 sources → 强制 fallback
        2. 并发抓所有 source，合并 items
        3. 全部失败 **或** items 不足 → fallback
        4. 截断到 ``max_items``
        5. **Phase 3.5**：跑同步质量门禁（fallback 跳过）

        Phase 5: 入口打 ``collect_start`` 事件，出口打 ``collect_end`` 事件
        """
        import time as _time
        from uuid import uuid4 as _uuid4

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

    # ------------------------------------------------------------------
    # Phase 3.5 — 质量门禁集成
    # ------------------------------------------------------------------
    # ``True`` 时 collect() 跳过同步门禁（fallback 路径也跳过）。
    # 测试可在 setUp() 里置 True 避免构造 QualityConfig 依赖。
    _skip_quality: bool = False

    async def _run_quality_gates(
        self, items: list[HotspotItem]
    ) -> list[HotspotItem]:
        """跑 :class:`QualityGatePipeline`；fallback 数据原样保留。

        Phase 9.2: 改为 async，每个 item 用 :func:`asyncio.to_thread` 包到
        thread pool 跑，避免 FinalUrlGate 内部 sync urllib 阻塞 event loop。
        """
        import asyncio
        from backend.exceptions import QualityGateFailed
        from backend.quality.config import QualityConfig
        from backend.quality.pipeline import (
            QualityGatePipeline,
            build_context,
        )

        try:
            cfg = QualityConfig()
        except Exception as e:  # pragma: no cover — DB 不可用时兜底
            self.logger.warning(
                f"QualityConfig init failed, skip gates: {e}"
            )
            return items

        # 预拉取 URL / title 集合
        existing_urls: set[str] = set()
        existing_titles: list[str] = []
        try:
            from backend.domain.enums import TimeRange
            from backend.repository.hotspot_repo import HotspotRepository

            hrepo = HotspotRepository()
            db_items, _ = hrepo.query(category=None, time_range=TimeRange.D7, limit=200)
            existing_urls = {str(it.url) for it in db_items}
            existing_titles = [it.title for it in db_items]
        except Exception:
            pass

        # Phase 8 Addendum: 构造本批次 url/title/source 三元组，注入到
        # context.url_title_pairs，供 DuplicateGate 做"同 URL 不同 title"
        # 歧义识别。失败/字段缺失时退化为空列表（DuplicateGate 会跳过该检测）。
        url_title_pairs: list[dict] = []
        try:
            url_title_pairs = [
                {
                    "url": str(it.url),
                    "title": it.title,
                    "source": it.source,
                    "id": it.id,
                    "is_fallback": it.is_fallback,
                    "fetched_at": it.fetched_at,
                }
                for it in items
            ]
        except Exception:
            url_title_pairs = []

        try:
            ctx = build_context(
                cfg,
                existing_urls=existing_urls,
                existing_titles=existing_titles,
                url_title_pairs=url_title_pairs,
            )
            pipeline = QualityGatePipeline(cfg)
        except Exception as e:
            self.logger.warning(
                f"pipeline init failed, skip gates: {e}"
            )
            return items

        out: list[HotspotItem] = []
        for item in items:
            if item.is_fallback:
                out.append(item)
                continue
            try:
                # Phase 9.2: 放到 thread pool 跑，避免 FinalUrlGate 内
                # 同步 urllib 阻塞 event loop
                presult = await asyncio.to_thread(pipeline.run_all, item, ctx)
            except QualityGateFailed as e:
                # 严格模式拒绝：丢弃该 item
                self.logger.warning(
                    f"strict-mode reject: id={item.id} score={e.score} flags={e.flags}"
                )
                continue
            except Exception as e:
                # 门禁本身崩了：保留原 item
                self.logger.error(f"gate pipeline error: {e}")
                out.append(item)
                continue

            # 写回 quality_score / quality_flags / quality_checked_at
            out.append(
                item.model_copy(
                    update={
                        "quality_score": presult.final_score,
                        "quality_flags": presult.final_flags,
                        "quality_checked_at": _now_utc(),
                    }
                )
            )
        return out


__all__ = ["BaseCollector"]
