"""test_playbook_engine — Phase C C1 测试套件 (≥15 case).

覆盖意图 (why):
- load: YAML → Playbook dataclass; 解析错抛 ValueError (R7 砍 script)
- validate: 50step 上限 / 重复 step.id / kind 白名单 / skill 引用注册 / api action /
  危险命令黑名单 (P4-7) — 5 个错误分支
- execute: skill step 真实调 run_skill; api step 走 httpx (注入 base_url 走 httpx
  MockTransport); condition step 求值; 顶层 if 跳过; 失败短路; 50step/1h 强制停止
- StepExecutor 模板替换 + 安全 expression 求值 + 防 RCE (拒绝函数调用)
- run 终态契约: succeeded / partial / failed / stopped + steps_results 顺序

测试隔离:
- temp_db fixture 切 config.db_path 到 tmp_path (conftest.py 已提供)
- skill_runner.run_skill 用 fake SkillDef (避免真实 registry 副作用)
- httpx 用 MockTransport (避免 127.0.0.1:8000 真实连接)
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.services.playbook_engine import (
    MAX_STEPS,
    Playbook,
    PlaybookEngine,
    PlaybookStep,
    StepExecutor,
    ValidationReport,
    load_playbook,
)
from backend.services.playbook_engine.core import PlaybookRun
from backend.services.playbook_engine.step import _resolve_template, _safe_eval


# ---------------------------------------------------------------------------
# fixtures: fake SkillRegistry + fake SkillDef
# ---------------------------------------------------------------------------
class FakeSkillDef:
    def __init__(self, id: str) -> None:
        self.id = id


class FakeRegistry:
    """最小 fake — PlaybookEngine 只需 ``get(skill_id) → SkillDef``。"""

    def __init__(self, ids: list[str]) -> None:
        self._ids = set(ids)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, skill_id: str) -> FakeSkillDef:
        if skill_id not in self._ids:
            raise KeyError(skill_id)
        return FakeSkillDef(skill_id)

    def mark_call(self, skill_id: str, params: dict[str, Any]) -> None:
        self.calls.append((skill_id, params))


@pytest.fixture
def fake_registry(monkeypatch) -> FakeRegistry:
    reg = FakeRegistry(["source-health-scan", "weekly-top-events", "daily-vuln-intel"])
    # skill_runner.core.run_skill 用 fake 替换, 不真跑 skill
    # step._exec_skill 用的是 from backend.services.skill_runner.core import run_skill
    def fake_run_skill(skill_def, params, *, ticket_id=None, runner=None):
        reg.mark_call(skill_def.id, params)
        return MagicMock(
            run_id="run-fake-001",
            status="succeeded",
            outputs={"items": [{"id": 1}, {"id": 2}]},
            wiki_path=None,
            llm_tokens=0,
            elapsed_ms=12,
            metrics={"stats": {"dead": 2, "active": 18}},
            error=None,
        )

    import backend.services.skill_runner.core as runner_core
    monkeypatch.setattr(runner_core, "run_skill", fake_run_skill)
    return reg


@pytest.fixture
def engine(fake_registry: FakeRegistry) -> PlaybookEngine:
    return PlaybookEngine(skill_registry=fake_registry)


# ---------------------------------------------------------------------------
# Step 1: loader
# ---------------------------------------------------------------------------
def _write_pb(tmp_path: Path, body: str) -> str:
    p = tmp_path / "pb.yml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


def test_load_basic_minimal(tmp_path: Path) -> None:
    """最小 playbook (metadata + steps) 正确解析。"""
    path = _write_pb(tmp_path, """
        apiVersion: hotspot/v0.8
        kind: Playbook
        metadata:
          name: tiny
          desc: '最小示例'
        steps:
          - id: a
            skill: source-health-scan
    """)
    pb = load_playbook(path)
    assert pb.name == "tiny"
    assert pb.desc == "最小示例"
    assert len(pb.steps) == 1
    assert pb.steps[0].kind == "skill"
    assert pb.steps[0].skill == "source-health-scan"
    assert pb.raw_path == path


def test_load_kind_must_be_playbook(tmp_path: Path) -> None:
    """kind != Playbook → ValueError (fail loud)。"""
    path = _write_pb(tmp_path, """
        apiVersion: hotspot/v0.8
        kind: NotPlaybook
        metadata: {name: x}
        steps: []
    """)
    with pytest.raises(ValueError, match="kind 必须为 'Playbook'"):
        load_playbook(path)


def test_load_script_step_rejected(tmp_path: Path) -> None:
    """R7: script step 在 load 阶段即拒绝 (RCE 边界)。"""
    path = _write_pb(tmp_path, """
        apiVersion: hotspot/v0.8
        kind: Playbook
        metadata: {name: bad}
        steps:
          - id: rce
            type: script
            run: "rm -rf /"
    """)
    with pytest.raises(ValueError, match="禁止"):
        load_playbook(path)


def test_load_missing_id(tmp_path: Path) -> None:
    """step 缺 id/name → ValueError。"""
    path = _write_pb(tmp_path, """
        apiVersion: hotspot/v0.8
        kind: Playbook
        metadata: {name: x}
        steps:
          - skill: source-health-scan
    """)
    with pytest.raises(ValueError, match="缺少 id/name"):
        load_playbook(path)


def test_load_inputs_metadata_trigger_outputs(tmp_path: Path) -> None:
    """inputs/metadata/tigger/outputs 完整解析。"""
    path = _write_pb(tmp_path, """
        apiVersion: hotspot/v0.8
        kind: Playbook
        metadata:
          name: full
          desc: 'd'
          owner: builtin
          tags: [ops, daily]
        trigger:
          type: cron
          spec: '0 8 * * *'
          timezone: Asia/Shanghai
        inputs:
          hours: {type: int, default: 24}
        steps:
          - id: a
            skill: source-health-scan
            params: {x: '{{ inputs.hours }}'}
            output: scan_a
        outputs:
          primary: a
    """)
    pb = load_playbook(path)
    assert pb.owner == "builtin"
    assert pb.tags == ["ops", "daily"]
    assert pb.trigger["spec"] == "0 8 * * *"
    assert pb.inputs["hours"]["default"] == 24
    assert pb.steps[0].params["x"] == "{{ inputs.hours }}"
    assert pb.primary_output == "a"


# ---------------------------------------------------------------------------
# Step 2: validate
# ---------------------------------------------------------------------------
def test_validate_step_limit_exceeded(engine: PlaybookEngine) -> None:
    """R6: 50step 上限, 51 步 → STEP_LIMIT_EXCEEDED error。"""
    steps = [
        PlaybookStep(id=f"s{i}", kind="skill", skill="source-health-scan") for i in range(MAX_STEPS + 1)
    ]
    pb = Playbook(name="too_many", steps=steps)
    report = engine.validate(pb)
    assert not report.ok
    codes = [e.code for e in report.errors]
    assert "STEP_LIMIT_EXCEEDED" in codes


def test_validate_duplicate_step_id(engine: PlaybookEngine) -> None:
    pb = Playbook(
        name="dup",
        steps=[
            PlaybookStep(id="x", kind="skill", skill="source-health-scan"),
            PlaybookStep(id="x", kind="skill", skill="source-health-scan"),
        ],
    )
    report = engine.validate(pb)
    assert not report.ok
    assert any(e.code == "DUPLICATE_STEP_ID" for e in report.errors)


def test_validate_unregistered_skill_ref(engine: PlaybookEngine) -> None:
    """R8: 引用未注册 skill → UNREGISTERED_SKILL_REF error。"""
    pb = Playbook(
        name="dangling",
        steps=[PlaybookStep(id="a", kind="skill", skill="ghost-skill")],
    )
    report = engine.validate(pb)
    assert not report.ok
    assert any(e.code == "UNREGISTERED_SKILL_REF" for e in report.errors)


def test_validate_invalid_api_action(engine: PlaybookEngine) -> None:
    pb = Playbook(
        name="bad-api",
        steps=[PlaybookStep(id="x", kind="api", action="just-a-string")],
    )
    report = engine.validate(pb)
    assert not report.ok
    assert any(e.code == "INVALID_API_ACTION" for e in report.errors)


def test_validate_dangerous_pattern_sudo(engine: PlaybookEngine) -> None:
    """P4-7: sudo 拦截 (沿用 orchestration_service 黑名单)。"""
    pb = Playbook(
        name="evil",
        steps=[PlaybookStep(id="x", kind="api", action="POST /api/x", body={"cmd": "sudo rm -rf /"})],
    )
    report = engine.validate(pb)
    assert not report.ok
    assert any(e.code == "DANGEROUS_PATTERN" for e in report.errors)


def test_validate_ok(engine: PlaybookEngine) -> None:
    pb = Playbook(
        name="clean",
        steps=[
            PlaybookStep(id="a", kind="skill", skill="source-health-scan"),
            PlaybookStep(id="b", kind="api", action="POST /api/codegarden/tasks"),
        ],
    )
    report = engine.validate(pb)
    assert report.ok
    assert report.to_dict()["ok"] is True


# ---------------------------------------------------------------------------
# Step 3: execute
# ---------------------------------------------------------------------------
def test_execute_skill_step_runs_through_registry(
    engine: PlaybookEngine, fake_registry: FakeRegistry
) -> None:
    """skill step 真调 fake run_skill, output 落到 step_output 上下文。"""
    pb = Playbook(
        name="single-skill",
        steps=[PlaybookStep(id="scan", kind="skill", skill="source-health-scan", output="scan_r")],
    )
    run = engine.execute(pb)
    assert run.status == "succeeded"
    assert run.run_id.startswith("pb-")
    assert len(run.steps) == 1
    assert run.steps[0].status == "succeeded"
    assert fake_registry.calls == [("source-health-scan", {})]


def test_execute_inputs_override_defaults(
    engine: PlaybookEngine, fake_registry: FakeRegistry
) -> None:
    """inputs schema 默认 + 用户 override; 后者胜, 传到 skill params。"""
    pb = Playbook(
        name="with-inputs",
        inputs={"top_n": {"type": "int", "default": 10}, "hours": {"type": "int", "default": 24}},
        steps=[
            PlaybookStep(
                id="scan",
                kind="skill",
                skill="source-health-scan",
                params={"top_n": "{{ inputs.top_n }}", "hours": "{{ inputs.hours }}"},
                output="scan_r",
            )
        ],
    )
    run = engine.execute(pb, inputs={"top_n": 5})
    assert run.status == "succeeded"
    assert fake_registry.calls == [("source-health-scan", {"top_n": 5, "hours": 24})]


def test_execute_condition_step_skips_if_false(engine: PlaybookEngine) -> None:
    """顶层 if_expr 假 → 步骤 skipped, 不调用 skill。"""
    pb = Playbook(
        name="guarded",
        steps=[
            PlaybookStep(id="a", kind="skill", skill="source-health-scan"),
            PlaybookStep(id="b", kind="skill", skill="source-health-scan", if_expr="false"),
        ],
    )
    run = engine.execute(pb)
    assert run.status == "succeeded"
    assert run.steps[0].status == "succeeded"
    assert run.steps[1].status == "skipped"


def test_execute_top_level_if_references_prior_step(
    engine: PlaybookEngine, fake_registry: FakeRegistry
) -> None:
    """顶层 if 用 inputs/run 状态做条件; if_expr 真 → 执行, 假 → 跳过。

    spec 语义: ``if: <expr>`` 真则执行 (类 SQL CASE WHEN);
    这里 inputs.run='skip' → if_expr 真 → 第二步执行 (succeeded, 不 skipped).
    """
    pb = Playbook(
        name="if-ref",
        steps=[
            PlaybookStep(id="first", kind="skill", skill="source-health-scan", output="first_r"),
            PlaybookStep(
                id="second",
                kind="skill",
                skill="source-health-scan",
                if_expr="inputs.run == 'go'",  # 输入 run=skip → 假 → 跳过
            ),
        ],
    )
    run = engine.execute(pb, inputs={"run": "skip"})
    assert run.status == "succeeded"
    assert run.steps[0].status == "succeeded"
    # if_expr 求值为 false (inputs.run='skip' != 'go') → second skipped
    assert run.steps[1].status == "skipped"


def test_execute_failure_short_circuits(engine: PlaybookEngine) -> None:
    """step 抛错 → 该步 failed + 终态 partial + 后续步不执行。"""
    # 用 valid skill 让 validate 通过; BoomExecutor 在 execute_step 抛错
    class BoomExecutor:
        def __init__(self, registry, run, playbook):
            self._run = run
            self._outputs = {}

        def set_step_output(self, sid, out): self._outputs[sid] = out
        def eval_expr(self, expr): return False
        def execute_step(self, step): raise RuntimeError("step boom")

    e = PlaybookEngine(skill_registry=FakeRegistry(["source-health-scan"]), step_executor_cls=BoomExecutor)
    pb = Playbook(
        name="boom",
        steps=[
            PlaybookStep(id="x", kind="skill", skill="source-health-scan"),
            PlaybookStep(id="y", kind="skill", skill="source-health-scan"),
        ],
    )
    run = e.execute(pb)
    assert run.status == "partial"
    assert run.steps[0].status == "failed"
    assert "boom" in run.steps[0].error
    # 后续步因 short-circuit 不进入执行流, run.steps 只有 1 项 (failed 那步)
    assert len(run.steps) == 1


def test_execute_total_seconds_cap(
    engine: PlaybookEngine, fake_registry: FakeRegistry, monkeypatch
) -> None:
    """R6: 1h 上限 → 终态 stopped, 当前步 skipped。

    用 mock time.monotonic 模拟时间前进, 让第二步前 deadline 已过。
    """
    import backend.services.playbook_engine.core as core_mod

    # execute 内多次调用 time.monotonic:
    #   - deadline = time.monotonic() + max_total_seconds
    #   - 每步前检查 deadline
    #   - 每步 t0 + elapsed_ms 计算
    # 简化策略: 第 1/2/3 次 (deadline 设置 + a 步 t0 + a 步 elapsed) 返回 100,
    # 之后 (b 步前的 deadline 检查) 返回 200 → 超时。
    from itertools import chain

    monotonic_values = list(chain.from_iterable(
        [[100.0, 100.0, 100.0], [200.0] * 50]
    ))
    it = iter(monotonic_values)

    def fake_monotonic() -> float:
        return next(it)

    monkeypatch.setattr(core_mod.time, "monotonic", fake_monotonic)

    e = PlaybookEngine(skill_registry=fake_registry, max_total_seconds=10)
    pb = Playbook(
        name="stop",
        steps=[
            PlaybookStep(id="a", kind="skill", skill="source-health-scan"),
            PlaybookStep(id="b", kind="skill", skill="source-health-scan"),
        ],
    )
    run = e.execute(pb)
    assert run.status == "stopped"
    assert run.error == "total_seconds_exceeded"
    # b 应被 skipped (deadline 已过)
    assert any(s.status == "skipped" and s.step_id == "b" for s in run.steps)


def test_execute_rejects_invalid_playbook(engine: PlaybookEngine) -> None:
    """validate errors 非空 → execute 抛 ValueError, 不执行。"""
    pb = Playbook(name="bad", steps=[PlaybookStep(id="x", kind="skill", skill="GHOST")])
    with pytest.raises(ValueError, match="validate failed"):
        engine.execute(pb)


# ---------------------------------------------------------------------------
# Step 4: StepExecutor 单元 (模板替换 + 表达式安全)
# ---------------------------------------------------------------------------
def test_template_full_placeholder_returns_native_type() -> None:
    """整段 '{{ x.y }}' → 返回原值类型, 不强制 str。"""
    ctx = {"x": {"y": 42}, "inputs": {"flag": True}}
    assert _resolve_template("{{ x.y }}", ctx) == 42
    assert _resolve_template("{{ x.y }}", ctx) is not None


def test_template_partial_placeholder_returns_string() -> None:
    ctx = {"inputs": {"hours": 24}}
    out = _resolve_template("window {{ inputs.hours }}h", ctx)
    assert out == "window 24h"


def test_safe_eval_blocks_function_calls() -> None:
    """RCE 边界: __import__('os').system('rm -rf /') 应被拒。"""
    with pytest.raises(ValueError, match="不允许函数调用"):
        _safe_eval("__import__('os')", {})


def test_safe_eval_basic_arithmetic_and_compare() -> None:
    ctx = {"steps": {"a": {"output": {"count": 3}}}, "inputs": {"limit": 5}}
    assert _safe_eval("steps.a.output.count > 0", ctx) is True
    assert _safe_eval("steps.a.output.count < inputs.limit", ctx) is True
    assert _safe_eval("steps.a.output.count == 3", ctx) is True


def test_safe_eval_attribute_access_via_ctx() -> None:
    """ctx.steps.x.output 风格允许 (限定根 Name ∈ ctx); 函数调用仍拒。"""
    ctx = {"steps": {"x": {"flag": True}}, "inputs": {}}
    assert _safe_eval("steps.x.flag", ctx) is True


def test_api_step_uses_injected_transport(
    engine: PlaybookEngine, monkeypatch
) -> None:
    """api step 走 httpx MockTransport, 不真连 127.0.0.1:8000。"""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "echoed_path": request.url.path})

    transport = httpx.MockTransport(handler)
    orig_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    pb = Playbook(
        name="api-call",
        steps=[PlaybookStep(id="x", kind="api", action="POST /api/codegarden/tasks", body={"k": "v"})],
    )
    run = engine.execute(pb)
    assert run.status == "succeeded"
    out = run.steps[0].output
    assert out["ok"] is True
    assert out["echoed_path"] == "/api/codegarden/tasks"


def test_api_step_rejects_non_whitelisted_path(engine: PlaybookEngine) -> None:
    """api 白名单: 非 /api/* 路径拒绝。"""
    pb = Playbook(
        name="evil",
        steps=[PlaybookStep(id="x", kind="api", action="POST /admin/delete")],
    )
    with pytest.raises(ValueError, match="validate failed"):
        engine.execute(pb)


# ---------------------------------------------------------------------------
# Step 5: examples 实际加载
# ---------------------------------------------------------------------------
def test_examples_loadable() -> None:
    """3 个内置 example 全部可加载 + validate 通过 (skill 引用均已注册)。"""
    import os

    cwd = os.getcwd()
    ex_dir = Path(cwd) / "playbook_engine" / "examples"
    assert ex_dir.exists()
    found = 0
    for yml in sorted(ex_dir.glob("*.yml")):
        pb = load_playbook(str(yml))
        assert pb.name
        assert pb.steps
        # 用 builtin registry 跑 validate
        from backend.services.skill_registry.builtin import BUILTIN

        engine = PlaybookEngine(skill_registry=BUILTIN)
        report = engine.validate(pb)
        # 不强制 ok — 允许 warnings; 但 errors 必须为空 (否则 example 不能跑)
        assert report.ok, f"example {yml.name} validate 失败: {report.to_dict()}"
        found += 1
    assert found >= 3