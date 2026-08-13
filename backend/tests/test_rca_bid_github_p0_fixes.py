"""P0 RCA 修复回归测试（2026-08-05 rca-bid-github-empty.md）

修复点
------
P0-bid: `backend/quality/config.py:NOISE_URL_PATTERNS` 移除 `r"^/"`,
        避免 `BaseCollector._parse_html` 在解析阶段把站内相对路径
        (如 ``/news/infor/2429.html`` / ``/detail/600632978b18ECC95ACt.html``)
        误判为噪声 → 0 items 入库。

P0-github: `backend/quality/author_verification_gate.py` 新增
        ``_AGGREGATOR_SOURCES`` 白名单。聚合站 (如 TopHub GitHub 热榜)
        抓的 content URL 指向第三方真实站点是正常业务,
        mismatch 时保留 source = 聚合站名,不设 url_check_status='mismatch',
        避免被 API 层 `url_check_status NOT IN ('mismatch')` 过滤全员消失。

覆盖
----
  P0-bid:
    1. NOISE_URL_REGEX 自身不再 match 裸相对路径
    2. 站内相对路径 (含 .html / /news/...) 走 BaseCollector._parse_html
       端到端可被抽出 → 解析为完整 URL
    3. 真实知了标讯/招标采购导航网 URL pattern 走 _parse_html 不被误杀
    4. 边界: 仍能拦截 beian / javascript: / mailto: / 裸 # 等真噪声

  P0-github (AuthorVerificationGate 聚合站豁免):
    1. TopHub + github URL: source 保留, url_check_status 不被设 mismatch
    2. flags 包含 author_via_aggregator + original_publisher=GitHub
    3. category=AI 时被纠正为 GITHUB
    4. 常规 mismatch (e.g. KrebsOnSecurity → MSRC) 行为不变
    5. 正常 match (e.g. source=GitHub, url=github.com) 行为不变
    6. unknown (URL 域名不在注册表) 行为不变
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.author_verification_gate import (
    AuthorVerificationGate,
    PENALTY_MISMATCH,
    PENALTY_UNKNOWN,
    REWARD_MATCH,
    _AGGREGATOR_SOURCES,
)
from backend.quality.base import GateContext
from backend.quality.config import NOISE_URL_PATTERNS, NOISE_URL_REGEX


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_item(
    *,
    title: str = "Sample Title",
    source: str = "src",
    category: Category = Category.SECURITY,
    url: str = "https://example.com/article/1",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id="rca_test_1",
        title=title,
        summary="",
        source=source,
        url=url,
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _ctx() -> GateContext:
    return GateContext(
        mode="loose",
        category_keywords={},
        source_reputation={},
        existing_urls=set(),
        existing_titles=[],
    )


class _StubCollector(BaseCollector):
    """BaseCollector stub for _parse_html 调用."""

    category = Category.SECURITY
    max_items = 50

    def _fallback(self):
        return []


@pytest.fixture
def parser():
    return _StubCollector()


# ===========================================================================
# P0-bid: NOISE_URL_PATTERNS 不再拦截相对路径
# ===========================================================================
class TestNoiseUrlRegexNoLongerKillsRelativePath:
    """回归: r"^/" 已从 NOISE_URL_PATTERNS 移除。"""

    def test_patterns_excludes_caret_slash(self):
        """NOISE_URL_PATTERNS 不能再包含裸 r"^/" pattern。"""
        for p in NOISE_URL_PATTERNS:
            # 兼容正则在 re.compile 后可能是 r"^/" 或被合并,但字符串原值不应单独是 r"^/"
            # 注意: 整个 pattern 是 "|" 拼接, 这里只检查裸条目
            assert p.strip() != r"^/", (
                f"NOISE_URL_PATTERNS 仍含 r'^/': {p!r} - 这是 bid 根因之一"
            )

    @pytest.mark.parametrize(
        "url",
        [
            "/news/infor/2429.html",                # 真实知了标讯相对路径
            "/detail/600632978b18ECC95ACt.html",    # 真实标讯详情路径
            "/bidindustry/i1_k1.html",              # 真实标讯分类路径
            "/article/2026/08/12345.html",          # 通用文章路径
            "/news/",                               # 短路径
        ],
    )
    def test_relative_path_not_matched(self, url):
        """所有站内相对路径都不应被 NOISE_URL_REGEX.match 命中。

        注: NOISE_URL_REGEX.match() 只在字符串开头匹配;
            ^# 仍应匹配 "#section" 但不应匹配 "/news/..."。
        """
        assert NOISE_URL_REGEX.match(url) is None, (
            f"{url!r} 被误判为噪声, 违反 2026-08-05 修复"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://beian.miit.gov.cn/",
            "javascript:void(0)",
            "tel:+86-10-12345678",
            "mailto:[email protected]",
            "#section1",
        ],
    )
    def test_real_noise_still_matched(self, url):
        """真噪声仍应被拦截(避免修复引入回归)。"""
        assert NOISE_URL_REGEX.match(url) is not None, url


# ===========================================================================
# P0-bid: BaseCollector._parse_html 端到端验证
# ===========================================================================
class TestParseHtmlRelativePathEndToEnd:
    """端到端: 站内相对路径可被 _parse_html 抽出, 并通过 _resolve_url 转为绝对 URL。"""

    def test_zhiliaobiaoxun_relative_path_extracted(self, parser):
        """真实知了标讯页面: 大量相对路径 → 至少 1 条应被抽出。"""
        html = """
        <html><body>
            <a href="/news/infor/2429.html">某单位网络安全运维服务项目招标公告</a>
            <a href="/detail/600632978b18ECC95ACt.html">防火墙设备采购项目公开招标</a>
            <a href="/bidindustry/i1_k1.html">等保测评服务项目比选公告</a>
        </body></html>
        """
        source = {"name": "知了标讯", "url": "https://www.zhiliaobiaoxun.com"}
        items = parser._parse_html(html, source)
        assert len(items) >= 1, (
            f"知了标讯相对路径应被抽出, 实际 0 条, items={items}"
        )
        # 所有抽出的 URL 应是绝对 URL (host 已拼接)
        for it in items:
            assert it["url"].startswith("http"), (
                f"应已 resolve 为绝对 URL, 实际: {it['url']!r}"
            )
            assert it["url"].startswith("https://www.zhiliaobiaoxun.com/"), (
                f"resolve 应已拼接 source host: {it['url']!r}"
            )

    def test_resolve_url_uses_source_host(self, parser):
        """resolve 后 URL 应包含 source 的 host。"""
        html = """
        <a href="/news/infor/2429.html">网络安全运维服务项目招标公告标题</a>
        """
        source = {"name": "测试", "url": "https://www.zhiliaobiaoxun.com"}
        items = parser._parse_html(html, source)
        assert len(items) == 1
        assert items[0]["url"] == (
            "https://www.zhiliaobiaoxun.com/news/infor/2429.html"
        )

    def test_root_path_still_filtered_by_is_noise_url(self, parser):
        """边界: 裸根路径 <a href="/">首页</a> 仍应被 _is_noise_url 跨域检查 + 短标题过滤兜底。

        之前 r"^/" 直接拦截, 现在依赖 _is_noise_url 跨域 + 短标题。
        验证: 短标题"首页"不会通过 length>=8 校验, 仍然被过滤。
        """
        html = """
        <a href="/">首页</a>
        <a href="/index.html">回到首页</a>
        """
        source = {"name": "测试", "url": "https://www.zhiliaobiaoxun.com"}
        items = parser._parse_html(html, source)
        # 两条都应被过滤: 短标题/导航词
        urls = {it["url"] for it in items}
        assert "https://www.zhiliaobiaoxun.com/" not in urls
        assert "https://www.zhiliaobiaoxun.com/index.html" not in urls

    def test_relative_path_with_realistic_bid_titles(self, parser):
        """真实招标相对路径 + 真实网安标题 → 全部抽出。"""
        html = """
        <html><body>
            <a href="/news/infor/2429.html">某单位网络安全运维服务项目招标公告</a>
            <a href="/bid/1234.html">防火墙采购项目公开比选公告</a>
            <a href="/detail/abc.html">等保 2.0 三级测评服务项目</a>
            <a href="/article/xyz.html">零信任安全架构建设项目招标公告</a>
        </body></html>
        """
        source = {"name": "测试", "url": "https://www.bid-example.com"}
        items = parser._parse_html(html, source)
        assert len(items) == 4, (
            f"4 个相对路径应全部抽出, 实际 {len(items)} 条, items={items}"
        )
        # 每条都应是绝对 URL
        for it in items:
            assert it["url"].startswith("https://www.bid-example.com/"), it["url"]

    def test_mixed_relative_and_absolute_paths(self, parser):
        """混合: 相对路径 + 绝对路径 + 真噪声 → 正常文章抽出, 噪声被过滤。"""
        html = """
        <html><body>
            <a href="/news/1.html">网络安全运维服务项目招标公告</a>
            <a href="https://other.com/news/2.html">防火墙采购项目公开比选</a>
            <a href="javascript:void(0)">点击登录</a>
            <a href="https://beian.miit.gov.cn/">备案号</a>
            <a href="/bid/3.html">等保测评服务项目招标公告标题</a>
        </body></html>
        """
        source = {"name": "测试", "url": "https://www.bid-example.com"}
        items = parser._parse_html(html, source)
        urls = {it["url"] for it in items}
        # 相对路径应被抽出并 resolve
        assert "https://www.bid-example.com/news/1.html" in urls
        assert "https://www.bid-example.com/bid/3.html" in urls
        # 噪声被过滤
        assert "javascript:void(0)" not in urls
        assert "https://beian.miit.gov.cn/" not in urls


# ===========================================================================
# P0-github: AuthorVerificationGate 聚合站豁免
# ===========================================================================
class TestAuthorVerificationGateAggregatorExemption:
    """TopHub GitHub 热榜等聚合站 mismatch 时,保留 source + 不设 mismatch。"""

    def test_tophub_whitelist_exists(self):
        """_AGGREGATOR_SOURCES 必须包含 TopHub GitHub 热榜。"""
        assert "TopHub GitHub 热榜" in _AGGREGATOR_SOURCES

    def test_tophub_with_github_url_preserves_source(self):
        """TopHub + github URL → source 保留为 TopHub, url_check_status 不被设 mismatch。"""
        g = AuthorVerificationGate()
        item = _make_item(
            title="TencentCloud/TencentDB-Agent-Memory trending repo",
            source="TopHub GitHub 热榜",
            category=Category.AI,  # 初始 AI, 应被纠正为 GITHUB
            url="https://github.com/TencentCloud/TencentDB-Agent-Memory",
        )
        r = g.check(item, _ctx())
        # 1. source 应保留
        assert item.source == "TopHub GitHub 热榜", (
            f"聚合站 source 应保留, 实际被改成: {item.source!r}"
        )
        # 2. url_check_status 不应是 mismatch
        assert item.url_check_status != "mismatch", (
            f"聚合站不应被设 mismatch, 实际: {item.url_check_status!r}"
        )
        # 3. 仍要扣分 (审计风险)
        assert r.score_deduction == PENALTY_MISMATCH
        # 4. flags 应包含豁免标记
        assert "author_via_aggregator" in r.flags
        assert "original_publisher=GitHub" in r.flags
        # 5. category 应被纠正为 GITHUB
        assert item.category == Category.GITHUB
        assert "category_corrected_to=github" in r.flags
        # 6. reason 应说明是聚合站
        assert "author_via_aggregator" in r.reason
        assert "TopHub GitHub 热榜" in r.reason
        # 7. 不会通过 (因为 mismatch, 不是 match)
        assert r.passed is False

    def test_tophub_github_url_with_github_category(self):
        """TopHub + github URL + category 已是 GITHUB → category 不再纠正。"""
        g = AuthorVerificationGate()
        item = _make_item(
            source="TopHub GitHub 热榜",
            category=Category.GITHUB,
            url="https://github.com/owner/repo",
        )
        r = g.check(item, _ctx())
        assert item.source == "TopHub GitHub 热榜"
        assert item.url_check_status != "mismatch"
        assert item.category == Category.GITHUB
        # 不应出现 category_corrected_to (因为 category 已经是 GITHUB)
        assert not any(
            f.startswith("category_corrected_to=") for f in r.flags
        ), f"category 已正确, 不应纠正: {r.flags}"

    def test_normal_mismatch_unchanged_krebsonsecurity_to_msrc(self):
        """回归: 常规 mismatch (KrebsOnSecurity → MSRC) 行为不变。"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            source="KrebsOnSecurity",
        )
        r = g.check(item, _ctx())
        # 常规 mismatch: source 被改写, url_check_status 被设置
        assert item.source == "MSRC (Microsoft Security Response Center)"
        assert item.url_check_status == "mismatch"
        assert "author_mismatch" in r.flags
        assert any(
            f.startswith("author_corrected_to=") for f in r.flags
        )
        # 不会走聚合站豁免路径
        assert "author_via_aggregator" not in r.flags
        assert r.score_deduction == PENALTY_MISMATCH

    def test_normal_match_unchanged(self):
        """回归: 正常 match (KrebsOnSecurity 自己的域名) 行为不变。"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://krebsonsecurity.com/2026/06/foo/",
            source="KrebsOnSecurity",
        )
        r = g.check(item, _ctx())
        # match: 奖励, source 不变, 无 flags
        assert r.passed is True
        assert r.score_deduction == -REWARD_MATCH
        assert item.source == "KrebsOnSecurity"
        assert item.url_check_status is None
        assert r.flags == []

    def test_unknown_url_unchanged(self):
        """回归: URL 域名不在注册表 → 行为不变 (unknown 路径, 不走聚合站豁免)。"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://www.some-random-blog.cn/article/123",
            source="SomeBlog",
        )
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_UNKNOWN
        assert "author_unknown" in r.flags
        assert "author_via_aggregator" not in r.flags
        # source 不被改
        assert item.source == "SomeBlog"
        # url_check_status 不被设
        assert item.url_check_status is None

    def test_aggregator_whitelist_specific_match(self):
        """白名单项: 当聚合站 source 指向自己的 tophub.today URL → 仍 match, 不进豁免路径。"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://tophub.today/n/rYqoXQ8vOD",
            source="TopHub GitHub 热榜",
        )
        r = g.check(item, _ctx())
        # claimed='TopHub GitHub 热榜' 与 canonical='TopHub GitHub 热榜' 匹配
        assert r.passed is True
        assert r.score_deduction == -REWARD_MATCH
        # 不应走豁免路径
        assert "author_via_aggregator" not in r.flags


# ===========================================================================
# 集成: _parse_html 抽出后过 AuthorVerificationGate 端到端
# ===========================================================================
class TestIntegrationParseHtmlThenAuthorGate:
    """模拟完整流程: 标讯页面解析出 item → 跑 AuthorVerificationGate。"""

    def test_bid_parsed_relative_path_then_gate_preserves_source(self):
        """标讯相对路径被 _parse_html 抽出 → 跑 AuthorVerificationGate
        不会误杀 (因为 source 是 bid 站名 + URL 域名一致, 走 match 路径)。
        """
        g = AuthorVerificationGate()
        # 模拟 _parse_html 输出 (已 resolve 为绝对 URL, source 是真实 bid 站)
        item = _make_item(
            title="网络安全运维服务项目招标公告",
            source="采招网",
            category=Category.BID,
            url="https://www.bidcenter.com.cn/news/12345.html",
        )
        r = g.check(item, _ctx())
        # source 域名是 bidcenter.com.cn, 已在 registry → match (claimed '采招网' alias → canonical '采招网')
        assert r.passed is True
        assert item.source == "采招网"  # 保留
        assert item.url_check_status is None
        # 没有 author_via_aggregator (因为 match, 不是 mismatch)
        assert "author_via_aggregator" not in r.flags
