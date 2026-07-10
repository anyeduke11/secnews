"""bid_search 单元测试（Phase 19）。

覆盖：
- _is_target_domain: host 后缀匹配 + 排除搜索引擎自身
- parse_bing_html: 真实 b_algo 块解析,按目标域名后置过滤
- build_query: 关键词拼接(不再用 site: 因 cn.bing.com 不遵守)
- search_one_source: 关键词过滤 (is_security_bid) + 去重
- 质量门禁对账: 提取的 URL 都不命中 FORBIDDEN_URL_PATTERNS
- 16 源全部走 search 路径
"""
from __future__ import annotations

from backend.collectors.bid_search import (
    _is_target_domain,
    build_query,
    parse_bing_html,
)
from backend.scripts.purge_synthetic_urls import FORBIDDEN_URL_PATTERNS


# ---------------------------------------------------------------------------
# _is_target_domain
# ---------------------------------------------------------------------------
def test_is_target_domain_exact_match():
    """host 严格等于 target_domain → True。"""
    assert _is_target_domain("https://ccgp.gov.cn/notice/1", "ccgp.gov.cn") is True


def test_is_target_domain_subdomain_match():
    """www.xxx / sub.xxx 也算 target_domain 域名。"""
    assert _is_target_domain("https://www.ccgp.gov.cn/notice", "ccgp.gov.cn") is True
    assert _is_target_domain("https://pms.adbc.com.cn/", "adbc.com.cn") is True


def test_is_target_domain_unrelated():
    """无关域名 → False。"""
    assert _is_target_domain("https://example.com/x", "ccgp.gov.cn") is False
    assert _is_target_domain("https://google.com/search?q=xx", "ccgp.gov.cn") is False


def test_is_target_domain_suffix_attack_blocked():
    """非真正子域(类似 ccfgov.cn) → False,不以 .target 结尾。"""
    assert _is_target_domain("https://ccgp.gov.cn.evil.cn/x", "ccgp.gov.cn") is False


def test_is_target_domain_excludes_search_engines():
    """bing.com / microsoft.com / go.microsoft.com 永远排除。"""
    for url in [
        "https://cn.bing.com/search?q=xx",
        "https://go.microsoft.com/fwlink/123",
        "https://login.live.com/123",
    ]:
        assert _is_target_domain(url, "cn.bing.com") is False, url


# ---------------------------------------------------------------------------
# parse_bing_html
# ---------------------------------------------------------------------------
SAMPLE_BING_HTML = """
<html><body>
<li class="b_algo">
  <h2><a target="_blank" href="https://ccgp.gov.cn/notice/1">国家医疗保障局网络安全运维服务项目招标公告</a></h2>
  <p class="b_lineclamp4 b_algoSlug">项目编号 XYZ,采购网络安全运维服务,预算 200 万元</p>
</li>
<li class="b_algo">
  <h2><a target="_blank" href="https://ec.chng.com.cn/bid/abc">华能集团防火墙设备采购项目</a></h2>
  <p class="b_lineclamp4">WAF 防火墙采购 100 万</p>
</li>
<li class="b_algo">
  <h2><a target="_blank" href="https://www.baidu.com/some">办公楼装修工程招标公告</a></h2>
  <p>无关来源</p>
</li>
<li class="b_algo">
  <h2><a target="_blank" href="https://ccgp.gov.cn/notice/2">等保测评服务采购公告</a></h2>
  <p>等级保护测评</p>
</li>
</body></html>
"""


def test_parse_bing_html_filters_by_target_domain():
    """parse_bing_html 只保留 target_domain 域名下的 URL。"""
    # target=ccgp.gov.cn → 只保留前 1 和 第 4
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn", max_results=10)
    urls = [r.url for r in results]
    assert "https://ccgp.gov.cn/notice/1" in urls
    assert "https://ccgp.gov.cn/notice/2" in urls
    assert "https://ec.chng.com.cn/bid/abc" not in urls
    assert "https://www.baidu.com/some" not in urls
    assert len(results) == 2


def test_parse_bing_html_respects_max_results():
    """max_results 截断生效。"""
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn", max_results=1)
    assert len(results) == 1


def test_parse_bing_html_empty():
    """空 HTML / 0 结果 → 空列表。"""
    assert parse_bing_html("", target_domain="ccgp.gov.cn") == []
    assert parse_bing_html("<html><body>no results</body></html>", target_domain="ccgp.gov.cn") == []


def test_parse_bing_html_extracts_real_urls():
    """返回的 URL 是真实源 URL,不是 bing.com 跳转。"""
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn")
    for r in results:
        assert "bing.com" not in r.url
        assert r.url.startswith(("http://", "https://"))


def test_parse_bing_html_extracts_titles():
    """title 正确提取(去 HTML 标签)。"""
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn")
    titles = [r.title for r in results]
    assert "国家医疗保障局网络安全运维服务项目招标公告" in titles
    assert "等保测评服务采购公告" in titles


def test_parse_bing_html_subdomain_target():
    """target=ec.chng.com.cn 也能匹配。"""
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ec.chng.com.cn")
    assert len(results) == 1
    assert results[0].url == "https://ec.chng.com.cn/bid/abc"


# ---------------------------------------------------------------------------
# build_query
# ---------------------------------------------------------------------------
def test_build_query_default_keywords():
    """默认 query: 四线网安关键词。"""
    q = build_query()
    assert "网络安全" in q
    assert "数据安全" in q
    assert "防火墙" in q


def test_build_query_extra_keywords():
    """额外关键词会拼到 query 末尾。"""
    q = build_query(extra_keywords=["等保 OR 密评"])
    assert "等保" in q
    assert "密评" in q


def test_build_query_no_site_operator():
    """Phase 19.1: 不再用 site: 限定(因 cn.bing.com 不遵守)。"""
    q = build_query()
    assert "site:" not in q


# ---------------------------------------------------------------------------
# 质量门禁对账
# ---------------------------------------------------------------------------
def test_parsed_urls_pass_forbidden_pattern_check():
    """parse_bing_html 提取的所有 URL 都不命中 FORBIDDEN_URL_PATTERNS。

    这是 Phase 19 整合的核心约束: 搜索引擎结果 URL 不能进 DB。
    """
    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn", max_results=20)
    for r in results:
        url_lower = r.url.lower()
        for forbidden in FORBIDDEN_URL_PATTERNS:
            assert forbidden not in url_lower, (
                f"URL {r.url!r} 命中禁止 pattern {forbidden!r}"
            )


def test_parsed_urls_pass_publisher_registry():
    """提取的 URL 域名都已被 publisher_registry 识别(Phase 19 新增 16 源)。

    不识别 → 触发 author_unknown 门禁,虽然不扣分但降低质量分。
    """
    from backend.quality.publisher_registry import resolve_publisher

    results = parse_bing_html(SAMPLE_BING_HTML, target_domain="ccgp.gov.cn", max_results=20)
    for r in results:
        canonical, _, reason = resolve_publisher(r.url)
        assert canonical is not None, (
            f"URL {r.url!r} 域名不在 publisher_registry: {reason}"
        )


# ---------------------------------------------------------------------------
# 关键词过滤
# ---------------------------------------------------------------------------
def test_search_one_source_filters_non_security():
    """search_one_source 走 is_security_bid 过滤掉非网安标讯。"""
    from backend.collectors.bid_search import search_one_source
    from unittest.mock import AsyncMock, patch

    async def fake_fetch(query, timeout=20):
        return SAMPLE_BING_HTML

    with patch(
        "backend.collectors.bid_search.fetch_bing_html",
        new=AsyncMock(side_effect=fake_fetch),
    ):
        import asyncio
        # target=ccgp.gov.cn → 保留 notice/1 (网络安全) + notice/2 (等保)
        # 过滤掉不在 ccgp.gov.cn 的链接
        source = {
            "name": "ccgp-test",
            "url": "https://ccgp.gov.cn/",
            "renderer": "search",
        }
        items = asyncio.run(
            search_one_source(source, max_results=10)
        )

    titles = [it["title"] for it in items]
    assert any("网络安全" in t for t in titles)
    assert any("等保" in t for t in titles)
    # 验证: 装修那条被过滤(原因:①不在 ccgp.gov.cn 域名 ② title 不命中 is_security_bid)
    assert not any("装修" in t for t in titles)
    # 验证: 防火墙(ec.chng.com.cn)被域名过滤掉
    assert not any("防火墙" in t for t in titles)
    # 验证: 所有返回的 URL 都是 ccgp.gov.cn 域名
    for it in items:
        assert "ccgp.gov.cn" in it["url"], f"非 ccgp 域名 URL 漏过: {it['url']}"


# ---------------------------------------------------------------------------
# 16 源全部走 search 路径
# ---------------------------------------------------------------------------
def test_all_phase19_sources_have_search_renderer():
    """Phase 19 16 源全部走 search 路径。"""
    from backend.collectors.bid_collector import BID_SOURCES

    expected_names = {
        "中国农业发展银行集中采购", "银保信", "中国银联采购", "知了标讯", "证保信",
        "华能电子商务平台", "大唐电子商务平台", "华电电子商务平台",
        "中化商务电子招投标", "深圳阳光采购平台",
        "招标采购导航网", "比地招标网", "元博招标网",
        "中国国际招标网", "中国政府采购招标网", "中国外汇交易中心",
    }
    found = {s["name"] for s in BID_SOURCES if s.get("renderer") == "search"}
    missing = expected_names - found
    assert not missing, f"Phase 19 search 源缺失: {missing}"
    assert len(found) >= 16
