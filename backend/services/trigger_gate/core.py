"""trigger-gate 单一入口 — TriggerTicket + TriggerGate (v0.8 Phase A Task A1).

所有 skill / playbook 的触发**必须**经过 ``TriggerGate.submit`` (单一入口):
先过限流 (超限抛 ``ThrottleExceededError``, **不入队**), 再落
``trigger_tickets`` 表持久化。此后由 worker 出队泵消费 (worker.py),
API / scheduler / 事件桥都只做生产者, 不直接执行。

submit 的编排顺序 (顺序即契约):
    1. 参数校验 (source / target_type / priority) — 非法值连限流配额都不消耗
    2. throttle.acquire(user_id) — 双层令牌桶, 拒绝时票据不落库
    3. queue.enqueue(ticket) — 持久化, status='pending'

ticket_id 格式: ``tg-`` + uuid4 hex 前 12 位 (短且进程间不冲突,
排查日志时肉眼可辨)。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from backend.logging_config import logger
from backend.services.trigger_gate.priority import Priority
from backend.services.trigger_gate.queue import TriggerQueue
from backend.services.trigger_gate.throttle import ThrottleExceededError, TriggerThrottle

# submit 允许的触发来源 — Literal 在签名层给静态检查, 元组在运行时强校验
VALID_SOURCES: tuple[str, ...] = (
    "manual",
    "cron",
    "webhook",
    "kl_event",
    "collector_event",
)
SourceName = Literal["manual", "cron", "webhook", "kl_event", "collector_event"]

VALID_TARGET_TYPES: tuple[str, ...] = ("skill", "playbook")


@dataclass
class TriggerTicket:
    """一条触发票据 — trigger_tickets 表的内存投影。

    inputs 为 dict (队列层负责 JSON 序列化/反序列化);
    priority 用 int (Priority 是 IntEnum, 两者互通)。
    """

    ticket_id: str
    target_type: str
    target_id: str
    priority: int = Priority.NORMAL
    source: str = "manual"
    user_id: str | None = None
    inputs: dict[str, Any] | None = None
    status: str = "pending"
    attempts: int = 0
    enqueued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class TriggerGate:
    """触发单一入口 — 限流 + 入队编排 (不含执行, 执行在 worker)。

    throttle / queue 均可注入 (测试用小桶限流或替换队列实现);
    默认按生产参数构造 (per-user 60/min, global 600/min)。
    """

    def __init__(
        self,
        throttle: TriggerThrottle | None = None,
        queue: TriggerQueue | None = None,
    ) -> None:
        self._throttle = throttle or TriggerThrottle()
        self._queue = queue or TriggerQueue()

    def submit(
        self,
        target_type: Literal["skill", "playbook"],
        target_id: str,
        *,
        inputs: dict[str, Any] | None = None,
        priority: Priority = Priority.NORMAL,
        source: SourceName,
        user_id: str | None = None,
    ) -> TriggerTicket:
        """提交一次触发: 校验 → 限流 → 持久化入队, 返回 pending 票据。

        Raises:
            ValueError: source / target_type / priority 非法。
            ThrottleExceededError: 限流超限 (票据不落库, API 层映射 429)。
        """
        if source not in VALID_SOURCES:
            raise ValueError(
                f"invalid source {source!r}: must be one of {VALID_SOURCES}"
            )
        if target_type not in VALID_TARGET_TYPES:
            raise ValueError(
                f"invalid target_type {target_type!r}: must be one of {VALID_TARGET_TYPES}"
            )
        if int(priority) not in (Priority.REALTIME, Priority.NORMAL, Priority.BATCH):
            raise ValueError(f"invalid priority {priority!r}: must be 0/1/2")

        # 限流在前: 超限直接抛出, 绝不落库
        self._throttle.acquire(user_id)

        ticket = TriggerTicket(
            ticket_id=f"tg-{uuid.uuid4().hex[:12]}",
            target_type=target_type,
            target_id=target_id,
            priority=int(priority),
            source=source,
            user_id=user_id,
            inputs=inputs,
        )
        self._queue.enqueue(ticket)
        logger.info(
            "trigger ticket submitted",
            extra={
                "trace_id": "",
                "ticket_id": ticket.ticket_id,
                "target_type": target_type,
                "target_id": target_id,
                "priority": int(priority),
                "source": source,
            },
        )
        return ticket


__all__ = ["SourceName", "TriggerGate", "TriggerTicket", "VALID_SOURCES", "VALID_TARGET_TYPES"]
