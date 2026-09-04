"""agent_loop.state — 阶段枚举 + LoopStatus + LoopResult (v0.8 Phase B B1).

设计纪律 (V0.8_REFACTOR_PLAN.md §5.3 状态机):
- 五阶段顺序固定: intent → plan → execute → reflect → commit
- run_fast 走 2 阶段: intent → execute → commit (A/B 类零 LLM)
- status 六态: pending / running / succeeded / partial / failed / skipped
  pending 仅作为"已声明但未运行"暂态; running 是崩溃恢复的扫描目标;
  succeeded / partial / failed 三态为终态, 不可再迁移;
  skipped 留给 run_fast (REFLECT 跳过)。

模块底部提供 :func:`next_phase` 与 :func:`should_run_phase` 两个纯函数
helper — ``AgentLoop`` 用它们驱动主循环, 单独抽出便于测试覆盖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopPhase(str, Enum):
    """五阶段枚举 — 值与 DB loop_checkpoints.phase CHECK 约束保持一致。

    继承 ``str`` 是为了 JSON 序列化 (None → dataclass.asdict) 与 DB 行
    字段 (sqlite3.Row["phase"]) 直接比对, 不需要再走 ``.value`` 转换。
    """

    INTENT = "intent"
    PLAN = "plan"
    EXECUTE = "execute"
    REFLECT = "reflect"
    COMMIT = "commit"


#: 全阶段顺序 (状态机定义序) — 字符串排序与状态机顺序同序, DB 索引扫描可直读
PHASE_ORDER: tuple[LoopPhase, ...] = (
    LoopPhase.INTENT,
    LoopPhase.PLAN,
    LoopPhase.EXECUTE,
    LoopPhase.REFLECT,
    LoopPhase.COMMIT,
)


#: run_fast 跳过的阶段 (A/B 类零 LLM 直调路径)
_FAST_SKIP_PHASES: frozenset[LoopPhase] = frozenset({LoopPhase.PLAN, LoopPhase.REFLECT})


class LoopStatus(str, Enum):
    """阶段终态 (succeeded / partial / failed / skipped) + 暂态 (pending / running)。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


#: 终态集合 — 不再迁移
_TERMINAL_STATUSES: frozenset[LoopStatus] = frozenset(
    {LoopStatus.SUCCEEDED, LoopStatus.PARTIAL, LoopStatus.FAILED, LoopStatus.SKIPPED}
)


def next_phase(current: LoopPhase, *, fast_path: bool = False) -> LoopPhase | None:
    """给定当前阶段返回下一阶段; 无下一阶段返回 None。

    fast_path=True 时跳 PLAN/REFLECT, 简化状态机用于 A/B 类。
    """
    order = PHASE_ORDER
    if fast_path:
        order = tuple(p for p in order if p not in _FAST_SKIP_PHASES)
    try:
        idx = order.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def should_run_phase(phase: LoopPhase, *, fast_path: bool) -> bool:
    """是否需要真正执行该阶段 (fast_path 下 PLAN/REFLECT 跳过)。"""
    if fast_path and phase in _FAST_SKIP_PHASES:
        return False
    return True


@dataclass
class LoopResult:
    """状态机运行总结果 — 返回给调用方 (skill_runner / API)。

    字段语义:
    - status: 终态 LoopStatus (succeeded / partial / failed; run_fast 不出 partial)
    - outputs: 阶段输出 dict (intent/plan/execute/reflect 累计), commit 后供 skill_runner 取用
    - partial: 显式布尔冗余字段, 让调用方不需 import LoopStatus 也能判断
    - error: 仅在 status=failed 时有值; partial 时为 None (业务可读)
    - phases: 各阶段终态的元组列表, 长度 = 实际跑过的阶段数
    - llm_tokens: 本次 run 累计 LLM token 消耗 (零基, fast_path 恒为 0)
    - metrics: 耗时 (毫秒) + 阶段耗时分解, 透传给 skill_runs.metrics 字段
    """

    status: LoopStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    partial: bool = False
    error: str | None = None
    phases: list[tuple[LoopPhase, LoopStatus]] = field(default_factory=list)
    llm_tokens: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)


def is_terminal(status: LoopStatus) -> bool:
    """终态判定 — 仅供 checkpoint 写入时防御性使用。"""
    return status in _TERMINAL_STATUSES


__all__ = [
    "LoopPhase",
    "LoopResult",
    "LoopStatus",
    "PHASE_ORDER",
    "is_terminal",
    "next_phase",
    "should_run_phase",
]
