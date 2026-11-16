"""pi 执行体 — 已审批 plan 的确定性 argv 执行 (v0.8.9 P4, R-3)。

派发形态裁决 (**偏差注②**, 见 `V0.8.9_IMPLEMENTATION_PLAN.md` §5 C4-2):
命令集合 = ``plan.commands`` (审批期即冻结), 执行体逐条 subprocess 执行并在
每条之前经 enforcer 前置校验。不把 LLM 放进确定性执行路径: D3 的
``agent_bridge`` jsonl 派发让 pi 在运行时自行生成命令, 无法前置拦截, 与 L2/L4
及 C4-4 越界演练验收直接冲突; 若确需 pi 参与, 把 ``pi --mode json ...`` 作为
plan 的一条 argv 显式审批即可 — 走同一校验路径。

红线 (P10 §7, 不可协商): 无 ``shell=True`` / 无交互式 stdin / cwd 锁
``codegarden/<project>/`` / env 不含凭据与代理 / 网络默认全禁 (env 级声明,
真实出站阻断归 L3 sandbox-exec, P5/R-4) / 不经 ai_hub。

L4 审计: 每命令一行 ``agent_runs`` (``result_excerpt``=stdout 尾 500 字,
``error``=rc + stderr 尾); 完整 stdout 由 C4-3 的 Artifact content_ref 承接。

终态回写 (C4-3): ``execute_and_settle`` = ``execute_plan`` + 产物登记 +
``RunService.finish``。状态机 / RA-9 / v1_run 事件 (四段指挥台 Run 段实时流)
全部复用 RunService 既有出口, 本模块不自建状态机。
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import config
from backend.logging_config import logger
from backend.observability_records import finish_agent_run, start_agent_run
from backend.services.execution_plan.enforcer import BoundaryViolation, compile_enforcement

_EXCERPT_CHARS = 500
_AGENT_NAME = "pi-executor"


class ExecutorDisabledError(RuntimeError):
    """执行体开关关闭 (默认态) — run 保持不推进, 由人工回执或开启开关后重试。"""


@dataclass
class CommandResult:
    """单条 argv 的执行留痕 (L4)。"""

    argv: tuple[str, ...]
    exit_code: int | None
    duration_ms: int
    stdout: str = ""          # 全量 (C4-3 产物原料); L4 仅落尾 500 字
    stderr_tail: str = ""
    timed_out: bool = False

    @property
    def stdout_tail(self) -> str:
        return _tail(self.stdout)


@dataclass
class ExecutionResult:
    """一次 plan 执行的整体结果 (C4-3 据此做终态回写)。"""

    ok: bool
    commands: list[CommandResult] = field(default_factory=list)
    reason_code: str | None = None
    error: str | None = None
    duration_ms: int = 0
    boundary_hash: str = ""

    @property
    def stdout(self) -> str:
        """末条命令的完整 stdout — 产物登记原料 (C4-3)。"""
        return self.commands[-1].stdout if self.commands else ""


def _tail(text: str | None, limit: int = _EXCERPT_CHARS) -> str:
    return (text or "").strip()[-limit:]


def _run_one(argv: list[str], *, cwd: str, env: dict[str, str], timeout: float) -> CommandResult:
    """执行单条 argv (shell=False 隐式: 传 list), 不喂 stdin。"""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=max(timeout, 0.1),
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            argv=tuple(argv), exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            stdout=e.stdout if isinstance(e.stdout, str) else "",
            timed_out=True,
        )
    except OSError as e:
        return CommandResult(
            argv=tuple(argv), exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            stderr_tail=_tail(f"spawn failed: {e}"),
        )
    return CommandResult(
        argv=tuple(argv),
        exit_code=proc.returncode,
        duration_ms=round((time.monotonic() - started) * 1000),
        stdout=proc.stdout or "",
        stderr_tail=_tail(proc.stderr),
    )


def execute_plan(
    run_id: str,
    envelope: dict[str, Any],
    *,
    workspace: str | None,
    expected_hash: str | None = None,
) -> ExecutionResult:
    """在审批边界内逐条执行 plan.commands。越界 / 超时 / 非零退出即停。

    越界 (``BoundaryViolation``) 不吞: 转 ``ExecutionResult(ok=False,
    reason_code=<原因码>)`` 并保留已执行命令的留痕 — 调用方按 failed 收口。
    """
    if not config.pi_executor_enabled:
        raise ExecutorDisabledError(
            "pi 执行体未启用 (config.pi_executor_enabled=false, 默认关)")

    started = time.monotonic()
    try:
        spec = compile_enforcement(
            envelope, run_id=run_id, workspace=workspace, expected_hash=expected_hash)
    except BoundaryViolation as e:
        logger.warning("run {} plan 编译越界: {}", run_id, e)
        return ExecutionResult(
            ok=False, reason_code=e.reason_code, error=e.message,
            duration_ms=round((time.monotonic() - started) * 1000),
            boundary_hash=(envelope or {}).get("boundary_hash") or "",
        )

    env = spec.build_env()
    commands: list[CommandResult] = []
    for argv in spec.commands:
        remaining = spec.remaining_seconds(started)
        if remaining <= 0:
            return ExecutionResult(
                ok=False, commands=commands, reason_code="E_TOTAL_TIMEOUT",
                error=f"总预算 {spec.total_timeout_sec}s 耗尽",
                duration_ms=round((time.monotonic() - started) * 1000),
                boundary_hash=spec.boundary_hash,
            )
        try:
            spec.check_command(list(argv))
        except BoundaryViolation as e:
            logger.warning("run {} 越界: {}", run_id, e)
            return ExecutionResult(
                ok=False, commands=commands, reason_code=e.reason_code, error=e.message,
                duration_ms=round((time.monotonic() - started) * 1000),
                boundary_hash=spec.boundary_hash,
            )

        rowid = start_agent_run(
            agent=_AGENT_NAME, protocol="argv",
            task_kind=f"run:{run_id}", trigger_source="executor",
        )
        result = _run_one(
            list(argv), cwd=spec.workspace, env=env,
            timeout=min(spec.command_timeout_sec, remaining),
        )
        commands.append(result)
        finish_agent_run(
            rowid,
            ok=(result.exit_code == 0),
            duration_ms=result.duration_ms,
            result_excerpt=result.stdout_tail or None,
            error=(
                None if result.exit_code == 0 else
                f"timeout>{spec.command_timeout_sec}s" if result.timed_out else
                f"rc={result.exit_code}: {result.stderr_tail}"
            ),
        )
        if result.timed_out:
            return ExecutionResult(
                ok=False, commands=commands, reason_code="E_COMMAND_TIMEOUT",
                error=f"命令超时 >{spec.command_timeout_sec}s: {list(result.argv)}",
                duration_ms=round((time.monotonic() - started) * 1000),
                boundary_hash=spec.boundary_hash,
            )
        if result.exit_code != 0:
            return ExecutionResult(
                ok=False, commands=commands, reason_code="E_COMMAND_FAILED",
                error=f"rc={result.exit_code}: {result.stderr_tail}",
                duration_ms=round((time.monotonic() - started) * 1000),
                boundary_hash=spec.boundary_hash,
            )

    return ExecutionResult(
        ok=True, commands=commands,
        duration_ms=round((time.monotonic() - started) * 1000),
        boundary_hash=spec.boundary_hash,
    )


def _materialize_artifact(run_id: str, envelope: dict[str, Any], content: str) -> dict[str, Any]:
    """末条命令完整 stdout 落盘 → 登记 artifact (R08: 落盘 hash 与 content 一致)。"""
    from pathlib import Path

    from backend.services.artifact_service import ArtifactService

    spec = (envelope.get("plan") or {}).get("output_artifact") or {}
    kind = spec.get("kind") or "report"
    fmt = "md" if kind == "report" else "txt"
    out_dir = Path(config.data_dir) / "run_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    content_ref = out_dir / f"{run_id}.{fmt}"
    content_ref.write_text(content, encoding="utf-8")
    return ArtifactService().create(
        run_id=run_id, kind=kind, format=fmt,
        title=(spec.get("title") or f"run {run_id} 产物")[:200],
        content=content, content_ref=str(content_ref),
    )


def execute_and_settle(
    run_id: str,
    envelope: dict[str, Any],
    *,
    workspace: str | None,
    expected_hash: str | None = None,
) -> ExecutionResult:
    """执行 + 产物登记 + 终态回写 (C4-3)。

    前置: run 已 ``claim(executor='pi')`` → ``start()`` (running)。终态统一走
    ``RunService.finish`` — RA-9 (done 必已有 ≥1 artifact)、失败必填 error、
    artifact_ids 实表回填、``v1_run`` 事件 (四段指挥台 Run 段实时流) 均复用
    该出口, 本函数不自建状态机。

    outcome 映射: ok → done; E_COMMAND_TIMEOUT / E_TOTAL_TIMEOUT → timeout;
    其余 (含越界拦截) → failed。ok 但 stdout 为空 → 无法登记 plan 声明的
    ``output_artifact``, 按 E_ARTIFACT_EMPTY 收口为 failed (不造空产物蒙混)。
    """
    result = execute_plan(run_id, envelope, workspace=workspace, expected_hash=expected_hash)
    from backend.services.run_service import RunService

    runs = RunService()
    if result.ok:
        content = result.stdout
        if not content.strip():
            result.ok = False
            result.reason_code = "E_ARTIFACT_EMPTY"
            result.error = "plan 声明 output_artifact 但末条命令 stdout 为空"
        else:
            _materialize_artifact(run_id, envelope, content)
            runs.finish(run_id, outcome="done", result_excerpt=content[:_EXCERPT_CHARS])
            return result

    outcome = (
        "timeout" if result.reason_code in ("E_COMMAND_TIMEOUT", "E_TOTAL_TIMEOUT")
        else "failed"
    )
    runs.finish(run_id, outcome=outcome, error=f"{result.reason_code}: {result.error}")
    return result


__all__ = [
    "CommandResult", "ExecutionResult", "ExecutorDisabledError",
    "execute_and_settle", "execute_plan",
]