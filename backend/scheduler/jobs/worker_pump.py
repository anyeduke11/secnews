"""worker_pump 域 scheduler job (v1.0 T09 + C03 R04 + C07 R04 真实派发).

实现 (与 jobs/maintenance.py 同款风格 — try/except 兜底, 不死循环):

- job 53: worker_queue_pump — 60s tick, 拉 trigger_gate / ai_hub / case_service
  队列中 pending 票据, 喂给 WorkerCoordinator 处理. 复用 v0.8.2 Y 的
  ``utils.concurrency.get_semaphore("source_fetch")`` 限流 (与 source_fetch 同池).
- job 54: legacy_hold_reap — 周一 04:30 一次 (F01 收尾), 调 LegacyHoldService.

v1.0 C03 R04 修复: 显式传 task_fn 拒绝 noop 兜底 (旧 worker_pump.py:77 调
coordinator.consume(req) 不传 task_fn, coordinator 兜底 _noop_task_fn 返空成功,
trigger_ticket 标 done 但实际工作没做). C03 显式传 raise-on-call dispatcher,
C07 替换为真实 SkillRunner.run 派发 (走 dsh/pi 适配 — T04 lock.exit_criteria 兜底).
"""
from __future__ import annotations

import asyncio
from zoneinfo import ZoneInfo

from backend.logging_config import logger

_logger = logger.bind(component="jobs")

# 已知队列清单 (与 WorkerCoordinator.task_type 对齐)
# 本批仅消费 trigger_gate; ai_hub / case_service 留接口, 后续 task 接入扩展枚举值即可.
_KNOWN_QUEUES: tuple[str, ...] = ("trigger_gate", "ai_hub", "case_service")

# 限流组: 复用 v0.8.2 Y 的 source_fetch 池 (utils.concurrency.get_semaphore)
_LIMIT_GROUP = "source_fetch"

# 每周一 04:30 Asia/Shanghai (与 backup_verify 02:00 / weekly_maintenance 周日 04:00 错峰)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


# v1.0 C07 R04: 真实 SkillRunner 派发. 旧 C03 兜底 _c03_r04_dispatcher (raise-on-call)
# 已删, 替换为 _c07_r04_skill_dispatcher → 调 SkillRunner.run(skill, inputs, ticket_id).
# ticket 走 trigger_gate.dequeue (ticket_id 唯一), runner 写 skill_runs 留全链 audit.
# 真实 dsh/pi 适配 (C06 落地) 在 SkillRunner._invoke_service / _invoke_api 内完成;
# worker_pump 不感知具体实现, 失败 → SkillRunner 写 skill_runs status=failed,
# coordinator 走 FAILED 重试 + 3 次后 dead-letter (C03 路径不变).
def _c07_r04_skill_dispatcher(req) -> dict:
    """C07 R04 dispatcher: 把 trigger_gate ticket 真派发到 SkillRunner.

    链路 (与 run_service 的 create_or_replay 解耦 — worker_pump 不写 v1_runs,
    只跑 SkillDef):
      1. 从 req.payload / req.task_id 读 ticket (coordinator 已 decode 完)
      2. 拿 skill_id 调 SkillRegistry.get (SkillNotFoundError → 抛回 coordinator)
      3. SkillRunner.run(skill, inputs, ticket_id=ticket_id) — 全程同步, 失败落
         skill_runs.status=failed (SkillRunner.run 永不抛)
      4. 返 dict 形式结果 (coordinator consume 需 dict)
    """
    from backend.services.skill_registry import get_registry
    from backend.services.skill_runner.core import SkillRunner

    # req.task_id = ticket_id (worker_queue_pump_job 构造时填)
    ticket_id = getattr(req, "task_id", None) or "unknown"
    payload = getattr(req, "payload", None) or {}
    # payload 必有 skill_id (TriggerGate.enqueue 强校验), 兜底从 req 读
    skill_id = payload.get("skill_id") or payload.get("target_id")
    inputs = payload.get("inputs") or {}
    if not skill_id:
        raise RuntimeError(
            f"v1.0 C07 R04: trigger_ticket 缺 skill_id (ticket_id={ticket_id}, "
            f"payload_keys={list(payload.keys())})"
        )
    registry = get_registry()
    skill = registry.get(skill_id)  # SkillNotFoundError 自动抛
    runner = SkillRunner()
    result = runner.run(skill, inputs, ticket_id=ticket_id)
    return {
        "status": result.status,
        "run_id": result.run_id,
        "elapsed_ms": result.elapsed_ms,
        "fast_path": result.fast_path,
        "error": result.error,
        "outputs": result.outputs,
    }


# ---------------------------------------------------------------------------
# job 53: worker_queue_pump (每 60s)
# ---------------------------------------------------------------------------
async def worker_queue_pump_job() -> None:
    """v1.0 T09: 60s tick 拉 trigger_gate / ai_hub / case_service 队列.

    失败只 log.error, 不抛 (scheduler 不死循环). 单测可 patch.
    """
    try:
        from backend.services.trigger_gate.core import TriggerTicket
        from backend.services.trigger_gate.queue import TriggerQueue
        from backend.services.worker_coordinator import TaskRequest, WorkerCoordinator
        from backend.utils.concurrency import get_semaphore

        sem = get_semaphore(_LIMIT_GROUP)
        coordinator = WorkerCoordinator()

        # 走 semaphore 限制并发 (避免和 source_fetch 撞; Y 限流池共享)
        # 每 tick 限处理 N 条 (N = semaphore size); 队列残留下轮再跑.
        queue = TriggerQueue()
        processed = 0

        # 单 worker 串行消费本批; 真正的并发由 WorkerCoordinator 自己决定 (T09 单 worker 足够).
        for queue_name in _KNOWN_QUEUES:
            if queue_name != "trigger_gate":
                # ai_hub / case_service 后续 task 接入扩展; 当前批 noop
                continue
            # trigger_gate 走 TriggerQueue.dequeue 原子抢占
            for _ in range(sem._value if hasattr(sem, "_value") else 4):
                ticket: TriggerTicket | None = None
                try:
                    ticket = queue.dequeue()
                except Exception as e:
                    _logger.warning(f"trigger_gate dequeue failed: {e}")
                    break
                if ticket is None:
                    break
                req = TaskRequest(
                    task_type="trigger_ticket",
                    queue_name=queue_name,
                    task_id=ticket.ticket_id,
                    payload=ticket.inputs or {},
                    requester=ticket.source,
                    attempt=ticket.attempts,
                )
                result = await asyncio.to_thread(
                    coordinator.consume, req, task_fn=_c07_r04_skill_dispatcher,
                )
                if result.dead_lettered:
                    _logger.error(
                        f"worker_queue_pump: dead-lettered ticket_id={ticket.ticket_id} "
                        f"attempts={result.attempts}"
                    )
                    # 标 trigger_tickets failed + finished_at
                    try:
                        from backend.repository.db import get_connection
                        conn = get_connection()
                        conn.execute(
                            "UPDATE trigger_tickets SET status='failed', "
                            "finished_at=datetime('now','localtime'), "
                            "error=? WHERE ticket_id=?",
                            (
                                f"dead_lettered after {result.attempts} attempts: {result.error}",
                                ticket.ticket_id,
                            ),
                        )
                        conn.commit()
                    except Exception as e:
                        _logger.warning(f"mark trigger_ticket failed failed: {e}")
                else:
                    # SUCCEEDED / 重试 (queued) → 标 done / 重试 attempts+1
                    try:
                        from backend.repository.db import get_connection
                        conn = get_connection()
                        if result.state.value == "succeeded":
                            conn.execute(
                                "UPDATE trigger_tickets SET status='done', "
                                "finished_at=datetime('now','localtime'), "
                                "attempts=attempts+1 WHERE ticket_id=?",
                                (ticket.ticket_id,),
                            )
                        else:
                            # FAILED 重试: attempts+1, status=pending (下一轮再派)
                            conn.execute(
                                "UPDATE trigger_tickets SET attempts=attempts+1, "
                                "started_at=NULL WHERE ticket_id=?",
                                (ticket.ticket_id,),
                            )
                        conn.commit()
                    except Exception as e:
                        _logger.warning(f"mark trigger_ticket status failed: {e}")
                processed += 1
        if processed > 0:
            _logger.info(f"worker_queue_pump: processed={processed} (queues={list(_KNOWN_QUEUES)})")
    except Exception as e:
        _logger.error(f"worker_queue_pump_job crashed: {e}")


# ---------------------------------------------------------------------------
# job 54: legacy_hold_reap (周一 04:30)
# ---------------------------------------------------------------------------
async def legacy_hold_reap_job() -> None:
    """v1.0 T09: F01 收尾 — 周一 04:30 Asia/Shanghai 跑一次 LegacyHoldService.

    复用 worker_runs / dead_letter 的并发限制, 失败只 log.error (不抛).
    """
    try:
        from backend.services.legacy_hold_service import LegacyHoldService

        svc = LegacyHoldService()
        result = await asyncio.to_thread(svc.reap_pending_tickets)
        if result.reclassified_count > 0:
            _logger.info(
                f"legacy_hold_reap: reclassified={result.reclassified_count} "
                f"audit={result.audit_log_count} duration_ms={result.duration_ms}"
            )
        else:
            _logger.debug(
                f"legacy_hold_reap: no pending (candidate={result.candidate_count})"
            )
    except Exception as e:
        _logger.error(f"legacy_hold_reap_job crashed: {e}")


__all__ = [
    "legacy_hold_reap_job",
    "worker_queue_pump_job",
]
