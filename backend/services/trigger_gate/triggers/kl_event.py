"""trigger_gate.triggers.kl_event — KL T1-T5 完成事件触发源 (D1).

KL (Knowledge Lifecycle) 五阶段: T1 raw→refine / T2 refine→link /
T3 link→structure / T4 structure→publish / T5 publish→refine (rollback).
本模块监听 stage 完成事件, 把"质量巡检" skill 送入 trigger 队列 ——
联动验证 (Phase D 验收条件)。

约定:
- stage ∈ {T1, T2, T3, T4, T5} 全部合法 (R8 完整覆盖)
- item_id 必为非空 str (R12)
- target_id 默认 = ``quality-patrol`` skill id (Phase A A2b 登记的 builtin)
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.services.trigger_gate import trigger_gate

__all__ = ["InvalidKLEventError", "KLEventTrigger", "submit_kl_event"]

VALID_KL_STAGES: tuple[str, ...] = ("T1", "T2", "T3", "T4", "T5")
DEFAULT_KL_TARGET_ID = "quality-patrol"


class InvalidKLEventError(ValueError):
    """KL 事件参数非法 (stage / item_id)."""


class KLEventTrigger:
    """KL 阶段完成事件触发器."""

    def submit(
        self,
        stage: str,
        item_id: str,
        *,
        target_id: str = DEFAULT_KL_TARGET_ID,
        user_id: str | None = None,
        priority: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> Any:
        """提交 KL 阶段完成事件 → quality-patrol skill (默认).

        Args:
            stage: T1/T2/T3/T4/T5
            item_id: knowledge item id (必填)
            target_id: 目标 skill id (默认 quality-patrol)
            user_id: 触发用户 (限流用)
            priority: 0=REALTIME / 1=NORMAL / 2=BATCH
            extra: 透传额外参数 (stage_metrics / etc.)

        Returns:
            ``TriggerTicket`` (pending)
        """
        if stage not in VALID_KL_STAGES:
            raise InvalidKLEventError(
                f"KL stage {stage!r} 非法, 仅允许 {VALID_KL_STAGES}"
            )
        if not item_id or not isinstance(item_id, str):
            raise InvalidKLEventError("KL item_id 必为非空 str")

        inputs = {"stage": stage, "item_id": item_id, "extra": extra or {}}
        ticket = trigger_gate.submit(
            target_type="skill",
            target_id=target_id,
            inputs=inputs,
            priority=priority,
            source="kl_event",
            user_id=user_id,
        )
        logger.info(
            "kl_event trigger submitted",
            extra={
                "trace_id": "",
                "ticket_id": ticket.ticket_id,
                "stage": stage,
                "item_id": item_id,
                "target_id": target_id,
            },
        )
        return ticket


_default = KLEventTrigger()


def submit_kl_event(
    stage: str,
    item_id: str,
    *,
    target_id: str = DEFAULT_KL_TARGET_ID,
    user_id: str | None = None,
    priority: int = 1,
    extra: dict[str, Any] | None = None,
) -> Any:
    return _default.submit(
        stage,
        item_id,
        target_id=target_id,
        user_id=user_id,
        priority=priority,
        extra=extra,
    )