"""skill_eval.report — 聚合 JudgeResult 列表, 生成 EvalReport + Markdown 渲染 (C5).

``EvalReport`` 是不可变聚合体:
- ``fixtures_total`` / ``fixtures_passed`` / ``fixtures_failed`` — fixture 维度
- ``assertions_total`` / ``assertions_passed`` / ``assertions_failed`` — assertion 维度
- ``pass_rate`` (float 0..1) — fixture 通过率
- ``results`` — 原始 JudgeResult 列表 (fixture-id → JudgeResult)
- ``verdict`` — overall pass/fail 标志 (pass_rate >= threshold)

``render_markdown(report)`` → Markdown 文本 (CI / 邮件用):
- 顶部 summary 卡 (pass_rate / total / failed fixtures)
- 每个 fixture 一节: id / skill_id / playbook / summary / assertion 明细
- 失败 assertion 高亮 reason (R12: 不静默跳过)

``to_dict(report)`` → JSON-safe dict (ReportFormat.JSON 路径使用)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.services.skill_eval.judge import AssertionResult, JudgeResult

__all__ = ["EvalReport", "ReportFormat", "render_markdown", "to_dict"]


class ReportFormat(str, Enum):
    """报告输出格式."""

    MARKDOWN = "markdown"
    JSON = "json"


@dataclass(frozen=True)
class EvalReport:
    """聚合后的评测报告; 由 ``build_report(judges)`` 构造."""

    fixtures_total: int
    fixtures_passed: int
    fixtures_failed: int
    assertions_total: int
    assertions_passed: int
    assertions_failed: int
    pass_rate: float
    threshold: float
    verdict: bool
    results: list[JudgeResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe 序列化 (ReportFormat.JSON 路径)."""
        return to_dict(self)

    def render(self, fmt: ReportFormat) -> str:
        if fmt == ReportFormat.JSON:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        return render_markdown(self)


def build_report(
    results: list[JudgeResult],
    threshold: float = 0.8,
) -> EvalReport:
    """聚合 JudgeResult 列表, 计算 pass_rate / verdict."""
    fixtures_total = len(results)
    fixtures_passed = sum(1 for r in results if r.passed)
    fixtures_failed = fixtures_total - fixtures_passed
    assertions_total = sum(len(r.assertions) for r in results)
    assertions_passed = sum(r.passed_count for r in results)
    assertions_failed = assertions_total - assertions_passed
    pass_rate = (fixtures_passed / fixtures_total) if fixtures_total else 0.0
    verdict = pass_rate >= threshold
    return EvalReport(
        fixtures_total=fixtures_total,
        fixtures_passed=fixtures_passed,
        fixtures_failed=fixtures_failed,
        assertions_total=assertions_total,
        assertions_passed=assertions_passed,
        assertions_failed=assertions_failed,
        pass_rate=pass_rate,
        threshold=threshold,
        verdict=verdict,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# JSON 序列化
# ---------------------------------------------------------------------------
def to_dict(report: EvalReport) -> dict[str, Any]:
    """递归 dataclass → dict (供 JSON 路径)."""

    def _ar(ar: AssertionResult) -> dict[str, Any]:
        return {
            "name": ar.assertion.name,
            "type": ar.assertion.type,
            "target": ar.assertion.target,
            "passed": ar.passed,
            "actual": ar.actual if _is_json_safe(ar.actual) else repr(ar.actual),
            "reason": ar.reason,
        }

    def _jr(jr: JudgeResult) -> dict[str, Any]:
        return {
            "fixture_id": jr.fixture_id,
            "passed": jr.passed,
            "summary": jr.summary,
            "assertions": [_ar(a) for a in jr.assertions],
        }

    return {
        "fixtures_total": report.fixtures_total,
        "fixtures_passed": report.fixtures_passed,
        "fixtures_failed": report.fixtures_failed,
        "assertions_total": report.assertions_total,
        "assertions_passed": report.assertions_passed,
        "assertions_failed": report.assertions_failed,
        "pass_rate": report.pass_rate,
        "threshold": report.threshold,
        "verdict": report.verdict,
        "results": [_jr(r) for r in report.results],
    }


def _is_json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_safe(v) for k, v in value.items())
    return False


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------
def render_markdown(report: EvalReport) -> str:
    """生成人类可读 Markdown 报告; CI / 邮件 digest 用."""
    lines: list[str] = []
    lines.append("# Skill Eval Report (v0.8 C5)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **verdict**: {'✅ PASS' if report.verdict else '❌ FAIL'}")
    lines.append(f"- **pass_rate**: {report.pass_rate:.0%} (threshold {report.threshold:.0%})")
    lines.append(f"- **fixtures**: {report.fixtures_passed}/{report.fixtures_total} passed ({report.fixtures_failed} failed)")
    lines.append(f"- **assertions**: {report.assertions_passed}/{report.assertions_total} passed ({report.assertions_failed} failed)")
    lines.append("")

    lines.append("## Fixtures")
    lines.append("")
    for jr in report.results:
        status = "✅" if jr.passed else "❌"
        title = jr.fixture_id
        sub = jr.summary
        lines.append(f"### {status} `{title}` — {sub}")
        lines.append("")
        for ar in jr.assertions:
            mark = "✓" if ar.passed else "✗"
            lines.append(
                f"  - {mark} **{ar.assertion.name}** "
                f"(`{ar.assertion.type}` → `{ar.assertion.target}`) "
                f"— {ar.reason or 'ok'}"
            )
        lines.append("")

    return "\n".join(lines) + "\n"