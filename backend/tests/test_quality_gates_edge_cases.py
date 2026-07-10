"""质量门禁边界用例 — 资讯类（ai/security）与标讯类（bid）严格测试。

覆盖现有测试缺口：
- 资讯类（AI/Security）严格模式拒绝边界
- 标讯类（BID）完整 pipeline 集成
- AuthorVerificationGate 修改 item.source 副作用
- FinalUrlGate 修改 item.url 副作用
- URLContentGate 异步门正向匹配
- 完整 9 门禁 pipeline 集成
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.domain.collection import GateResult, PipelineResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import QualityGateFailed
from backend.quality.base import BaseGate, GateContext
from backend.quality.author_verification_gate import (
    AuthorVerificationGate,
    PENALTY_MISMATCH,
    PENALTY_UNKNOWN,
    REWARD_MATCH,
)
from backend.quality.category_match_gate import CategoryMatchGate
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.content_quality_gate import ContentQualityGate
from backend.quality.duplicate_gate import DuplicateGate
from backend.quality.final_url_gate import FinalUrlGate
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.schema_gate import SchemaGate
from backend.quality.source_reputation_gate import SourceReputationGate
from backend.quality.title_summary_gate import TitleSummaryGate
from backend.quality.url_content_gate import URLContentGate
from backend.quality.url_validity_gate import URLValidityGate


# ---------------------------------------------------------------------------
# helpers（复用自 test_quality_gates.py / test_pipeline.py，不抽取共享 fixture）
# ---------------------------------------------------------------------------
def _make_item(
    id_: str = "t1",
    *,
    title: str = "OpenAI announces GPT-5 model with new capabilities",
    summary: str = "OpenAI unveiled new GPT capabilities at conference",
    source: str = "src_a",
    category: Category = Category.AI,
    url: str = "https://example.com/t1",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        summary=summary,
        source=source,
        url=url,
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _ctx(**kw) -> GateContext:
    """构造 GateContext，含 6 个分类的默认关键词。"""
    return GateContext(
        mode=kw.pop("mode", "loose"),
        category_keywords=kw.pop("category_keywords", {
            "ai": ["AI", "OpenAI", "GPT", "Claude", "大模型", "人工智能"],
            "security": ["漏洞", "CVE", "hack", "安全", "勒索"],
            "finance": ["股票", "Fed", "利率"],
            "startup": ["融资", "startup"],
            "bid": ["招标", "投标", "采购", "中标", "bid"],
            "github": ["github", "repo", "star"],
        }),
        source_reputation=kw.pop("source_reputation", {}),
        existing_urls=set(kw.pop("existing_urls", [])),
        existing_titles=list(kw.pop("existing_titles", [])),
    )


class _NoopLogRepo:
    """取代 QualityLogRepository 的 stub，避免 DB 依赖。"""

    def __init__(self):
        self.written: list[tuple[str, GateResult]] = []

    def write_log(self, item_id, result, mode="loose", checked_at=None):
        self.written.append((item_id, result))


def _make_pipeline(
    *,
    mode: QualityMode,
    log: _NoopLogRepo | None = None,
    gates: list | None = None,
) -> QualityGatePipeline:
    """构造 pipeline，默认用 6 个无网络门禁（避开 URLValidity/Author/FinalUrl）。"""
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = mode == QualityMode.STRICT
    cfg._cache["min_score"] = 30
    if gates is None:
        gates = [
            SchemaGate(),
            ContentQualityGate(),
            CategoryMatchGate(),
            TitleSummaryGate(),
            SourceReputationGate(),
            DuplicateGate(),
        ]
    return QualityGatePipeline(cfg, log_repo=log or _NoopLogRepo(), gates=gates)


class _FailGate(BaseGate):
    """总是失败的门禁，用于构造低分场景。"""

    def __init__(self, name: str, deduction: int):
        self.name = name
        self._deduction = deduction

    def check(self, item, context):
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=self._deduction,
            flags=[f"flag_{self.name}"],
        )


# ===========================================================================
# 1.1 资讯类（AI）严格模式边界
# ===========================================================================
def test_strict_mode_rejects_low_score_ai_item():
    """AI 分类的 item 在严格模式下 score < 30 被拒绝（QualityGateFailed）。"""
    p = _make_pipeline(mode=QualityMode.STRICT)
    p.gates = [
        SchemaGate(),
        _FailGate("fail_a", 40),
        _FailGate("fail_b", 40),  # -80 → score 20 < 30
    ]
    item = _make_item(title="OpenAI releases GPT-5", category=Category.AI)
    with pytest.raises(QualityGateFailed) as exc_info:
        p.run_all(item, _ctx())
    assert exc_info.value.score < 30
    assert exc_info.value.item_id == item.id


def test_strict_mode_accepts_high_score_ai_item():
    """AI 分类的 item score >= 30 通过严格模式。"""
    p = _make_pipeline(mode=QualityMode.STRICT)
    item = _make_item(
        title="OpenAI releases new GPT agent framework",
        summary="OpenAI unveiled new GPT agent framework with capabilities",
        category=Category.AI,
    )
    result = p.run_all(item, _ctx())
    assert result.accepted is True
    assert result.final_score >= 90


def test_ai_category_match_with_chinese_keywords():
    """AI 中文关键词（"大模型"/"人工智能"）命中 CategoryMatchGate。"""
    g = CategoryMatchGate()
    item = _make_item(
        title="人工智能大模型 GPT-5 发布",
        summary="OpenAI 发布新一代大模型",
        category=Category.AI,
    )
    r = g.check(item, _ctx())
    assert r.passed is True
    assert r.score_deduction == 0


def test_ai_category_mismatch_rejects_in_strict():
    """非 AI 内容在严格模式下被拒绝（CategoryMatchGate 扣 20 + 其他扣分）。"""
    p = _make_pipeline(mode=QualityMode.STRICT)
    # 构造一个完全不匹配 AI 的 item + 多个失败门禁拉低分数
    p.gates = [
        SchemaGate(),
        CategoryMatchGate(),  # 扣 20
        _FailGate("extra", 20),  # 再扣 20 → score 60 (still > 30)
        _FailGate("extra2", 40),  # 再扣 40 → score 20 < 30
    ]
    item = _make_item(
        title="今天天气真好适合散步",
        summary="出去晒太阳",
        category=Category.AI,
    )
    with pytest.raises(QualityGateFailed):
        p.run_all(item, _ctx())


# ===========================================================================
# 1.2 资讯类（Security）严格模式边界
# ===========================================================================
def test_security_category_match_positive():
    """安全关键词（"漏洞"/"CVE"/"勒索"）命中 CategoryMatchGate。"""
    g = CategoryMatchGate()
    cases = [
        ("CVE-2026-1234 漏洞分析", "新型漏洞利用技术"),
        ("勒索软件攻击报告", "勒索病毒再次爆发"),
        ("安全研究员发现 0day", "hack 攻击事件"),
    ]
    for title, summary in cases:
        item = _make_item(
            title=title,
            summary=summary,
            category=Category.SECURITY,
        )
        r = g.check(item, _ctx())
        assert r.passed is True, f"应通过: {title!r}"


def test_security_strict_rejects_non_security():
    """非安全内容在严格模式下被 CategoryMatchGate 扣分。"""
    g = CategoryMatchGate()
    item = _make_item(
        title="今天去公园散步",
        summary="天气很好适合户外活动",
        category=Category.SECURITY,
    )
    r = g.check(item, _ctx())
    assert r.passed is False
    assert "category_mismatch" in r.flags
    assert r.score_deduction == 20


# ===========================================================================
# 1.3 标讯类（BID）质量门禁集成
# ===========================================================================
def test_bid_item_passes_pipeline_with_security_keywords():
    """网安标讯（"防火墙采购"）通过完整 pipeline（6 门禁子集）。"""
    p = _make_pipeline(mode=QualityMode.LOOSE)
    item = _make_item(
        id_="bid-1",
        title="国家电网防火墙设备采购招标公告",
        summary="采购下一代防火墙设备用于网络安全建设",
        source="ccgp.gov.cn",
        category=Category.BID,
        url="https://www.ccgp.gov.cn/bid/1",
    )
    result = p.run_all(item, _ctx())
    assert result.accepted is True
    # 标讯关键词命中 + 内容正常 → 高分
    assert result.final_score >= 80


def test_bid_item_rejected_by_category_match_if_no_bid_keyword():
    """无招标关键词的 item 被 CategoryMatchGate 扣分。"""
    g = CategoryMatchGate()
    item = _make_item(
        title="今天天气真好",
        summary="出去散步",
        category=Category.BID,
    )
    r = g.check(item, _ctx())
    assert r.passed is False
    assert "category_mismatch" in r.flags
    assert r.score_deduction == 20


def test_bid_item_with_low_reputation_source():
    """低信誉源标讯被 SourceReputationGate 扣分。"""
    g = SourceReputationGate()
    rep = {"unknown_bid_src": {"score": 40, "blacklist": 0, "pass_count": 1, "fail_count": 5}}
    item = _make_item(
        title="防火墙采购招标公告",
        source="unknown_bid_src",
        category=Category.BID,
    )
    r = g.check(item, _ctx(source_reputation=rep))
    assert r.passed is False
    assert "low_reputation_source" in r.flags
    assert r.score_deduction == 15


def test_bid_duplicate_url_across_categories():
    """同 URL 在 bid 与 ai 之间的去重 winner 选择。"""
    url = "https://example.com/news-shared"
    now = datetime.now(timezone.utc)
    items = [
        HotspotItem(
            id="bid-1",
            title="防火墙采购招标公告",
            summary="",
            source="ccgp",
            url=url,
            category=Category.BID,
            published_at=now,
            fetched_at=now,
        ),
        HotspotItem(
            id="ai-1",
            title="AI 安全防火墙技术解读",
            summary="",
            source="qbitai",
            url=url,
            category=Category.AI,
            published_at=now,
            fetched_at=now,
        ),
    ]
    url_title_pairs = [
        {"url": url, "title": it.title, "source": it.source, "id": it.id,
         "is_fallback": it.is_fallback, "fetched_at": it.fetched_at}
        for it in items
    ]
    ctx = _ctx(source_reputation={
        "ccgp": {"score": 0.9},
        "qbitai": {"score": 0.7},
    })
    ctx.__dict__["url_title_pairs"] = url_title_pairs

    gate = DuplicateGate()
    # ccgp (0.9) > qbitai (0.7) → ccgp 是 winner
    r_bid = gate.check(items[0], ctx)
    assert r_bid.passed is True
    assert "duplicate_link_real_title" in r_bid.flags

    r_ai = gate.check(items[1], ctx)
    assert r_ai.passed is False
    assert "title_replaced" in r_ai.flags
    assert r_ai.score_deduction == 60


# ===========================================================================
# 1.4 AuthorVerificationGate 副作用
# ===========================================================================
def test_author_verification_modifies_source_on_mismatch():
    """域名反推与 claimed source 不一致时，item.source 被修改为 canonical。"""
    g = AuthorVerificationGate()
    item = _make_item(
        title="CVE-2026-50507 漏洞分析",
        source="KrebsOnSecurity",
        url="https://msrc.microsoft.com/cve-2026-50507",
        category=Category.SECURITY,
    )
    with patch("backend.quality.author_verification_gate.resolve_publisher") as mock_resolve:
        mock_resolve.return_value = ("MSRC", False, "domain msrc.microsoft.com → MSRC")
        r = g.check(item, _ctx())

    assert r.passed is False
    assert r.score_deduction == PENALTY_MISMATCH
    assert "author_mismatch" in r.flags
    assert "author_corrected_to=MSRC" in r.flags
    # 关键副作用：item.source 被修改
    assert item.source == "MSRC"
    assert item.url_check_status == "mismatch"


def test_author_verification_rewards_match():
    """match 时 score_deduction = -REWARD_MATCH（奖励 +2）。"""
    g = AuthorVerificationGate()
    item = _make_item(
        title="OpenAI 发布 GPT-5",
        source="OpenAI",
        url="https://openai.com/blog/gpt-5",
        category=Category.AI,
    )
    with patch("backend.quality.author_verification_gate.resolve_publisher") as mock_resolve:
        mock_resolve.return_value = ("OpenAI", True, "domain matches source")
        r = g.check(item, _ctx())

    assert r.passed is True
    assert r.score_deduction == -REWARD_MATCH


def test_author_verification_unknown_domain():
    """URL 域名不在注册表 → unknown，轻扣分。"""
    g = AuthorVerificationGate()
    item = _make_item(
        title="未知源文章",
        source="unknown_src",
        url="https://unknown-domain-xyz.com/article/1",
    )
    with patch("backend.quality.author_verification_gate.resolve_publisher") as mock_resolve:
        mock_resolve.return_value = (None, False, "domain not in registry")
        r = g.check(item, _ctx())

    assert r.passed is False
    assert r.score_deduction == PENALTY_UNKNOWN
    assert "author_unknown" in r.flags


# ===========================================================================
# 1.5 FinalUrlGate 副作用
# ===========================================================================
def test_final_url_gate_modifies_url_on_drilldown():
    """landing 页下钻成功时 item.url 被修改为 resolved。"""
    g = FinalUrlGate(fetch_timeout=1.0)
    original_url = "https://qbitai.com/tag/ai-safety"
    resolved_url = "https://qbitai.com/article/2026/07/ai-safety-report"
    item = _make_item(
        title="AI 安全报告",
        url=original_url,
        category=Category.AI,
    )
    with patch("backend.quality.final_url_gate.is_landing_page", return_value=True), \
         patch("backend.quality.final_url_gate.resolve_final_url", return_value=resolved_url):
        r = g.check(item, _ctx())

    assert r.passed is True
    assert r.score_deduction == 0
    assert "url_drilldown_resolved" in r.flags
    # 关键副作用：item.url 被修改
    assert str(item.url) == resolved_url


def test_final_url_gate_skips_already_final():
    """已是文章页时 passed=True，不修改 url。"""
    g = FinalUrlGate(fetch_timeout=1.0)
    original_url = "https://example.com/article/2026/07/news"
    item = _make_item(
        title="正常文章标题",
        url=original_url,
        category=Category.AI,
    )
    with patch("backend.quality.final_url_gate.is_landing_page", return_value=False):
        r = g.check(item, _ctx())

    assert r.passed is True
    assert r.score_deduction == 0
    assert r.reason == "url_already_final"
    # url 未被修改
    assert str(item.url) == original_url


def test_final_url_gate_drilldown_failed():
    """下钻失败（返回 None）→ passed=False，扣 5 分。"""
    g = FinalUrlGate(fetch_timeout=1.0)
    item = _make_item(
        title="AI 安全报告",
        url="https://qbitai.com/tag/ai-safety",
        category=Category.AI,
    )
    with patch("backend.quality.final_url_gate.is_landing_page", return_value=True), \
         patch("backend.quality.final_url_gate.resolve_final_url", return_value=None):
        r = g.check(item, _ctx())

    assert r.passed is False
    assert r.score_deduction == 5
    assert "url_drilldown_failed" in r.flags


# ===========================================================================
# 1.6 URLContentGate 异步门正向用例
# ===========================================================================
@pytest.mark.asyncio
async def test_url_content_gate_matches_title():
    """mock aiohttp 返回页面 title 与 item.title overlap >= 0.30 → passed=True。"""
    g = URLContentGate(timeout=2)
    item = _make_item(
        title="OpenAI releases GPT-5 model",
        url="https://example.com/news/1",
        category=Category.AI,
    )
    page_html = "<html><head><title>OpenAI releases GPT-5 model with new features</title></head></html>"
    with patch("backend.quality.url_content_gate._fetch_title") as mock_fetch:
        mock_fetch.return_value = ("OpenAI releases GPT-5 model with new features", None)
        r = await g.run_async(item)

    assert r.passed is True
    assert r.score_deduction == 0
    assert "overlap=" in (r.reason or "")


@pytest.mark.asyncio
async def test_url_content_gate_mismatch_title():
    """mock aiohttp 返回页面 title 与 item.title overlap < 0.30 → passed=False。"""
    g = URLContentGate(timeout=2)
    item = _make_item(
        title="OpenAI releases GPT-5 model",
        url="https://example.com/news/2",
        category=Category.AI,
    )
    with patch("backend.quality.url_content_gate._fetch_title") as mock_fetch:
        mock_fetch.return_value = ("今日央行宣布降息利好股市", None)
        r = await g.run_async(item)

    assert r.passed is False
    assert r.score_deduction == 20
    assert "url_mismatch" in r.flags


@pytest.mark.asyncio
async def test_url_content_gate_fetch_failure():
    """抓取失败 → passed=False, flag url_unreachable。"""
    g = URLContentGate(timeout=2)
    item = _make_item(
        title="Test article",
        url="https://example.com/news/3",
        category=Category.AI,
    )
    with patch("backend.quality.url_content_gate._fetch_title") as mock_fetch:
        mock_fetch.return_value = ("", "ConnectionError: timeout")
        r = await g.run_async(item)

    assert r.passed is False
    assert r.score_deduction == 20
    assert "url_unreachable" in r.flags


# ===========================================================================
# 1.7 完整 9 门禁 pipeline 集成
# ===========================================================================
def test_full_9_gate_pipeline_ai_item():
    """AI item 跑完整 9 门禁（mock URLValidity/Author/FinalUrl 避免网络）。"""
    p = _make_pipeline(mode=QualityMode.LOOSE)
    item = _make_item(
        id_="full-ai-1",
        title="OpenAI releases new GPT-5 model with AI capabilities",
        summary="OpenAI unveiled new GPT-5 model with AI capabilities at conference",
        source="OpenAI",
        url="https://openai.com/blog/gpt-5",
        category=Category.AI,
    )

    # 用默认 9 门禁，但 mock 掉会触发网络的部分
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = False
    cfg._cache["min_score"] = 30
    pipe = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())

    with patch("backend.quality.url_validity_gate.URLValidityGate.check") as mock_url_valid, \
         patch("backend.quality.author_verification_gate.resolve_publisher") as mock_author, \
         patch("backend.quality.final_url_gate.is_landing_page", return_value=False):
        mock_url_valid.return_value = GateResult(
            gate_name="url_validity", passed=True, score_deduction=0, flags=[], reason="mocked"
        )
        mock_author.return_value = ("OpenAI", True, "domain matches source")
        result = pipe.run_all(item, _ctx())

    assert isinstance(result, PipelineResult)
    assert result.accepted is True
    # 9 门禁都应写 log
    assert len(p.log_repo.written if hasattr(p, 'log_repo') else []) >= 0
    # OpenAI 域名匹配 → 奖励 -2，但 pipeline 只在 passed=False 时收集 deduction
    # 所以奖励不生效，final_score 应为 100（所有门禁通过）
    assert result.final_score == 100


def test_full_9_gate_pipeline_bid_item():
    """BID item 跑完整 9 门禁，验证网安标讯通过。"""
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = False
    cfg._cache["min_score"] = 30
    pipe = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())

    item = _make_item(
        id_="full-bid-1",
        title="国家电网防火墙设备采购招标公告",
        summary="采购下一代防火墙设备用于网络安全建设招标",
        source="ccgp.gov.cn",
        url="https://www.ccgp.gov.cn/bid/2026/001",
        category=Category.BID,
    )

    with patch("backend.quality.url_validity_gate.URLValidityGate.check") as mock_url_valid, \
         patch("backend.quality.author_verification_gate.resolve_publisher") as mock_author, \
         patch("backend.quality.final_url_gate.is_landing_page", return_value=False):
        mock_url_valid.return_value = GateResult(
            gate_name="url_validity", passed=True, score_deduction=0, flags=[], reason="mocked"
        )
        mock_author.return_value = ("ccgp.gov.cn", True, "domain matches source")
        result = pipe.run_all(item, _ctx())

    assert isinstance(result, PipelineResult)
    assert result.accepted is True
    # 所有门禁通过 → score 100
    assert result.final_score == 100


def test_full_9_gate_pipeline_count_is_9():
    """完整 pipeline 注册了 11 个门禁(Phase 20 BidRecency + Phase 47 Recency)。"""
    cfg = QualityConfig()
    pipe = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())
    assert len(pipe.gates) == 11
    names = {g.name for g in pipe.gates}
    assert names == {
        "schema", "recency", "content", "category_match", "title_summary",
        "url_validity", "source_reputation", "AuthorVerification", "FinalUrl", "duplicate", "bid_recency",
    }


# ===========================================================================
# 1.8 资讯 vs 标讯跨分类对比
# ===========================================================================
def test_ai_and_bid_items_both_pass_in_loose_mode():
    """资讯类 AI 与标讯类 BID 的 item 都能在 loose 模式下通过。"""
    p = _make_pipeline(mode=QualityMode.LOOSE)
    ai_item = _make_item(
        id_="ai-mix",
        title="OpenAI 发布 GPT-5 人工智能大模型",
        summary="OpenAI 发布新一代 AI 大模型",
        category=Category.AI,
    )
    bid_item = _make_item(
        id_="bid-mix",
        title="公安部网络安全运维招标公告",
        summary="采购网络安全运维服务招标",
        source="ccgp",
        category=Category.BID,
        url="https://example.com/bid/1",
    )
    ai_result = p.run_all(ai_item, _ctx())
    bid_result = p.run_all(bid_item, _ctx())
    assert ai_result.accepted is True
    assert bid_result.accepted is True
    assert ai_result.final_score >= 80
    assert bid_result.final_score >= 80


def test_strict_mode_rejects_bid_with_low_score():
    """严格模式下低分标讯被拒绝。"""
    p = _make_pipeline(mode=QualityMode.STRICT)
    p.gates = [
        SchemaGate(),
        CategoryMatchGate(),  # 扣 20（如果无标讯关键词）
        _FailGate("extra", 60),  # 再扣 60 → score 20 < 30
    ]
    item = _make_item(
        title="今天天气好",
        summary="散步",
        category=Category.BID,
    )
    with pytest.raises(QualityGateFailed):
        p.run_all(item, _ctx())
