"""skill_registry.abstractor 测试 — 反模式 linter 三条客观信号规则。

验证 docs/V0.8_SKILL_ABSTRACTION.md §5 的 R1/R2/R3 与裁决语义
(findings 非空 → eligible=False; 全部 severity=warning 允许人工复议)。
纯函数无 DB 依赖, 直接构造 SkillCandidate 断言命中/放行。
"""
from __future__ import annotations

from backend.services.skill_registry import (
    AbstractorVerdict,
    SkillCandidate,
    check_candidate,
    find_anti_patterns,
)


class TestR1CrudEndpoint:
    """R1 — CRUD 内部端点 (写方法 + /api/<resource> 路径形态)。"""

    def test_post_knowledge_hits_r1(self):
        """POST /api/knowledge/ 是典型 CRUD 写操作 → R1 命中且不 eligible。"""
        candidate = SkillCandidate(
            kind="endpoint",
            path="/api/knowledge/",
            name="create-knowledge-item",
            http_method="POST",
        )
        verdict = check_candidate(candidate)
        assert isinstance(verdict, AbstractorVerdict)
        assert verdict.eligible is False
        assert [f.rule_id for f in verdict.findings] == ["R1"]
        # severity 契约: 恒为 warning (客观启发式, 允许人工复议)
        assert verdict.findings[0].severity == "warning"
        assert verdict.findings[0].reason  # reason 必须可读, 供人工复议

    def test_get_rotation_status_passes(self):
        """GET /api/secrets/rotation-status 是读操作 → R1 放行 (B 类查询型合法)。"""
        candidate = SkillCandidate(
            kind="endpoint",
            path="/api/secrets/rotation-status",
            name="secrets-rotation-status",
            http_method="GET",
        )
        verdict = check_candidate(candidate)
        assert verdict.eligible is True
        assert verdict.findings == []


class TestR2HighFrequencyCron:
    """R2 — 已有高频 cron (kind=job 且 cron_interval_seconds < 300)。"""

    def test_cron_60s_hits_r2(self):
        """60s cron 的 job 是高频调度 → R2 命中 (双调度反模式)。"""
        candidate = SkillCandidate(
            kind="job",
            path="collect_all_hotspots",
            name="collect-all-hotspots",
            cron_interval_seconds=60,
        )
        verdict = check_candidate(candidate)
        assert verdict.eligible is False
        assert [f.rule_id for f in verdict.findings] == ["R2"]

    def test_cron_600s_passes(self):
        """600s (10 分钟) cron 不属高频 → 放行。"""
        candidate = SkillCandidate(
            kind="job",
            path="weekly_digest_job",
            name="weekly-digest",
            cron_interval_seconds=600,
        )
        assert find_anti_patterns(candidate) == []

    def test_cron_boundary_300s_passes(self):
        """边界: 恰好 300s 不算高频 (规则为严格小于 300)。"""
        candidate = SkillCandidate(
            kind="job",
            path="source_scheduler_tick",
            name="source-scheduler-tick",
            cron_interval_seconds=300,
        )
        assert find_anti_patterns(candidate) == []


class TestR3HotPath:
    """R3 — 高 QPS 采集热路径 (kind=endpoint 且 path/name 含关键词)。"""

    def test_collect_run_hits_r3(self):
        """/api/collect/run 命中热路径关键词家族 → R3 命中 (且仅 R3, 读动词不触发 R1)。"""
        candidate = SkillCandidate(
            kind="endpoint",
            path="/api/collect/run",
            name="trigger-collect",
        )
        verdict = check_candidate(candidate)
        assert verdict.eligible is False
        assert [f.rule_id for f in verdict.findings] == ["R3"]


class TestPositiveCandidate:
    """正例 — 合法 skill 候选应零 findings 通过注册门。"""

    def test_source_health_scan_service_eligible(self):
        """A 类巡检 source-health-scan (kind=service) → eligible=True。

        service 直调: 无写方法 / 无 cron / 不属端点热路径 — 三条规则全不命中。
        """
        candidate = SkillCandidate(
            kind="service",
            path="backend.services.source_scheduler_service",
            name="source-health-scan",
        )
        verdict = check_candidate(candidate)
        assert verdict.eligible is True
        assert verdict.findings == []


class TestMultipleRules:
    """多规则叠加 — 同一候选可同时命中 R1 + R3。"""

    def test_post_collect_run_hits_r1_and_r3(self):
        """POST /api/collect/run: 写方法命中 R1 + 热路径关键词命中 R3。"""
        candidate = SkillCandidate(
            kind="endpoint",
            path="/api/collect/run",
            name="collect-run-now",
            http_method="POST",
        )
        verdict = check_candidate(candidate)
        assert verdict.eligible is False
        assert len(verdict.findings) >= 2
        assert {f.rule_id for f in verdict.findings} == {"R1", "R3"}
