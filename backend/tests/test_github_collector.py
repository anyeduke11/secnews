"""GitHubCollector 单元测试（Phase 6）。

覆盖：
  - ``category`` 设置为 ``Category.GITHUB``
  - ``_fallback()`` 返回 ≥ ``min_items_threshold`` 条且全部为 GITHUB 分类
  - ``HAS_PROXY`` 代理会话可用
  - 已注册进 :class:`CollectionService` 的 collectors 字典
  - Phase 9: fallback URL 必须是真实的 ``https://github.com/{owner}/{repo}`` 格式
  - Phase 9: ``_is_repo_url`` 过滤器正确识别真实项目链接
  - Phase 9: ``_extract_repo_url`` 从 title 正确提取 URL
"""
from __future__ import annotations

from backend.collectors.base import HAS_PROXY
from backend.collectors.github_collector import (
    GITHUB_SOURCES,
    GitHubCollector,
    _extract_repo_url,
    _is_repo_url,
)
from backend.domain.enums import Category
from backend.services.collection_service import CollectionService


# ---------------------------------------------------------------------------
# 基本属性
# ---------------------------------------------------------------------------
def test_github_collector_has_category():
    """GitHubCollector 的 category 应为 ``Category.GITHUB``。"""
    assert GitHubCollector().category is Category.GITHUB


def test_github_collector_name():
    """GitHubCollector.name == 'github'。"""
    assert GitHubCollector().name == "github"


# ---------------------------------------------------------------------------
# _fallback 行为 (Phase 13 硬约束: fallback 必须返回空列表)
# ---------------------------------------------------------------------------
def test_github_collector_fallback_returns_empty():
    """Phase 13 硬约束 (SPEC §3.3.1): GitHubCollector 不实现 _fallback。
    BaseCollector 默认 _fallback() 返回 [],子类继承即可。
    """
    c = GitHubCollector()
    items = c._fallback()
    assert items == [], (
        f"GitHubCollector._fallback() 返回 {len(items)} 条合成数据,违反 Phase 13 硬约束"
    )


# ---------------------------------------------------------------------------
# _is_repo_url 过滤器
# ---------------------------------------------------------------------------
def test_is_repo_url_accepts_real_project_urls():
    """Phase 9: 真实项目链接应被接受。"""
    real_urls = [
        "https://github.com/langchain-ai/langgraph",
        "https://github.com/openai/openai-python",
        "https://github.com/ggerganov/llama.cpp",
        "https://github.com/denoland/deno",
        "https://github.com/rust-cli/ripgrep",
        "https://github.com/star-history/star-history",
    ]
    for url in real_urls:
        assert _is_repo_url(url), f"应接受真实项目链接: {url}"


def test_is_repo_url_rejects_non_project_urls():
    """Phase 9: 非项目链接应被拒绝。"""
    bad_urls = [
        "https://github.com/trending",
        "https://github.com/trending/developers",
        "https://github.com/trending/projects/0",
        "https://github.com/collections",
        "https://github.com/sponsors/explore",
        "https://github.com/security",
        "https://github.com/topics/github",
        "https://github.com/topics/star-history",
        "https://docs.github.com/search-github/github-code-search/syntax",
        "https://github.community/",
        "https://meetily.ai/",
        "https://bytebase.com/?source=star-history",
        "https://github.com/star-history/star-history/blob/main/README.md",
        "https://github.com/star-history/star-history/#start-of-content",
        "https://github.com/star-history",  # 只有 owner 没有 repo
    ]
    for url in bad_urls:
        assert not _is_repo_url(url), f"应拒绝非项目链接: {url}"


# ---------------------------------------------------------------------------
# _extract_repo_url 从 title 提取
# ---------------------------------------------------------------------------
def test_extract_repo_url_from_title():
    """Phase 9: 从 title 提取真实项目 URL。"""
    cases = [
        ("langchain-ai/langgraph: 构建可编排 AI Agent 的开源框架",
         "https://github.com/langchain-ai/langgraph"),
        ("openai/openai-python: OpenAI 官方 Python SDK v2.0 发布",
         "https://github.com/openai/openai-python"),
        ("ggerganov/llama.cpp: 本地 LLM 推理引擎",
         "https://github.com/ggerganov/llama.cpp"),
    ]
    for title, expected in cases:
        assert _extract_repo_url(title) == expected, (
            f"从 title {title!r} 提取的 URL 不正确"
        )


def test_extract_repo_url_fallback_to_trending():
    """Phase 9: 无法从 title 提取时回退到 GitHub Trending 主页（非 404）。"""
    assert _extract_repo_url("没有 owner/repo 格式的标题") == "https://github.com/trending"


# ---------------------------------------------------------------------------
# _parse_html 重写（从 GitHub Trending HTML 提取真实项目链接）
# ---------------------------------------------------------------------------
def test_parse_html_extracts_repo_links_from_article_cards():
    """Phase 9: 从 GitHub Trending 页面结构提取真实项目链接。"""
    html = """
    <html><body>
    <nav><a href="/trending">Trending</a> | <a href="/collections">Collections</a></nav>
    <article class="Box-row">
      <h2><a href="/langchain-ai/langgraph">langchain-ai/langgraph</a></h2>
      <p>Build resilient language agents as graphs.</p>
    </article>
    <article class="Box-row">
      <h2><a href="/openai/openai-python">openai/openai-python</a></h2>
      <p>The official Python library for the OpenAI API.</p>
    </article>
    <article class="Box-row">
      <h2><a href="/trending">Some non-repo link</a></h2>
    </article>
    <footer><a href="/about">About</a></footer>
    </body></html>
    """
    c = GitHubCollector()
    source = {"name": "GitHub Trending", "url": "https://github.com/trending"}
    items = c._parse_html(html, source)

    # 应该提取出 2 个真实项目链接，过滤掉 /trending /collections /about
    assert len(items) == 2
    urls = [it["url"] for it in items]
    assert "https://github.com/langchain-ai/langgraph" in urls
    assert "https://github.com/openai/openai-python" in urls
    # 确保非项目链接被过滤
    assert "https://github.com/trending" not in urls
    assert "https://github.com/collections" not in urls


# ---------------------------------------------------------------------------
# Proxy 会话
# ---------------------------------------------------------------------------
def test_github_collector_uses_proxy_session():
    """HAS_PROXY 应为 True（GitHub 走代理）。"""
    assert HAS_PROXY is True


# ---------------------------------------------------------------------------
# sources 配置
# ---------------------------------------------------------------------------
def test_github_collector_sources_match_module_constant():
    """instance.sources 数量与模块级常量 GITHUB_SOURCES 一致。"""
    c = GitHubCollector()
    assert len(c.sources) == len(GITHUB_SOURCES)
    assert len(c.sources) >= 2


# ---------------------------------------------------------------------------
# Phase 29: TopHub GitHub 热榜 (聚合站, SSR HTML, 默认 aiohttp 抓取)
# ---------------------------------------------------------------------------
def test_tophub_source_in_github_sources():
    """Phase 29: tophub.today 的"GitHub 今日热榜"分类页应注册到 GITHUB_SOURCES。"""
    tophub_sources = [s for s in GITHUB_SOURCES if "tophub" in s["url"]]
    assert len(tophub_sources) == 1, (
        f"应有且仅有一个 tophub GitHub 热榜源, 实际: {tophub_sources}"
    )
    src = tophub_sources[0]
    assert src["url"] == "https://tophub.today/n/rYqoXQ8vOD"
    assert src["name"] == "TopHub GitHub 热榜"
    # 不写 renderer → 走默认 aiohttp (无需 crawl4ai)
    assert "renderer" not in src, (
        "tophub 是 SSR HTML, 走默认 aiohttp 抓取, 不应强制 renderer=crawl4ai"
    )


def test_parse_html_tophub_extracts_repo_links():
    """Phase 29: 从 tophub.today 列表页 HTML 提取真实 GitHub 项目链接。

    页面结构特征:
    - 每个项目是 <a href="https://github.com/{owner}/{repo}">owner / repo</a>
    - 旁边有排名数字 (1, 2, 3...) 和 star 数 (6.4万)
    - 顶部有导航 (登录, 首页, 近期历史)
    - 默认 _parse_html 的 <a> regex 要求文本 8-80 字符, 排名/star 数字
      < 8 字符被自动过滤; 导航文本 < 8 字符也自动过滤
    - _is_repo_url 进一步只接受 github.com/{owner}/{repo} 形式
    """
    html = """
    <html><body>
    <nav>
      <a href="/">首页</a>
      <a href="/login">登录</a>
      <a href="/history">近期历史</a>
    </nav>
    <div class="list">
      <a href="https://github.com/harry0703/MoneyPrinterTurbo">harry0703 / MoneyPrinterTurbo</a>
      <a href="https://github.com/Lum1104/Understand-Anything">Lum1104 / Understand-Anything</a>
      <a href="https://github.com/affaan-m/ECC">affaan-m / ECC</a>
      <a href="https://github.com/anthropics/knowledge-work-plugins">anthropics / knowledge-work-plugins</a>
      <a href="https://github.com/obra/superpowers">obra / superpowers</a>
    </div>
    <div class="metrics">
      <span>1</span><span>6.4万</span>
      <span>2</span><span>4.1万</span>
    </div>
    </body></html>
    """
    c = GitHubCollector()
    source = {
        "name": "TopHub GitHub 热榜",
        "url": "https://tophub.today/n/rYqoXQ8vOD",
    }
    items = c._parse_html(html, source)

    # 应该提取出 5 个真实项目链接
    assert len(items) == 5, f"应提取 5 个项目, 实际: {len(items)}"
    urls = [it["url"] for it in items]
    assert "https://github.com/harry0703/MoneyPrinterTurbo" in urls
    assert "https://github.com/Lum1104/Understand-Anything" in urls
    assert "https://github.com/affaan-m/ECC" in urls
    assert "https://github.com/anthropics/knowledge-work-plugins" in urls
    assert "https://github.com/obra/superpowers" in urls
    # 导航/排名/star 数字被 _is_repo_url 拒绝
    for bad in ("/", "/login", "/history"):
        assert bad not in urls, f"导航链接 {bad} 应被 _is_repo_url 拒绝"
    # title 应是 <a> 文本 (owner / repo 形式)
    titles = [it["title"] for it in items]
    assert "harry0703 / MoneyPrinterTurbo" in titles


# ---------------------------------------------------------------------------
# CollectionService 注册
# ---------------------------------------------------------------------------
def test_github_collector_registers_in_collection_service():
    """``CollectionService().collectors`` 应包含 ``Category.GITHUB``。"""
    svc = CollectionService()
    assert Category.GITHUB in svc.collectors
    assert isinstance(svc.collectors[Category.GITHUB], GitHubCollector)
