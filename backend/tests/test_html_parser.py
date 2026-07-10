"""Phase 10 修复: HTML parser 噪声过滤 + entry-title 优先匹配

覆盖:
  1. ``test_entry_title_priority``: 主页 h1/h2.entry-title 内的 <a rel=bookmark> 优先被抽到
  2. ``test_filter_comment_count_link``: "99 Comments" / "X comments" 链接被过滤
  3. ``test_filter_permalink_attribute``: "Permalink to X" WordPress 锚点属性被过滤
  4. ``test_filter_skip_to_content``: "Skip to content" 导航链接被过滤
  5. ``test_filter_url_anchor``: URL 含 #comments 锚点被过滤
  6. ``test_decode_html_entity``: 标题中 &#8217; / &amp; 等 HTML entity 被 decode
  7. ``test_krebs_full_html_simulation``: 真实 KrebsOnSecurity 主页 HTML 模拟
  8. ``test_filter_lowercase_fragment``: "a blog post" / "residential proxy" 等小写开头短语被过滤
  9. ``test_max_items_respected``: max_items 上限被尊重
 10. ``test_dedup_works``: 同一标题只出现一次
"""
from __future__ import annotations

import pytest

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing _parse_html
# ---------------------------------------------------------------------------
class _TestCollector(BaseCollector):
    category = Category.SECURITY
    max_items = 20

    def _fallback(self):
        return []


@pytest.fixture
def parser():
    return _TestCollector()


# ===========================================================================
# 1. entry-title 优先匹配
# ===========================================================================
class TestEntryTitlePriority:
    def test_h2_entry_title_a_bookmark_extracted(self, parser):
        """WordPress 标准: <h2 class="entry-title"><a rel="bookmark">真实标题</a></h2>"""
        html = """
        <html><body>
            <h2 class="entry-title">
                <a href="https://krebsonsecurity.com/2026/05/cisa-admin-leaked/"
                   rel="bookmark">CISA Admin Leaked AWS GovCloud Keys on Github</a>
            </h2>
        </body></html>
        """
        source = {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 1
        assert items[0]["title"] == "CISA Admin Leaked AWS GovCloud Keys on Github"
        assert "krebsonsecurity.com/2026/05" in items[0]["url"]

    def test_h1_entry_title_also_works(self, parser):
        """文章详情页: <h1 class="entry-title"> 也可"""
        html = """
        <h1 class="entry-title">Detailed Article Title Here</h1>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # h1.entry-title 但没有 <a rel=bookmark> 不会被 stage 1 匹配
        # stage 2 fallback 抓到 <h1> text? 不, stage 2 只抓 <a>
        # 所以 h1.entry-title 单独不会被抓
        assert items == []

    def test_mixed_entry_title_and_other_links(self, parser):
        """entry-title 模式下, comment 链接被忽略, 只保留 article 链接"""
        html = """
        <h2 class="entry-title">
            <a href="https://krebsonsecurity.com/2026/05/article-a/" rel="bookmark">Real Article A</a>
        </h2>
        <h2 class="entry-title">
            <a href="https://krebsonsecurity.com/2026/05/article-b/" rel="bookmark">Real Article B</a>
        </h2>
        <a href="https://krebsonsecurity.com/2026/05/article-a/#comments">17 Comments</a>
        <a href="https://krebsonsecurity.com/2026/05/article-b/#comments">34 Comments</a>
        <a href="https://krebsonsecurity.com/about/">About the Author</a>
        <a href="https://krebsonsecurity.com/cpm/">Advertising/Speaking</a>
        <a href="https://krebsonsecurity.com/#content">Skip to content</a>
        """
        source = {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/"}
        items = parser._parse_html(html, source)
        # 只有 2 个 entry-title 模式的 article 链接
        assert len(items) == 2
        titles = {it["title"] for it in items}
        assert "Real Article A" in titles
        assert "Real Article B" in titles
        # 噪声全部被过滤
        for it in items:
            assert "Comments" not in it["title"]
            assert "#comments" not in it["url"]
            assert "Permalink" not in it["title"]


# ===========================================================================
# 2. 噪声过滤
# ===========================================================================
class TestNoiseFilter:
    def test_filter_comment_count_link(self, parser):
        """'X comments' 链接应被过滤"""
        html = """
        <a href="https://example.com/article1/">17 Comments</a>
        <a href="https://example.com/article2/">99 comments</a>
        <a href="https://example.com/article3/">1 Comment</a>
        <a href="https://example.com/real/">Real Article Title</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 1
        assert items[0]["title"] == "Real Article Title"

    def test_filter_permalink_attribute(self, parser):
        """WordPress 'Permalink to X' 标题属性应被过滤"""
        html = """
        <a href="https://example.com/article1/" title="Permalink to Real Article One">Real Article One</a>
        <a href="https://example.com/real/">Real Article Title</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # 'Permalink to Real Article One' 是 title 属性, 但 _add_item 检查 title 变量
        # 实际: pattern 1 抓 (href, title, text) -> title 来自 title 属性
        # 但 _is_noise_title 拦截 'permalink to ...'
        # 第二个 <a> 是 Real Article Title
        titles = [it["title"] for it in items]
        # "Permalink to Real Article One" 不应出现
        assert not any(t.lower().startswith("permalink to ") for t in titles)
        # 真实标题应出现
        assert "Real Article Title" in titles

    def test_filter_skip_to_content(self, parser):
        """'Skip to content' / 'About' 导航应被过滤"""
        html = """
        <a href="https://example.com/skip">Skip to content</a>
        <a href="https://example.com/main">Skip to main content</a>
        <a href="https://example.com/about">About the Author</a>
        <a href="https://example.com/ad">Advertising/Speaking</a>
        <a href="https://example.com/real">Real Article Title Here</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # 只有 Real Article Title Here
        assert len(items) == 1
        assert items[0]["title"] == "Real Article Title Here"

    def test_filter_url_with_anchor(self, parser):
        """URL 含 #comments / #respond / #comment-123 锚点的链接应被过滤"""
        html = """
        <a href="https://example.com/article/#comments">17 Comments</a>
        <a href="https://example.com/article/#respond">Reply</a>
        <a href="https://example.com/article/#comment-42">Comment by user</a>
        <a href="https://example.com/real">Real Article Title Here</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 1
        assert items[0]["title"] == "Real Article Title Here"

    def test_filter_lowercase_fragment(self, parser):
        """'a blog post' / 'residential proxy' 等小写开头短语应被过滤"""
        html = """
        <a href="https://example.com/blog">a blog post</a>
        <a href="https://example.com/breach">a breach</a>
        <a href="https://example.com/proxy">residential proxy</a>
        <a href="https://example.com/real">Real Article Title Here</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # 小写开头的短语应被过滤
        assert len(items) == 1
        assert items[0]["title"] == "Real Article Title Here"


# ===========================================================================
# 3. HTML entity decode
# ===========================================================================
class TestHTMLEntityDecode:
    def test_decode_apos(self, parser):
        """&#8217; → ' (right single quotation mark)"""
        html = """
        <h2 class="entry-title">
            <a href="https://example.com/x/" rel="bookmark">Who Runs the Group &#8216;Popa&#8217; Botnet?</a>
        </h2>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 1
        # 实体被 decode 为 unicode 字符
        assert "‘Popa’" in items[0]["title"]
        assert "&#8216;" not in items[0]["title"]
        assert "&#8217;" not in items[0]["title"]

    def test_decode_amp(self, parser):
        """&amp; → &"""
        html = """
        <h2 class="entry-title">
            <a href="https://example.com/x/" rel="bookmark">Q&amp;A: Real Article Title</a>
        </h2>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert "&amp;" not in items[0]["title"]
        assert "&" in items[0]["title"]


# ===========================================================================
# 4. 真实 KrebsOnSecurity 主页 HTML 模拟
# ===========================================================================
class TestKrebsOnSecurityRealistic:
    def test_realistic_krebs_html(self, parser):
        """模拟 KrebsOnSecurity 主页真实 HTML 结构"""
        html = """
        <html>
        <body>
            <h2 class="entry-title">
                <a href="https://krebsonsecurity.com/2026/05/cisa-admin-leaked-aws-govcloud-keys-on-github/" rel="bookmark">CISA Admin Leaked AWS GovCloud Keys on Github</a>
            </h2>
            <h2 class="entry-title">
                <a href="https://krebsonsecurity.com/2026/05/lawmakers-demand-answers-as-cisa-tries-to-contain-data-leak/" rel="bookmark">Lawmakers Demand Answers as CISA Tries to Contain Data Leak</a>
            </h2>
            <a href="https://krebsonsecurity.com/2026/05/cisa-admin-leaked-aws-govcloud-keys-on-github/#comments">99 comments</a>
            <a href="https://krebsonsecurity.com/2026/05/lawmakers-demand-answers-as-cisa-tries-to-contain-data-leak/#comments">17 Comments</a>
            <a href="https://krebsonsecurity.com/about/" title="Permalink to about page">About the Author</a>
            <a href="https://krebsonsecurity.com/cpm/">Advertising/Speaking</a>
            <a href="https://krebsonsecurity.com/#content">Skip to content</a>
        </body>
        </html>
        """
        source = {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/"}
        items = parser._parse_html(html, source)
        # 只有 2 个真实 article
        assert len(items) == 2
        titles = {it["title"] for it in items}
        assert titles == {
            "CISA Admin Leaked AWS GovCloud Keys on Github",
            "Lawmakers Demand Answers as CISA Tries to Contain Data Leak",
        }
        # 噪声全部消失
        for it in items:
            assert "#comments" not in it["url"]
            assert "comments" not in it["title"].lower()
            assert "advertising" not in it["title"].lower()
            assert "about" not in it["title"].lower()
            assert "skip" not in it["title"].lower()

    def test_no_entry_title_falls_back_to_a_pattern(self, parser):
        """如果 HTML 没有 entry-title, stage 2 兜底抓 <a>"""
        html = """
        <a href="https://example.com/article1/">Article One Title Here</a>
        <a href="https://example.com/article2/">Article Two Title Here</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == 2


# ===========================================================================
# 5. max_items + dedup
# ===========================================================================
class TestMaxItemsAndDedup:
    def test_max_items_respected(self, parser):
        html = "<br>".join(
            f'<a href="https://example.com/{i}/">Article Title Number {i} Here</a>'
            for i in range(50)
        )
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        assert len(items) == parser.max_items

    def test_dedup_same_title(self, parser):
        html = """
        <a href="https://example.com/a/">Real Article Title</a>
        <a href="https://example.com/b/">Real Article Title</a>
        <a href="https://example.com/c/">Real Article Title</a>
        """
        source = {"name": "X", "url": "https://example.com/"}
        items = parser._parse_html(html, source)
        # 同一标题只出现一次
        assert len(items) == 1
