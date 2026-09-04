"""trigger_gate.triggers.collector_event — collector 失败/超时事件触发源 (D1).

监听 collector 失败/超时事件, 把"信源健康扫描" skill 送入 trigger 队列
—— 联动验证 (Phase D 验收条件)。三种 status:
- success  → 不主动触发 (健康, 不浪费限流配额)
- failed   → 触发, 优先级 NORMAL (及时排查)
- timeout  → 触发, 优先级 REALTIME (网络/服务异常)

约定:
- collector_name 必为非空 str (R12)
- status ∈ {success, failed, timeout} (R8 完整覆盖)
- target_id 默认 = ``source-health-scan`` (A2b builtin)
- success 走早返回, 不调 trigger_gate.submit (R6: 不浪费 60/min 配额)
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.services.trigger_gate import trigger_gate
from backend.services.trigger_gate.priority import Priority

__all__ = [
    "CollectorEventTrigger",
    "InvalidCollectorStatusError",
    "submit_collector_event",
]

VALID_COLLECTOR_STATUSES: tuple[str, ...] = ("success", "failed", "timeout")
DEFAULT_COLLECTOR_TARGET_ID = "source-health-scan"


class InvalidCollectorStatusError(ValueError):
    """collector 事件 status 非法."""


class CollectorEventTrigger:
    """collector 完成事件触发器."""

    def submit(
        self,
        collector_name: str,
        status: str,
        *,
        error: str | None = None,
        target_id: str = DEFAULT_COLLECTOR_TARGET_ID,
        user_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Any | None:
        """提交 collector 事件 → 信源健康扫描 skill (默认).

        Args:
            collector_name: collector 名 (e.g. ``ai_security_collector``)
            status: success / failed / timeout
            error: 失败时的错误消息 (可选)
            target_id: 目标 skill id (默认 source-health-scan)
            user_id: 触发用户 (限流用)
            extra: 透传额外参数 (duration_ms / items_count)

        Returns:
            ``TriggerTicket`` (pending) 或 None (success 早返回)
        """
        if not collector_name or not isinstance(collector_name, str):
            raise InvalidCollectorStatusError("collector_name 必为非空 str")
        if status not in VALID_COLLECTOR_STATUSES:
            raise InvalidCollectorStatusError(
                f"collector status {status!r} 非法, 仅允许 {VALID_COLLECTOR_STATUSES}"
            )

        # success 不触发 (R6 不浪费限流配额; 健康常态无需 skill 干预)
        if status == "success":
            logger.debug(
                "collector_event success ignored (no skill trigger)",
                extra={"trace_id": "", "collector": collector_name},
            )
            return None

        # failed = NORMAL, timeout = REALTIME (网络/服务异常更紧急)
        priority = Priority.REALTIME if status == "timeout" else Priority.NORMAL

        inputs = {
            "collector": collector_name,
            "status": status,
            "error": error,
            "extra": extra or {},
        }
        ticket = trigger_gate.submit(
            target_type="skill",
            target_id=target_id,
            inputs=inputs,
            priority=priority,
            source="collector_event",
            user_id=user_id,
        )
        logger.info(
            "collector_event trigger submitted",
            extra={
                "trace_id": "",
                "ticket_id": ticket.ticket_id,
                "collector": collector_name,
                "status": status,
                "priority": int(priority),
                "target_id": target_id,
            },
        )
        return ticket


_default = CollectorEventTrigger()


def submit_collector_event(
    collector_name: str,
    status: str,
    *,
    error: str | None = None,
    target_id: str = DEFAULT_COLLECTOR_TARGET_ID,
    user_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Any | None:
    return _default.submit(
        collector_name,
        status,
        error=error,
        target_id=target_id,
        user_id=user_id,
        extra=extra,
    )