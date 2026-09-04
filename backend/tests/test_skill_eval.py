"""test_skill_eval.py — C5 Eval v1 黄金 fixture 评测框架测试 (≥8 cases).

覆盖:
- dataset: load 5 fixtures + 非法 fixture 拒绝 + list_fixture_ids
- runner: fake engine 跑 skill / playbook / 失败注入
- judge: type_check / equal / range / field_type / length_eq / list_field_* /
         list_avg_above / dict_has_keys / skip_if_null / skip_if_empty
- report: pass_rate / verdict / render_markdown / to_dict
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.services.skill_eval import (
    Assertion,
    EvalReport,
    FIXTURES_DIR,
    FixtureRunner,
    JudgeResult,
    ReportFormat,
    build_report,
    judge,
    list_fixture_ids,
    load_fixture,
    load_fixture_by_id,
    render_markdown,
    run_fixture,
    to_dict,
)
from backend.services.skill_eval.dataset import ASSERTION_TYPES, EvalFixture
from backend.services.skill_eval.runner import SkillRunResult


# ---------------------------------------------------------------------------
# Fake engine — deterministic outputs per skill_id
# ---------------------------------------------------------------------------
class FakeEngine:
    """deterministic skill_eval engine — 每个 skill_id 返回固定 dict."""

    def __init__(self, *, raise_for: set[str] | None = None) -> None:
        self.raise_for = raise_for or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run_skill(self, skill_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((skill_id, inputs))
        if skill_id in self.raise_for:
            raise RuntimeError(f"fake engine boom for {skill_id}")
        if skill_id == "source-health-scan":
            return {
                "running_count": 12,
                "stats": {"active": 10, "dead": 2, "total": 12, "active_rate": 0.83},
                "error": None,
            }
        if skill_id == "weekly-top-events":
            return {
                "top5": [
                    {"title": "CVE-2026-0001 发布高危漏洞", "importance": "影响关键基础设施", "source": "NVD"},
                    {"title": "AI 工具链出现新型钓鱼攻击", "importance": "AI 安全热点事件", "source": "AIHot"},
                    {"title": "某大厂数据泄露 1.2 亿条", "importance": "数据合规风险", "source": "OpenBB"},
                    {"title": "开源软件供应链投毒案例", "importance": "供应链安全警钟", "source": "SecNews"},
                    {"title": "某监管机构发布新合规指南", "importance": "合规动态", "source": "监管"},
                ],
                "error": None,
            }
        if skill_id == "compliance-status":
            return {
                "http_status": 200,
                "body": {
                    "categories": ["level_2", "level_3", "关基"],
                    "level": "level_2",
                    "coverage_pct": 86,
                },
                "error": None,
            }
        if skill_id == "cve-cross-period":
            return {
                "correlations": [
                    {"cve_id": "CVE-2026-0001", "period_a": "2025-12", "period_b": "2026-01", "score": 0.85, "period_gap_days": 31},
                    {"cve_id": "CVE-2026-0002", "period_a": "2025-11", "period_b": "2026-01", "score": 0.72, "period_gap_days": 60},
                    {"cve_id": "CVE-2026-0003", "period_a": "2025-10", "period_b": "2026-01", "score": 0.91, "period_gap_days": 90},
                ],
                "error": None,
            }
        return {"error": None}

    def run_playbook(self, playbook_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((playbook_name, inputs))
        if playbook_name == "daily-source-health":
            return {
                "steps": [{"id": "scan", "status": "success"}, {"id": "ticket_if_dead", "status": "success"}, {"id": "outputs", "status": "success"}],
                "step_outputs": {"scan": {"running_count": 12}},
                "error": None,
            }
        return {"steps": [], "error": None}


# ---------------------------------------------------------------------------
# dataset
# ---------------------------------------------------------------------------
def test_list_fixture_ids_returns_5_golden_fixtures():
    ids = list_fixture_ids()
    assert len(ids) >= 5, f"expected ≥5 fixtures, got {len(ids)}: {ids}"
    for required in (
        "source_health_a",
        "weekly_top5_c",
        "compliance_query_b",
        "cve_correlate_d",
        "playbook_dryrun",
    ):
        assert required in ids, f"missing fixture: {required}"


def test_load_fixture_by_id_all_succeed():
    for fid in ("source_health_a", "weekly_top5_c", "compliance_query_b", "cve_correlate_d", "playbook_dryrun"):
        fx = load_fixture_by_id(fid)
        assert isinstance(fx, EvalFixture)
        assert fx.id
        assert fx.assertions, f"fixture {fid} 无 assertions"


def test_load_fixture_rejects_invalid_assertion_type():
    with pytest.raises(ValueError):
        EvalFixture.from_dict(
            {
                "id": "bad",
                "skill_id": "x",
                "assertions": [{"name": "x", "type": "nonsense", "target": "result"}],
            }
        )


def test_load_fixture_rejects_missing_id():
    with pytest.raises(ValueError):
        EvalFixture.from_dict({"skill_id": "x", "assertions": [{"name": "x", "type": "equal", "target": "result", "expected": 1}]})


def test_assertion_types_contains_known_keys():
    for t in (
        "type_check",
        "equal",
        "range",
        "field_type",
        "length_eq",
        "list_field_type",
        "list_field_eq",
        "list_field_range",
        "list_field_min",
        "list_field_min_length",
        "list_avg_above",
        "dict_has_keys",
    ):
        assert t in ASSERTION_TYPES


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def test_runner_run_skill_produces_skill_run_result():
    fx = load_fixture_by_id("source_health_a")
    engine = FakeEngine()
    out = run_fixture(fx, engine)
    assert isinstance(out, SkillRunResult)
    assert out.error is None
    assert out.success
    assert out.result["running_count"] == 12
    assert out.meta["call_count"] == 1
    assert engine.calls == [("source-health-scan", fx.inputs)]


def test_runner_run_playbook_produces_step_outputs():
    fx = load_fixture_by_id("playbook_dryrun")
    engine = FakeEngine()
    out = run_fixture(fx, engine)
    assert out.error is None
    assert out.success
    assert out.result["steps"][0]["status"] == "success"
    assert out.result["step_outputs"]["scan"]["running_count"] == 12


def test_runner_records_exception_in_error_field():
    fx = load_fixture_by_id("source_health_a")
    engine = FakeEngine(raise_for={"source-health-scan"})
    out = run_fixture(fx, engine)
    assert out.success is False
    assert "boom" in (out.error or "")


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------
def test_judge_all_assertions_pass_for_source_health_a():
    fx = load_fixture_by_id("source_health_a")
    run = run_fixture(fx, FakeEngine())
    jr = judge(run, fx)
    assert jr.passed, f"expected pass, got {jr.summary}: {[a.reason for a in jr.assertions if not a.passed]}"
    assert jr.failed_count == 0


@pytest.mark.parametrize(
    "fixture_id",
    ["weekly_top5_c", "compliance_query_b", "cve_correlate_d", "playbook_dryrun"],
)
def test_judge_each_golden_fixture_passes(fixture_id: str):
    fx = load_fixture_by_id(fixture_id)
    run = run_fixture(fx, FakeEngine())
    jr = judge(run, fx)
    assert jr.passed, f"{fixture_id} failed: {jr.summary}"


def test_judge_runner_error_marks_all_assertions_failed():
    fx = load_fixture_by_id("source_health_a")
    run = run_fixture(fx, FakeEngine(raise_for={"source-health-scan"}))
    jr = judge(run, fx)
    assert not jr.passed
    assert all("runner error" in a.reason for a in jr.assertions)


def test_judge_equal_type_check_range_field_type():
    fx = load_fixture_by_id("compliance_query_b")
    run = run_fixture(fx, FakeEngine())
    jr = judge(run, fx)
    types_seen = {a.assertion.type for a in jr.assertions}
    assert {"equal", "type_check", "range", "field_type", "dict_has_keys"} <= types_seen


def test_judge_skip_if_null_skips_when_value_is_none():
    fx = load_fixture_by_id("source_health_a")
    run = run_fixture(fx, FakeEngine())
    # 注入一个 null 字段
    run.result["stats"]["active_rate"] = None
    jr = judge(run, fx)
    # active_rate range 带 skip_if_null, 应 skip 通过
    range_assertion = next(a for a in jr.assertions if a.assertion.type == "range")
    assert range_assertion.passed
    assert "skipped" in range_assertion.reason


def test_judge_skip_if_empty_skips_when_list_is_empty():
    fx = load_fixture_by_id("cve_correlate_d")
    run = run_fixture(fx, FakeEngine())
    # 注入空 correlations
    run.result["correlations"] = []
    jr = judge(run, fx)
    list_assertions = [a for a in jr.assertions if a.assertion.type.startswith("list_field")]
    assert all(a.passed for a in list_assertions), [a.reason for a in list_assertions]


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def test_build_report_pass_rate_and_verdict():
    fixtures = [
        load_fixture_by_id("source_health_a"),
        load_fixture_by_id("weekly_top5_c"),
    ]
    runs = [run_fixture(fx, FakeEngine()) for fx in fixtures]
    judges = [judge(r, fx) for r, fx in zip(runs, fixtures)]
    rep = build_report(judges, threshold=0.8)
    assert rep.fixtures_total == 2
    assert rep.fixtures_passed == 2
    assert rep.fixtures_failed == 0
    assert rep.pass_rate == 1.0
    assert rep.verdict is True


def test_build_report_verdict_fail_when_below_threshold():
    fixtures = [load_fixture_by_id("source_health_a")]
    runs = [run_fixture(fx, FakeEngine()) for fx in fixtures]
    judges = [judge(r, fx) for r, fx in zip(runs, fixtures)]
    rep = build_report(judges, threshold=1.1)  # 永远不达
    assert rep.verdict is False


def test_to_dict_is_json_serializable():
    fixtures = [
        load_fixture_by_id("source_health_a"),
        load_fixture_by_id("weekly_top5_c"),
    ]
    runs = [run_fixture(fx, FakeEngine()) for fx in fixtures]
    judges = [judge(r, fx) for r, fx in zip(runs, fixtures)]
    rep = build_report(judges)
    d = to_dict(rep)
    assert d["fixtures_total"] == 2
    assert d["verdict"] is True
    assert d["results"][0]["fixture_id"] == "source-health-scan-A-001"


def test_render_markdown_contains_summary_and_each_fixture():
    fixtures = [load_fixture_by_id("source_health_a"), load_fixture_by_id("weekly_top5_c")]
    runs = [run_fixture(fx, FakeEngine()) for fx in fixtures]
    judges = [judge(r, fx) for r, fx in zip(runs, fixtures)]
    rep = build_report(judges)
    md = render_markdown(rep)
    assert "# Skill Eval Report" in md
    assert "Summary" in md
    assert "source-health-scan-A-001" in md
    assert "weekly-top-events-C-001" in md


def test_report_render_json_is_serializable():
    fixtures = [load_fixture_by_id("source_health_a")]
    runs = [run_fixture(fx, FakeEngine()) for fx in fixtures]
    judges = [judge(r, fx) for r, fx in zip(runs, fixtures)]
    rep = build_report(judges)
    import json

    blob = rep.render(ReportFormat.JSON)
    parsed = json.loads(blob)
    assert parsed["fixtures_total"] == 1
    assert parsed["verdict"] is True