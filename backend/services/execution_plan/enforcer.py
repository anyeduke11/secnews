"""Enforce 编译器 — 审批快照 → 进程级约束 (L2/L4 边界, v0.8.9 P4 R-3)。

职责只有一个: 把「已审批的 ExecutionPlan」编译成执行体可逐条比对的
``EnforcementSpec``, 并在任何越界点上抛 ``BoundaryViolation`` (带原因码)。
绝不 fail-open — L1 默认拒绝语义在进程层的对应物。

- L2 进程层: workspace 锁定根 (复用 ``agent_bridge.resolve_workspace`` 的
  ``codegarden/<project>/`` 语义) + argv 双重校验 (静态白名单 ∩ plan 动态
  子集, P0-A 白名单只收紧不放松) + 网络默认全禁 + 双超时。
- L4 审计层: 本 spec 的 ``boundary_hash`` / ``argv_set`` 是执行体落
  agent_runs 与逐条比对的唯一依据。

网络口径 (不夸大): L2 只做 **env 级** 隔离 (剥离凭据/代理变量 + 注入 plan
放行清单)。出站真实阻断归 L3 sandbox-exec per-plan profile (P5/R-4)。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.services.agent_bridge import resolve_workspace
from backend.services.dsh.supervisor import DshCommandNotAllowedError, validate_command_argv
from backend.services.execution_plan.schema import ExecutionPlan
from backend.services.execution_plan.service import boundary_hash

# env 级隔离: 含这些片段的环境变量不下传给执行进程 (llm_secrets 红线)
_SECRET_ENV_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
_PROXY_ENV_KEYS = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
})


class BoundaryViolation(RuntimeError):
    """越界 (原因码 + 人读消息)。执行体必须转 run failed + 告警, 不得吞。"""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.message = message


@dataclass(frozen=True)
class EnforcementSpec:
    """一条已审批 plan 编译出的进程约束 (执行体唯一放行依据)。"""

    run_id: str
    boundary_hash: str
    workspace: str
    commands: tuple[tuple[str, ...], ...]
    argv_set: frozenset[tuple[str, ...]]
    writable_paths: tuple[str, ...]
    readable_paths: tuple[str, ...]
    network: tuple[str, ...]
    command_timeout_sec: int
    total_timeout_sec: int

    @property
    def network_open(self) -> bool:
        return bool(self.network)

    # -- L2: argv 双重校验 ------------------------------------------------
    def check_command(self, argv: list[str]) -> tuple[str, ...]:
        """静态白名单 (P0-A) ∩ plan.commands 动态子集 (更严不放松)。"""
        if not argv:
            raise BoundaryViolation("E_ARGV_NOT_IN_PLAN", "空 argv 不在任何审批 plan 内")
        try:
            validate_command_argv(list(argv))
        except DshCommandNotAllowedError as e:
            raise BoundaryViolation("E_ARGV_NOT_ALLOWED", str(e)) from e
        key = tuple(argv)
        if key not in self.argv_set:
            raise BoundaryViolation(
                "E_ARGV_NOT_IN_PLAN",
                f"argv 未列入审批 plan: {list(argv)} (plan 仅批准 {len(self.argv_set)} 条)",
            )
        return key

    # -- 双超时 -----------------------------------------------------------
    def remaining_seconds(self, started_monotonic: float) -> float:
        """总预算剩余秒 (<0 = 已耗尽, 执行体须终止并标 timed_out)。"""
        return self.total_timeout_sec - (time.monotonic() - started_monotonic)

    # -- 网络 env 隔离 ----------------------------------------------------
    def build_env(self, base: dict[str, str] | None = None) -> dict[str, str]:
        src = dict(os.environ if base is None else base)
        env = {
            k: v for k, v in src.items()
            if k not in _PROXY_ENV_KEYS and not _is_secret_key(k)
        }
        env["HOTSPOT_EXEC_BOUNDARY_HASH"] = self.boundary_hash
        env["HOTSPOT_EXEC_NETWORK"] = ",".join(self.network)
        return env


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in _SECRET_ENV_MARKERS)


def _check_paths(paths: list[str], field_name: str) -> tuple[str, ...]:
    """writable/readable 必须相对 workspace 锁定根 (禁绝对路径与 ..)。"""
    for p in paths:
        parts = Path(p).parts
        if Path(p).is_absolute() or ".." in parts:
            raise BoundaryViolation(
                "E_PATH_OUTSIDE_WORKSPACE",
                f"{field_name} 含越界路径 {p!r} (只允许 workspace 内相对路径)",
            )
    return tuple(paths)


def compile_enforcement(
    envelope: dict[str, Any],
    *,
    run_id: str,
    workspace: str | None,
    expected_hash: str | None = None,
) -> EnforcementSpec:
    """审批信封 → EnforcementSpec。未 approved / 篡改 / 越界路径一律抛。"""
    if not envelope or envelope.get("status") != "approved":
        raise BoundaryViolation(
            "E_PLAN_NOT_APPROVED",
            f"run {run_id} 无 approved plan (status={(envelope or {}).get('status')}); 默认拒绝",
        )
    try:
        plan = ExecutionPlan.model_validate(envelope["plan"])
    except ValidationError as e:
        raise BoundaryViolation("E_PLAN_INVALID", f"plan 载荷校验失败: {e.errors()[:3]}") from e

    # L4 完整性: 审批快照落库后不得再被改 (boundary_hash 重算比对)
    actual_hash = boundary_hash(plan)
    if expected_hash is not None and actual_hash != expected_hash:
        raise BoundaryViolation(
            "E_BOUNDARY_HASH_MISMATCH",
            f"plan 载荷指纹 {actual_hash[:16]}… 与审批快照 {expected_hash[:16]}… 不符",
        )

    try:
        ws = resolve_workspace(workspace)
    except ValueError as e:
        raise BoundaryViolation("E_WORKSPACE_INVALID", str(e)) from e
    if ws is None:
        raise BoundaryViolation(
            "E_WORKSPACE_INVALID", "执行必须落在 codegarden/<project>/ 锁定根内")

    return EnforcementSpec(
        run_id=run_id,
        boundary_hash=actual_hash,
        workspace=ws,
        commands=tuple(tuple(argv) for argv in plan.commands),
        argv_set=frozenset(tuple(argv) for argv in plan.commands),
        writable_paths=_check_paths(plan.writable_paths, "writable_paths"),
        readable_paths=_check_paths(plan.readable_paths, "readable_paths"),
        network=tuple(plan.network),
        command_timeout_sec=plan.command_timeout_sec,
        total_timeout_sec=plan.total_timeout_sec,
    )


__all__ = ["BoundaryViolation", "EnforcementSpec", "compile_enforcement"]