"""news_alert_service — 资讯告警判定 (spec 2026-09-27 four-modes §2)。

契约:
- match_rules 纯函数: (title, summary, quality_score) → 命中规则 dict 列表
- R3 AI 语境限定: 安全词命中但无 AI 语境词 → 不进 major_ai_security_event
- R2 双信号门槛: 单信号 + quality_score < 75 → 不命中
- config 从 alert_rule_definitions.config JSON 读, 词表可调
"""

from backend.services.news_alert_service import match_rules


CFG = {
    "critical_vuln": {"max_per_run": 5, "keywords": ["在野利用", "0day", "PoC", "紧急补丁"]},
    "major_security_event": {
        "max_per_run": 5,
        "keywords": ["数据泄露", "勒索攻击", "供应链攻击", "APT"],
        "min_signals_alone": 2,
        "quality_score_gate": 75,
    },
    "major_ai_security_event": {
        "max_per_run": 5,
        "keywords": ["提示注入", "模型投毒", "MCP 漏洞"],
        "ai_context_words": ["AI", "LLM", "大模型"],
    },
    "must_know_regulatory": {"max_per_run": 5, "keywords": ["紧急通报", "等保", "报送"]},
}


def _hit(rule):
    return rule["rule"]


class TestMatchRules:
    def test_critical_vuln_single_signal_hits(self):
        hits = match_rules("Chrome 0day 在野利用公开", "详情见原文", 80, CFG)
        assert _hit(hits[0]) == "critical_vuln"

    def test_major_event_two_signals_hits(self):
        hits = match_rules("某厂商遭 APT 数据泄露", "大规模供应链攻击背景", 60, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_low_score_misses(self):
        """R2 门槛: 单信号 + score<75 → 不命中 (降噪声)。"""
        hits = match_rules("某小站数据泄露", "无更多背景", 60, CFG)
        assert not any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_high_score_hits(self):
        hits = match_rules("某厂商数据泄露", "背景", 80, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_ai_event_requires_ai_context(self):
        """R3 限定: 安全词命中但无 AI 语境词 → 不命中。"""
        hits = match_rules("新型提示注入攻击手法", "针对传统 Web 框架", 80, CFG)
        assert not any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_ai_event_with_context_hits(self):
        hits = match_rules("针对 LLM 的新型提示注入攻击", "大模型应用受影响", 80, CFG)
        assert any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_regulatory_hits(self):
        hits = match_rules("网信办发布紧急通报", "等保报送时限调整", 70, CFG)
        assert any(_hit(h) == "must_know_regulatory" for h in hits)

    def test_no_match_returns_empty(self):
        assert match_rules("普通 AI 新闻: 新模型发布", "性能提升", 80, CFG) == []

    def test_hit_carries_matched_signals(self):
        hits = match_rules("Chrome 0day 在野利用公开", "", 80, CFG)
        assert set(hits[0]["signals"]) == {"0day", "在野利用"}
