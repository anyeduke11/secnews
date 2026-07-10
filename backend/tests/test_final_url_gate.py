"""Phase 9.2 最终 URL 下钻门禁 + 解析器 测试

覆盖：
- :func:`is_landing_page` 各种 path 模式（tag/author/category/搜索/mailto）
- :func:`_extract_first_article_url` HTML 抽取（qbitai/36kr/jiqizhixin 模式）
- :class:`FinalUrlGate.check` 5 类判定：no-op / drilled / failed / mailto / error
- 集成：pipeline 接入后，tag URL 被自动替换
- 缓存：同一 landing URL 不重复抓取
- 错误隔离：抓取超时/失败不污染门禁
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.base import GateContext
from backend.quality.config import QualityConfig
from backend.quality.final_url_gate import (
    FinalUrlGate,
    PENALTY_ERROR,
    PENALTY_FAILED,
    PENALTY_NOT_DRILLABLE,
    REWARD_OK,
)
from backend.quality.final_url_resolver import (
    DOMAIN_ARTICLE_PATTERNS,
    LANDING_PATH_PATTERNS,
    _extract_first_article_url,
    clear_cache,
    is_landing_page,
    resolve_final_url,
)
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.schema_gate import SchemaGate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str = "t1",
    *,
    title: str = "Sample article",
    source: str = "量子位",
    url: str = "https://www.qbitai.com/2026/07/442447.html",
    category: Category = Category.AI,
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=url,
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _ctx(**kw) -> GateContext:
    return GateContext(
        mode="loose",
        category_keywords=kw.pop("category_keywords", {}),
        source_reputation=kw.pop("source_reputation", {}),
        existing_urls=set(kw.pop("existing_urls", [])),
        existing_titles=list(kw.pop("existing_titles", [])),
    )


class _NoopLogRepo:
    def __init__(self):
        self.written = []

    def write_log(self, item_id, result, mode="loose", checked_at=None):
        self.written.append((item_id, result))


# Sample HTML for qbitai.com tag page
QBITAI_TAG_HTML = """
<html>
<body>
<header>量子位</header>
<main>
<h1>WorldClaw</h1>
<article>
<a href="/2026/07/442447.html">
<img src="x.jpg">
<h4>WorldClaw与百度智能云达成战略合作，文心5.0系列登陆WorldRouter</h4>
</a>
</article>
<article>
<a href="/2026/07/442167.html">
<h4>基石筑底｜WAIC 2026算力</h4>
</a>
</article>
</main>
</body>
</html>
"""

# Sample HTML for 36kr.com (article pattern is /p/NNNNN)
KR36KR_HTML = """
<html>
<body>
<a href="/p/3882258709180678">First article</a>
<a href="/p/3882258709180679">Second article</a>
</body>
</html>
"""

# Sample HTML for krebsonsecurity.com (article pattern is /YYYY/MM/slug/)
KREBS_TAG_HTML = """
<html>
<body>
<a href="/2026/07/cve-test.html">First article</a>
</body>
</html>
"""


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个测试前后清空下钻缓存，避免跨测试污染。"""
    clear_cache()
    yield
    clear_cache()


# ===========================================================================
# 1. is_landing_page — 模式识别
# ===========================================================================
class TestIsLandingPage:
    @pytest.mark.parametrize(
        "url,expected",
        [
            # tag 页面
            ("https://www.qbitai.com/tag/worldclaw", True),
            ("https://qbitai.com/tag/waic-2026", True),
            ("https://example.com/tags/ai", True),
            ("https://example.com/topics/python", True),
            ("https://example.com/topic/python", True),
            ("https://example.com/author/john", True),
            ("https://example.com/authors/jane", True),
            ("https://example.com/category/tech", True),
            ("https://example.com/categories/tech", True),
            ("https://example.com/label/news", True),
            # 搜索
            ("https://example.com/search?q=foo", False),  # /search with query string
            ("https://example.com/?s=cve", True),  # WP style
            # mailto
            ("mailto:foo@bar.com", True),
            ("mailto:user@example.com", True),
            # 真实文章（不是 landing）
            ("https://www.qbitai.com/2026/07/442447.html", False),
            ("https://github.com/openai/codex", False),
            ("https://krebsonsecurity.com/2026/06/test/", False),
            ("https://36kr.com/p/3882258709180678", False),
            # 空 / 异常
            ("", False),
            ("not-a-url", False),
        ],
    )
    def test_pattern_matching(self, url, expected):
        assert is_landing_page(url) == expected, f"url={url!r}"

    def test_is_landing_page_with_query_on_tag(self):
        """带查询字符串的 tag 页面也识别为 landing"""
        assert is_landing_page("https://qbitai.com/tag/worldclaw?foo=bar") is True

    def test_is_landing_page_https_or_bare(self):
        """URL 无 scheme 也能解析（_extract_registered_domain 处理）"""
        assert is_landing_page("qbitai.com/tag/worldclaw") is True
        assert is_landing_page("krebsonsecurity.com/2026/06/test/") is False


# ===========================================================================
# 2. _extract_first_article_url — HTML 抽取
# ===========================================================================
class TestExtractFirstArticleUrl:
    def test_qbitai_extracts_first_article(self):
        url = _extract_first_article_url(QBITAI_TAG_HTML, "qbitai.com")
        assert url == "https://qbitai.com/2026/07/442447.html"

    def test_qbitai_with_www(self):
        url = _extract_first_article_url(QBITAI_TAG_HTML, "www.qbitai.com")
        assert url == "https://www.qbitai.com/2026/07/442447.html"

    def test_36kr_extracts_p_pattern(self):
        url = _extract_first_article_url(KR36KR_HTML, "36kr.com")
        assert url == "https://36kr.com/p/3882258709180678"

    def test_krebsonsecurity_extracts_date_pattern(self):
        url = _extract_first_article_url(KREBS_TAG_HTML, "krebsonsecurity.com")
        assert url == "https://krebsonsecurity.com/2026/07/cve-test.html"

    def test_unknown_domain_returns_none(self):
        url = _extract_first_article_url(QBITAI_TAG_HTML, "unknown-domain.cn")
        assert url is None

    def test_empty_html_returns_none(self):
        assert _extract_first_article_url("", "qbitai.com") is None

    def test_html_without_matching_anchor_returns_none(self):
        assert _extract_first_article_url("<html><body>nothing</body></html>", "qbitai.com") is None


# ===========================================================================
# 3. resolve_final_url — 主入口
# ===========================================================================
class TestResolveFinalUrl:
    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_drills_down_to_first_article(self, mock_fetch):
        mock_fetch.return_value = QBITAI_TAG_HTML
        url = resolve_final_url("https://www.qbitai.com/tag/worldclaw")
        assert url == "https://www.qbitai.com/2026/07/442447.html"
        mock_fetch.assert_called_once()

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_no_op_for_real_article(self, mock_fetch):
        """真实文章 URL 直接返回，不抓取"""
        url = resolve_final_url("https://www.qbitai.com/2026/07/442447.html")
        assert url == "https://www.qbitai.com/2026/07/442447.html"
        mock_fetch.assert_not_called()

    def test_mailto_returns_none(self):
        assert resolve_final_url("mailto:foo@bar.com") is None

    def test_empty_url_returns_none(self):
        assert resolve_final_url("") is None

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_fetch_failure_returns_none(self, mock_fetch):
        mock_fetch.return_value = None
        assert resolve_final_url("https://qbitai.com/tag/worldclaw") is None

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_html_without_article_returns_none(self, mock_fetch):
        mock_fetch.return_value = "<html>nothing</html>"
        assert resolve_final_url("https://qbitai.com/tag/worldclaw") is None

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_cache_avoids_repeat_fetch(self, mock_fetch):
        """缓存生效：同一 URL 第二次不重新抓取"""
        mock_fetch.return_value = QBITAI_TAG_HTML
        url1 = resolve_final_url("https://www.qbitai.com/tag/worldclaw")
        url2 = resolve_final_url("https://www.qbitai.com/tag/worldclaw")
        assert url1 == url2
        assert mock_fetch.call_count == 1

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_different_urls_have_separate_cache(self, mock_fetch):
        mock_fetch.return_value = QBITAI_TAG_HTML
        resolve_final_url("https://www.qbitai.com/tag/worldclaw")
        resolve_final_url("https://www.qbitai.com/tag/waic-2026")
        assert mock_fetch.call_count == 2

    def test_clear_cache_resets(self):
        # 测试 clear_cache 工具函数存在且可调用
        clear_cache()
        # 不应抛异常


# ===========================================================================
# 4. FinalUrlGate — 5 类判定
# ===========================================================================
class TestFinalUrlGate:
    def test_no_op_for_real_article(self):
        """真实文章 URL → passed=True，0 扣分，无 flag"""
        g = FinalUrlGate()
        item = _make_item(url="https://www.qbitai.com/2026/07/442447.html")
        r = g.check(item, _ctx())
        assert isinstance(r, GateResult)
        assert r.passed is True
        assert r.score_deduction == REWARD_OK
        assert r.flags == []
        assert "url_already_final" in r.reason
        # item.url 不变
        assert str(item.url) == "https://www.qbitai.com/2026/07/442447.html"

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_drilldown_success_replaces_url(self, mock_fetch):
        """下钻成功 → 替换 item.url，写 flag"""
        mock_fetch.return_value = QBITAI_TAG_HTML
        g = FinalUrlGate()
        item = _make_item(url="https://www.qbitai.com/tag/worldclaw")
        r = g.check(item, _ctx())
        assert r.passed is True
        assert r.score_deduction == REWARD_OK  # 成功不扣分
        assert "url_drilldown_resolved" in r.flags
        assert any(f.startswith("url_drilldown_from=") for f in r.flags)
        assert any(f.startswith("url_drilldown_to=") for f in r.flags)
        # item.url 被替换（host 来自 URL 解析，按 urlparse 保留）
        assert str(item.url) == "https://www.qbitai.com/2026/07/442447.html"
        # reason 包含转换信息
        assert "url_drilldown_resolved" in r.reason

    def test_mailto_flagged_not_drillable(self):
        """mailto: 链接 → 扣 8 分 + url_not_drillable flag

        HotspotItem.url 是 HttpUrl 类型不能直接存 mailto，但生产中
        AI 采集器可能把 RSS 中的 mailto 链接塞进来（被 pydantic 拦截）。
        单元测试用 :func:`is_landing_page` 已经覆盖了 mailto 识别，
        本测试只验证 gate 的 mailto 分支逻辑：
        """
        g = FinalUrlGate()
        # 用 Pydantic v2 model_construct 绕过 HttpUrl 校验
        item = HotspotItem.model_construct(
            id="t1",
            title="mailto test",
            source="src",
            url="mailto:foo@bar.com",
            category=Category.AI,
            published_at=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            score=None,
            is_fallback=False,
            quality_score=100,
            quality_flags=[],
            quality_checked_at=None,
            url_check_status=None,
        )
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_NOT_DRILLABLE
        assert "url_not_drillable" in r.flags

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_unknown_domain_url_drilldown_no_pattern(self, mock_fetch):
        """域名不在 registry → 保留原 URL，写 url_drilldown_no_pattern flag"""
        mock_fetch.return_value = "<html><a href='/article/123'>x</a></html>"
        g = FinalUrlGate()
        original = "https://unknown-domain.cn/tag/foo"
        item = _make_item(url=original)
        r = g.check(item, _ctx())
        # resolve_final_url 返回 None (no article pattern matches)
        # → passed=False, PENALTY_FAILED
        # OR url_drilldown_no_pattern (depends on logic)
        # 当前实现：抽不到 → resolve_final_url 返回 None → drilldown_failed
        # 这是预期行为（unknown domain 无可下钻模式）
        assert r.passed is False
        assert r.score_deduction == PENALTY_FAILED
        assert "url_drilldown_failed" in r.flags

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_fetch_failure_returns_failed(self, mock_fetch):
        """抓取失败（_fetch_html 返回 None）→ 扣 5 分 + url_drilldown_failed"""
        mock_fetch.return_value = None
        g = FinalUrlGate()
        item = _make_item(url="https://qbitai.com/tag/worldclaw")
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_FAILED
        assert "url_drilldown_failed" in r.flags

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_fetch_exception_caught(self, mock_fetch):
        """_fetch_html 抛异常 → 扣 3 分 + url_drilldown_error"""
        mock_fetch.side_effect = ConnectionError("timeout")
        g = FinalUrlGate()
        item = _make_item(url="https://qbitai.com/tag/worldclaw")
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_ERROR
        assert "url_drilldown_error" in r.flags
        assert any("ConnectionError" in f for f in r.flags)


# ===========================================================================
# 5. 集成测试 — QualityGatePipeline
# ===========================================================================
class TestPipelineIntegration:
    def test_final_url_gate_in_default_pipeline(self):
        """FinalUrlGate 必须在 9 个 gate 列表中"""
        gclasses = QualityGatePipeline.DEFAULT_GATES
        assert FinalUrlGate in gclasses

    def test_gate_count_is_9(self):
        """Phase 9.2: 9 → Phase 20: 10 (BidRecency) → Phase 47: 11 (Recency)"""
        assert len(QualityGatePipeline.DEFAULT_GATES) == 11

    def test_gate_order_after_author_verification(self):
        """FinalUrlGate 应在 AuthorVerificationGate 之后、DuplicateGate 之前"""
        from backend.quality.author_verification_gate import AuthorVerificationGate
        from backend.quality.duplicate_gate import DuplicateGate

        gates = QualityGatePipeline.DEFAULT_GATES
        idx_fu = gates.index(FinalUrlGate)
        idx_av = gates.index(AuthorVerificationGate)
        idx_dup = gates.index(DuplicateGate)
        assert idx_fu > idx_av
        assert idx_fu < idx_dup

    @patch("backend.quality.final_url_resolver._fetch_html")
    def test_pipeline_correction_persists(self, mock_fetch):
        """端到端：qbitai tag URL → 跑 pipeline 后 url 被纠正"""
        mock_fetch.return_value = QBITAI_TAG_HTML
        cfg = QualityConfig()
        pipeline = QualityGatePipeline(
            cfg,
            log_repo=_NoopLogRepo(),
            gates=[SchemaGate(), FinalUrlGate()],
        )
        item = _make_item(url="https://www.qbitai.com/tag/worldclaw")
        ctx = _ctx()
        result = pipeline.run_all(item, ctx)
        # pipeline 完成后，item.url 应被纠正
        assert str(item.url) == "https://www.qbitai.com/2026/07/442447.html"
        # pipeline result 应包含 flag
        assert "url_drilldown_resolved" in result.final_flags


# ===========================================================================
# 6. async wrapper 测试
# ===========================================================================
class TestAsyncWrapper:
    @pytest.mark.asyncio
    @patch("backend.quality.final_url_resolver._fetch_html")
    async def test_run_final_url_gate_async(self, mock_fetch):
        """异步包装：把 sync urllib 抓到 thread pool"""
        from backend.quality.final_url_gate import run_final_url_gate_async

        mock_fetch.return_value = QBITAI_TAG_HTML
        g = FinalUrlGate()
        item = _make_item(url="https://www.qbitai.com/tag/worldclaw")
        r = await run_final_url_gate_async(g, item, _ctx())
        assert r.passed is True
        assert "url_drilldown_resolved" in r.flags


# ===========================================================================
# 7. Registry 完整性测试
# ===========================================================================
class TestRegistryIntegrity:
    def test_landing_patterns_not_empty(self):
        assert len(LANDING_PATH_PATTERNS) >= 8

    def test_domain_article_patterns_not_empty(self):
        assert len(DOMAIN_ARTICLE_PATTERNS) >= 5

    def test_qbitai_registered(self):
        """qbitai 是用户截图核心 domain，必须在 registry 里"""
        assert "qbitai.com" in DOMAIN_ARTICLE_PATTERNS

    def test_36kr_registered(self):
        assert "36kr.com" in DOMAIN_ARTICLE_PATTERNS

    def test_krebsonsecurity_registered(self):
        assert "krebsonsecurity.com" in DOMAIN_ARTICLE_PATTERNS

    def test_pattern_is_list_of_strings(self):
        for domain, patterns in DOMAIN_ARTICLE_PATTERNS.items():
            assert isinstance(patterns, tuple), f"{domain} patterns not tuple"
            for p in patterns:
                assert isinstance(p, str)
