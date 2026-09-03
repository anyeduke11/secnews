"""agent_loop.checkpoint — loop_checkpoints 表读写 + 崩溃恢复扫描 (B1 R3).

设计纪律 (V0.8_REFACTOR_PLAN.md §5.3 R3 queue-first):
- **每阶段落地一行** — AgentLoop 主循环每进入一阶段先 mark_running
  写 (status, payload=入参); 阶段完成再 mark_terminal 写 (status, payload=输出);
  中间任何进程崩溃都留下 status='running' 的僵尸行。
- **崩溃恢复** — LoopCheckpointRepo.find_stale_running() 扫描
  status='running' 行, 调用方根据 ``payload`` 决定从该阶段的 successor
  续跑 (R6 语义与 trigger_gate 一致, 不修改已落地的状态)。
- **唯一性** — UNIQUE(run_id, phase) 由 DB 强制; 调用方用 INSERT OR REPLACE
  保证崩溃恢复重写 pending/running 时不抛 IntegrityError。

公开 API:
- :class:`LoopCheckpoint` — 内存投影 (run_id + phase + status + payload + error)
- :class:`LoopCheckpointRepo` — 表读写, 方法含 upsert / get / list_for_run /
  find_stale_running / delete_for_run (测试清理)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.agent_loop.state import LoopPhase, LoopStatus

__all__ = ["LoopCheckpoint", "LoopCheckpointRepo"]


@dataclass
class LoopCheckpoint:
    """loop_checkpoints 单行的内存投影。

    payload 为 dict (raw JSON), 调用方在 mark_running / mark_terminal 时
    传 dict, repo 负责 JSON 序列化; 读出时反序列化。空 → None 方便判空。
    """

    run_id: str
    phase: LoopPhase
    status: LoopStatus
    payload: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


def _row_to_checkpoint(row: Any) -> LoopCheckpoint:
    """sqlite3.Row → LoopCheckpoint (payload JSON 反序列化, 防御性容错)。"""
    raw = row["payload"]
    payload: dict[str, Any] | None = None
    if raw:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = None
    return LoopCheckpoint(
        run_id=row["run_id"],
        phase=LoopPhase(row["phase"]),
        status=LoopStatus(row["status"]),
        payload=payload,
        error=row["error"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


class LoopCheckpointRepo:
    """loop_checkpoints 表的持久化门面 — 无状态, 全部即时走库。

    设计要点 (与 trigger_gate.queue 同源):
    - mark_running / mark_terminal 走 INSERT OR REPLACE, DB UNIQUE 约束
      保证同一 (run_id, phase) 唯一行, 重写即覆盖。
    - find_stale_running 扫描 status='running' 行, 不加时间条件 — 调用方
      按"运行时间 > 阈值"决策; DB 没存运行起始时间 (created_at 即落地时间),
      由调用方补 stale_seconds 派生。
    """

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def mark_running(
        self,
        run_id: str,
        phase: LoopPhase,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """写 running 行 — INSERT OR REPLACE (崩溃后 re-enter 同一 phase 不爆)。"""
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO loop_checkpoints "
            "(run_id, phase, status, payload, error, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, NULL, "
            "COALESCE((SELECT created_at FROM loop_checkpoints "
            "          WHERE run_id=? AND phase=?), datetime('now','localtime')), "
            "NULL)",
            (
                run_id,
                phase.value,
                LoopStatus.RUNNING.value,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                run_id,
                phase.value,
            ),
        )

    def mark_terminal(
        self,
        run_id: str,
        phase: LoopPhase,
        status: LoopStatus,
        *,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """写终态行 (succeeded/partial/failed/skipped), completed_at 取 DB now。

        status 防御: 非终态 (pending/running) 拒绝写入, 防止循环依赖状态机
        写脏数据 (R12 fail-loud)。
        """
        if status not in (
            LoopStatus.SUCCEEDED,
            LoopStatus.PARTIAL,
            LoopStatus.FAILED,
            LoopStatus.SKIPPED,
        ):
            raise ValueError(
                f"mark_terminal 只接受终态 status, 收到 {status.value!r}"
            )
        conn = get_connection()
        # 终态重写时保留 created_at (同 mark_running), 改 completed_at
        conn.execute(
            "INSERT OR REPLACE INTO loop_checkpoints "
            "(run_id, phase, status, payload, error, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, "
            "COALESCE((SELECT created_at FROM loop_checkpoints "
            "          WHERE run_id=? AND phase=?), datetime('now','localtime')), "
            "datetime('now','localtime'))",
            (
                run_id,
                phase.value,
                status.value,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                error,
                run_id,
                phase.value,
            ),
        )
        logger.debug(
            "agent_loop checkpoint terminal",
            extra={
                "trace_id": "",
                "run_id": run_id,
                "phase": phase.value,
                "status": status.value,
            },
        )

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, run_id: str, phase: LoopPhase) -> LoopCheckpoint | None:
        """按 (run_id, phase) 读单行; 不存在返回 None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT run_id, phase, status, payload, error, created_at, completed_at "
            "FROM loop_checkpoints WHERE run_id=? AND phase=?",
            (run_id, phase.value),
        ).fetchone()
        return _row_to_checkpoint(row) if row is not None else None

    def list_for_run(self, run_id: str) -> list[LoopCheckpoint]:
        """按 run 拉全部阶段行, 按 phase 状态机定义序 (DB 索引扫描稳定)。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT run_id, phase, status, payload, error, created_at, completed_at "
            "FROM loop_checkpoints WHERE run_id=? ORDER BY phase ASC",
            (run_id,),
        ).fetchall()
        return [_row_to_checkpoint(r) for r in rows]

    def find_stale_running(self) -> list[LoopCheckpoint]:
        """扫 status='running' 行 — 调用方按 created_at 决定续跑起点。

        不在 SQL 内加时间过滤, 让调用方决定 stale 阈值; 跨进程语义下
        "运行超过 N 秒" 是策略, 不是 schema 约束。
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT run_id, phase, status, payload, error, created_at, completed_at "
            "FROM loop_checkpoints WHERE status='running' "
            "ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_checkpoint(r) for r in rows]

    def delete_for_run(self, run_id: str) -> int:
        """按 run 清空全部阶段行 — 测试清理 / 重新跑场景。返回删除行数。"""
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM loop_checkpoints WHERE run_id=?", (run_id,)
        )
        return cur.rowcount
