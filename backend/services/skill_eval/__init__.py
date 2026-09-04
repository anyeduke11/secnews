"""skill_eval — v0.8 Phase C C5 Eval v1 黄金 fixture 评测框架.

模块分层:
- ``dataset.py``  — EvalFixture / Assertion dataclass + YAML 加载
- ``runner.py``   — 跑一个 fixture (调 skill / playbook), 产出 SkillRunResult
- ``judge.py``    — 对比 SkillRunResult 与 EvalFixture 断言, 产出 JudgeVerdict
- ``report.py``   — 聚合 JudgeVerdict 列表, 生成 EvalReport + Markdown 渲染

设计要点 (Phase C / R8):
- 黄金 fixture 不调真实 LLM; 测试用 fake engine 注入确定性结果 (详见
  backend/tests/test_skill_eval.py 的 FakeEngine)
- 评测数据流单向: fixtures YAML → EvalFixture → SkillRunResult → JudgeVerdict → EvalReport
- report 落 SQLite (skill_eval_runs 表) 或 stdout (CI 用), 通过 ReportFormat 枚举控制
- 全程 fail loud: 任一断言失败 verdict 写 failed + 详细 reason, 报告层不静默跳过
"""
from __future__ import annotations

from backend.services.skill_eval.dataset import (
    FIXTURES_DIR,
    Assertion,
    EvalFixture,
    list_fixture_ids,
    load_fixture,
    load_fixture_by_id,
)
from backend.services.skill_eval.judge import AssertionResult, JudgeResult, judge
from backend.services.skill_eval.report import (
    EvalReport,
    ReportFormat,
    build_report,
    render_markdown,
    to_dict,
)
from backend.services.skill_eval.runner import (
    FixtureRunner,
    SkillRunResult,
    run_fixture,
)

__all__ = [
    "Assertion",
    "AssertionResult",
    "EvalFixture",
    "EvalReport",
    "FIXTURES_DIR",
    "FixtureRunner",
    "JudgeResult",
    "ReportFormat",
    "SkillRunResult",
    "build_report",
    "judge",
    "list_fixture_ids",
    "load_fixture",
    "load_fixture_by_id",
    "render_markdown",
    "run_fixture",
    "to_dict",
]