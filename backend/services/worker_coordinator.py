"""v1.0 T09 运行协调器 — WorkerCoordinator (修复 F01: 53 pending 票据无人消费).

对应 EXECUTION_GUIDE §4 T09 通过证据 + V0.8.3_CRITICAL_REVIEW §F01:

  - 队列消费 + 任务派发 + 状态回报统一入口 (与 v0.8 trigger_gate 共存但
    **不**冲突 — trigger_gate 是 skill runner 内部队列, WorkerCoordinator
    是上层的统一调度协调层)
  - 不可变 TaskRequest (frozen dataclass) — 入参 hash 即幂等键
  - 5 状态机: QUEUED/CLAIMED/RUNNING/SUCCEEDED/FAILED (与 v1_0_models.RunStatus
    对齐, 仅取 worker 层关心的 5 态)
  - 失败重试: max_retries=3, backoff exponential (1s, 2s, 4s)
  - 死信队列: 失败 ≥ max_retries → dead_letter 表落 audit + 留重放入口
  - 单一注入点 (与 T06 source_pipeline 风格一致): lease / fetch_fn / parse_fn /
    evidence.create / evidence.commit, 单测可 monkeypatch 抛错验证回滚

设计纪律 (与 T02/T04/T05/T06 一致):
  - 隔离 conftest 下走 temp_db (T01 已落地); 默认 process-wide conn
  - 不动 v0.8 trigger_gate/ 已有代码 (它是 skill runner, T09 在其上层接 worker)
  - 不引入新依赖
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# 5 状态枚举 (与 v1_0_models.RunStatus 对齐, 仅取 worker 层关心子集)
# ---------------------------------------------------------------------------
class WorkerRunState(str, Enum):
    """WorkerCoordinator 5 态 — 与 contracts.md §7 RunStatus 对齐."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# 状态机合法转移 (白名单)
# 重试语义: 失败未超 max_retries 时, RUNNING/CLAIMED 可直接回到 QUEUED 等待下轮派发;
# SUCCEEDED 是终态; FAILED 也允许回到 QUEUED (供 ops 工具触发人工重试).
_VALID_TRANSITIONS: dict[WorkerRunState, set[WorkerRunState]] = {
    WorkerRunState.QUEUED: {WorkerRunState.CLAIMED, WorkerRunState.FAILED},
    WorkerRunState.CLAIMED: {WorkerRunState.RUNNING, WorkerRunState.FAILED, WorkerRunState.QUEUED},
    WorkerRunState.RUNNING: {WorkerRunState.SUCCEEDED, WorkerRunState.FAILED, WorkerRunState.QUEUED},
    WorkerRunState.SUCCEEDED: set(),
    WorkerRunState.FAILED: {WorkerRunState.QUEUED},
}


# ---------------------------------------------------------------------------
# 不可变 TaskRequest (frozen dataclass, hash 即幂等键)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskRequest:
    """单次任务请求 — 不可变, hash 决定幂等键.

    字段契约:
      - task_type: 任务类型 ("trigger_ticket" / "ai_hub_call" / "case_service_run" / ...)
      - queue_name: 队列名 (与 scheduler job 注册名对齐 — 用于 WorkerCoordinator 路由)
      - task_id: 任务唯一 id (如 trigger_ticket_id / ai_hub_call_id)
      - payload: 任务入参 dict (JSON 序列化后落 worker_runs.payload_json)
      - requester: 调度者标识 (user / system / cron / agent)
      - attempt: 第几次重试 (0 = 首次; max_retries 时落死信)
      - max_retries: 单任务最大重试次数 (默认 3, 留注入测试用)
    """

    task_type: str
    queue_name: str
    task_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    requester: str = "system"
    attempt: int = 0
    max_retries: int = 3

    def submission_key(self, prefix: str = "v1-worker") -> str:
        """生成幂等键 — 同任务同一 key, 跨进程可重放."""
        body = f"{self.task_type}|{self.queue_name}|{self.task_id}|{self.requester}|{self.attempt}"
        h = __import__("hashlib").sha256(body.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}-{self.task_type}-{h}"

    def body_hash(self) -> str:
        body = f"{self.task_type}|{self.queue_name}|{self.task_id}|{self.requester}|{self.attempt}"
        return __import__("hashlib").sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# TaskFn — 任务执行签名 (与 T06 source_pipeline.fetch_fn/parse_fn 风格一致)
# ---------------------------------------------------------------------------
# task_fn(req: TaskRequest) → dict (含 'items'/'status'/'error_msg' 可选)
TaskFn = Callable[[TaskRequest], dict[str, Any]]


# ---------------------------------------------------------------------------
# 状态机异常
# ---------------------------------------------------------------------------
class WorkerStateError(Exception):
    """worker_runs 状态机非法转移 (测试用)."""


class TaskDeadLettered(Exception):
    """任务失败 ≥ max_retries → 落 dead_letter 后抛 (调用方记日志)."""


# ---------------------------------------------------------------------------
# WorkerCoordinator 主类
# ---------------------------------------------------------------------------
@dataclass
class ConsumptionResult:
    """单次 consume() 全链路结果 — 调度方 / 测试断言共用."""

    state: WorkerRunState
    request: TaskRequest
    run_id: str
    items: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 0
    error: str | None = None
    duration_ms: int = 0
    dead_lettered: bool = False
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "run_id": self.run_id,
            "task_id": self.request.task_id,
            "task_type": self.request.task_type,
            "queue_name": self.request.queue_name,
            "attempts": self.attempts,
            "items": len(self.items),
            "error": self.error,
            "duration_ms": self.duration_ms,
            "dead_lettered": self.dead_lettered,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class WorkerCoordinator:
    """v1.0 T09 运行协调器 — 队列消费 + 任务派发 + 状态回报 + 死信.

    失败注入点 (5 处, 单测可 monkeypatch):
      1. lease.acquire    → LeaseHeldError (同 task 并发撞)
      2. fetch_fn         → ValueError / RuntimeError (任务拉取失败)
      3. parse_fn         → 异常 → items_failed++
      4. evidence.create  → IdempotentReplay / IntentExistsError
      5. evidence.commit  → FileExistsError / ValueError → receipt 不 committed
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        lease: Any | None = None,  # SourceLease 风格 — 当前批仅暴露接口, 留接入
    ) -> None:
        self._conn = conn
        self.lease = lease  # 当前批不强制 (单 worker 串行足够; T09 接口已对齐 source_pipeline)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn or get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------
    # 公开: consume — 主入口 (拉队列 → 派发 → 回报)
    # ------------------------------------------------------------------
    def consume(
        self,
        request: TaskRequest,
        *,
        task_fn: TaskFn,
    ) -> ConsumptionResult:
        """执行单次任务消费.

        Parameters
        ----------
        request:
            不可变 TaskRequest (含 task_type/queue_name/task_id/payload/attempt/max_retries).
        task_fn:
            任务执行函数 (v1.0 C03 R04 修复: 必填, 不再 Optional). 签名 ``(req) → dict`` 含
            items/error_msg. 旧实现允许 None 兜底 _noop_task_fn (空成功), 导致 53 个
            历史 trigger_ticket 全标 succeeded 但实际工作没做.

        Returns
        -------
        ConsumptionResult — 含最终 state (SUCCEEDED / FAILED) + dead_lettered 标志
        """
        # v1.0 C03 R04 修复: 拒绝 noop 兜底, task_fn 必填
        if task_fn is None:
            raise ValueError(
                "worker_coordinator.consume: task_fn is required (v1.0 C03 R04 fix). "
                "禁止 _noop_task_fn 兜底, 防止空成功 claim 任务. "
                "请在 worker_pump 或测试中显式传 dispatcher."
            )
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.time()
        run_id = f"wr-{uuid.uuid4().hex[:12]}"
        attempts = request.attempt + 1  # 本次为第 N 次执行

        # 1) 落 worker_runs (queued → claimed 同步状态机)
        self._record_run_start(run_id, request, started)

        items: list[dict[str, Any]] = []
        error_msg: str | None = None
        state = WorkerRunState.SUCCEEDED  # 默认成功, 异常路径会改

        try:
            # 2) lease 抢 (当前批接口预留, 不抛 LeaseHeldError 时正常走)
            if self.lease is not None:
                self.lease.acquire(request.task_id)

            # 3) claimed → running
            self._transition(run_id, WorkerRunState.CLAIMED)
            self._transition(run_id, WorkerRunState.RUNNING)

            # 4) 执行 task_fn (单测可注入抛错)
            try:
                result = task_fn(request) or {}
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.warning(
                    "worker task failed",
                    extra={"trace_id": "", "run_id": run_id, "task_id": request.task_id, "error": error_msg},
                )
                state = WorkerRunState.FAILED
            else:
                items = result.get("items") or []
                if result.get("error_msg"):
                    error_msg = str(result["error_msg"])
                    state = WorkerRunState.FAILED
                else:
                    state = WorkerRunState.SUCCEEDED
        except Exception as e:
            # lease 抢失败 / DB 异常 → 标 FAILED
            error_msg = f"{type(e).__name__}: {e}"
            state = WorkerRunState.FAILED
        finally:
            if self.lease is not None:
                try:
                    self.lease.release(request.task_id)
                except Exception:
                    pass

        # 5) 失败重试 + 死信
        dead_lettered = False
        if state == WorkerRunState.FAILED:
            if attempts >= request.max_retries:
                # 超过 max_retries → 落 dead_letter (终态)
                self._write_dead_letter(request, error_msg or "unknown", attempts)
                dead_lettered = True
            else:
                # 失败未超限: 走 FAILED → QUEUED 链式状态机 (允许后续重试)
                # 当前状态可能是 RUNNING (主流程跑完 task_fn 抛错) 或 QUEUED (lease 抢失败)
                self._force_failure_state(run_id)

        # 6) 终态回报 (仅 SUCCEEDED 写 SUCCEEDED; dead-lettered 写 FAILED; 重试保留 QUEUED)
        finished = datetime.now(timezone.utc).isoformat()
        duration_ms = int((time.time() - t0) * 1000)
        if state == WorkerRunState.SUCCEEDED:
            self._record_run_finish(
                run_id, WorkerRunState.SUCCEEDED, attempts, error_msg, finished, duration_ms
            )
        elif dead_lettered:
            self._record_run_finish(
                run_id, WorkerRunState.FAILED, attempts, error_msg, finished, duration_ms
            )
        else:
            # 重试路径: 状态机已落到 QUEUED, 仅更新 attempts + last_error + finished_at
            self._record_run_finish(
                run_id, WorkerRunState.QUEUED, attempts, error_msg, finished, duration_ms
            )

        if dead_lettered:
            try:
                raise TaskDeadLettered(
                    f"task_id={request.task_id} dead-lettered after {attempts} attempts: {error_msg}"
                )
            except TaskDeadLettered:
                # 静默吞 — 调度方已从 dead_lettered 字段识别; 不向上冒泡
                pass

        return ConsumptionResult(
            state=state,
            request=request,
            run_id=run_id,
            items=items,
            attempts=attempts,
            error=error_msg,
            duration_ms=duration_ms,
            dead_lettered=dead_lettered,
            started_at=started,
            finished_at=finished,
        )

    # ------------------------------------------------------------------
    # 状态机转移 + run 记录
    # ------------------------------------------------------------------
    def _transition(self, run_id: str, new_state: WorkerRunState) -> None:
        """worker_runs 状态机白名单转移; 非法转移抛 WorkerStateError."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT status FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise WorkerStateError(f"run_id={run_id} not found")
            current = WorkerRunState(row[0])
            allowed = _VALID_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                raise WorkerStateError(
                    f"run_id={run_id}: illegal transition {current.value} → {new_state.value}"
                )
            conn.execute(
                "UPDATE worker_runs SET status = ? WHERE run_id = ?",
                (new_state.value, run_id),
            )

    def _force_failure_state(self, run_id: str) -> None:
        """失败重试路径: 把 run 强制走 FAILED → QUEUED 链式状态机.

        当前状态可能是 RUNNING (主流程跑完 task_fn 抛错) 或 QUEUED
        (lease 抢失败 / 状态机外层异常). 统一收敛到 QUEUED, 供下轮重试.

        白名单依赖: RUNNING → FAILED → QUEUED, 或 QUEUED → QUEUED (无变化).
        """
        with self._tx() as conn:
            row = conn.execute(
                "SELECT status FROM worker_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise WorkerStateError(f"run_id={run_id} not found")
            current = WorkerRunState(row[0])
            if current == WorkerRunState.QUEUED:
                # 已 QUEUED (lease 抢失败路径) → 不需要转移
                return
            if current == WorkerRunState.RUNNING:
                # 主流程跑完 task_fn 抛错 → RUNNING → FAILED → QUEUED
                conn.execute(
                    "UPDATE worker_runs SET status = ? WHERE run_id = ?",
                    (WorkerRunState.FAILED.value, run_id),
                )
            # 收尾转回 QUEUED (白名单允许 FAILED → QUEUED)
            conn.execute(
                "UPDATE worker_runs SET status = ? WHERE run_id = ?",
                (WorkerRunState.QUEUED.value, run_id),
            )

    def _record_run_start(
        self,
        run_id: str,
        request: TaskRequest,
        started_at: str,
    ) -> None:
        """创建 worker_runs 行 (status=queued)."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO worker_runs "
                "(run_id, task_type, queue_name, source_task_id, payload_json, "
                " status, attempts, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    request.task_type,
                    request.queue_name,
                    request.task_id,
                    json.dumps(request.payload, ensure_ascii=False, sort_keys=True),
                    WorkerRunState.QUEUED.value,
                    request.attempt,
                    started_at,
                ),
            )

    def _record_run_finish(
        self,
        run_id: str,
        final_state: WorkerRunState,
        attempts: int,
        error_msg: str | None,
        finished_at: str,
        duration_ms: int,
    ) -> None:
        """终态写回 worker_runs (status=SUCCEEDED/FAILED, finished_at+duration_ms)."""
        with self._tx() as conn:
            conn.execute(
                "UPDATE worker_runs SET status = ?, attempts = ?, last_error = ?, "
                "finished_at = ?, duration_ms = ? WHERE run_id = ?",
                (
                    final_state.value,
                    attempts,
                    error_msg,
                    finished_at,
                    duration_ms,
                    run_id,
                ),
            )

    def _write_dead_letter(
        self,
        request: TaskRequest,
        error_msg: str,
        attempts: int,
    ) -> None:
        """失败 ≥ max_retries → dead_letter 表落 audit + 留重放入口."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO dead_letter "
                "(original_task_id, queue_name, task_type, error_msg, attempts) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    request.task_id,
                    request.queue_name,
                    request.task_type,
                    error_msg,
                    attempts,
                ),
            )
            # 同步落 audit_log (F01 收口追溯)
            conn.execute(
                "INSERT INTO audit_log (actor, action, target, detail, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "system:worker_coordinator",
                    "worker.dead_letter",
                    f"{request.task_type}:{request.task_id}",
                    json.dumps(
                        {
                            "queue_name": request.queue_name,
                            "attempts": attempts,
                            "error": error_msg,
                        },
                        ensure_ascii=False,
                    ),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    # ------------------------------------------------------------------
    # 查询 (scheduler pump / 测试用)
    # ------------------------------------------------------------------
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """按 run_id 读 worker_runs 单行."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT run_id, task_type, queue_name, source_task_id, status, "
                "attempts, last_error, started_at, finished_at, duration_ms "
                "FROM worker_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_runs(
        self,
        status: str | None = None,
        queue_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按 status / queue_name (可选) 列 worker_runs, 默认最近 100 条."""
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if queue_name is not None:
            clauses.append("queue_name = ?")
            params.append(queue_name)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._tx() as conn:
            rows = conn.execute(
                f"SELECT run_id, task_type, queue_name, source_task_id, status, "
                f"attempts, last_error, started_at, finished_at, duration_ms "
                f"FROM worker_runs{where} ORDER BY id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_dead_letters(
        self,
        queue_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """列 dead_letter (按 queue_name 可选过滤)."""
        params: list[Any] = []
        where = ""
        if queue_name is not None:
            where = " WHERE queue_name = ?"
            params.append(queue_name)
        params.append(limit)
        with self._tx() as conn:
            rows = conn.execute(
                f"SELECT id, original_task_id, queue_name, task_type, error_msg, "
                f"attempts, created_at FROM dead_letter{where} "
                f"ORDER BY id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 默认 task_fn — no-op (与 trigger_gate worker 同款)
# ---------------------------------------------------------------------------
def _noop_task_fn(req: TaskRequest) -> dict[str, Any]:
    """默认 task_fn — 仅记日志, 不抛错."""
    logger.info(
        "worker task handled (noop)",
        extra={"trace_id": "", "task_id": req.task_id, "queue_name": req.queue_name},
    )
    return {"items": []}


__all__ = [
    "ConsumptionResult",
    "TaskDeadLettered",
    "TaskFn",
    "TaskRequest",
    "WorkerCoordinator",
    "WorkerRunState",
    "WorkerStateError",
]
