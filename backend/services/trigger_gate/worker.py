"""trigger-gate 出队泵 — 进程内守护线程消费 trigger_tickets (v0.8 Phase A).

调度模型 (R6 非抢占语义):
- 泵线程按 ``poll_interval_seconds`` 轮询, 每轮先做崩溃恢复
  (``reset_stale_running`` — 超时 running 票据重置 pending + attempts+1),
  再尝试拿并发信号量; 拿不到 (max_running 个槽位全满) 就**不出队**,
  等待下一轮 — 并发上限靠 ``threading.Semaphore`` 而非线程池。
- 拿到槽位才 ``dequeue()`` (原子抢占), 随后在**独立短线程**里执行
  ``handler(ticket)``; handler 正常返回 → ``mark_done``, 抛异常 →
  ``mark_failed`` (error 落库) — 泵线程与执行线程都不崩。
- **非抢占**: 已在运行的 handler 绝不被中断, 优先级只决定出队顺序;
  ``stop()`` 也只停泵, 不杀在飞任务 (在飞线程为 daemon, 进程退出时随之结束)。

handler 可注入 (``Callable[[TriggerTicket], None]``, 默认 no-op logger),
后续任务把 skill 执行器接进来; 每张票据一个短线程意味着每个执行线程
会各自懒开一条 SQLite thread-local 连接 (WAL + busy_timeout 兜底)。
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from backend.logging_config import logger
from backend.services.trigger_gate.core import TriggerTicket
from backend.services.trigger_gate.queue import TriggerQueue

Handler = Callable[[TriggerTicket], None]


def _noop_handler(ticket: TriggerTicket) -> None:
    """默认 handler — 仅记日志 (接线前的安全占位)。"""
    logger.info(
        "trigger ticket handled (noop)",
        extra={"trace_id": "", "ticket_id": ticket.ticket_id, "target_id": ticket.target_id},
    )


class TriggerWorker:
    """进程内出队泵 — 消费 trigger_tickets 并派发 handler。

    参数:
        queue: 队列实现 (默认 TriggerQueue, 测试可注入)。
        handler: 票据执行函数 (默认 no-op)。
        poll_interval_seconds: 泵轮询间隔 (测试可调小)。
        max_running: 并发执行上限 (信号量槽位数)。
        stale_seconds: running 票据判定超时的秒数 (崩溃恢复阈值)。
    """

    def __init__(
        self,
        queue: TriggerQueue | None = None,
        handler: Handler | None = None,
        poll_interval_seconds: float = 1.0,
        max_running: int = 3,
        stale_seconds: float = 3600.0,
    ) -> None:
        self._queue = queue or TriggerQueue()
        self._handler: Handler = handler or _noop_handler
        self._poll_interval_seconds = poll_interval_seconds
        self._stale_seconds = stale_seconds
        self._semaphore = threading.Semaphore(max_running)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> TriggerWorker:
        """启动泵线程 (幂等 — 已存活则原样返回)。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._pump, name="trigger-gate-worker", daemon=True
            )
            self._thread.start()
            return self

    def stop(self) -> TriggerWorker:
        """停泵 (幂等; Event 置位 + join, 不中断在飞任务)。"""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        return self

    def is_alive(self) -> bool:
        """泵线程是否存活。"""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # 泵主体
    # ------------------------------------------------------------------
    def _pump(self) -> None:
        """泵循环 — 每轮: 崩溃恢复 → 抢槽位 → 出队派发。"""
        while not self._stop_event.is_set():
            self._recover_stale()
            if self._semaphore.acquire(blocking=False):
                ticket = self._safe_dequeue()
                if ticket is None:
                    # 队列空 / 本轮被并发抢走 → 归还槽位
                    self._semaphore.release()
                else:
                    self._dispatch(ticket)
            self._stop_event.wait(self._poll_interval_seconds)

    def _recover_stale(self) -> None:
        """每轮崩溃恢复 — 拿不到锁语义上的异常时只记日志, 不崩泵。"""
        try:
            self._queue.reset_stale_running(self._stale_seconds)
        except Exception:
            logger.exception("trigger worker stale-recover failed", extra={"trace_id": ""})

    def _safe_dequeue(self) -> TriggerTicket | None:
        """出队包装 — DB 异常只记日志 (持有槽位由调用方释放)。"""
        try:
            return self._queue.dequeue()
        except Exception:
            logger.exception("trigger worker dequeue failed", extra={"trace_id": ""})
            return None

    def _dispatch(self, ticket: TriggerTicket) -> None:
        """为票据开短线程执行 handler (泵立即回下一轮)。"""
        runner = threading.Thread(
            target=self._run_ticket,
            args=(ticket,),
            name=f"trigger-run-{ticket.ticket_id}",
            daemon=True,
        )
        runner.start()

    def _run_ticket(self, ticket: TriggerTicket) -> None:
        """执行单张票据 — handler 异常 → mark_failed, finally 归还槽位。"""
        try:
            self._handler(ticket)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.error(
                "trigger handler raised",
                extra={"trace_id": "", "ticket_id": ticket.ticket_id, "error": error},
            )
            self._safe_transition(ticket, failed=True, error=error)
        else:
            self._safe_transition(ticket, failed=False)
        finally:
            self._semaphore.release()

    def _safe_transition(self, ticket: TriggerTicket, *, failed: bool, error: str = "") -> None:
        """收尾状态转移 — DB 异常只记日志 (票据留 running, 交给 stale 恢复)。"""
        try:
            if failed:
                self._queue.mark_failed(ticket.ticket_id, error or "unknown error")
            else:
                self._queue.mark_done(ticket.ticket_id)
        except Exception:
            logger.exception(
                "trigger worker mark ticket status failed",
                extra={"trace_id": "", "ticket_id": ticket.ticket_id},
            )


__all__ = ["Handler", "TriggerWorker", "_noop_handler"]
