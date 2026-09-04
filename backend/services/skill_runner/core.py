"""skill_runner.core — SkillRunner 主类 + run_skill 顶层入口 (B2).

设计目标:
- ``run_skill(skill, inputs, ticket_id=...)`` 是 trigger-gate worker 的派发
  目标 (B5 接线), 也是 B6 SSE 推送的最终来源.
- A/B 类走 fast-path (resolve→execute→commit, 不调 LLM, 不进 agent_loop 五阶段)
- C/D 类走完整五阶段 (agent_loop.run 调度, pipeline steps 在 EXECUTE 阶段执行)
- 全 run 写 skill_runs (R3 统一数据源): 先 insert(running) → 终态 mark_finished.
- run_id = uuid4() hex, 全局唯一, 作 skill_runs 主键.

非目标 (B2 不做):
- SSE 推送 — B6 通过 hooks.on_phase_change 接入, B2 只预留接口.
- 并发跑 skill — worker 派发层保证单线程 per ticket, runner 自身不引入锁.
- LLM provider 选择 — 默认走 build_default_llm_port() (ai_hub 解析).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from backend.logging_config import logger
from backend.services.agent_loop import (
    AgentLoop,
    AgentLoopHooks,
    AgentLoopSettings,
    LLMPort,
    LoopResult,
    LoopStatus,
    build_default_llm_port,
)
from backend.services.skill_registry.core import (
    ApiTarget,
    ServiceTarget,
    SkillDef,
    Step,
)
from backend.services.skill_runner.dispatch import (
    dispatch_fast,
    dispatch_pipeline,
)
from backend.services.skill_runner.result import (
    SkillRunRepo,
    SkillRunResult,
)


# ---------------------------------------------------------------------------
# SkillRunnerSettings — 构造参数
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SkillRunnerSettings:
    """runner 配置 — 留 fast-path 是否写 skill_runs 等口子, 默认全开."""

    persist_runs: bool = True  # False 时不写 skill_runs (B5 e2e 调试用)


# ---------------------------------------------------------------------------
# SkillRunner — 主类
# ---------------------------------------------------------------------------
class SkillRunner:
    """skill 派发器 — 按 skill_type 决定 fast-path vs 完整五阶段。

    构造参数 (全部可选):
        repo:       skill_runs DAO, 默认 SkillRunRepo()
        llm:        LLMPort, 默认 build_default_llm_port()
        agent_loop: AgentLoop 实例, 默认 None (懒构造)
        settings:   SkillRunnerSettings
        hooks:      AgentLoopHooks (B6 SSE 推送用)

    入口:
        run(skill, inputs, ticket_id=...) → SkillRunResult

    内部流程:
        1. 解析 skill.skill_type (A/B → fast-path; C/D → full path)
        2. 生成 run_id + insert skill_runs (status=running)
        3. A/B: dispatch_fast + mark_finished(succeeded) → 返回
        4. C/D: 构造 ctx (含 executor.execute/reflect) → agent_loop.run
                → 终态映射成 SkillRunResult → mark_finished
    """

    def __init__(
        self,
        repo: SkillRunRepo | None = None,
        llm: LLMPort | None = None,
        agent_loop: AgentLoop | None = None,
        settings: SkillRunnerSettings | None = None,
        hooks: AgentLoopHooks | None = None,
    ) -> None:
        self._repo = repo or SkillRunRepo()
        self._llm = llm or build_default_llm_port()
        self._settings = settings or SkillRunnerSettings()
        self._hooks = hooks
        self._agent_loop = agent_loop

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------
    def run(
        self,
        skill: SkillDef,
        inputs: dict[str, Any],
        *,
        ticket_id: str | None = None,
    ) -> SkillRunResult:
        """跑一次 skill — 按 skill_type 自动分流 fast/full path。

        异常不会从 run 抛出 — 任何异常会被捕获并标 failed (skill_runs
        永远写一行终态, 方便 RunHistory / Dashboard 查询).
        """
        run_id = uuid.uuid4().hex
        started = time.perf_counter()
        if self._settings.persist_runs:
            self._repo.insert(
                run_id,
                skill_id=skill.id,
                ticket_id=ticket_id,
                status="running",
                phase="resolve",
                inputs=inputs,
            )
        try:
            if skill.skill_type in ("A", "B"):
                return self._run_fast(skill, inputs, run_id=run_id, ticket_id=ticket_id, started=started)
            return self._run_full(skill, inputs, run_id=run_id, ticket_id=ticket_id, started=started)
        except Exception as exc:  # noqa: BLE001 — runner 永远不向外抛
            err = f"{type(exc).__name__}: {exc}"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "skill_runner run raised",
                extra={"trace_id": "", "skill_id": skill.id, "run_id": run_id, "error": err},
            )
            if self._settings.persist_runs:
                self._repo.mark_finished(
                    run_id,
                    status="failed",
                    metrics={
                        "elapsed_ms": elapsed_ms,
                        "fast_path": skill.skill_type in ("A", "B"),
                        "target_kind": _target_kind(skill),
                    },
                    error=err,
                )
            return SkillRunResult(
                run_id=run_id,
                skill_id=skill.id,
                ticket_id=ticket_id,
                status="failed",
                fast_path=skill.skill_type in ("A", "B"),
                elapsed_ms=elapsed_ms,
                metrics={
                    "elapsed_ms": elapsed_ms,
                    "fast_path": skill.skill_type in ("A", "B"),
                    "target_kind": _target_kind(skill),
                },
                error=err,
            )

    # ------------------------------------------------------------------
    # A/B fast-path
    # ------------------------------------------------------------------
    def _run_fast(
        self,
        skill: SkillDef,
        inputs: dict[str, Any],
        *,
        run_id: str,
        ticket_id: str | None,
        started: float,
    ) -> SkillRunResult:
        """A/B 类快速路径 — resolve→execute→commit, 零 LLM token.

        流程:
            1. resolve (phase=resolve → execute)
            2. dispatch_fast 直调 target (ServiceTarget 反射 / ApiTarget httpx)
            3. commit (phase=commit → done), mark_finished
        """
        if self._settings.persist_runs:
            self._repo.update_phase(run_id, "execute")
        outputs = dispatch_fast(skill, inputs)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        metrics = {
            "elapsed_ms": elapsed_ms,
            "fast_path": True,
            "phase_count": 3,  # resolve → execute → commit
            "target_kind": _target_kind(skill),
        }
        if self._settings.persist_runs:
            self._repo.mark_finished(
                run_id,
                status="succeeded",
                result=outputs,
                metrics=metrics,
            )
        return SkillRunResult(
            run_id=run_id,
            skill_id=skill.id,
            ticket_id=ticket_id,
            status="succeeded",
            fast_path=True,
            outputs=outputs,
            wiki_path=None,
            llm_tokens=0,
            elapsed_ms=elapsed_ms,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # C/D full path (agent_loop 五阶段 + pipeline steps)
    # ------------------------------------------------------------------
    def _run_full(
        self,
        skill: SkillDef,
        inputs: dict[str, Any],
        *,
        run_id: str,
        ticket_id: str | None,
        started: float,
    ) -> SkillRunResult:
        """C/D 类完整路径 — agent_loop.run 五阶段 + pipeline steps 在 EXECUTE 跑.

        EXECUTE 阶段注入 ``executor.execute`` (B1 stub 由 skill_runner 接管),
        REFLECT 阶段注入 ``executor.reflect`` (走 LLMPort 自评, 失败 retry 1).
        终态由 agent_loop.LoopResult 映射成 SkillRunResult.
        """
        loop = self._agent_loop or AgentLoop(llm=self._llm, hooks=self._hooks)

        def execute_executor(_inputs: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
            if self._settings.persist_runs:
                self._repo.update_phase(run_id, "execute")
            pipeline_result = dispatch_pipeline(skill, inputs, llm=self._llm)
            return {
                "status": "succeeded",
                "step_outputs": pipeline_result["step_outputs"],
                "wiki_path": pipeline_result["wiki_path"],
                "llm_tokens": pipeline_result["llm_tokens"],
            }

        def reflect_executor(_inputs: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
            if self._settings.persist_runs:
                self._repo.update_phase(run_id, "reflect")
            # C/D 类 LLM 自评: 取最后一步 llm 输出 + wiki path 拼 prompt
            verdict = self._llm.complete(_build_reflect_prompt(skill, inputs))
            text = verdict.get("text", "")
            ok = bool(text) or verdict.get("error") is None
            return {
                "status": "succeeded" if ok else "failed",
                "verdict": text or "no_verdict",
                "llm_tokens": int(verdict.get("tokens", 0) or 0),
            }

        ctx = {
            "skill_id": skill.id,
            "executor.execute": execute_executor,
            "executor.reflect": reflect_executor,
        }
        loop_result: LoopResult = loop.run(skill, inputs, run_id=run_id, ctx=ctx)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # 聚合: 从 agent_loop.phases 抽 wiki_path / llm_tokens
        wiki_path = _extract_wiki_path(loop_result)
        llm_tokens = loop_result.llm_tokens

        # status 映射
        if loop_result.status == LoopStatus.SUCCEEDED:
            status = "succeeded"
        elif loop_result.status == LoopStatus.PARTIAL:
            status = "partial"
        else:
            status = "failed"
        outputs = {
            "phases": [
                {"phase": p.value, "status": s.value}
                for p, s in loop_result.phases
            ],
            "execute_output": loop_result.outputs.get("execute"),
        }
        metrics = {
            "elapsed_ms": elapsed_ms,
            "fast_path": False,
            "phase_count": len(loop_result.phases),
            "llm_tokens_total": llm_tokens,
            **loop_result.metrics,
        }
        if self._settings.persist_runs:
            self._repo.mark_finished(
                run_id,
                status=status,
                result=outputs,
                metrics=metrics,
                error=loop_result.error,
            )
        return SkillRunResult(
            run_id=run_id,
            skill_id=skill.id,
            ticket_id=ticket_id,
            status=status,
            fast_path=False,
            outputs=outputs,
            wiki_path=wiki_path,
            llm_tokens=llm_tokens,
            elapsed_ms=elapsed_ms,
            metrics=metrics,
            error=loop_result.error,
        )


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------
def run_skill(
    skill: SkillDef,
    inputs: dict[str, Any],
    *,
    ticket_id: str | None = None,
    runner: SkillRunner | None = None,
) -> SkillRunResult:
    """顶层便捷入口 — 默认构造 SkillRunner() 跑一次 skill。

    B5 (skill_registry e2e 接线) 直接调用此函数。
    """
    r = runner or SkillRunner()
    return r.run(skill, inputs, ticket_id=ticket_id)


def _target_kind(skill: SkillDef) -> str:
    """target 类型标识 — 写 metrics 用."""
    if isinstance(skill.target, ServiceTarget):
        return "service"
    if isinstance(skill.target, ApiTarget):
        return "api"
    return "unknown"


def _extract_wiki_path(loop_result: LoopResult) -> str | None:
    """从 agent_loop 输出抽 wiki_path — EXECUTE 阶段 output 必含."""
    execute_out = loop_result.outputs.get("execute") or {}
    return execute_out.get("wiki_path")


def _build_reflect_prompt(skill: SkillDef, inputs: dict[str, Any]) -> str:
    """REFLECT prompt 默认 — 检查 step_outputs 是否含期望字段。

    C/D 类可由 skill.prompt_template 覆盖 (R1: C/D 类必填 prompt_template);
    但 builder 默认实现仍走 _build_reflect_prompt 以兼容缺省场景。
    """
    skill_id = skill.id
    return (
        f"评估 skill={skill_id} 执行结果 (入参 keys={sorted(inputs.keys())}):\n"
        "- 若 wiki_path 已落, 视为成功 (verdict=ok)\n"
        "- 若 step_outputs 全 succeeded, 视为成功\n"
        "- 否则 verdict=failed\n"
        "只输出 'ok' 或 'failed' 单行。"
    )


__all__ = ["SkillRunner", "SkillRunnerSettings", "run_skill"]