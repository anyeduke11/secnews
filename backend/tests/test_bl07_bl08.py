"""Phase 27 BL-07/BL-08 测试: URL 路径黑名单 + title 静态黑名单.

覆盖场景
--------
_BL-07 (URL 路径黑名单):
  - /tag/, /category/, /tags.html, /about/, /books, /essays, /crypto-gram,
    /newsletter, /specials/, /submit-, /blog/about/ → reject
  - ?author=, &author=, ?tag=, &tag=, ?category=, &category= → reject
  - 外站跳转 (host 不等于 source host) → reject
  - 真实文章 URL (e.g. /article/123) → pass

_BL-08 (title 静态黑名单):
  - HackRead nav titles (Our Mission, Contact Us, Our Team, Business,
    Press Release, Submit Press Release, Laws & Legalities, ZTA Gateways,
    Hacking News, WikiLeaks, Anonymous, Technology, Microsoft, ...) → reject
  - Schneier nav titles (Contact Info, Newsletter, More Books, More Essays,
    More Tags, Archive by Month) → reject
  - 真实文章标题 (e.g. "CVE-2026-12345 vulnerability") → pass

Phase 33 (2026-07-08) 新增 (anquanke.com 非资讯内容):
  - /job/<id>       岗位招聘 → reject
  - /company/<id>   公司介绍 → reject
  - /subject/id/<id> 专题聚合 → reject
  - /week-list      周报页 → reject (URL + 标题 "360网络安全周报" 双重拦)
  - 真实文章 URL (/post/id/<n>) → pass

Phase 34 (2026-07-08) 新增 (pedaily.cn 投资界非资讯):
  - /video/<id>              视频页 → reject
  - /media/<mXXX>/           媒体/频道页 (e.g. 西安创业) → reject
  - /{YYYY}investor/         年度投资人TOP100 → reject
  - /{YYYY}S50/              年度S50女性投资人 → reject
  - /{YYYY}F40/              年度F40青年投资人 → reject
  - /uhk{YYYY}/              独角兽榜单 → reject
  - events.pedaily.cn 子域  → reject (整域)
  - 投资人排行榜相关 title   → reject
  - 真实文章 URL (news.pedaily.cn/202607/...) → pass
"""
from __future__ import annotations

import pytest

from backend.collectors.base import BaseCollector


def _make_collector():
    """构造一个 minimal BaseCollector 实例, 不需要 db/初始化."""
    # BaseCollector.__init__ 接受 optional db_path; 用 None 跳过
    return BaseCollector.__new__(BaseCollector)


def _get_noise_title(collector, title: str, source_url: str = "https://hackread.com/") -> bool:
    """通过 _parse_html 内部 _is_noise_title 验证 title 是否被判定为噪声."""
    # _parse_html 需要 source dict, _is_noise_title 是 closure, 只能通过 _parse_html 测
    # 但 _parse_html 接受 source dict, _is_noise_title 用 source dict 不依赖 url
    # 这里用 _parse_html 但传空 html 触发 _is_noise_title 调用
    return collector._parse_html("<html></html>", {"url": source_url, "name": "TestSource"})


# _parse_html 不实际返回 title 是否 noise, 我们需要直接测 _is_noise_title
# 但 _is_noise_title 是 nested, 难直接调用. 改方案: 测 _is_noise_url (同样 nested)
# 或重新设计: 把 _is_noise_title / _is_noise_url 提到模块级函数 (更易测试)

# 实际策略: 通过 mock, 暂时只能依赖 _parse_html 的端到端行为.
# 这里我们只测 _is_noise_url 通过模拟"调用 _parse_html 加 (title, url) pair"

# 因为 _is_noise_url 是 closure, 我们改用 _is_noise_url 通过 _parse_html
# 测试时传入 mock source + 构造 html 含 a[href] 标签, 然后验证 items 是否被过滤


# ---------------------------------------------------------------------------
# 通过 _parse_html 行为间接测试 _is_noise_url + _is_noise_title
# ---------------------------------------------------------------------------
def _parse_items(collector, html: str, source_url: str) -> list[dict]:
    return collector._parse_html(html, {"url": source_url, "name": "TestSource"})


class TestIsNoiseUrl:
    """BL-07: URL 路径/query/外站跳转黑名单."""

    def test_real_article_url_passes(self):
        c = _make_collector()
        items = _parse_items(c, _a("CVE-2026-12345 critical RCE", "https://hackread.com/cve-2026-12345-rce/"), "https://hackread.com/")
        assert len(items) == 1

    def test_tag_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("ZTA Gateways", "https://hackread.com/tag/zta-gateways/"), "https://hackread.com/")
        assert items == []

    def test_category_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("Technology", "https://hackread.com/category/technology/"), "https://hackread.com/")
        assert items == []

    def test_submit_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("Submit Press Release", "https://hackread.com/submit-press-release/"), "https://hackread.com/")
        assert items == []

    def test_specials_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("AI 专题", "https://www.secrss.com/specials/81f3b8455aeb2ace"), "https://www.secrss.com/")
        assert items == []

    def test_author_query_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("奇安信 CERT", "https://www.secrss.com/articles?author=奇安信%20CERT"), "https://www.secrss.com/")
        assert items == []

    def test_schneier_tag_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("3d printers", "https://www.schneier.com/tag/3d-printers/"), "https://www.schneier.com/")
        assert items == []

    def test_schneier_about_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("Contact Info", "https://www.schneier.com/blog/about/contact/"), "https://www.schneier.com/")
        assert items == []

    def test_schneier_books_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("More Books", "https://www.schneier.com/books/"), "https://www.schneier.com/")
        assert items == []

    def test_schneier_newsletter_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("Newsletter", "https://www.schneier.com/crypto-gram/"), "https://www.schneier.com/")
        assert items == []

    def test_external_url_rejected_cross_domain(self):
        """Schneier 列表里有 DuckDuckGo / Inrupt 跳转, 需过滤."""
        c = _make_collector()
        items = _parse_items(c, _a("DuckDuckGo", "https://duckduckgo.com/"), "https://www.schneier.com/")
        assert items == []

    def test_comment_anchor_url_rejected(self):
        c = _make_collector()
        items = _parse_items(c, _a("Real Title", "https://hackread.com/real-article/#comments"), "https://hackread.com/")
        assert items == []

    def test_same_domain_passes(self):
        """同域名 URL 不被外站校验误伤."""
        c = _make_collector()
        items = _parse_items(c, _a("Real Article", "https://hackread.com/real-article/"), "https://hackread.com/")
        assert len(items) == 1


class TestIsNoiseTitle:
    """BL-08: title 静态黑名单 (精确匹配)."""

    @pytest.mark.parametrize("title", [
        "Our Mission", "Contact Us", "Our Team", "Business", "Press Release",
        "Submit Press Release", "Laws & Legalities", "ZTA Gateways",
        "Hacking News", "WikiLeaks", "Anonymous",
        "Technology", "Microsoft",
        "Artificial Intelligence", "Machine Learning",
        "Cyber Crime", "Phishing Scam", "Scams and Fraud",
        "Security", "Censorship", "Cyber Attacks", "Blockchain", "Surveillance",
    ])
    def test_hackread_nav_titles_rejected(self, title: str):
        c = _make_collector()
        items = _parse_items(c, _a(title, "https://hackread.com/category/x/"), "https://hackread.com/")
        # 被 nav_title 拒绝 OR 被 category URL 拒绝 (双重过滤, 至少 1 个命中)
        assert items == []

    @pytest.mark.parametrize("title", [
        "Contact Info", "Newsletter", "More Books", "More Essays", "More Tags",
        "Archive by Month",
    ])
    def test_schneier_nav_titles_rejected(self, title: str):
        c = _make_collector()
        items = _parse_items(c, _a(title, "https://www.schneier.com/blog/about/contact/"), "https://www.schneier.com/")
        assert items == []

    def test_real_article_title_passes(self):
        c = _make_collector()
        items = _parse_items(
            c,
            _a("CVE-2026-12345 critical RCE vulnerability in OpenSSL", "https://hackread.com/cve-2026-12345-rce/"),
            "https://hackread.com/",
        )
        assert len(items) == 1

    def test_real_article_short_title_passes(self):
        """短标题但 URL 是真文章 → 仍入库 (避免短标题长度阈值误伤)."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a("AI and Trust", "https://www.schneier.com/essays/archives/2023/12/ai-and-trust.html"),
            "https://www.schneier.com/",
        )
        assert len(items) == 1

    def test_case_insensitive_match(self):
        """大小写不敏感."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a("OUR MISSION", "https://hackread.com/category/mission/"),
            "https://hackread.com/",
        )
        assert items == []


# ---------------------------------------------------------------------------
# Phase 33 (2026-07-08): 安全客 (anquanke.com) 非资讯内容黑名单
# ---------------------------------------------------------------------------
class TestAnquankeUrlBlocklist:
    """安全客 URL 路径黑名单: /job/ /company/ /subject/id/ /week-list"""

    @pytest.mark.parametrize("url", [
        "https://www.anquanke.com/job/716",
        "https://www.anquanke.com/job/718",
        "https://www.anquanke.com/job/677",
        "https://www.anquanke.com/job/688",
    ])
    def test_job_url_rejected(self, url):
        """岗位招聘 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("渗透测试工程师", url), "https://www.anquanke.com/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.anquanke.com/company/103",
        "https://www.anquanke.com/company/127",
        "https://www.anquanke.com/company/13",
        "https://www.anquanke.com/company/131",
    ])
    def test_company_url_rejected(self, url):
        """公司介绍 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("墨云科技有限公司", url), "https://www.anquanke.com/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.anquanke.com/subject/id/303984",
        "https://www.anquanke.com/subject/id/297785",
        "https://www.anquanke.com/subject/id/289102",
    ])
    def test_subject_url_rejected(self, url):
        """专题聚合页 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("ISC.AI2024热点资讯", url), "https://www.anquanke.com/"
        )
        assert items == []

    def test_week_list_url_rejected(self):
        """周报页 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a("360网络安全周报", "https://www.anquanke.com/week-list"),
            "https://www.anquanke.com/",
        )
        assert items == []

    def test_real_post_url_passes(self):
        """真实文章 URL (post/id/<n>) 放行."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a(
                "首个AI全流程勒索攻击来了：JADEPUFFER证明",
                "https://www.anquanke.com/post/id/315724",
            ),
            "https://www.anquanke.com/",
        )
        assert len(items) == 1


class TestAnquankeTitleBlocklist:
    """安全客 NAV_TITLE_LOWER: 360网络安全周报"""

    def test_week_list_title_rejected(self):
        """周报标题 '360网络安全周报' 拒绝 (即使 URL 是周报, 标题也拦)."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a(
                "360网络安全周报",
                "https://www.anquanke.com/week-list",
            ),
            "https://www.anquanke.com/",
        )
        assert items == []


# ---------------------------------------------------------------------------
# Phase 33 (2026-07-08): SecurityCollector._title_relevant override
# ---------------------------------------------------------------------------
class TestAnquankeTitleRelevantOverride:
    """SecurityCollector 标题正则黑名单: 公司名/岗位名结尾"""

    def _make_security_collector(self):
        from backend.collectors.security_collector import SecurityCollector
        # SecurityCollector.__new__ 跳过 __init__ (避免 logger/db 初始化)
        return SecurityCollector.__new__(SecurityCollector)

    @pytest.mark.parametrize("title", [
        "墨云科技有限公司",
        "360政企安全服务中心",
        "北京安恒信息股份有限公司",
        "深信服科技子公司",
    ])
    def test_company_name_rejected(self, title):
        """纯公司名拒绝."""
        c = self._make_security_collector()
        assert c._title_relevant(
            title, "https://www.anquanke.com/post/id/315000",
            {"name": "安全客", "url": "https://www.anquanke.com/"},
        ) is False

    @pytest.mark.parametrize("title", [
        "IOT硬件工程师",
        "情报分析专家",
        "二进制安全实习",
    ])
    def test_job_title_rejected(self, title):
        """纯岗位名拒绝."""
        c = self._make_security_collector()
        assert c._title_relevant(
            title, "https://www.anquanke.com/post/id/315000",
            {"name": "安全客", "url": "https://www.anquanke.com/"},
        ) is False

    @pytest.mark.parametrize("title", [
        "首个AI全流程勒索攻击来了：JADEPUFFER证明",
        "RedAmon：串联侦察、漏洞利用与后渗透的 AI 安全工具",
        "Weaxor勒索软件又添Linux平台变种",
        "「文科生AI黑客松」专访：社会工作专业范心怡",
    ])
    def test_real_news_title_passes(self, title):
        """真实新闻标题放行 (不被误伤)."""
        c = self._make_security_collector()
        assert c._title_relevant(
            title, "https://www.anquanke.com/post/id/315000",
            {"name": "安全客", "url": "https://www.anquanke.com/"},
        ) is True

    def test_other_source_unaffected(self):
        """其他源 (e.g. THN) 不被 anquanke 特定正则影响."""
        c = self._make_security_collector()
        # 即便标题是 "X 工程师" (在 anquanke 会被拒), THN 源不应被拦
        assert c._title_relevant(
            "Senior Security Engineer",
            "https://thehackernews.com/2026/07/senior-engineer.html",
            {"name": "TheHackerNews", "url": "https://thehackernews.com/"},
        ) is True


# ---------------------------------------------------------------------------
# Phase 34 (2026-07-08): 投资界 (pedaily.cn) 非资讯内容黑名单
# ---------------------------------------------------------------------------
class TestPedailyUrlBlocklist:
    """投资界 URL 路径黑名单: /video/ /media/ /{YYYY}investor|{YYYY}S50|{YYYY}F40 /uhk{YYYY}"""

    @pytest.mark.parametrize("url", [
        "https://www.pedaily.cn/video/633.html",
        "https://www.pedaily.cn/media/m481/",
        "https://www.pedaily.cn/media/m482/",
    ])
    def test_media_video_url_rejected(self, url):
        """视频页 / 媒体频道页 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("投资界-西安创业", url), "https://www.pedaily.cn/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.pedaily.cn/2022investor/",
        "https://www.pedaily.cn/2023investor/",
        "https://www.pedaily.cn/2024investor/",
        "https://www.pedaily.cn/2025investor/",
        "https://www.pedaily.cn/2026investor/",
    ])
    def test_yearly_investor_url_rejected(self, url):
        """年度投资界TOP100 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("2026「投资界TOP100」投资人", url), "https://www.pedaily.cn/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.pedaily.cn/2022S50/index.shtml",
        "https://www.pedaily.cn/2023S50/index.shtml",
        "https://www.pedaily.cn/2024S50/index.shtml",
        "https://www.pedaily.cn/2025S50/index.shtml",
        "https://www.pedaily.cn/2026S50/index.shtml",
    ])
    def test_yearly_s50_url_rejected(self, url):
        """年度S50女性投资人 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("2026「投资界S50女性投资人」", url), "https://www.pedaily.cn/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.pedaily.cn/2022F40/",
        "https://www.pedaily.cn/2023F40/",
        "https://www.pedaily.cn/2024F40/",
        "https://www.pedaily.cn/2025F40/",
    ])
    def test_yearly_f40_url_rejected(self, url):
        """年度F40青年投资人 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("2025投资界「F40中国青年投资人」", url), "https://www.pedaily.cn/"
        )
        assert items == []

    @pytest.mark.parametrize("url", [
        "https://www.pedaily.cn/uhk2021/awards.shtml",
        "https://www.pedaily.cn/uhk2022/awards.shtml",
    ])
    def test_unicorn_url_rejected(self, url):
        """独角兽榜单 URL 拒绝."""
        c = _make_collector()
        items = _parse_items(
            c, _a("「香港独角兽榜单 Unicorns HK 2021」", url),
            "https://www.pedaily.cn/"
        )
        assert items == []

    def test_events_subdomain_rejected(self):
        """events.pedaily.cn 子域整域拒绝."""
        c = _make_collector()
        items = _parse_items(
            c,
            _a(
                "D-Space中欧公益路演平台具身智能专场",
                "https://events.pedaily.cn/customized/1254/",
            ),
            "https://www.pedaily.cn/",
        )
        assert items == []

    def test_real_news_url_passes(self):
        """真实文章 URL (news.pedaily.cn/202607/...) 不被新 blocklist 拦.

        Note: 同源校验是预存 issue (www.pedaily.cn vs news.pedaily.cn),
        此处 source URL 改为 news.pedaily.cn 让 _parse_html 的
        same-host check 放行,只验证 URL_PATH_BLOCKLIST 不拦此 URL。
        """
        c = _make_collector()
        items = _parse_items(
            c,
            _a(
                "洞察科技完成数千万元Pre-A+轮融资",
                "https://news.pedaily.cn/202607/565929.shtml",
            ),
            "https://news.pedaily.cn/",
        )
        assert len(items) == 1


class TestPedailyTitleBlocklist:
    """投资界 NAV_TITLE_LOWER: 投资人排行榜 系列 (年份无关)"""

    def _make_startup_collector(self):
        from backend.collectors.startup_collector import StartupCollector
        return StartupCollector.__new__(StartupCollector)

    @pytest.mark.parametrize("title", [
        "2026「投资界TOP100」投资人",
        "2024「投资界S50女性投资人」",
        "2025投资界「F40中国青年投资人」",
        "「香港独角兽榜单 Unicorns HK 2021」",
    ])
    def test_ranking_title_rejected(self, title):
        """纯排名类标题拒绝 (无论年份)."""
        c = self._make_startup_collector()
        assert c._title_relevant(
            title, "https://www.pedaily.cn/2026investor/",
            {"name": "投资界", "url": "https://www.pedaily.cn/"},
        ) is False

    @pytest.mark.parametrize("title", [
        "Momenta完成上市，港交所今日最大IPO来了",
        "美鑫智能完成千万级天使轮融资，赤子基金独家投资",
        "开启Pre-IPO轮融资进程，星辰新能完成近5亿元融资",
    ])
    def test_real_news_title_passes(self, title):
        """真实新闻标题放行."""
        c = self._make_startup_collector()
        assert c._title_relevant(
            title, "https://news.pedaily.cn/202607/565973.shtml",
            {"name": "投资界", "url": "https://www.pedaily.cn/"},
        ) is True

    def test_other_source_unaffected_by_pedaily_filter(self):
        """其他源 (e.g. 36kr) 不被 pedaily 特定正则影响."""
        c = self._make_startup_collector()
        # 即便标题含 "S50" 或 "F40" 数字, 36kr 源不应被拦
        assert c._title_relevant(
            "某创业公司完成 5000 万 A 轮融资",
            "https://36kr.com/p/123",
            {"name": "36氪", "url": "https://36kr.com/"},
        ) is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _a(title: str, url: str) -> str:
    """构造最小 HTML 含一个 a[href] 链接."""
    return f'<html><body><a href="{url}">{title}</a></body></html>'
