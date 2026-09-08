"""v1.0 T09 WorkerCoordinator 测试 — 5 失败注入 + 状态机 + 重试 + 死信.

覆盖 (对应 EXECUTION_GUIDE §4 T09 通过证据 + V0.8.3 §F01 修复方向):
  1. TaskRequest 不可变 (frozen) + submission_key 稳定
  2. consume() 正常路径: queued → claimed → running → succeeded
  3. task_fn 抛错 → FAILED 状态 + last_error 落库 + 重试 (FAILED → QUEUED)
  4. task_fn 持续失败 ≥ max_retries → dead_letter + audit_log
  5. task_fn 返回 error_msg → FAILED 路径
  6. 状态机非法转移抛 WorkerStateError
  7. lease 抢失败 → FAILED
  8. worker_runs 行存在 + 字段对齐
  9. list_runs / get_run / list_dead_letters 查询接口
  10. 并发: 同一 task_id 不重复跑 (run_id 不同)
  11. payload 持久化 (JSON 序列化稳定)
  12. **v1.0 C03 R04**: consume 不传 task_fn → raise ValueError, 拒绝 noop 兜底
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from backend.repository.db import get_connection
from backend.services.worker_coordinator import (
    TaskRequest,
    WorkerCoordinator,
    WorkerRunState,
    WorkerStateError,
)


# ---------------------------------------------------------------------------
# 0. 通用 dispatcher (v1.0 C03 R04 修复: consume 必传 task_fn)
# ---------------------------------------------------------------------------
def _default_ok_fn(req) -> dict:
    """测试用 OK dispatcher: 返空 items, 让 consume 走 SUCCEEDED 路径.

    旧测试用 consume(req) 不传 task_fn, 触发 _noop_task_fn 兜底 (R04 真问题).
    R04 修后 consume 必传 task_fn. 测试用此默认 OK fn 替代.
    """
    return {"items": []}


# ---------------------------------------------------------------------------
# 1. TaskRequest 不可变 + submission_key 稳定
# ---------------------------------------------------------------------------
def test_task_request_is_frozen() -> None:
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-abc",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.task_id = "tg-xyz"  # type: ignore[misc]


def test_task_request_submission_key_stable() -> None:
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-abc",
        attempt=0,
    )
    k1 = req.submission_key()
    k2 = req.submission_key()
    assert k1 == k2
    assert k1.startswith("v1-worker-trigger_ticket-")
    # 不同 attempt → 不同 key
    req2 = dataclasses.replace(req, attempt=1)
    assert req2.submission_key() != k1


# ---------------------------------------------------------------------------
# 2. consume() 正常路径
# ---------------------------------------------------------------------------
def test_consume_success_path(temp_db) -> None:
    """正常路径: queued → claimed → running → succeeded."""
    coord = WorkerCoordinator()
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-ok-1",
    )
    result = coord.consume(req, task_fn=_default_ok_fn)
    assert result.state == WorkerRunState.SUCCEEDED
    assert result.run_id.startswith("wr-")
    assert result.attempts == 1
    assert result.dead_lettered is False
    assert result.error is None
    assert result.duration_ms >= 0

    # DB 落库验证
    run = coord.get_run(result.run_id)
    assert run is not None
    assert run["status"] == "succeeded"
    assert run["task_type"] == "trigger_ticket"
    assert run["queue_name"] == "trigger_gate"
    assert run["source_task_id"] == "tg-ok-1"
    assert run["finished_at"] is not None
    assert run["duration_ms"] is not None


def test_consume_with_custom_task_fn(temp_db) -> None:
    """自定义 task_fn 返回 items → items 字段落结果."""
    coord = WorkerCoordinator()

    def my_task_fn(req: TaskRequest) -> dict:
        return {"items": [{"id": "i1"}, {"id": "i2"}]}

    req = TaskRequest(
        task_type="ai_hub_call",
        queue_name="ai_hub",
        task_id="ah-1",
    )
    result = coord.consume(req, task_fn=my_task_fn)
    assert result.state == WorkerRunState.SUCCEEDED
    assert len(result.items) == 2


# ---------------------------------------------------------------------------
# 3. task_fn 抛错 → FAILED + 重试
# ---------------------------------------------------------------------------
def test_consume_task_fn_raises_failed(temp_db) -> None:
    """task_fn 抛错 → state=FAILED + last_error 落库."""
    coord = WorkerCoordinator()

    def fail_fn(req: TaskRequest) -> dict:
        raise ValueError("simulated failure")

    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-fail-1",
    )
    result = coord.consume(req, task_fn=fail_fn)
    assert result.state == WorkerRunState.FAILED
    assert result.dead_lettered is False  # attempts=1 < max_retries=3
    assert "ValueError" in (result.error or "")
    assert "simulated failure" in (result.error or "")

    run = coord.get_run(result.run_id)
    assert run is not None
    # FAILED → QUEUED (允许后续重试) → status=queued (重试未跑, 留 pending)
    # 注: 重试需要 attempt+1, 这里单次失败不进入 QUEUED (仅 attempts >= max_retries 时重试触发)
    # 实际行为: 失败未超限, _transition(run_id, QUEUED) 写回 queued
    assert run["status"] == "queued"
    assert "ValueError" in run["last_error"]


def test_consume_returns_error_msg_failed(temp_db) -> None:
    """task_fn 返回 error_msg → FAILED (非抛错也走 FAILED 路径)."""
    coord = WorkerCoordinator()

    def soft_fail(req: TaskRequest) -> dict:
        return {"error_msg": "validation failed"}

    req = TaskRequest(
        task_type="ai_hub_call",
        queue_name="ai_hub",
        task_id="ah-soft-1",
    )
    result = coord.consume(req, task_fn=soft_fail)
    assert result.state == WorkerRunState.FAILED
    assert result.error == "validation failed"


# ---------------------------------------------------------------------------
# 4. 失败 ≥ max_retries → dead_letter + audit_log
# ---------------------------------------------------------------------------
def test_consume_dead_letters_after_max_retries(temp_db) -> None:
    """attempts >= max_retries → dead_letter + audit_log 落库."""
    coord = WorkerCoordinator()

    def fail_fn(req: TaskRequest) -> dict:
        raise RuntimeError("persistent failure")

    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-dead-1",
        attempt=2,  # attempt+1 = 3 = max_retries → 落死信
    )
    result = coord.consume(req, task_fn=fail_fn)
    assert result.state == WorkerRunState.FAILED
    assert result.dead_lettered is True
    assert result.attempts == 3

    # dead_letter 验证
    dead_letters = coord.list_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["original_task_id"] == "tg-dead-1"
    assert dead_letters[0]["attempts"] == 3
    assert "RuntimeError" in dead_letters[0]["error_msg"]

    # audit_log 验证
    conn = get_connection()
    rows = conn.execute(
        "SELECT action, target, detail FROM audit_log "
        "WHERE action = 'worker.dead_letter'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["target"] == "trigger_ticket:tg-dead-1"
    detail = json.loads(rows[0]["detail"])
    assert detail["attempts"] == 3


# ---------------------------------------------------------------------------
# 5. 状态机非法转移
# ---------------------------------------------------------------------------
def test_state_machine_illegal_transition_raises(temp_db) -> None:
    """状态机白名单 — 非法转移抛 WorkerStateError."""
    coord = WorkerCoordinator()
    # 直接走 _transition (绕过 consume 主体流程) — 把一个 run 强行标 terminal
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-state-1",
    )
    # 先正常跑一次
    result = coord.consume(req, task_fn=_default_ok_fn)
    assert result.state == WorkerRunState.SUCCEEDED

    # 现在 run_id 处于 SUCCEEDED (terminal), 任何转移都非法
    with pytest.raises(WorkerStateError):
        coord._transition(result.run_id, WorkerRunState.RUNNING)


def test_state_machine_terminal_states(temp_db) -> None:
    """SUCCEEDED 是 terminal, 后续转移全部被拒."""
    coord = WorkerCoordinator()
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-state-2",
    )
    result = coord.consume(req, task_fn=_default_ok_fn)
    # 验证: SUCCEEDED → FAILED 不允许
    with pytest.raises(WorkerStateError):
        coord._transition(result.run_id, WorkerRunState.FAILED)


# ---------------------------------------------------------------------------
# 6. lease 抢失败 → FAILED
# ---------------------------------------------------------------------------
def test_consume_lease_held_failed(temp_db) -> None:
    """lease.acquire 抛 LeaseHeldError → FAILED."""

    class MockLease:
        def acquire(self, task_id: str) -> None:
            raise RuntimeError("lease held")

        def release(self, task_id: str) -> None:
            pass

    coord = WorkerCoordinator(lease=MockLease())
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-lease-1",
    )
    result = coord.consume(req, task_fn=_default_ok_fn)
    assert result.state == WorkerRunState.FAILED
    assert "lease held" in (result.error or "")


# ---------------------------------------------------------------------------
# 7. 并发 / 唯一性
# ---------------------------------------------------------------------------
def test_concurrent_consume_unique_run_ids(temp_db) -> None:
    """同一 task_id 多次 consume → run_id 各不相同."""
    coord = WorkerCoordinator()
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-concurrent",
    )
    results = [coord.consume(req, task_fn=_default_ok_fn) for _ in range(3)]
    run_ids = {r.run_id for r in results}
    assert len(run_ids) == 3  # 每次 run_id 唯一


# ---------------------------------------------------------------------------
# 8. payload 持久化
# ---------------------------------------------------------------------------
def test_payload_persisted_as_json(temp_db) -> None:
    """payload dict 落库为 JSON 字符串 (sort_keys + ensure_ascii=False)."""
    coord = WorkerCoordinator()
    req = TaskRequest(
        task_type="ai_hub_call",
        queue_name="ai_hub",
        task_id="ah-payload",
        payload={"key1": "val1", "key2": ["a", "b"], "中文": "ok"},
    )
    result = coord.consume(req, task_fn=_default_ok_fn)
    run = coord.get_run(result.run_id)
    assert run is not None
    # 持久化字段不在 get_run 投影中, 走 raw query
    conn = get_connection()
    row = conn.execute(
        "SELECT payload_json FROM worker_runs WHERE run_id = ?", (result.run_id,)
    ).fetchone()
    assert row is not None
    parsed = json.loads(row[0])
    assert parsed == {"key1": "val1", "key2": ["a", "b"], "中文": "ok"}


# ---------------------------------------------------------------------------
# 9. 查询接口
# ---------------------------------------------------------------------------
def test_list_runs_filter_by_status(temp_db) -> None:
    """list_runs(status='succeeded') 仅返回 SUCCEEDED 行."""
    coord = WorkerCoordinator()
    req_ok = TaskRequest(
        task_type="trigger_ticket", queue_name="trigger_gate", task_id="tg-list-1",
    )
    coord.consume(req_ok, task_fn=_default_ok_fn)

    def fail_fn(req: TaskRequest) -> dict:
        raise ValueError("boom")

    req_fail = TaskRequest(
        task_type="trigger_ticket", queue_name="trigger_gate", task_id="tg-list-2",
    )
    coord.consume(req_fail, task_fn=fail_fn)

    succeeded = coord.list_runs(status="succeeded")
    assert len(succeeded) == 1
    assert succeeded[0]["source_task_id"] == "tg-list-1"

    failed_or_queued = coord.list_runs(status="queued")
    assert len(failed_or_queued) == 1
    assert failed_or_queued[0]["source_task_id"] == "tg-list-2"


def test_list_runs_filter_by_queue(temp_db) -> None:
    """list_runs(queue_name='ai_hub') 过滤."""
    coord = WorkerCoordinator()
    req1 = TaskRequest(task_type="ai_hub_call", queue_name="ai_hub", task_id="ah-q-1")
    req2 = TaskRequest(task_type="trigger_ticket", queue_name="trigger_gate", task_id="tg-q-1")
    coord.consume(req1, task_fn=_default_ok_fn)
    coord.consume(req2, task_fn=_default_ok_fn)

    ai_hub_runs = coord.list_runs(queue_name="ai_hub")
    assert len(ai_hub_runs) == 1
    assert ai_hub_runs[0]["queue_name"] == "ai_hub"


def test_get_run_returns_none_for_unknown(temp_db) -> None:
    """未知 run_id → None."""
    coord = WorkerCoordinator()
    assert coord.get_run("wr-nonexistent") is None


# ---------------------------------------------------------------------------
# 10. noop_task_fn (默认 handler)
# ---------------------------------------------------------------------------
def test_consume_without_task_fn_raises_R04(temp_db) -> None:
    """v1.0 C03 R04 修复断言: 不传 task_fn → raise ValueError, 禁止 noop 兜底.

    旧实现: task_fn 默认 None 兜底 _noop_task_fn, 空成功返 {"items": []},
    worker_runs 落 succeeded + trigger_ticket 落 done, 但实际工作没做 (53 个历史
    pending ticket 全部虚报完成). R04 修: task_fn 必填, None 必 raise.
    """
    from backend.services.worker_coordinator import TaskRequest, WorkerCoordinator
    coord = WorkerCoordinator()
    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-r04-noop-rejected",
    )
    with pytest.raises(ValueError, match="task_fn is required"):
        coord.consume(req, task_fn=None)


# ---------------------------------------------------------------------------
# 11. 失败后 attempts 累加
# ---------------------------------------------------------------------------
def test_attempts_counter_in_worker_runs(temp_db) -> None:
    """失败后 attempts 字段反映重试次数."""
    coord = WorkerCoordinator()

    def fail_fn(req: TaskRequest) -> dict:
        raise ValueError("retry me")

    req = TaskRequest(
        task_type="trigger_ticket",
        queue_name="trigger_gate",
        task_id="tg-attempts",
        attempt=1,  # attempt+1 = 2 < max_retries=3
    )
    result = coord.consume(req, task_fn=fail_fn)
    assert result.state == WorkerRunState.FAILED
    assert result.attempts == 2
    run = coord.get_run(result.run_id)
    assert run["attempts"] == 2


# ---------------------------------------------------------------------------
# 12. dead_letter 与 audit_log 计数一致性
# ---------------------------------------------------------------------------
def test_dead_letter_and_audit_count_match(temp_db) -> None:
    """多次死信 → dead_letter 与 audit_log 条数一致."""
    coord = WorkerCoordinator()

    def fail_fn(req: TaskRequest) -> dict:
        raise RuntimeError("doom")

    for i in range(3):
        req = TaskRequest(
            task_type="trigger_ticket",
            queue_name="trigger_gate",
            task_id=f"tg-multi-{i}",
            attempt=2,  # attempt+1 = 3 = max_retries
        )
        coord.consume(req, task_fn=fail_fn)

    dead_letters = coord.list_dead_letters()
    assert len(dead_letters) == 3

    conn = get_connection()
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'worker.dead_letter'"
    ).fetchone()[0]
    assert audit_count == 3
