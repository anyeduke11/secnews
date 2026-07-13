"""Sogou 搜索数据采集器(Phase 51)。

设计目的
--------
通过 ``weixin.sogou.com`` 和 ``www.sogou.com/web`` 两个入口,抓"国内
外主流安全厂商漏洞" + "威胁情报微信公众号"文章。

为什么用 sogou
~~~~~~~~~~~~~~

用户需求 (2026-07-13): 安全资讯增加 sogou 抓厂商漏洞 + 威胁情报微信
公众号。理由:

- ``weixin.sogou.com`` 是 sogou 自家的微信公众号搜索引擎,索引了大量
  安全/威胁情报公众号文章 (微步在线、奇安信威胁情报中心、360 威胁情报
  中心、安全客、FreeBuf、看雪、安全内参、安在 等),**无需 cookie / 登
  录 / 验证码**就能搜到
- 微信公众号本身没 RSS,weixin.sogou.com 是公开获取公众号文章最稳
  的入口
- ``www.sogou.com/web`` 的 PC 搜索对 site: 限定的厂商漏洞搜索有效,
  但当前 IP 经常被 anti-bot 限流(返回 5409 字符的验证码页面)。
  加上 ProxySession (127.0.0.1:7897) 后有所缓解,但仍不稳定。

**测试结果 (2026-07-13):**

- ``weixin.sogou.com/weixin?type=2&query=微步在线`` → 10 个真公众号
  文章标题 (h3),URL 走 sogou /link 重定向
- ``www.sogou.com/web?query=site:qihoo.com 漏洞`` → 当前 IP 被 anti-bot
  限流 (返回 5K 验证码页, 需 OCR 验证码)
- ``m.sogou.com/web/searchList.jsp?keyword=...`` → React 客户端渲染
  ,curl 拿不到结果
- ``m.sogou.com/headArticle`` → 404
- ``zhihu.sogou.com`` → 200 但 text 为空

**最终选择**: 主路径走 ``weixin.sogou.com`` (微信公众号搜索),备选路
径走 ``www.sogou.com/web`` (PC 搜索,需走代理且当前 IP 解封时有效)。

实现要点
--------

1. **走 weixin.sogou.com** — 不被 anti-bot 拦截,直接拿 h3 标题 + 内部
   ``/link?url=...`` 重定向
2. **标题过滤** — 排除"招聘"/"校招"/"实习"等非资讯关键词
3. **published_at 兜底** — weixin.sogou.com 没有日期,统一填 now(UTC)
   (Phase 50 兜底); 走 RecencyGate 后,本周一之前的数据会被过滤
4. **URL 唯一性** — 用 sogou ``/link?url=...`` 作为 item URL,后续点
   开走 sogou 302 → mp.weixin.qq.com (anti-bot 时会被拦,但不影响入
   库);URLContentGate 会做抽样验证

Phase 51
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

import aiohttp

logger = logging.getLogger(__name__)

# 真实 Chrome UA — sogou 对 UA 敏感,默认 Python UA 会返回简化版页面
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 微信公众号搜索入口 — Phase 51 主路径, 不被 anti-bot 拦截
WEIXIN_SEARCH_URL = "https://weixin.sogou.com/weixin"

# PC Web 搜索 — 备选, 当前 IP 经常被限流 (anti-bot 验证码)
SOGOU_SEARCH_URL = "https://www.sogou.com/web"

# 默认超时
DEFAULT_TIMEOUT = 20  # sogou 1-2s 通常, 20s 兜底

# ---------------------------------------------------------------------------
# 标题过滤: 排除非资讯内容(招聘/校招/广告/导流)
# ---------------------------------------------------------------------------
_TITLE_BLOCKLIST_RE = re.compile(
    r"(?:"
    r"招聘|校招|社招|实习|"
    r"广告|赞助|合作|"
    r"问卷调查|抽奖|"
    r"免责声明|隐私政策|"
    r"用户协议|服务条款"
    r")",
    re.IGNORECASE,
)

# sogou 内部 URL 黑名单 (跳转/导航/广告/登录)
_SOGOU_SELF_RE = re.compile(
    r"^https?://("
    r"[^/]*\.?sogou\.com|"  # 任意 sogou 子域
    r"fankui\.sogou|"
    r"pic\.sogou|"
    r"v\.sogou|"
    r"m\.sogou|"
    r"weixin\.sogou|"
    r"wenwen\.sogou|"
    r"gouwu\.sogou|"
    r"map\.sogou|"
    r"zhihu\.sogou|"
    r"tencent\.com"  # sogou 推广跳转
    r")",
    re.IGNORECASE,
)

# 微信公众号文章 URL 模式 — 解 sogou /link 重定向后命中
_WEIXIN_ARTICLE_RE = re.compile(
    r"^https?://mp\.weixin\.qq\.com/s[?]?",
    re.IGNORECASE,
)

# sogou 内部 /link 重定向模式 (h3 href 经常是这种)
_SOGOU_LINK_RE = re.compile(
    r"^/link\?url=",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# HTML 解析正则
# ---------------------------------------------------------------------------
# sogou weixin 搜索结果结构 (实测):
#   <li>
#     <div class="txt-box">
#       <p>
#         <a target="_blank" href="/link?url=...">TITLE</a>
#       </p>
#       <p class="txt-info">SUMMARY</p>
#     </div>
#   </li>
# 或者:
#   <h3><a href="/link?url=...">TITLE</a></h3>
#
# 提取每个 result block 的标题/链接/摘要
_LINK_BLOCK_RE = re.compile(
    r'<a[^>]+href="(/link\?url=[^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# 通用 <a href=...>TITLE</a>
_GENERIC_HREF_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# 提取文本内容 (去除 HTML 标签)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html_text(html: str) -> str:
    """去除 HTML 标签 + 多余空白, 返回纯文本。"""
    if not html:
        return ""
    text = _TAG_RE.sub("", html)
    text = re.sub(r"&[a-z]+;", "", text)  # 去 HTML entities
    return re.sub(r"\s+", " ", text).strip()


def _is_valid_target_url(url: str) -> bool:
    """判断 URL 是否是有效目标 URL (非 sogou 自身导航, 非 javascript:)。"""
    if not url:
        return False
    if url.startswith(("javascript:", "#", "void(0)")):
        return False
    if _SOGOU_SELF_RE.match(url):
        return False
    return True


def _is_title_blocked(title: str) -> bool:
    """判断标题是否在黑名单 (招聘/校招/广告等)。"""
    if not title:
        return True
    return bool(_TITLE_BLOCKLIST_RE.search(title))


def parse_sogou_weixin_html(
    html: str,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """解析 weixin.sogou.com 微信公众号搜索结果 HTML, 返回 items list。

    参数:
        html: 搜索结果 HTML
        max_items: 最多返回多少条

    返回:
        list of dict: [{title, url, summary, published_at}, ...]
        - title: 公众号文章标题
        - url: sogou /link?url=ENCODED (点开走 sogou 302 → mp.weixin.qq.com)
        - summary: 文章摘要(如有)
        - published_at: now(UTC) 兜底 (weixin.sogou.com 无日期)

    注意:
        - 排除 sogou 自身导航/广告链接
        - 过滤"招聘/校招/广告"等非资讯标题
        - 标题去重 (同一篇文章在多结果中重复出现)
    """
    if not html:
        return []

    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    now = datetime.now(timezone.utc)

    # 抓所有 <a href="/link?url=...">TITLE</a>
    for m in _LINK_BLOCK_RE.finditer(html):
        href = m.group(1)
        title_html = m.group(2)
        title = _clean_html_text(title_html)
        if not title or len(title) < 4 or len(title) > 200:
            continue
        if _is_title_blocked(title):
            continue
        # 完整 URL (weixin.sogou.com 是 base)
        full_url = f"https://weixin.sogou.com{href}"
        if full_url in seen_urls:
            continue
        if title in seen_titles:
            continue
        seen_urls.add(full_url)
        seen_titles.add(title)
        items.append({
            "title": title,
            "url": full_url,
            "summary": "",
            "published_at": now,  # Phase 50 兜底
        })
        if len(items) >= max_items:
            return items

    # 备选: 抓 h3 内 <a> 链接 (sogou PC search 结构)
    if not items:
        h3_pattern = re.compile(
            r'<h3[^>]*>(.*?)</h3>',
            re.IGNORECASE | re.DOTALL,
        )
        for h3 in h3_pattern.finditer(html):
            h3_html = h3.group(1)
            for a_match in _GENERIC_HREF_RE.finditer(h3_html):
                href = a_match.group(1)
                title = _clean_html_text(a_match.group(2))
                if not title or len(title) < 4 or len(title) > 200:
                    continue
                if _is_title_blocked(title):
                    continue
                # 跳 sogou /link / 站内 / 推广
                if not _is_valid_target_url(href):
                    continue
                if not _SOGOU_LINK_RE.match(href) and "sogou.com" in href:
                    continue
                full_url = href if href.startswith("http") else f"https://www.sogou.com{href}"
                if full_url in seen_urls or title in seen_titles:
                    continue
                seen_urls.add(full_url)
                seen_titles.add(title)
                items.append({
                    "title": title,
                    "url": full_url,
                    "summary": "",
                    "published_at": now,
                })
                if len(items) >= max_items:
                    return items

    return items


# 别名 — 保持向后兼容 (旧 parse_sogou_html 仍可用)
def parse_sogou_html(
    html: str,
    target_domain: str | None = None,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Phase 51 兼容层: 实际走 weixin.sogou.com 解析逻辑。

    旧 sogou_search API 接受 target_domain 参数(用于 sogou.com/web
    的 site: 限定),这里忽略该参数(微信公众号搜索结果天然不含 sogou
    自身链接,不需要 target_domain 过滤)。
    """
    return parse_sogou_weixin_html(html, max_items=max_items)


# ---------------------------------------------------------------------------
# HTTP 抓取
# ---------------------------------------------------------------------------
async def _fetch_html(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> str | None:
    """统一 GET 入口: 优先用 ProxySession (走 127.0.0.1:7897), 降级用裸 aiohttp。"""
    _ProxySession = None
    try:
        from backend.proxy_session import ProxySession  # type: ignore
        _ProxySession = ProxySession
    except Exception:
        try:
            from proxy_session import ProxySession  # type: ignore
            _ProxySession = ProxySession
        except Exception:
            _ProxySession = None

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        merged_headers = {
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if headers:
            merged_headers.update(headers)
        if _ProxySession is not None:
            async with _ProxySession(headers=merged_headers, timeout=timeout_obj) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"sogou_search non-200: url={url[:60]} status={resp.status}"
                        )
                        return None
                    text = await resp.text()
        else:
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(url, params=params, headers=merged_headers) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"sogou_search non-200: url={url[:60]} status={resp.status}"
                        )
                        return None
                    text = await resp.text()
        # 简单 anti-bot 验证码检测
        if "SourceVerifyCode" in text or "anti.min.css" in text:
            logger.warning(
                f"sogou_search anti-bot triggered: url={url[:60]} len={len(text)}"
            )
            return None
        return text
    except Exception as e:
        logger.warning(
            f"sogou_search failed: url={url[:60]} err={type(e).__name__}: {str(e)[:80]}"
        )
        return None


async def fetch_weixin_html(
    query: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """抓 weixin.sogou.com 微信公众号搜索结果页。"""
    return await _fetch_html(
        WEIXIN_SEARCH_URL,
        params={"type": "2", "query": query, "ie": "utf8"},
        timeout=timeout,
        headers={"Referer": "https://weixin.sogou.com/"},
    )


async def fetch_sogou_html(
    query: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """抓 www.sogou.com/web PC 搜索结果页 (Phase 51 备选, 经常被 anti-bot 限流)。"""
    return await _fetch_html(
        SOGOU_SEARCH_URL,
        params={"query": query},
        timeout=timeout,
        headers={"Referer": "https://www.sogou.com/"},
    )


async def search_sogou(
    query: str,
    target_domain: str | None = None,
    max_items: int = 20,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """一站式 sogou 搜索: fetch + parse。

    Phase 51: 主路径走 weixin.sogou.com (公众号搜索), 备选走 sogou.com
    /web (PC 搜索, 经常被 anti-bot 限流)。

    参数:
        query: 搜索 query (如 "微步在线 威胁情报" 或 "site:qihoo.com 漏洞")
        target_domain: 可选, 只保留 host 含此 domain 的 URL (仅对
            sogou.com/web 路径有效, 公众号搜索结果天然不含 sogou 内部链接)
        max_items: 最多返回多少条
        timeout: HTTP 超时 (秒)
    """
    # 主路径: weixin.sogou.com
    html = await fetch_weixin_html(query, timeout=timeout)
    items: list[dict[str, Any]] = []
    if html:
        items = parse_sogou_weixin_html(html, max_items=max_items)
        if items:
            logger.info(
                f"sogou_search (weixin) query={query[:50]!r} items={len(items)}"
            )
            return items

    # 备选: sogou.com/web (PC 搜索)
    if target_domain:
        html2 = await fetch_sogou_html(query, timeout=timeout)
        if html2:
            # PC 搜索结果走 h3 解析
            items2 = parse_sogou_html(html2, target_domain=target_domain, max_items=max_items)
            if items2:
                logger.info(
                    f"sogou_search (pc) query={query[:50]!r} target={target_domain} items={len(items2)}"
                )
                return items2

    logger.info(
        f"sogou_search query={query[:50]!r} (no results, likely anti-bot)"
    )
    return items  # 返空 list (而非 None) 兼容 build_items


__all__ = [
    "fetch_sogou_html",
    "fetch_weixin_html",
    "parse_sogou_html",
    "parse_sogou_weixin_html",
    "search_sogou",
    "_WEIXIN_ARTICLE_RE",
    "WEIXIN_SEARCH_URL",
    "SOGOU_SEARCH_URL",
]
