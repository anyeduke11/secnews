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

L3 系统层 (P5/R-4): 本模块把 P4 的「声明级」边界落到系统层 ——
``sandbox-exec`` per-plan profile (文件读写隔离 + 凭据禁读 + 出网全禁)
与 ulimit (CPU/文件大小/文件数)。L3 不可用 (非 macOS) 时降级为「仅 ulimit」
并在 L4 留痕说明, 不静默假装有沙箱。

L4 审计: 每命令一行 ``agent_runs`` (``result_excerpt``=stdout 尾 500 字,
``error``=rc + stderr 尾); 完整 stdout 由 C4-3 的 Artifact content_ref 承接。

终态回写 (C4-3): ``execute_and_settle`` = ``execute_plan`` + 产物登记 +
``RunService.finish``。状态机 / RA-9 / v1_run 事件 (四段指挥台 Run 段实时流)
全部复用 RunService 既有出口, 本模块不自建状态机。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import config
from backend.logging_config import logger
from backend.observability_records import finish_agent_run, start_agent_run
from backend.services.execution_plan.enforcer import BoundaryViolation, compile_enforcement
from backend.services.execution_runner.sandbox import (
    SandboxSpec,
    describe_limits,
    ensure_writable_dirs,
    run_with_limits,
    sandbox_supported,
)

_EXCERPT_CHARS = 500
_AGENT_NAME = "pi-executor"
_BOUNDARY_ALERT_METRIC = "executor.boundary_violation"

# CPU 限额的信号投递宽限 (秒) — wall timeout 比 CPU 限额多给这么多。
# 理由: RLIMIT_CPU 超限时内核发 SIGXCPU, 进程需时间接收并退出; 若 wall
# timeout 与 CPU 限额同值, 超时总是先到 → 内核限额**永远不生效** (形同虚设)。
# 总预算 (total_timeout_sec) 仍是硬上限, 不被此宽限放大。
_CPU_SIGNAL_GRACE_SECONDS = 2

# 系统层拒绝的特征 (Seatbelt / ulimit): 与「命令自己失败」区分开 ——
# 前者是越界 (要告警), 后者只是命令非零退出 (不告警, 否则告警会被噪声淹没)。
_SYSTEM_DENY_MARKERS = (
    "Operation not permitted",   # Seatbelt file-read*/file-write* 拒绝
    "Permission denied",         # POSIX 权限拒绝
    "File too large",            # RLIMIT_FSIZE 越限
)



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


def _run_one(
    argv: list[str], *, cwd: str, env: dict[str, str], timeout: float,
    sandbox: SandboxSpec | None = None,
) -> CommandResult:
    """执行单条 argv (shell=False 隐式: 传 list), 不喂 stdin。

    L3 (P5): 有 sandbox spec → 经 sandbox-exec + ulimit 执行 (系统层隔离);
    无 (非 macOS) → 退回纯 subprocess, 由调用方在 L4 留痕说明降级。
    """
    started = time.monotonic()
    try:
        if sandbox is not None:
            proc = run_with_limits(
                list(argv),
                sandbox,
                capture_output=True,
                text=True,
                timeout=max(timeout, 0.1),
                cwd=cwd,
                env=env,
            )
        else:
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


def _fire_boundary_alert(
    *,
    run_id: str,
    reason_code: str,
    message: str,
    layer: str,
    argv: tuple[str, ...] | None = None,
) -> None:
    """越界告警 — L3/L4 层的可见性出口 (PRD R-4 ③)。

    写 ``observability_alerts`` (metric=``executor.boundary_violation``) +
    SSE breach + 渠道投递。告警自身失败只 log — 越界事实另由 run.error 与
    ``agent_runs`` 承载, 告警是附加可见性而非唯一真相来源。
    """
    try:
        from backend.services.observability_alert_service import fire_alert_sync

        fire_alert_sync(
            metric=_BOUNDARY_ALERT_METRIC,
            level="critical",
            value=1.0,
            threshold=1.0,
            detail={
                "run_id": run_id,
                "reason_code": reason_code,
                "layer": layer,
                "message": message[:400],
                "argv": list(argv or ()),
            },
            source="execution_runner",
            window_minutes=60,
            cooldown_minutes=1,
            # 按 run 去重: 同一 run 的重复越界合并, 跨 run 的真实越界各自可见
            # (全局 cooldown 会吞掉跨 run 越界 — 演练④ 实测 6 次越界只落 1 条)。
            dedupe_key=run_id,
        )
    except Exception as e:  # pragma: no cover — 告警链路不抛 (fail-open)
        logger.warning(f"boundary alert failed for run {run_id}: {e}")


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

    L3 (P5/R-4): 每条命令经 ``sandbox-exec`` per-plan profile + ulimit 执行 —
    文件读写隔离 / 凭据禁读 / 出网全禁落到系统层, 而非仅声明层。越界事实
    (L2 前置拦截 或 L3 系统层拦截) 同时触发 ``executor.boundary_violation``
    告警 (observability_alerts + SSE + 渠道投递)。
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
        _fire_boundary_alert(
            run_id=run_id, reason_code=e.reason_code, message=e.message, layer="L2-plan")
        return ExecutionResult(
            ok=False, reason_code=e.reason_code, error=e.message,
            duration_ms=round((time.monotonic() - started) * 1000),
            boundary_hash=(envelope or {}).get("boundary_hash") or "",
        )

    sandbox = _build_sandbox(spec)
    # L4 留痕: 本 run 实际生效的系统层约束 (可复现边界)。降级时也留痕 —
    # 明确标记 sandbox 不可用, 不静默按无约束执行。
    from backend.observability_records import record_audit

    if sandbox is None:
        degraded = _empty_sandbox_spec(spec)
        logger.warning(
            "run {} L3 降级: sandbox-exec 不可用 (platform={}), 仅 ulimit 生效",
            run_id, describe_limits(degraded, sandbox="unavailable")["platform"])
        record_audit(
            "executor", "executor.sandbox", target=run_id,
            detail=describe_limits(degraded, sandbox="unavailable"),
        )
    else:
        record_audit(
            "executor", "executor.sandbox", target=run_id,
            detail=describe_limits(sandbox, sandbox="sandbox-exec"),
        )
        ensure_writable_dirs(sandbox)

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
            _fire_boundary_alert(
                run_id=run_id, reason_code=e.reason_code, message=e.message,
                layer="L2-argv", argv=tuple(argv))
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
            # wall timeout 比 CPU 限额多给信号投递宽限 (见 _CPU_SIGNAL_GRACE_SECONDS):
            # 否则 wall 超时总是先到, 内核 RLIMIT_CPU 永远不触发。
            # 总预算 remaining 仍是硬上限 (min 取严)。
            timeout=min(spec.command_timeout_sec + _CPU_SIGNAL_GRACE_SECONDS, remaining),
            sandbox=sandbox,
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
            if _is_system_denial(result):
                _fire_boundary_alert(
                    run_id=run_id, reason_code="E_COMMAND_FAILED",
                    message=f"rc={result.exit_code}: {result.stderr_tail}",
                    layer="L3-sandbox", argv=tuple(argv))
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


def _is_system_denial(result: CommandResult) -> bool:
    """判定失败是否来自**系统层拒绝** (Seatbelt / ulimit) 而非命令自身错误。

    只有系统层拒绝才是「越界」, 才发 boundary_violation 告警; 普通非零
    退出 (如命令写错) 不告警 — 否则告警被噪声淹没, 反而看不见真越界。
    """
    return any(marker in result.stderr_tail for marker in _SYSTEM_DENY_MARKERS)


def _empty_sandbox_spec(spec) -> SandboxSpec:
    """降级路径用的空约束 spec (仅用于描述平台, 不实际执行)。"""
    return SandboxSpec(
        workspace=spec.workspace,
        writable_paths=spec.writable_paths,
        readable_paths=spec.readable_paths,
        network=spec.network,
        max_cpu_seconds=spec.command_timeout_sec,
    )


def _build_sandbox(spec) -> SandboxSpec | None:
    """由 EnforcementSpec 编译 L3 约束集 (非 macOS → None = 降级)。"""
    if not sandbox_supported():
        return None
    return SandboxSpec(
        workspace=spec.workspace,
        writable_paths=spec.writable_paths,
        readable_paths=spec.readable_paths,
        network=spec.network,
        max_cpu_seconds=spec.command_timeout_sec,
        repo_root=_repo_root(),
        extra_allow_read=_interpreter_paths(),
    )


def _interpreter_paths() -> tuple[str, ...]:
    """Python 解释器自身路径 — 沙箱内必须可读, 否则 execvp 失败。

    launcher 与被执行的 argv 通常都用同一个解释器 (venv 常在仓库内, 会被
    仓库级 deny 挡住)。返回字面路径 + realpath 两条 (symlink 两端都要)。
    """
    exe = sys.executable
    if not exe:
        return ()
    return (exe, os.path.realpath(exe))


def _repo_root() -> str | None:
    """仓库根 (凭据载体所在处) — 沙箱内整体禁读。

    workspace 锁定根是 ``codegarden/<project>/`` (相对 CWD), 故仓库根 = CWD。
    CWD 非仓库根时 (如测试的 tmp_path) 返回 None — 不做仓库级收窄, 只靠
    凭据载体 deny, 避免误伤。
    """
    cwd = os.getcwd()
    if not (Path(cwd) / "backend").is_dir() or not (Path(cwd) / "AGENTS.md").exists():
        return None
    return cwd


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