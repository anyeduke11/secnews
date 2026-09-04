"""trigger_gate — v0.8 Phase A (Task A1) 触发单一入口包。

模块分层:
- ``priority.py`` — 三档优先级 (REALTIME/NORMAL/BATCH, IntEnum)
- ``throttle.py`` — 双层令牌桶限流 (per-user 60/min + global 600/min)
- ``queue.py``    — trigger_tickets 持久化队列 (原子出队 + 崩溃恢复)
- ``core.py``     — TriggerTicket + TriggerGate (submit 编排: 校验 → 限流 → 入队)
- ``worker.py``   — 进程内出队泵 (非抢占, max_running 并发信号量)

对外契约: 一切 skill / playbook 触发走 ``trigger_gate.submit()``
(模块级单例), 限流超限抛 ``ThrottleExceededError`` (API 层映射 429);
执行侧由 ``TriggerWorker`` 消费, 后续任务接线 scheduler。
"""
from __future__ import annotations

from backend.services.trigger_gate.core import (
    SourceName,
    TriggerGate,
    TriggerTicket,
    VALID_SOURCES,
    VALID_TARGET_TYPES,
)
from backend.services.trigger_gate.priority import PRIORITY_NAMES, Priority
from backend.services.trigger_gate.queue import TriggerQueue
from backend.services.trigger_gate.throttle import ThrottleExceededError, TriggerThrottle
from backend.services.trigger_gate.worker import Handler, TriggerWorker

# 模块级单例 — 沿用仓库惯例 (ai_hub / dsh 同款):
# 与单进程应用生命周期一致, 提交侧一律 ``from backend.services.trigger_gate import trigger_gate``
trigger_gate = TriggerGate()

__all__ = [
    "Handler",
    "PRIORITY_NAMES",
    "Priority",
    "SourceName",
    "ThrottleExceededError",
    "TriggerGate",
    "TriggerQueue",
    "TriggerTicket",
    "TriggerThrottle",
    "TriggerWorker",
    "VALID_SOURCES",
    "VALID_TARGET_TYPES",
    "trigger_gate",
]
