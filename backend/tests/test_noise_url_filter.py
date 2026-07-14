"""验证 _parse_html 在源头过滤噪音 URL (Task 4 of fix-bug-github-category-dedup)。

被测对象: ``backend.quality.config.NOISE_URL_REGEX`` +
          ``backend.collectors.base.BaseCollector._parse_html``。

覆盖:
  1. beian.miit.gov.cn 备案号链接被过滤
  2. javascript: / void(0) 死链被过滤
  3. tel: / mailto: 联系方式被过滤
  4. # 锚点链接被过滤
  5. 正常绝对 URL 被保留
  6. NOISE_URL_REGEX 自身的行为契约
"""
from __future__ import annotations

import pytest

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category
from backend.quality.config import NOISE_URL_PATTERNS, NOISE_URL_REGEX


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing _parse_html
# ---------------------------------------------------------------------------
class _NoiseTestCollector(BaseCollector):
    category = Category.SECURITY
    max_items = 20

    def _fallback(self):
        return []


@pytest.fixture
def parser():
    return _NoiseTestCollector()


# ===========================================================================
# 1. NOISE_URL_REGEX 自身行为契约
# ===========================================================================
class TestNoiseUrlRegexContract:
    def test_patterns_constant_is_list(self):
        assert isinstance(NOISE_URL_PATTERNS, list)
        assert len(NOISE_URL_PATTERNS) >= 1

    def test_regex_compiled(self):
        assert NOISE_URL_REGEX is not None
        # Pattern 对象支持 .match / .search
        assert hasattr(NOISE_URL_REGEX, "match")

    @pytest.mark.parametrize(
        "url",
        [
            "https://beian.miit.gov.cn/",
            "http://beian.miit.gov.cn",
            "https://beian.miit.gov.cn/query/icp",
        ],
    )
    def test_beian_matched(self, url):
        assert NOISE_URL_REGEX.match(url) is not None, url

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:void(0)",
            "javascript:alert(1)",
            "void(0)",
        ],
    )
    def test_javascript_matched(self, url):
        assert NOISE_URL_REGEX.match(url) is not None, url

    @pytest.mark.parametrize(
        "url",
        [
            "tel:+86-10-12345678",
            "mailto:[email protected]",
        ],
    )
    def test_contact_protocol_matched(self, url):
        assert NOISE_URL_REGEX.match(url) is not None, url

    @pytest.mark.parametrize(
        "url",
        [
            "#section1",
            "#comments",
        ],
    )
    def test_anchor_matched(self, url):
        assert NOISE_URL_REGEX.match(url) is not None, url

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/article/1",
            "http://news.example.com/2026/07/foo.html",
        ],
    )
    def test_normal_url_not_matched(self, url):
        assert NOISE_URL_REGEX.match(url) is None, url


# ===========================================================================
# 2. _parse_html 端到端: 噪音 URL 在源头被过滤
# ===========================================================================
class TestParseHtmlFiltersNoiseUrl:
    def test_beian_miit_url_filtered(self, parser):
        """beian.miit.gov.cn 备案号链接不应进入 raw_items。"""
        html = (
            '<a href="https://beian.miit.gov.cn/">沪ICP备12345678号</a>'
        )
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert items == [], f"beian.miit.gov.cn 应被过滤, 实际: {items}"

    def test_javascript_url_filtered(self, parser):
        """javascript: 死链不应进入 raw_items。"""
        html = '<a href="javascript:void(0)">点我跳转</a>'
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert items == [], f"javascript: 应被过滤, 实际: {items}"

    def test_mailto_url_filtered(self, parser):
        """mailto: 联系方式不应进入 raw_items。"""
        html = '<a href="mailto:[email protected]">联系我们</a>'
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert items == [], f"mailto: 应被过滤, 实际: {items}"

    def test_anchor_only_url_filtered(self, parser):
        """纯 # 锚点链接不应进入 raw_items。"""
        html = '<a href="#section1">跳到第二节</a>'
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert items == [], f"# 锚点应被过滤, 实际: {items}"

    def test_normal_url_preserved(self, parser):
        """正常绝对 URL 应保留。"""
        html = (
            '<a href="https://example.com/article/1">'
            '这是一篇关于噪音过滤的测试文章标题'
            '</a>'
        )
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 1, f"正常 URL 应保留, 实际: {items}"
        assert "测试文章标题" in items[0]["title"]
        assert items[0]["url"] == "https://example.com/article/1"

    def test_mixed_noise_and_normal(self, parser):
        """混合页面: beian 备案号被过滤, 正常文章 URL 保留。"""
        html = """
        <html><body>
            <a href="https://beian.miit.gov.cn/">沪ICP备</a>
            <a href="javascript:void(0)">登录</a>
            <a href="mailto:[email protected]">联系</a>
            <a href="#top">回到顶部</a>
            <a href="https://example.com/article/1">正常文章标题示例</a>
            <a href="https://example.com/article/2">另一篇正常文章标题</a>
        </body></html>
        """
        source = {"name": "test", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # 只应剩 2 条正常文章
        urls = {it["url"] for it in items}
        assert "https://beian.miit.gov.cn/" not in urls
        assert "javascript:void(0)" not in urls
        assert "mailto:[email protected]" not in urls
        assert "#top" not in urls
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls
