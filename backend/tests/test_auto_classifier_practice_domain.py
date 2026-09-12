"""DEV-0176 — 实践域词表 (Workbench Focus PRD P0.1) 测试。

覆盖 (DEV_PLAN T0.1 退出判据: 每域 ≥2 正例 + 1 反例):
- 8 个实践域的 tag 命中 / 标题命中
- 非安全内容 (finance/dev/startup) 返回 None
- classify_item / batch_classify 透传 practice_domain
- 既有 classify_domain 行为不回归
- PRACTICE_DOMAINS 与 LABELS 完整性
"""
from __future__ import annotations

import pytest

from backend.services.auto_classifier import (
    PRACTICE_DOMAIN_LABELS,
    PRACTICE_DOMAINS,
    batch_classify,
    classify_domain,
    classify_item,
    classify_practice_domain,
)


class TestPracticeDomainTagHits:
    """每域 ≥1 个 tag 正例。"""

    @pytest.mark.parametrize(
        "tag, expected",
        [
            ("大模型安全", "ai_security"),
            ("AI安全", "ai_security"),
            ("威胁情报", "threat_hunting"),
            ("应急响应", "incident_response"),
            ("漏洞", "vuln_research"),
            ("CVE", "vuln_research"),
            # DEV-0181: owner 10 域口径
            ("渗透测试", "pentest"),
            ("红队攻防", "pentest"),
            ("护网", "pentest"),
            ("代码审计", "appsec"),
            ("数据安全", "data_security"),
            ("隐私", "data_security"),
            ("国密", "crypto_security"),
            ("密钥管理", "crypto_security"),
            ("密码学", "crypto_security"),
            ("等保", "compliance"),
            ("合规", "compliance"),
            ("零信任", "network_security"),
            ("安全运营", "network_security"),
            ("云安全", "network_security"),
        ],
    )
    def test_tag_hit(self, tag: str, expected: str):
        assert classify_practice_domain([tag], title="") == expected

    def test_specific_tag_beats_order_of_domains(self):
        """AI安全 tag 命中 ai_security 而非泛化 security 系。"""
        assert classify_practice_domain(["大模型安全", "安全运营"], "") == "ai_security"


class TestPracticeDomainTitleHits:
    """每域 ≥1 个标题正例 (不依赖 tag)。"""

    @pytest.mark.parametrize(
        "title, expected",
        [
            ("提示注入攻击大模型的十种姿势", "ai_security"),
            ("ChatGPT 越狱手法汇总", "ai_security"),
            # DEV-0179: 无偏人评发现的攻击动词词系
            ("OpenAI 内部 Agent 再爆新攻击：入侵 rubydoc 窃取 API 密钥", "ai_security"),
            ("调查披露 Hugging Face 遭 1200 个 AI 智能体协作入侵", "ai_security"),
            ("CVE-2026-31337 漏洞分析与复现", "vuln_research"),
            ("某 CMS 0day 在野利用披露", "vuln_research"),
            ("基于 ATT&CK 的威胁狩猎实战", "threat_hunting"),
            ("APT 组织 Lazarus 最新溯源报告", "threat_hunting"),
            ("勒索病毒应急响应全记录", "incident_response"),
            ("一次入侵事件的取证与处置", "incident_response"),
            ("Java 代码审计入门指南", "appsec"),
            ("DevSecOps 流水线落地实践", "appsec"),
            # DEV-0181: 渗透攻防独立
            ("某金融单位红队攻防演练复盘：从外网到域控", "pentest"),
            ("内网渗透实战：横向移动路径与规避", "pentest"),
            ("密码学基础：哈希碰撞与签名方案", "crypto_security"),
            ("国密 SM4 改造中的常见坑", "crypto_security"),
            # DEV-0181: 数据安全独立 / 密钥归密码安全
            ("2026 数据泄露事件年报", "data_security"),
            ("数据分类分级建设指南解读", "data_security"),
            # DEV-0181: 网络安全 (防御运营/建设/云)
            ("Kubernetes 安全加固清单", "network_security"),
            ("企业安全建设的五年规划方法", "network_security"),
            ("SOC 运营中心成熟度评估", "network_security"),
            ("等保 2.0 三级测评要点解读", "compliance"),
            ("网信办就新规公开征求意见", "compliance"),
            ("70余名英国议员联名呼吁立法禁止开发超级智能AI", "compliance"),
        ],
    )
    def test_title_hit(self, title: str, expected: str):
        assert classify_practice_domain([], title=title) == expected


class TestPracticeDomainNegatives:
    """非安全内容返回 None (降权不删契约的前提)。"""

    @pytest.mark.parametrize(
        "tags, title",
        [
            (["金融科技"], "央行数字货币进展"),
            (["效率工具"], "独立开发者的效率工具箱"),
            (["编程", "开源"], "Rust 异步运行时原理"),
            ([], "本周宏观经济观察"),
        ],
    )
    def test_non_security_returns_none(self, tags: list[str], title: str):
        assert classify_practice_domain(tags, title=title) is None

    def test_empty_input_returns_none(self):
        assert classify_practice_domain([], title="") is None


class TestTaxonomyIntegrity:
    def test_all_domains_have_labels(self):
        assert set(PRACTICE_DOMAINS) == set(PRACTICE_DOMAIN_LABELS.keys())
        assert len(PRACTICE_DOMAINS) == 10

    def test_title_rules_only_target_known_domains(self):
        from backend.services.auto_classifier import TITLE_PRACTICE_RULES

        for _, domain in TITLE_PRACTICE_RULES:
            assert domain in PRACTICE_DOMAINS

    def test_tag_map_only_targets_known_domains(self):
        from backend.services.auto_classifier import TAG_PRACTICE_MAP

        for domain in TAG_PRACTICE_MAP.values():
            assert domain in PRACTICE_DOMAINS


class TestIntegration:
    def test_classify_item_includes_practice_domain(self):
        result = classify_item(tags=["漏洞"], title="CVE-2026-1234 分析")
        assert result["practice_domain"] == "vuln_research"
        # 既有字段不回归
        assert set(result.keys()) == {"domain", "type", "difficulty", "practice_domain"}

    def test_batch_classify_propagates_practice_domain(self):
        items = [
            {"id": "k1", "title": "等保测评指南", "tags": [], "source_url": ""},
            {"id": "k2", "title": "某个基金走势", "tags": [], "source_url": ""},
        ]
        out = batch_classify(items)
        assert out[0]["practice_domain"] == "compliance"
        assert out[1]["practice_domain"] is None

    def test_existing_domain_classification_not_regressed(self):
        """既有粗粒度 domain 行为不受新增实践域影响。"""
        assert classify_domain(["威胁情报"], title="") == "security"
        assert classify_domain(["AI"], title="") == "ai"
        assert classify_domain([], title="银行发布年报") == "finance"
