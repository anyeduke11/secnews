"""trigger_gate 测试 — v0.8 Phase A Task A1 (单一入口: 限流/排队/优先级/worker 泵)。

覆盖四块契约:
1. submit 编排 — ticket 形态 / inputs JSON 往返 / source 校验 / 限流拒绝不入队
2. 队列原语 — 优先级出队 / FIFO / 原子抢占 / 状态转移 / stale 恢复 / 持久化
3. worker 泵 — 自动消费 / 并发上限 / handler 异常存活 / 非抢占 / stop 幂等
4. 限流桶 — per-user 与 global 独立 / 时间推进恢复 (假时钟)

线程类用例 (worker) 全部用 Event 同步 + try/finally stop, 保证泵线程
不跨测试泄漏 (泄漏线程会拿着旧 config.db_path 开连接污染别的库)。
"""
from __future__ import annotations

import threading
import time

import pytest

from backend.services.trigger_gate import (
    Priority,
    ThrottleExceededError,
    TriggerGate,
    TriggerQueue,
    TriggerThrottle,
    TriggerTicket,
    TriggerWorker,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

POLL = 0.05  # 测试用泵轮询间隔 (秒)


class FakeClock:
    """可推进的假时钟 — throttle time_fn 注入用。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_gate(per_user: int = 60, global_per_minute: int = 600, clock: FakeClock | None = None) -> TriggerGate:
    """构造注入小桶限流器的 gate (默认桶大, 由调用方收窄)。"""
    throttle = TriggerThrottle(
        per_user_per_minute=per_user,
        global_per_minute=global_per_minute,
        time_fn=clock or FakeClock(),
    )
    return TriggerGate(throttle=throttle)


def make_ticket(ticket_id: str, priority: int = Priority.NORMAL) -> TriggerTicket:
    """直接构造票据 (queue 层测试不经 submit)。"""
    return TriggerTicket(
        ticket_id=ticket_id,
        target_type="skill",
        target_id=f"skill-of-{ticket_id}",
        priority=priority,
        source="manual",
    )


def wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """轮询等待谓词成立 (DB 状态异步变化用), 超时返回 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# 1. submit 编排契约
# ---------------------------------------------------------------------------
def test_submit_returns_pending_ticket_with_inputs_roundtrip(temp_db):
    """submit 返回 pending 票据, inputs 经 JSON 序列化落库后无损往返。"""
    gate = make_gate()
    ticket = gate.submit(
        "skill",
        "daily_report",
        inputs={"query": "ai 安全", "limit": 10},
        source="manual",
        user_id="u1",
    )
    assert ticket.ticket_id.startswith("tg-") and len(ticket.ticket_id) == 15
    assert ticket.status == "pending"
    assert ticket.target_type == "skill"
    assert ticket.target_id == "daily_report"
    assert ticket.priority == Priority.NORMAL
    assert ticket.inputs == {"query": "ai 安全", "limit": 10}

    loaded = TriggerQueue().get(ticket.ticket_id)
    assert loaded is not None
    assert loaded.inputs == {"query": "ai 安全", "limit": 10}  # 中文/数字 JSON 往返
    assert loaded.status == "pending"
    assert loaded.enqueued_at is not None


def test_throttle_rejects_fourth_submit_without_enqueue(temp_db):
    """per-user 小桶: 第 4 次 submit 抛 ThrottleExceededError 且票据不落库。"""
    clock = FakeClock()
    gate = make_gate(per_user=3, clock=clock)
    for i in range(3):
        gate.submit("skill", f"s{i}", source="manual", user_id="u1")
    with pytest.raises(ThrottleExceededError) as excinfo:
        gate.submit("skill", "s3", source="manual", user_id="u1")
    assert excinfo.value.retry_after_seconds > 0
    # 被拒的提交绝不入队 — 队列里只有前 3 条
    assert TriggerQueue().stats()["pending"] == 3


def test_throttle_global_bucket_independent_of_user(temp_db):
    """global 桶独立于用户桶: 换 user 也要吃同一个全局配额。"""
    clock = FakeClock()
    gate = make_gate(per_user=60, global_per_minute=3, clock=clock)
    for i in range(3):
        gate.submit("skill", f"s{i}", source="cron", user_id=f"user-{i}")
    # 第 4 个是新用户 — 用户桶有余量, 但全局桶已耗尽
    with pytest.raises(ThrottleExceededError) as excinfo:
        gate.submit("skill", "s3", source="cron", user_id="user-99")
    assert excinfo.value.scope == "global"
    assert TriggerQueue().stats()["pending"] == 3


def test_throttle_recovers_after_time_advance(temp_db):
    """时间推进 60s 后令牌回满 — 之前被拒的提交恢复放行。"""
    clock = FakeClock()
    gate = make_gate(per_user=2, clock=clock)
    gate.submit("skill", "s0", source="manual", user_id="u1")
    gate.submit("skill", "s1", source="manual", user_id="u1")
    with pytest.raises(ThrottleExceededError):
        gate.submit("skill", "s2", source="manual", user_id="u1")

    clock.advance(60)  # 容量=速率 → 一整分钟回满
    ticket = gate.submit("skill", "s2", source="manual", user_id="u1")
    assert ticket.status == "pending"
    assert TriggerQueue().stats()["pending"] == 3


def test_submit_rejects_invalid_source(temp_db):
    """source 非法值被拒 (ValueError), 且不入队不消耗配额。"""
    gate = make_gate()
    with pytest.raises(ValueError, match="source"):
        gate.submit("skill", "x", source="yolo")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="target_type"):
        gate.submit("agent", "x", source="manual")  # type: ignore[arg-type]
    assert TriggerQueue().stats()["pending"] == 0


# ---------------------------------------------------------------------------
# 2. 队列原语
# ---------------------------------------------------------------------------
def test_dequeue_priority_order_realtime_before_batch(temp_db):
    """先入 BATCH 再入 REALTIME → 出队先出 REALTIME (优先级只管顺序)。"""
    q = TriggerQueue()
    batch = make_ticket("tg-batch-0001", priority=Priority.BATCH)
    realtime = make_ticket("tg-rt-00000001", priority=Priority.REALTIME)
    q.enqueue(batch)
    q.enqueue(realtime)

    first = q.dequeue()
    assert first is not None and first.ticket_id == realtime.ticket_id
    second = q.dequeue()
    assert second is not None and second.ticket_id == batch.ticket_id
    assert q.dequeue() is None  # 队列空


def test_dequeue_fifo_within_same_priority(temp_db):
    """同优先级按入队顺序 (id 自增) FIFO。"""
    q = TriggerQueue()
    for name in ("a", "b", "c"):
        q.enqueue(make_ticket(f"tg-{name}-000000001"))
    order = [q.dequeue().ticket_id for _ in range(3)]  # type: ignore[union-attr]
    assert order == ["tg-a-000000001", "tg-b-000000001", "tg-c-000000001"]


def test_dequeue_atomic_two_threads_only_one_wins(temp_db):
    """并发 dequeue: 两线程同时抢, 只有一个拿到票据 (UPDATE 原子抢占)。"""
    q = TriggerQueue()
    q.enqueue(make_ticket("tg-race-0000001"))
    barrier = threading.Barrier(2)
    results: list = []

    def racer() -> None:
        barrier.wait()  # 两线程尽量同时出队
        results.append(q.dequeue())

    threads = [threading.Thread(target=racer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1  # 恰好一个线程抢到
    assert claimed[0].ticket_id == "tg-race-0000001"
    assert claimed[0].status == "running"
    assert claimed[0].started_at is not None


def test_mark_done_and_failed_transitions(temp_db):
    """mark_done / mark_failed 的状态转移 + finished_at / error 落库。"""
    q = TriggerQueue()
    t_ok = make_ticket("tg-ok-0000000001")
    t_bad = make_ticket("tg-bad-0000000001")
    q.enqueue(t_ok)
    q.enqueue(t_bad)

    running = q.dequeue()
    assert running is not None and running.ticket_id == t_ok.ticket_id
    assert q.mark_done(t_ok.ticket_id)
    failed = q.dequeue()
    assert failed is not None and failed.ticket_id == t_bad.ticket_id
    assert q.mark_failed(t_bad.ticket_id, "boom")

    done_row = q.get(t_ok.ticket_id)
    assert done_row is not None and done_row.status == "done"
    assert done_row.finished_at is not None and done_row.error is None
    failed_row = q.get(t_bad.ticket_id)
    assert failed_row is not None and failed_row.status == "failed"
    assert failed_row.error == "boom" and failed_row.finished_at is not None


def test_reset_stale_running_resets_and_increments_attempts(temp_db):
    """running 超时 → pending + attempts+1 (崩溃恢复)。"""
    q = TriggerQueue()
    q.enqueue(make_ticket("tg-stale-00000001"))
    ticket = q.dequeue()
    assert ticket is not None and ticket.status == "running"
    # 把 started_at 拨回 2 小时前, 模拟进程崩溃后重启
    from backend.repository.db import get_connection

    get_connection().execute(
        "UPDATE trigger_tickets SET started_at=datetime('now','localtime','-2 hours') "
        "WHERE ticket_id=?",
        ("tg-stale-00000001",),
    )

    reset = q.reset_stale_running(3600)
    assert reset == 1
    revived = q.get("tg-stale-00000001")
    assert revived is not None
    assert revived.status == "pending"
    assert revived.attempts == 1
    assert revived.started_at is None


def test_reset_stale_running_does_not_touch_pending(temp_db):
    """pending 票据不受 stale 扫描影响 — 没有起始时间就不存在过期。"""
    q = TriggerQueue()
    q.enqueue(make_ticket("tg-a-00000000001"))
    q.enqueue(make_ticket("tg-b-00000000001"))
    first = q.dequeue()  # FIFO → 先出 tg-a
    assert first is not None and first.ticket_id == "tg-a-00000000001"
    q.mark_done("tg-a-00000000001")

    assert q.reset_stale_running(0) == 0  # 阈值 0 也不碰 pending/done
    stats = q.stats()
    assert stats == {"pending": 1, "running": 0, "done": 1, "failed": 0}
    fresh = q.get("tg-b-00000000001")
    assert fresh is not None and fresh.status == "pending" and fresh.attempts == 0


def test_queue_persists_across_db_reopen(temp_db):
    """enqueue 后关库重开 (模拟进程重启) — 票据仍在, 仍可出队。"""
    from backend.repository import db

    q = TriggerQueue()
    q.enqueue(make_ticket("tg-persist-00001", priority=Priority.REALTIME))
    db.close_db()
    db.init_db()  # 同一 tmp db 路径, 重放迁移为 no-op

    revived_q = TriggerQueue()
    revived = revived_q.get("tg-persist-00001")
    assert revived is not None and revived.status == "pending"
    claimed = revived_q.dequeue()
    assert claimed is not None and claimed.ticket_id == "tg-persist-00001"


# ---------------------------------------------------------------------------
# 3. worker 泵
# ---------------------------------------------------------------------------
def test_worker_dequeues_and_calls_handler(temp_db):
    """泵自动出队并调用注入 handler; handler 正常返回后票据置 done。"""
    called = threading.Event()
    seen: dict = {}

    def handler(ticket: TriggerTicket) -> None:
        seen["ticket"] = ticket
        called.set()

    q = TriggerQueue()
    worker = TriggerWorker(queue=q, handler=handler, poll_interval_seconds=POLL)
    worker.start()
    try:
        q.enqueue(make_ticket("tg-w1-0000000001"))
        assert called.wait(timeout=5), "handler 未被调用"
        assert seen["ticket"].ticket_id == "tg-w1-0000000001"
        # handler 返回后 mark_done 异步落库
        assert wait_until(lambda: q.get("tg-w1-0000000001").status == "done")
    finally:
        worker.stop()


def test_worker_max_running_caps_concurrency(temp_db):
    """3 个慢 handler 占满槽位后, 第 4 张票据保持 pending。"""
    entered: list[str] = []
    entered_guard = threading.Lock()
    release = threading.Event()

    def slow_handler(ticket: TriggerTicket) -> None:
        with entered_guard:
            entered.append(ticket.ticket_id)
        release.wait(timeout=10)

    q = TriggerQueue()
    worker = TriggerWorker(queue=q, handler=slow_handler, poll_interval_seconds=POLL, max_running=3)
    worker.start()
    try:
        for i in range(4):
            q.enqueue(make_ticket(f"tg-cap-{i:011d}"))
        # 等 3 个 handler 进入 (第 4 个因信号量满无法出队)
        assert wait_until(lambda: len(entered) >= 3), "前 3 个 handler 未全部启动"
        time.sleep(0.3)  # 留足多个轮询周期, 确认第 4 个确实没被捞走
        stats = q.stats()
        assert stats["running"] == 3
        assert stats["pending"] == 1
        # 放行慢 handler → 槽位归还, 泵还活着 → 第 4 张也被消费
        release.set()
        assert wait_until(lambda: q.stats()["done"] == 4), "释放槽位后第 4 张票据未被消费"
    finally:
        release.set()
        worker.stop()


def test_worker_handler_exception_marks_failed_and_survives(temp_db):
    """handler 抛异常 → 票据 failed + error 落库, 泵线程继续活着消费后续票据。"""
    def bad_handler(ticket: TriggerTicket) -> None:
        raise RuntimeError(f"boom-{ticket.ticket_id}")

    q = TriggerQueue()
    worker = TriggerWorker(queue=q, handler=bad_handler, poll_interval_seconds=POLL)
    worker.start()
    try:
        q.enqueue(make_ticket("tg-x1-0000000001"))
        assert wait_until(lambda: q.get("tg-x1-0000000001").status == "failed")
        failed = q.get("tg-x1-0000000001")
        assert "RuntimeError" in failed.error and "boom" in failed.error

        assert worker.is_alive(), "handler 异常不应带崩泵线程"
        q.enqueue(make_ticket("tg-x2-0000000001"))  # 泵还活着 → 继续消费
        assert wait_until(lambda: q.get("tg-x2-0000000001").status == "failed")
        assert worker.is_alive()
    finally:
        worker.stop()


def test_worker_non_preemption_running_batch_not_interrupted(temp_db):
    """非抢占: BATCH handler 运行中, REALTIME 到达被立即执行, 但 BATCH 不被中断。"""
    batch_entered = threading.Event()
    batch_done = threading.Event()
    release_batch = threading.Event()
    realtime_done = threading.Event()

    def handler(ticket: TriggerTicket) -> None:
        if ticket.priority == Priority.BATCH:
            batch_entered.set()
            release_batch.wait(timeout=10)  # 模拟长任务, 直到测试放行
            batch_done.set()
        else:
            realtime_done.set()

    q = TriggerQueue()
    worker = TriggerWorker(queue=q, handler=handler, poll_interval_seconds=POLL)
    worker.start()
    try:
        q.enqueue(make_ticket("tg-b1-0000000001", priority=Priority.BATCH))
        assert batch_entered.wait(timeout=5), "BATCH handler 未启动"

        q.enqueue(make_ticket("tg-r1-0000000001", priority=Priority.REALTIME))
        assert realtime_done.wait(timeout=5), "REALTIME 未被执行"
        assert not batch_done.is_set(), "BATCH 被提前中断了 (违反非抢占语义)"
        assert q.get("tg-b1-0000000001").status == "running"

        release_batch.set()
        assert batch_done.wait(timeout=5), "BATCH handler 未自然完成"
        assert wait_until(
            lambda: q.get("tg-b1-0000000001").status == "done"
            and q.get("tg-r1-0000000001").status == "done"
        )
    finally:
        release_batch.set()
        worker.stop()


def test_worker_stop_idempotent_and_thread_exits(temp_db):
    """stop 幂等 + 泵线程退出 + 停止后不再消费新票据。"""
    q = TriggerQueue()
    worker = TriggerWorker(queue=q, handler=lambda t: None, poll_interval_seconds=POLL)
    worker.start()
    assert worker.is_alive()
    worker.stop()
    worker.stop()  # 幂等
    assert not worker.is_alive()

    q.enqueue(make_ticket("tg-after-stop-001"))
    time.sleep(0.2)  # 远大于多个轮询周期
    assert q.get("tg-after-stop-001").status == "pending"
