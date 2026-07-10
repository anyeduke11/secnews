"""GitHub / 开源生态热点数据采集器（Phase 6）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.GITHUB``
- ``sources``   : GitHub Trending / Star History
- ``timeout``   : 25s（GitHub 页面 JS 重）
- ``max_items`` : 30
- ``min_items_threshold`` : 5

外网抓取走 ``BaseCollector.fetch_source`` 默认实现（HTML 锚点正则解析）；
抓取失败 / 数量不足时走 ``_fallback()``，返回 8 条覆盖 2026 年热门
开源项目（LLM 工具 / AI Agent / Rust CLI / IDE 插件等）的合成数据。

Phase 9 修复：
1. fallback 数据的 URL 从 title 中提取真实 ``owner/repo``，构造
   ``https://github.com/{owner}/{repo}`` 格式，避免点击卡片 404。
2. 重写 ``_parse_html``：从 GitHub Trending 页面的 ``<article>`` 卡片
   中提取真实项目链接，过滤掉导航 / footer / topics 等非项目链接。
3. 添加 ``_is_repo_url`` 过滤器：只保留 ``/{owner}/{repo}`` 格式的 URL。
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

GITHUB_SOURCES: list[dict] = [
    {
        "name": "GitHub Trending",
        "url": "https://github.com/trending",
        "score": 82,
        "keywords": ["github", "trending", "open-source"],
        "renderer": "crawl4ai",  # Phase 14: JS SPA 需要 Playwright 渲染
    },
    {
        "name": "Star History",
        "url": "https://github.com/star-history/star-history",
        "score": 78,
        "keywords": ["github", "star", "history"],
        "renderer": "crawl4ai",
    },
    {
        # Phase 29: tophub.today 聚合站"GitHub 今日热榜"分类页
        # 页面是 SSR 渲染的普通 HTML, 默认 aiohttp 抓取即可 (无需 crawl4ai)
        # 链接形如 <a href="https://github.com/owner/repo">owner / repo</a>
        # 默认 _parse_html 的 <a> regex 文本 8-80 字符能命中
        # 再经 _is_repo_url 过滤只接受 github.com/{owner}/{repo} 形式
        "name": "TopHub GitHub 热榜",
        "url": "https://tophub.today/n/rYqoXQ8vOD",
        "score": 76,
        "keywords": ["github", "trending", "tophub", "open-source", "聚合"],
        # 不写 renderer → 走默认 aiohttp
    },
]

# 匹配 title 开头的 ``owner/repo`` 模式（如 ``langchain-ai/langgraph: ...``）
_OWNER_REPO_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)")

# GitHub 非项目路径前缀（导航 / footer / topics / docs 等）
_NON_REPO_PATHS = {
    "/trending", "/collections", "/sponsors", "/security", "/topics",
    "/explore", "/marketplace", "/pricing", "/features", "/enterprise",
    "/about", "/opensource", "/customer-stories", "/readme", "/events",
    "/community", "/organization", "/notifications", "/login", "/signup",
    "/session", "/settings", "/new", "/codespaces", "/copilot",
    "/search", "/footer", "/site", "/github-sponsors",
}

# 文档 / 社区 / 外部站点域名
_NON_REPO_HOSTS = {
    "docs.github.com", "help.github.com", "support.github.com",
    "github.community", "resources.github.com", "skills.github.com",
    "lab.github.com", "education.github.com",
}


def _is_repo_url(url: str) -> bool:
    """判断 URL 是否是真实的 GitHub 项目链接。

    真实项目链接格式：``https://github.com/{owner}/{repo}``（无更多路径）。

    排除：
    - 非 github.com 域名（docs.github.com / github.community / 外部站点）
    - 路径段数 != 2（如 /trending、/topics/x、/owner/repo/blob/...）
    - owner 或 repo 命中非项目路径（/trending、/collections 等）
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # 只接受 github.com / www.github.com，其他域名（docs.github.com、
    # github.community、bytebase.com、meetily.ai 等）都不是项目链接
    if parsed.hostname not in ("github.com", "www.github.com"):
        return False

    # 带查询参数或 fragment 的不是干净项目链接（如 /owner/repo/?source=x、
    # /owner/repo/#start-of-content）— 真实项目链接应直接是 /owner/repo
    if parsed.query or parsed.fragment:
        return False

    path = parsed.path.rstrip("/")
    if not path:
        return False  # 根路径

    parts = path.lstrip("/").split("/")
    if len(parts) != 2:
        return False  # 不是 /owner/repo 格式

    owner, repo = parts
    if not owner or not repo:
        return False
    if f"/{owner}" in _NON_REPO_PATHS or f"/{owner}/{repo}" in _NON_REPO_PATHS:
        return False
    # owner 以 "-" 开头或包含 "." 通常是特殊路径
    if owner.startswith("-") or "." in owner:
        return False
    # repo 不能是纯数字（避免 /trending/123 之类）
    if repo.isdigit():
        return False
    return True


def _extract_repo_url(title: str) -> str:
    """从 title 中提取 ``owner/repo`` 并构造 ``https://github.com/{owner}/{repo}``。

    title 格式示例：
    - ``langchain-ai/langgraph: 构建可编排 AI Agent 的开源框架``
    - ``openai/openai-python: OpenAI 官方 Python SDK v2.0 发布``
    - ``ggerganov/llama.cpp: 本地 LLM 推理引擎 Q4_K_M 性能再翻倍``

    匹配失败时回退到 GitHub Trending 主页（避免 404）。
    """
    m = _OWNER_REPO_RE.match(title.strip())
    if m:
        owner, repo = m.group(1), m.group(2)
        repo = repo.rstrip("/").removesuffix(".git")
        return f"https://github.com/{owner}/{repo}"
    return "https://github.com/trending"


class GitHubCollector(BaseCollector):
    """采集 GitHub / 开源生态热点项目数据。"""

    category = Category.GITHUB
    name = "github"
    sources = GITHUB_SOURCES
    timeout = 60  # Phase 30: stealth 模式 + 真实浏览器启动慢, GitHub Trending 需 60s
    max_items = 30
    min_items_threshold = 5

    def _parse_html(self, html: str, source: dict) -> list[dict[str, Any]]:
        """重写: 从 GitHub / GitHub 聚合站页面提取真实项目链接。

        策略:
        1. 优先从 ``<article>`` 卡片中提取 ``<h1>/<h2>`` 内的 ``<a href="/owner/repo">``
           (GitHub Trending 页面结构)
        2. 回退到从所有 ``<a href="...">text</a>`` 抓取, 但用 ``_is_repo_url`` 严格过滤
           (tophub.today / Star History 等聚合站结构)
        3. 关键: 不调 ``super()._parse_html``, 跳过 base 默认的
           ``_is_noise_title("t[0].islower() and len(t) < 60")`` 误判 —
           ``owner / repo`` 形式 (e.g. "harry0703 / MoneyPrinterTurbo") 都是小写开头,
           会被 base 误判为"句子片段"过滤掉
        4. 确保所有 URL 都是 ``https://github.com/{owner}/{repo}`` 格式
        """
        items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # 策略 1：从 article 卡片提取（GitHub Trending 页面结构）
        # 匹配 <article>...<h1><a href="/owner/repo">...</a></h1>...</article>
        article_pattern = re.compile(
            r'<article[^>]*>(.*?)</article>',
            re.DOTALL | re.IGNORECASE,
        )
        repo_link_pattern = re.compile(
            r'<h[12][^>]*>\s*<a[^>]*href="(/[^"]+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE,
        )

        for article_match in article_pattern.finditer(html):
            article_html = article_match.group(1)
            for link_match in repo_link_pattern.finditer(article_html):
                href = link_match.group(1)
                text = link_match.group(2).strip()
                if not text or len(text) < 2:
                    continue
                full_url = self._resolve_url(href, source["url"])
                if not _is_repo_url(full_url):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                items.append({
                    "title": text,
                    "summary": source.get("name", ""),
                    "url": full_url,
                })
                if len(items) >= self.max_items:
                    return items

        # 策略 2：从所有 <a href> 提取 (覆盖 tophub.today / Star History 等
        # 无 <article> 卡片结构的页面)。关键差异: 不调 super()._parse_html,
        # 自己提取后用 _is_repo_url 严格过滤, 跳过 base 的 _is_noise_title 误判。
        if len(items) < self.min_items_threshold:
            # 匹配 <a href="...">text</a>, text 长度 2-200 (覆盖 owner/repo + 短链接)
            generic_link_pattern = re.compile(
                r'<a[^>]*href="([^"]+)"[^>]*>([^<]{2,200})</a>',
                re.IGNORECASE,
            )
            for m in generic_link_pattern.finditer(html):
                href = m.group(1)
                text = m.group(2).strip()
                if not text:
                    continue
                full_url = self._resolve_url(href, source["url"])
                if not _is_repo_url(full_url):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                items.append({
                    "title": text,
                    "summary": source.get("name", ""),
                    "url": full_url,
                })
                if len(items) >= self.max_items:
                    break

        return items


__all__ = ["GitHubCollector", "GITHUB_SOURCES"]
