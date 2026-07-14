"""Phase 9 资讯作者核实门禁 测试

覆盖：
- :func:`resolve_publisher` 全场景（match/mismatch/unknown/alias/www./子域/中文）
- :class:`AuthorVerificationGate.check` 3 类判定
- 集成测试：接 pipeline 后 msrc.microsoft.com URL 的 source 被纠正
- edge case：空 URL / 畸形 URL / 长 suffix 优先匹配
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.author_verification_gate import (
    AuthorVerificationGate,
    PENALTY_MISMATCH,
    PENALTY_UNKNOWN,
    REWARD_MATCH,
)
from backend.quality.base import GateContext
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.publisher_registry import (
    ALIASES,
    PUBLISHER_REGISTRY,
    _extract_registered_domain,
    _find_matching_suffix,
    _normalize_name,
    resolve_publisher,
)
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.schema_gate import SchemaGate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str = "t1",
    *,
    title: str = "MSRC announces CVE-2026-50507 patch",
    summary: str = "Microsoft released security updates for critical CVE",
    source: str = "src",
    category: Category = Category.SECURITY,
    url: str = "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
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
    return GateContext(
        mode="loose",
        category_keywords=kw.pop("category_keywords", {}),
        source_reputation=kw.pop("source_reputation", {}),
        existing_urls=set(kw.pop("existing_urls", [])),
        existing_titles=list(kw.pop("existing_titles", [])),
    )


class _NoopLogRepo:
    """取代 QualityLogRepository 的 stub，避免 DB 依赖。"""

    def __init__(self):
        self.written: list[tuple[str, object]] = []

    def write_log(self, item_id, result, mode="loose", checked_at=None):
        self.written.append((item_id, result))


# ===========================================================================
# 1. resolve_publisher — match 场景
# ===========================================================================
class TestResolvePublisherMatch:
    def test_msrc_exact_match(self):
        canonical, is_match, reason = resolve_publisher(
            "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            "MSRC (Microsoft Security Response Center)",
        )
        assert canonical == "MSRC (Microsoft Security Response Center)"
        assert is_match is True
        assert "url_match" in reason

    def test_krebsonsecurity_match(self):
        canonical, is_match, reason = resolve_publisher(
            "https://krebsonsecurity.com/2026/06/foo/",
            "KrebsOnSecurity",
        )
        assert canonical == "KrebsOnSecurity"
        assert is_match is True

    def test_alias_match_msrc_abbrev(self):
        """claimed='msrc' 经 alias 解析后等于 canonical 'msrc'（去括号归一）"""
        canonical, is_match, reason = resolve_publisher(
            "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            "msrc",
        )
        assert canonical == "MSRC (Microsoft Security Response Center)"
        assert is_match is True
        # 'msrc' 归一后等于 'msrc'，与 canonical 归一值相同 → 走 url_match
        assert "url_match" in reason

    def test_alias_match_cisa(self):
        canonical, is_match, _ = resolve_publisher(
            "https://cisa.gov/news-events/cybersecurity-advisories/.../aa26-127a",
            "cisa",
        )
        assert canonical == "CISA"
        assert is_match is True

    def test_www_prefix_stripped(self):
        """URL 含 www. 前缀也应命中同 suffix"""
        canonical, is_match, _ = resolve_publisher(
            "https://www.krebsonsecurity.com/2026/06/foo/",
            "KrebsOnSecurity",
        )
        assert canonical == "KrebsOnSecurity"
        assert is_match is True

    def test_chinese_alias_match(self):
        """中文 alias 也应匹配"""
        canonical, is_match, reason = resolve_publisher(
            "https://www.anquanke.com/post/.../123",
            "安全客",
        )
        assert canonical == "安全客"
        assert is_match is True

    def test_alias_match_knownsec_to_knownsec(self):
        """knownsec.com 应匹配 '知道创宇'（通过 alias 解析）"""
        canonical, is_match, reason = resolve_publisher(
            "https://www.knownsec.com/posts/.../123",
            "知道创宇",
        )
        assert canonical == "知道创宇"
        assert is_match is True
        # '知道创宇' 归一后 = canonical 归一值 '知道创宇'，走 url_match
        assert "url_match" in reason

    def test_alias_match_path_apple_shortname(self):
        """真正走 alias_match 路径：claimed='apple'（归一 'apple'）≠
        canonical='Apple Security'（归一 'applesecurity'），但 ALIASES['apple']
        = canonical → 走 alias_match。"""
        canonical, is_match, reason = resolve_publisher(
            "https://support.apple.com/en-us/HT121234",
            "apple",
        )
        assert canonical == "Apple Security"
        assert is_match is True
        assert "alias_match" in reason

    def test_github_url_match(self):
        canonical, is_match, _ = resolve_publisher(
            "https://github.com/openai/codex-plugin-cc",
            "GitHub",
        )
        assert canonical == "GitHub"
        assert is_match is True


# ===========================================================================
# 2. resolve_publisher — mismatch 场景（用户截图核心问题）
# ===========================================================================
class TestResolvePublisherMismatch:
    def test_krebsonsecurity_claimed_for_msrc_url(self):
        """核心 bug 场景：URL 是 msrc.microsoft.com 但 claimed=KrebsOnSecurity"""
        canonical, is_match, reason = resolve_publisher(
            "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            "KrebsOnSecurity",
        )
        assert canonical == "MSRC (Microsoft Security Response Center)"
        assert is_match is False
        assert "url_mismatch" in reason
        assert "KrebsOnSecurity" in reason  # reason 应记录 claimed

    def test_freebuf_claimed_for_msrc_url(self):
        canonical, is_match, _ = resolve_publisher(
            "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            "FreeBuf",
        )
        assert is_match is False
        assert canonical == "MSRC (Microsoft Security Response Center)"

    def test_no_claimed_with_known_domain(self):
        """无 claimed 但域名已知 → 返回 canonical，is_match=False"""
        canonical, is_match, reason = resolve_publisher(
            "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            None,
        )
        assert canonical == "MSRC (Microsoft Security Response Center)"
        assert is_match is False
        assert "url_known" in reason

    def test_apple_support_mismatch_claimed(self):
        """URL 是 support.apple.com 但 claimed=Google → mismatch"""
        canonical, is_match, _ = resolve_publisher(
            "https://support.apple.com/en-us/HT121234",
            "Google",
        )
        assert canonical == "Apple Security"
        assert is_match is False


# ===========================================================================
# 3. resolve_publisher — unknown 场景
# ===========================================================================
class TestResolvePublisherUnknown:
    def test_unknown_domain_with_claim(self):
        """URL 域名不在注册表但有 claimed → 仍 unknown"""
        canonical, is_match, reason = resolve_publisher(
            "https://www.some-random-blog.cn/article/123",
            "SomeBlog",
        )
        assert canonical is None
        assert is_match is False
        assert "url_unknown" in reason

    def test_unknown_domain_no_claim(self):
        canonical, is_match, reason = resolve_publisher(
            "https://www.some-random-blog.cn/article/123",
            None,
        )
        assert canonical is None
        assert is_match is False
        assert "url_unknown" in reason

    def test_invalid_url(self):
        """完全无效的 URL → url_invalid"""
        canonical, is_match, reason = resolve_publisher(
            "",
            "Some",
        )
        assert canonical is None
        assert is_match is False
        assert reason == "url_invalid"

    def test_bare_domain_no_scheme(self):
        """无 scheme 的裸域名也能解析"""
        canonical, is_match, _ = resolve_publisher(
            "krebsonsecurity.com/2026/06/foo/",
            "KrebsOnSecurity",
        )
        assert canonical == "KrebsOnSecurity"


# ===========================================================================
# 4. resolve_publisher — suffix 优先级
# ===========================================================================
class TestSuffixPriority:
    def test_longest_suffix_wins(self):
        """chromereleases.googleblog.com 应优先匹配 Chrome Releases，
        而非更短的安全 blog 命中。
        但实际 registry 中两个都是 googleblog 子域，且都不冲突。
        用 msrc-blog.microsoft.com（MSRC Blog 优先于 Microsoft Blog）。"""
        canonical, _, _ = resolve_publisher(
            "https://msrc-blog.microsoft.com/2026/06/post/",
            None,
        )
        assert canonical == "MSRC Blog"

    def test_subdomain_match(self):
        """子域（如 blog.krebsonsecurity.com）应匹配 krebsonsecurity.com"""
        canonical, _, _ = resolve_publisher(
            "https://blog.krebsonsecurity.com/2026/06/post/",
            None,
        )
        # blog. 是子域，长 suffix 列表里没有 blog.krebsonsecurity.com
        # 但 krebsonsecurity.com 是 suffix → 匹配 KrebsOnSecurity
        assert canonical == "KrebsOnSecurity"


# ===========================================================================
# 5. helpers 单元测试
# ===========================================================================
class TestHelpers:
    def test_extract_registered_domain_basic(self):
        assert _extract_registered_domain("https://krebsonsecurity.com/x") == "krebsonsecurity.com"

    def test_extract_registered_domain_www_stripped(self):
        assert _extract_registered_domain("https://www.krebsonsecurity.com/x") == "krebsonsecurity.com"

    def test_extract_registered_domain_uppercase_lowered(self):
        assert _extract_registered_domain("https://Krebsonsecurity.com/x") == "krebsonsecurity.com"

    def test_extract_registered_domain_empty(self):
        assert _extract_registered_domain("") is None

    def test_find_matching_suffix_exact(self):
        assert _find_matching_suffix("msrc.microsoft.com") == "MSRC (Microsoft Security Response Center)"

    def test_find_matching_suffix_subdomain(self):
        assert _find_matching_suffix("blog.krebsonsecurity.com") == "KrebsOnSecurity"

    def test_find_matching_suffix_no_match(self):
        assert _find_matching_suffix("unknown-domain.cn") is None

    def test_normalize_name_strip_parens(self):
        assert _normalize_name("MSRC (Microsoft Security Response Center)") == "msrc"

    def test_normalize_name_strip_chinese_parens(self):
        assert _normalize_name("MSRC（测试）") == "msrc"

    def test_normalize_name_preserves_chinese(self):
        assert _normalize_name("安全客") == "安全客"

    def test_normalize_name_lowers_case(self):
        assert _normalize_name("KrebsonSecurity") == "krebsonsecurity"

    def test_normalize_name_empty(self):
        assert _normalize_name("") == ""


# ===========================================================================
# 6. AuthorVerificationGate — 3 类判定
# ===========================================================================
class TestAuthorVerificationGate:
    """3 类判定：match → 奖励, mismatch → 纠正+扣分, unknown → 轻扣分。"""

    def test_match_reward(self):
        """claimed 与 canonical 一致 → 奖励（负 deduction）"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://krebsonsecurity.com/2026/06/foo/",
            source="KrebsOnSecurity",
        )
        r = g.check(item, _ctx())
        assert isinstance(r, GateResult)
        assert r.gate_name == "AuthorVerification"
        assert r.passed is True
        assert r.score_deduction == -REWARD_MATCH  # 奖励
        assert r.flags == []
        assert "author_verified" in r.reason

    def test_match_with_alias(self):
        """claimed='msrc' 是 alias → 仍 match"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            source="msrc",
        )
        r = g.check(item, _ctx())
        assert r.passed is True
        assert r.score_deduction == -REWARD_MATCH

    def test_mismatch_correction(self):
        """核心场景：URL=msrc, claimed=KrebsOnSecurity → 纠正+扣分"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            source="KrebsOnSecurity",
        )
        r = g.check(item, _ctx())
        assert r.gate_name == "AuthorVerification"
        assert r.passed is False
        assert r.score_deduction == PENALTY_MISMATCH
        assert "author_mismatch" in r.flags
        # 检查 corrected flag
        assert any(f.startswith("author_corrected_to=") for f in r.flags)
        # item.source 被直接修改为 canonical
        assert item.source == "MSRC (Microsoft Security Response Center)"
        # url_check_status 也被设置
        assert item.url_check_status == "mismatch"

    def test_mismatch_no_claim_with_known_domain(self):
        """URL 域名已知但 claimed=unknown_source → mismatch → source 被纠正"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            source="unknown_source",
        )
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_MISMATCH
        # source 被纠正
        assert item.source == "MSRC (Microsoft Security Response Center)"
        # url_check_status 也被设置
        assert item.url_check_status == "mismatch"

    def test_unknown_url(self):
        """URL 域名不在注册表 → 轻扣分 + flag，不纠正 source"""
        g = AuthorVerificationGate()
        original_source = "SomeBlog"
        item = _make_item(
            url="https://www.some-random-blog.cn/article/123",
            source=original_source,
        )
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == PENALTY_UNKNOWN
        assert "author_unknown" in r.flags
        # source 不被修改
        assert item.source == original_source
        # url_check_status 也不被设置
        assert item.url_check_status is None

    def test_no_score_change_passed_unknown(self):
        """unknown 场景 passed=False 但 flags 写明 author_unknown"""
        g = AuthorVerificationGate()
        item = _make_item(
            url="https://unknown.cn/1",
            source="SomeSource",
        )
        r = g.check(item, _ctx())
        assert r.passed is False
        assert r.score_deduction == 3  # PENALTY_UNKNOWN
        assert "author_unknown" in r.flags


# ===========================================================================
# 7. 集成测试 — 接入 QualityGatePipeline
# ===========================================================================
class TestPipelineIntegration:
    """验证 AuthorVerificationGate 真的被编入了 DEFAULT_GATES。"""

    def test_gate_in_default_pipeline(self):
        """AuthorVerificationGate 必须在 8 个 gate 列表中"""
        gclasses = QualityGatePipeline.DEFAULT_GATES
        assert AuthorVerificationGate in gclasses

    def test_gate_count_is_9(self):
        """Phase 9.2: 7 → 8 → 9 (FinalUrl) → Phase 20: 10 (BidRecency) → Phase 47: 11 (Recency) → fix-bug-github-category-dedup Task 3: 12 (NoiseContent)"""
        assert len(QualityGatePipeline.DEFAULT_GATES) == 12

    def test_gate_order_after_source_reputation(self):
        """AuthorVerificationGate 应在 SourceReputationGate 之后、DuplicateGate 之前"""
        from backend.quality.duplicate_gate import DuplicateGate
        from backend.quality.source_reputation_gate import SourceReputationGate

        gates = QualityGatePipeline.DEFAULT_GATES
        idx_av = gates.index(AuthorVerificationGate)
        idx_sr = gates.index(SourceReputationGate)
        idx_dup = gates.index(DuplicateGate)
        # AuthorVerification 应在 SourceReputation 之后
        assert idx_av > idx_sr
        # AuthorVerification 应在 Duplicate 之前
        assert idx_av < idx_dup

    def test_pipeline_runs_author_gate_and_corrections_persist(self):
        """端到端：msrc URL + KrebsOnSecurity source → 跑 pipeline 后 source 被纠正

        关键验证：AuthorVerificationGate.check() 直接修改 item.source 后，
        _run_quality_gates 末尾的 model_copy(update=...) 只覆盖 quality 字段，
        **保留** source 修改 → 最终入库的 source 应该是 MSRC。
        """
        # 直接构造 pipeline + item
        cfg = QualityConfig()
        cfg._cache["strict_mode"] = False
        cfg._cache["min_score"] = 0
        pipeline = QualityGatePipeline(
            cfg,
            log_repo=_NoopLogRepo(),
            gates=[
                SchemaGate(),
                AuthorVerificationGate(),
            ],
        )
        item = _make_item(
            url="https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
            source="KrebsOnSecurity",
        )
        ctx = _ctx()
        result = pipeline.run_all(item, ctx)
        # pipeline 完成后，item.source 应被 AuthorVerificationGate 纠正
        assert item.source == "MSRC (Microsoft Security Response Center)"
        # pipeline result 应反映扣分
        assert "author_mismatch" in result.final_flags
        # 扣分后 final_score < 100
        assert result.final_score < 100


# ===========================================================================
# 8. Registry 完整性测试
# ===========================================================================
class TestRegistryIntegrity:
    """验证注册表本身不出低级错。"""

    def test_registry_not_empty(self):
        assert len(PUBLISHER_REGISTRY) >= 30

    def test_aliases_not_empty(self):
        assert len(ALIASES) >= 10

    def test_no_duplicate_suffixes(self):
        suffixes = [s for s, _ in PUBLISHER_REGISTRY]
        assert len(suffixes) == len(set(suffixes))

    def test_canonical_names_unique(self):
        names = [n for _, n in PUBLISHER_REGISTRY]
        # canonical name 允许重复（多个 domain 指向同一发布者）
        # 但至少应有一些覆盖
        assert len(set(names)) >= 5

    def test_msrc_in_registry(self):
        """MSRC 是用户截图核心 domain，必须在注册表里"""
        assert any(s == "msrc.microsoft.com" for s, _ in PUBLISHER_REGISTRY)

    def test_krebsonsecurity_in_registry(self):
        assert any(s == "krebsonsecurity.com" for s, _ in PUBLISHER_REGISTRY)

    def test_phase29_tophub_in_registry(self):
        """Phase 29: tophub.today 聚合站必须在 PUBLISHER_REGISTRY (避免 author_unknown)。"""
        registry_map = {s: n for s, n in PUBLISHER_REGISTRY}
        assert "tophub.today" in registry_map
        assert registry_map["tophub.today"] == "TopHub GitHub 热榜"
        # 别名也要能命中
        canonical, is_match, _ = resolve_publisher(
            "https://tophub.today/n/rYqoXQ8vOD", "TopHub"
        )
        assert canonical == "TopHub GitHub 热榜"
        assert is_match is True

    def test_phase21_security_domains_in_registry(self):
        """Phase 21 扩充: 全 Phase 17 安全源(信源总览 §二 §三 §四 §八)
        必须在注册表,避免 author_unknown。
        """
        expected = {
            # Phase 17 §二 监管
            "nfra.gov.cn": "国家金融监督管理总局",
            "csrc.gov.cn": "中国证监会",
            "pbc.gov.cn": "中国人民银行",
            # Phase 17 §三 §八 安全媒体
            "thehackernews.com": "The Hacker News",
            "secrss.com": "安全内参",
            "easyaq.com": "E安全",
            "hackread.com": "HackRead",
            "schneier.com": "Schneier on Security",
            # Phase 17 §四 标准/漏洞库
            "djbh.net": "等级保护网",
            "tc260.org.cn": "TC260 信安标委",
            "cnnvd.org.cn": "CNNVD 国家漏洞库",
            # Phase 17 §八 厂商
            "ti.qianxin.com": "奇安信威胁情报",
            "sangfor.com.cn": "深信服科技",
            "nsfocus.com": "绿盟科技",
            "venustech.com.cn": "启明星辰",
            "knownsec.com": "知道创宇",
        }
        registry_map = {s: n for s, n in PUBLISHER_REGISTRY}
        for domain, expected_name in expected.items():
            assert domain in registry_map, f"{domain} 不在 PUBLISHER_REGISTRY"
            assert registry_map[domain] == expected_name, (
                f"{domain} -> {registry_map[domain]!r}, expected {expected_name!r}"
            )

    def test_phase21_startup_domains_in_registry(self):
        """Phase 21 扩充: startup collector 的 huxiu/itjuzi 域名必须在注册表。"""
        expected = {
            "huxiu.com": "虎嗅",
            "itjuzi.com": "IT桔子",
        }
        registry_map = {s: n for s, n in PUBLISHER_REGISTRY}
        for domain, expected_name in expected.items():
            assert domain in registry_map
            assert registry_map[domain] == expected_name

    def test_phase21_4hou_canonical_is_sihou(self):
        """Phase 21 回归: 4hou.com 的 canonical 必须是「嘶吼」(修复历史错误别名)。"""
        canonical, is_match, _ = resolve_publisher(
            "https://www.4hou.com/posts/abc", "嘶吼"
        )
        assert canonical == "嘶吼"
        assert is_match is True

    def test_phase21_4hou_alias_sige_to_sihou(self):
        """Phase 21 回归: 历史别名「四哥」必须能 alias 匹配到「嘶吼」。"""
        canonical, is_match, _ = resolve_publisher(
            "https://www.4hou.com/posts/abc", "四哥"
        )
        assert canonical == "嘶吼"
        assert is_match is True, "历史别名「四哥」必须能 alias 匹配到「嘶吼」"

    def test_phase21_bid_domains_in_registry(self):
        """Phase 21 扩充: bid collector 各源域名必须全部在注册表(避免 bid author_unknown)。"""
        expected_domains = {
            "ccgp.gov.cn", "ggzy.gov.cn", "zycg.gov.cn",
            "bidcenter.com.cn", "chengezhao.com", "qianlima.com",
            "zcygov.cn", "plap.cn", "zhaobiao.cn", "zgzbw.com",
            "dlzb.com", "dlnyzb.com", "yifangbao.com",
            "b2b.10086.cn", "caigou.chinatelecom.com.cn", "chinaunicombidding.com",
            "nhc.gov.cn", "moe.gov.cn", "mot.gov.cn", "crgc.cc",
            "ecp.sgcc.com.cn", "bidding.csg.cn", "chnenergybidding.com.cn",
            "sinopec-ec.com", "szexgrp.com",
        }
        registry_set = {s for s, _ in PUBLISHER_REGISTRY}
        for d in expected_domains:
            assert d in registry_set, f"bid 域名 {d} 不在 PUBLISHER_REGISTRY"

    def test_phase22_secwiki_in_registry(self):
        """Phase 22: SecWiki 必须登记(secnews §三 RSS 5 源补齐)。"""
        canonical, is_match, _ = resolve_publisher(
            "http://www.sec-wiki.com/?2026-07-06", "SecWiki"
        )
        assert canonical == "SecWiki"
        assert is_match is True
