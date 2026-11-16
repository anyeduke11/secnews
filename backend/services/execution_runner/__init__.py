"""pi 执行体 (v0.8.9 P4) — 确定性 argv 执行 + L4 逐条落账 + 终态回写 (C4-3)。"""
from backend.services.execution_runner.runner import (
    CommandResult,
    ExecutionResult,
    ExecutorDisabledError,
    execute_and_settle,
    execute_plan,
)

__all__ = [
    "CommandResult",
    "ExecutionResult",
    "ExecutorDisabledError",
    "execute_and_settle",
    "execute_plan",
]