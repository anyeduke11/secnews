"""agent_loop.core — AgentLoop 状态机主类 (v0.8 Phase B B1).

设计纪律 (V0.8_REFACTOR_PLAN.md §5.3):
- 5 阶段顺序固定: Intent → Plan → Execute → Reflect → Commit
- REFLECT 阶段失败自动 retry 1 次; 仍失败 → 终态 partial=True, 仍写入结果
- 任何阶段抛异常 → 当前阶段 failed + COMMIT 阶段补 SKIPPED + 终态 failed
- run_fast 跳过 PLAN + REFLECT (A/B 类零 LLM)
- 每阶段 mark_running / mark_terminal 持久化, 进程崩溃可续跑
- LLMPort 是协议, 默认实现包 ai_hub.llm_service (no direct SDK import)

公开 API:
- :class:`AgentLoop`     — 状态机主类, run/run_fast 入口
- :class:`LLMPort`        — LLM 调用协议 (完成 chat() + 累计 token)
- :class:`AgentLoopHooks` — 可选回调 (after_phase), 用于 SSE 推送 / 日志
- :class:`AgentLoopSettings` — REFLECT retry 上限, 默认 1
- :func:`build_default_llm_port` — 工厂函数, 默认从 ai_hub 解析 LLMService

非目标 (B1 不做, 留 B2/B5 接线):
- 真实 LLM 调用 — 本模块的 _run_phase_* 是 stub 实现, B2 由 skill_runner
  注入 executor; 实际 LLM 仅在 default executor 路径上走 ai_hub。
- SSE 推送 — 留 B6, hooks 是预留接口。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.logging_config import logger
from backend.services.agent_loop.checkpoint import LoopCheckpointRepo
from backend.services.agent_loop.state import (
    LoopPhase,
    LoopResult,
    LoopStatus,
    PHASE_ORDER,
    is_terminal,
    next_phase,
    should_run_phase,
)

__all__ = [
    "AgentLoop",
    "AgentLoopHooks",
    "AgentLoopSettings",
    "LLMPort",
    "build_default_llm_port",
    "recover_stale_checkpoints",
]


# ---------------------------------------------------------------------------
# LLMPort — LLM 调用协议 (DI, 解除 ai_hub 硬依赖)
# ---------------------------------------------------------------------------
class LLMPort(Protocol):
    """LLM 调用协议 — skill_runner 在 C/D 类调 LLM 时通过此协议取 token + 文本。

    真实实现由 ``build_default_llm_port()`` 工厂按需解析 ai_hub.llm_service;
    测试可注入 fake 避免真实网络。返回值 dict 必含 ``text`` 键, 可选含
    ``tokens`` 整数键 (累计 token 估算, 缺省 0)。
    """

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        """发一次 LLM completion, 返回 {"text": str, "tokens": int}。"""
        ...


def build_default_llm_port() -> LLMPort:
    """默认 LLMPort 工厂 — 解析 ai_hub.llm_service.summarize 当作同步完成。

    ai_hub 不可用 (LLM 未配置) 或 import 失败时回退到 no-op port, 永不抛 —
    run 仍可继续 (A/B 类不用 LLM, C/D 缺 LLM 时会落到 partial=True 终态)。
    """
    try:
        from backend.services.ai_hub import llm_service

        return _AiHubLLMPort(llm_service)
    except Exception as exc:
        logger.warning(
            "agent_loop: default LLMPort unavailable, using noop",
            extra={"trace_id": "", "reason": str(exc)},
        )
        return _NoopLLMPort()


class _AiHubLLMPort:
    """默认 LLMPort — 委托 ai_hub.llm_service (异步接口), 同步等待。"""

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        """调 LLMService.summarize 把 prompt 视作单 chunk; tokens 估算走现成 helper。

        真实项目里 v0.7 Batch ② 引入了异步 chat, 这里走 summarize 兼容层
        (LLMService.summarize 是 sync 包装, 等价但慢一点, B2 接线时由
        skill_runner 注入更高效的 async port)。
        """
        # 默认走同步入口, 失败吞 — 状态机 partial 路径接管
        try:
            # summarize 接受 list[str] chunks; 单 chunk 即单 prompt
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # 已在事件循环里 → 跑协程; 不阻塞当前协程
                text = loop.run_until_complete(self._llm.summarize([prompt]))
            else:
                text = asyncio.run(self._llm.summarize([prompt]))
        except Exception as exc:  # noqa: BLE001 — LLM 路径容错
            logger.warning(
                "agent_loop: LLM call failed",
                extra={"trace_id": "", "reason": str(exc)},
            )
            return {"text": "", "tokens": 0, "error": str(exc)}
        # 估算 token: len(prompt + text) / 4 (粗略; ai_hub.prompts._est_tokens 等价)
        tokens = max(1, (len(prompt) + len(text or "")) // 4)
        return {"text": text or "", "tokens": tokens}


class _NoopLLMPort:
    """无 LLM 实现 — 全部返回空, token 0 (C/D 类跑出 partial)。"""

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        return {"text": "", "tokens": 0}


# ---------------------------------------------------------------------------
# AgentLoopSettings — REFLECT retry 上限 / 阶段超时 (留口子, B1 不强制)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AgentLoopSettings:
    """状态机运行参数 — 改 retry 数 / 阶段 timeout 走 settings 即可, 不改类。

    reflect_max_retries: REFLECT 阶段失败自动重试上限, 默认 1 (R-08 任务书
    §3.2: 1 次 retry, 仍失败 → commit partial=True, 不无限循环)。
    """

    reflect_max_retries: int = 1


# ---------------------------------------------------------------------------
# AgentLoopHooks — 可选回调 (B6 SSE 推送 / 日志统一入口)
# ---------------------------------------------------------------------------
@dataclass
class AgentLoopHooks:
    """状态机阶段回调 — after_phase 接收 (phase, status, payload) 三元组。

    B1 不强制, 默认 None 即不开回调; B6 前端 SSE 接入时注册 on_phase_change。
    on_error 单独抽出, 阶段抛异常时调用 (用于全局审计/告警)。
    """

    on_phase_change: Callable[[LoopPhase, LoopStatus, dict[str, Any] | None], None] | None = None
    on_error: Callable[[LoopPhase, str], None] | None = None


# ---------------------------------------------------------------------------
# AgentLoop — 状态机主类
# ---------------------------------------------------------------------------
class AgentLoop:
    """五阶段状态机 (Intent→Plan→Execute→Reflect→Commit) 驱动单次 skill run。

    构造参数 (全部可选):
        llm: LLMPort 实现, 默认 build_default_llm_port()
        checkpoint_repo: 持久化实现, 默认 LoopCheckpointRepo()
        settings: 运行参数, 默认 AgentLoopSettings()
        hooks: 回调, 默认 None

    入口方法:
        run(skill, inputs, *, run_id, fast_path=False) → LoopResult
        run_fast(skill, inputs, *, run_id) → LoopResult (fast_path=True 短调)

    skill 参数: dict 形式, 至少含 ``id`` 键; 完整 SkillDef 留 B2 接线注入。
    """
    _state_lock = threading.Lock()

    def __init__(
        self,
        llm: LLMPort | None = None,
        checkpoint_repo: LoopCheckpointRepo | None = None,
        settings: AgentLoopSettings | None = None,
        hooks: AgentLoopHooks | None = None,
    ) -> None:
        self._llm = llm or build_default_llm_port()
        self._checkpoints = checkpoint_repo or LoopCheckpointRepo()
        self._settings = settings or AgentLoopSettings()
        self._hooks = hooks

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------
    def run(
        self,
        skill: Any,
        inputs: dict[str, Any],
        *,
        run_id: str,
        ctx: dict[str, Any] | None = None,
    ) -> LoopResult:
        """5 阶段全跑: Intent→Plan→Execute→Reflect→Commit。"""
        return self._run(skill, inputs, run_id=run_id, fast_path=False, ctx=ctx)

    def run_fast(
        self,
        skill: Any,
        inputs: dict[str, Any],
        *,
        run_id: str,
        ctx: dict[str, Any] | None = None,
    ) -> LoopResult:
        """2 阶段快速路径: Intent→Execute→Commit (A/B 类零 LLM)。

        等价于 ``run(..., fast_path=True)`` — 单独命名让调用方代码更可读。
        """
        return self._run(skill, inputs, run_id=run_id, fast_path=True, ctx=ctx)

    # ------------------------------------------------------------------
    # 状态机主体
    # ------------------------------------------------------------------
    def _run(
        self,
        skill: Any,
        inputs: dict[str, Any],
        *,
        run_id: str,
        fast_path: bool,
        ctx: dict[str, Any] | None,
    ) -> LoopResult:
        """跑完整状态机, 返回 LoopResult。

        主循环:
        1. intent 阶段 — 解析输入, 产出 intent dict
        2. plan 阶段 (非 fast_path) — 生成执行计划
        3. execute 阶段 — 调 executor (B2 注入); 默认 stub
        4. reflect 阶段 (非 fast_path) — 调 LLM 自评; 失败 retry 1
        5. commit 阶段 — 终态聚合, 写 LoopResult

        任何阶段异常: 标 failed, 跳过剩余阶段, commit 阶段跑 "failed→skipped"
        收尾, 终态 LoopResult.status=FAILED。
        """
        outputs: dict[str, Any] = {}
        phases: list[tuple[LoopPhase, LoopStatus]] = []
        llm_tokens = 0
        started = time.perf_counter()
        skill_id = getattr(skill, "id", None) or str(skill.get("id", "<unknown>"))
        ctx = ctx or {}

        # 阶段分发表: 真实 executor 在 B2 由 skill_runner 注入 (B1 默认 stub)
        executors: dict[LoopPhase, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = (
            ctx.get("executors")
            or {
                LoopPhase.INTENT: self._executor_intent,
                LoopPhase.PLAN: self._executor_plan,
                LoopPhase.EXECUTE: self._executor_execute,
                LoopPhase.REFLECT: self._executor_reflect,
                LoopPhase.COMMIT: self._executor_commit,
            }
        )

        # 阶段起始 — 顺序固定, 始终遍历 PHASE_ORDER 全 5 阶段
        # (fast_path 走 should_run_phase 跳过 PLAN/REFLECT 的实际执行,
        #  但 SKIPPED 状态仍要写 checkpoint 行 — 保证历史回放读 5 行
        #  对齐业务可观察性, 不会因快路径而丢阶段)
        final_status: LoopStatus = LoopStatus.SUCCEEDED
        final_error: str | None = None

        for phase in PHASE_ORDER:
            if not should_run_phase(phase, fast_path=fast_path):
                # 跳过: 直接 mark_terminal(SKIPPED) + 进 phases
                self._checkpoints.mark_terminal(run_id, phase, LoopStatus.SKIPPED)
                phases.append((phase, LoopStatus.SKIPPED))
                self._fire_hook(phase, LoopStatus.SKIPPED, None)
                continue

            # 进入阶段 — mark_running 持久化入参快照
            payload_in = {"inputs": inputs, "skill_id": skill_id, "phase": phase.value}
            self._checkpoints.mark_running(run_id, phase, payload=payload_in)
            self._fire_hook(phase, LoopStatus.RUNNING, payload_in)

            try:
                exec_fn = executors.get(phase)
                if exec_fn is None:
                    raise RuntimeError(f"agent_loop: no executor for phase {phase.value}")
                # 阶段输出 dict (含可能的 LLM 文本)
                phase_output = exec_fn(inputs, {"run_id": run_id, "ctx": ctx})
                outputs[phase.value] = phase_output
                llm_tokens += int(phase_output.get("llm_tokens", 0) or 0)
            except Exception as exc:  # noqa: BLE001 — 状态机容错
                err = f"{type(exc).__name__}: {exc}"
                self._checkpoints.mark_terminal(
                    run_id, phase, LoopStatus.FAILED, error=err
                )
                phases.append((phase, LoopStatus.FAILED))
                self._fire_hook(phase, LoopStatus.FAILED, {"error": err})
                self._fire_error_hook(phase, err)
                final_status = LoopStatus.FAILED
                final_error = err
                # 异常路径: 把后续所有阶段 (含 COMMIT) 走 SKIPPED 提前写,
                # 然后强制执行一次 COMMIT 阶段让其 SUCCEEDED (R-08 收尾)
                self._mark_skip_remaining_from(run_id, phase, phases)
                self._run_commit_after_failure(
                    run_id, executors, inputs, ctx, phases, outputs
                )
                # 异常: 跳出 for 循环, 不再继续 PHASE_ORDER
                break

            # REFLECT 阶段: 失败 retry 1
            if (
                phase == LoopPhase.REFLECT
                and phase_output.get("status") == "failed"
                and self._settings.reflect_max_retries >= 1
            ):
                # 重试一次, 仍失败 → 终态 partial=True
                try:
                    retry_output = executors[phase](inputs, {"run_id": run_id, "ctx": ctx})
                    outputs[phase.value] = retry_output
                    llm_tokens += int(retry_output.get("llm_tokens", 0) or 0)
                except Exception as exc:  # noqa: BLE001
                    retry_output = {"status": "failed", "error": str(exc)}
                if retry_output.get("status") != "failed":
                    phase_output = retry_output

            # 终态写 checkpoint
            status = self._coerce_status(phase_output.get("status"), phase)
            # PARTIAL 仅在 REFLECT retry 仍失败时出现, 其他阶段都 succeeded/failed
            if (
                phase == LoopPhase.REFLECT
                and status == LoopStatus.FAILED
                and self._settings.reflect_max_retries >= 1
            ):
                status = LoopStatus.PARTIAL
                final_status = LoopStatus.PARTIAL
            elif status == LoopStatus.FAILED and final_status != LoopStatus.PARTIAL:
                final_status = LoopStatus.FAILED
                final_error = phase_output.get("error")

            self._checkpoints.mark_terminal(
                run_id,
                phase,
                status,
                payload={"outputs": phase_output},
                error=phase_output.get("error"),
            )
            phases.append((phase, status))
            self._fire_hook(phase, status, {"outputs": phase_output})

        # 终态聚合
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        metrics: dict[str, Any] = {
            "elapsed_ms": elapsed_ms,
            "phase_count": len(phases),
            "fast_path": fast_path,
        }
        if final_error is not None and final_status == LoopStatus.FAILED:
            metrics["error"] = final_error
        return LoopResult(
            status=final_status,
            outputs=outputs,
            partial=final_status == LoopStatus.PARTIAL,
            error=final_error if final_status == LoopStatus.FAILED else None,
            phases=phases,
            llm_tokens=llm_tokens,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # 阶段执行器 (B1 stub; B2 由 skill_runner 注入真实实现)
    # ------------------------------------------------------------------
    def _executor_intent(self, inputs: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
        """INTENT 阶段 stub — 解析入参, 提取 skill_id + 顶层 key 列表。

        真实 INTENT 由 B2 skill_runner 接管: 解析 input_schema, 校验参数,
        提取 goal 字段; B1 只做最薄一层, 保证状态机本身有内容。
        """
        intent = {
            "skill_id": scope.get("ctx", {}).get("skill_id", ""),
            "goal_keys": sorted([str(k) for k in (inputs or {}).keys()]),
            "raw": inputs,
        }
        return {"status": "succeeded", "intent": intent, "llm_tokens": 0}

    def _executor_plan(self, inputs: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
        """PLAN 阶段 stub — 空 plan; 真实实现 B2 由 skill_runner 接管。

        非 fast_path 必跑, 但 stub 不产生实际计划; skill_runner 会在
        EXECUTE 阶段直接根据 SkillDef.pipeline 跑步骤, 不依赖 PLAN 输出。
        """
        return {"status": "succeeded", "plan": [], "llm_tokens": 0}

    def _executor_execute(
        self, inputs: dict[str, Any], scope: dict[str, Any]
    ) -> dict[str, Any]:
        """EXECUTE 阶段 stub — 空结果; B2 由 skill_runner 注入真实实现。

        ctx.get("executor.execute") 不为 None 时调用方 (B2) 接管, 状态机
        只负责阶段调度。
        """
        custom = scope.get("ctx", {}).get("executor.execute")
        if custom is not None:
            result = custom(inputs, scope)
            result.setdefault("llm_tokens", 0)
            return result
        return {"status": "succeeded", "executed": False, "llm_tokens": 0}

    def _executor_reflect(
        self, inputs: dict[str, Any], scope: dict[str, Any]
    ) -> dict[str, Any]:
        """REFLECT 阶段 stub — 默认 succeeded; B2 由 skill_runner 注入 LLM 评。

        设计纪律: B1 stub 不调 LLM, 也不能因 "execute_out 缺失" 而 fail
        (否则 B1 全链路 happy path 测试都要 mock execute, 无意义).
        默认返回 succeeded + verdict='default_stub_ok'; 真实自评 (C/D 类)
        由 B2 skill_runner 注入 ctx['executor.reflect'] 接管.
        """
        custom = scope.get("ctx", {}).get("executor.reflect")
        if custom is not None:
            result = custom(inputs, scope)
            result.setdefault("llm_tokens", 0)
            return result
        # 默认: stub 模式, 直接 succeeded; B2 真实 LLM 评接管
        return {
            "status": "succeeded",
            "verdict": "default_stub_ok",
            "llm_tokens": 0,
        }

    def _executor_commit(
        self, inputs: dict[str, Any], scope: dict[str, Any]
    ) -> dict[str, Any]:
        """COMMIT 阶段 — 聚合各阶段输出, 标 succeeded (终态由 _run 主循环决定)。"""
        return {
            "status": "succeeded",
            "committed": True,
            "llm_tokens": 0,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _coerce_status(self, raw: Any, phase: LoopPhase) -> LoopStatus:
        """把 phase_output.status 字符串转 LoopStatus; 异常值 → SUCCEEDED。

        防御: stub executor 可能写 "succeeded"/"failed"; 真实 executor 可能
        写出未识别值; 主循环不应被它打断, 容错回退 SUCCEEDED。
        """
        if not isinstance(raw, str):
            return LoopStatus.SUCCEEDED
        try:
            st = LoopStatus(raw)
        except ValueError:
            return LoopStatus.SUCCEEDED
        # 终态强制: pending/running 是中间态, 不可作为阶段终态
        if not is_terminal(st):
            return LoopStatus.SUCCEEDED
        return st

    def _mark_skip_remaining_from(
        self,
        run_id: str,
        failed_phase: LoopPhase,
        phases: list[tuple[LoopPhase, LoopStatus]],
    ) -> None:
        """阶段抛异常时, 把 failed 之后的所有阶段 (含 COMMIT 之前) 标 SKIPPED。

        始终按 PHASE_ORDER 全 5 阶段推进, 不受 fast_path 影响 (历史回放
        必须读 5 行对齐可观察性)。COMMIT 单独由 _run_commit_after_failure
        处理 (SUCCEEDED 收尾), 不在本函数内写。
        """
        try:
            start_idx = PHASE_ORDER.index(failed_phase) + 1
        except ValueError:
            return
        for p in PHASE_ORDER[start_idx:]:
            if p == LoopPhase.COMMIT:
                # COMMIT 由 _run_commit_after_failure 接管, 此处跳过
                continue
            self._checkpoints.mark_terminal(run_id, p, LoopStatus.SKIPPED)
            phases.append((p, LoopStatus.SKIPPED))
            self._fire_hook(p, LoopStatus.SKIPPED, None)

    def _run_commit_after_failure(
        self,
        run_id: str,
        executors: dict,
        inputs: dict,
        ctx: dict,
        phases: list,
        outputs: dict,
    ) -> None:
        """异常路径的 COMMIT 收尾 — 强制 SUCCEEDED, 不调业务 executor。

        业务 COMMIT executor 可能因为 inputs 异常而抛; 收尾 COMMIT 必须
        简单可预测, 直接写 SUCCEEDED + committed=True, 异常时把 final_status
        升级为 FAILED (R-12 fail-loud)。
        """
        self._checkpoints.mark_running(run_id, LoopPhase.COMMIT, payload={"after_failure": True})
        self._fire_hook(LoopPhase.COMMIT, LoopStatus.RUNNING, None)
        try:
            commit_out = self._executor_commit(inputs, {"run_id": run_id, "ctx": ctx})
            self._checkpoints.mark_terminal(
                run_id, LoopPhase.COMMIT, LoopStatus.SUCCEEDED, payload={"outputs": commit_out}
            )
            phases.append((LoopPhase.COMMIT, LoopStatus.SUCCEEDED))
            self._fire_hook(LoopPhase.COMMIT, LoopStatus.SUCCEEDED, {"outputs": commit_out})
            outputs[LoopPhase.COMMIT.value] = commit_out
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            self._checkpoints.mark_terminal(
                run_id, LoopPhase.COMMIT, LoopStatus.FAILED, error=err
            )
            phases.append((LoopPhase.COMMIT, LoopStatus.FAILED))
            self._fire_hook(LoopPhase.COMMIT, LoopStatus.FAILED, {"error": err})
            self._fire_error_hook(LoopPhase.COMMIT, err)

    def _fire_hook(
        self,
        phase: LoopPhase,
        status: LoopStatus,
        payload: dict[str, Any] | None,
    ) -> None:
        """触发 on_phase_change 回调; 异常仅记录, 不影响状态机。"""
        hook = self._hooks.on_phase_change if self._hooks else None
        if hook is None:
            return
        try:
            hook(phase, status, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "agent_loop hook raised",
                extra={"trace_id": "", "phase": phase.value, "error": str(exc)},
            )

    def _fire_error_hook(self, phase: LoopPhase, err: str) -> None:
        """触发 on_error 回调; 同 _fire_hook 异常隔离策略。"""
        hook = self._hooks.on_error if self._hooks else None
        if hook is None:
            return
        try:
            hook(phase, err)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "agent_loop on_error hook raised",
                extra={"trace_id": "", "phase": phase.value, "error": str(exc)},
            )


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------
def recover_stale_checkpoints(
    repo: LoopCheckpointRepo,
    *,
    stale_seconds: float = 60.0,
    now_epoch: float | None = None,
) -> list[tuple[str, LoopPhase]]:
    """进程启动恢复 — 找出 status='running' 且 created_at 早于阈值的行。

    返回 ``[(run_id, phase), ...]``; 调用方按需对每个 (run_id, phase)
    决定续跑起点 (从当前阶段的 successor 重新进入主循环)。
    """
    import time as _t

    now = now_epoch if now_epoch is not None else _t.time()
    rows = repo.find_stale_running()
    import datetime as _dt

    stale: list[tuple[str, LoopPhase]] = []
    for row in rows:
        # created_at 是 "YYYY-MM-DD HH:MM:SS" 形式 (DB localtime); 转 epoch 估算
        try:
            ts = _dt.datetime.strptime(row.created_at or "", "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if (now - ts) > stale_seconds:
            stale.append((row.run_id, row.phase))
    return stale
