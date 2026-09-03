"""trigger-gate 持久化队列 — trigger_tickets 表读写 (v0.8 Phase A R3).

队列即表: 所有状态流转都落在 SQLite ``trigger_tickets`` 行上,
进程重启后票据仍在 (queue-first), 崩溃恢复靠 ``reset_stale_running``。

核心原语 — **原子出队** (并发安全的关键):

    1. SELECT id ... WHERE status='pending' ORDER BY priority ASC, id ASC LIMIT 1
    2. UPDATE ... SET status='running' WHERE id=? AND status='pending'
    3. rowcount == 1 → 抢到 (读整行返回); rowcount == 0 → 被并发线程抢走, 返回 None

第 2 步的 ``AND status='pending'`` 是防御核心: 两个线程 SELECT 到
同一个 id 时, 后执行 UPDATE 的那个 rowcount=0, 不会重复消费同一票据
(单进程多线程 / SQLite WAL 下成立, 无需额外锁)。

排序规则 (priority ASC, id ASC): 优先级数字小者先出; 同优先级按
自增 id FIFO。与 ``idx_trigger_tickets_status_priority`` 索引完全对齐。

注意: 本模块**顶部不 import core** (core 顶部 import 本模块, 反向
顶层 import 会成环) — ``TriggerTicket`` 在函数内延迟 import, 与
``backend/api/__init__.py`` 的 lazy import 协议同源。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from backend.logging_config import logger
from backend.repository.db import get_connection

if TYPE_CHECKING:  # 仅类型标注用, 运行时走函数内延迟 import
    from backend.services.trigger_gate.core import TriggerTicket

_TICKET_COLUMNS = (
    "ticket_id, target_type, target_id, priority, source, user_id, "
    "inputs, status, attempts, enqueued_at, started_at, finished_at, error"
)


def _row_to_ticket(row: Any) -> TriggerTicket:
    """sqlite3.Row → TriggerTicket (inputs JSON 反序列化)。"""
    from backend.services.trigger_gate.core import TriggerTicket  # 延迟 import 防环

    raw_inputs = row["inputs"]
    return TriggerTicket(
        ticket_id=row["ticket_id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        priority=row["priority"],
        source=row["source"],
        user_id=row["user_id"],
        inputs=json.loads(raw_inputs) if raw_inputs else None,
        status=row["status"],
        attempts=row["attempts"],
        enqueued_at=row["enqueued_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error"],
    )


class TriggerQueue:
    """trigger_tickets 表的队列原语封装 (无状态, 全部即时走库)。"""

    def enqueue(self, ticket: TriggerTicket) -> None:
        """入队一条 pending 票据 (INSERT, enqueued_at 走 DB 默认值)。"""
        conn = get_connection()
        conn.execute(
            "INSERT INTO trigger_tickets "
            "(ticket_id, target_type, target_id, priority, source, user_id, inputs, status, attempts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticket.ticket_id,
                ticket.target_type,
                ticket.target_id,
                int(ticket.priority),
                ticket.source,
                ticket.user_id,
                json.dumps(ticket.inputs, ensure_ascii=False) if ticket.inputs is not None else None,
                ticket.status,
                ticket.attempts,
            ),
        )
        logger.debug(
            "trigger ticket enqueued",
            extra={"trace_id": "", "ticket_id": ticket.ticket_id, "priority": int(ticket.priority)},
        )

    def dequeue(self) -> TriggerTicket | None:
        """原子取一条最高优先级 pending 票据置 running; 队列空/被抢走 → None。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM trigger_tickets WHERE status='pending' "
            "ORDER BY priority ASC, id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        # WHERE 带 status='pending' 双保险: 并发线程先抢到时 rowcount=0 → 放弃本轮
        cur = conn.execute(
            "UPDATE trigger_tickets SET status='running', started_at=datetime('now','localtime') "
            "WHERE id=? AND status='pending'",
            (row["id"],),
        )
        if cur.rowcount != 1:
            return None
        claimed = conn.execute(
            f"SELECT {_TICKET_COLUMNS} FROM trigger_tickets WHERE id=?", (row["id"],)
        ).fetchone()
        ticket = _row_to_ticket(claimed)
        logger.debug("trigger ticket dequeued", extra={"trace_id": "", "ticket_id": ticket.ticket_id})
        return ticket

    def mark_done(self, ticket_id: str) -> bool:
        """票据执行成功 → done (写 finished_at); 返回是否命中。"""
        conn = get_connection()
        cur = conn.execute(
            "UPDATE trigger_tickets SET status='done', finished_at=datetime('now','localtime') "
            "WHERE ticket_id=?",
            (ticket_id,),
        )
        return cur.rowcount == 1

    def mark_failed(self, ticket_id: str, error: str) -> bool:
        """票据执行失败 → failed (error 落库 + finished_at); 返回是否命中。"""
        conn = get_connection()
        cur = conn.execute(
            "UPDATE trigger_tickets SET status='failed', error=?, "
            "finished_at=datetime('now','localtime') WHERE ticket_id=?",
            (error, ticket_id),
        )
        return cur.rowcount == 1

    def reset_stale_running(self, stale_seconds: float) -> int:
        """启动恢复: 超时 running → pending + attempts+1, 返回重置条数。

        只碰 running (崩溃/进程被杀留下的僵尸票据), pending/done/failed
        一律不动 — pending 没有起始时间语义, 不存在"过期"。
        """
        conn = get_connection()
        modifier = f"-{int(stale_seconds)} seconds"
        cur = conn.execute(
            "UPDATE trigger_tickets SET status='pending', attempts=attempts+1, started_at=NULL "
            "WHERE status='running' AND started_at IS NOT NULL "
            "AND started_at < datetime('now','localtime', ?)",
            (modifier,),
        )
        if cur.rowcount:
            logger.warning(
                "reset stale running tickets",
                extra={"trace_id": "", "count": cur.rowcount, "stale_seconds": stale_seconds},
            )
        return cur.rowcount

    def get(self, ticket_id: str) -> TriggerTicket | None:
        """按 ticket_id 读单条票据 (测试 / API 查询用)。"""
        conn = get_connection()
        row = conn.execute(
            f"SELECT {_TICKET_COLUMNS} FROM trigger_tickets WHERE ticket_id=?", (ticket_id,)
        ).fetchone()
        return _row_to_ticket(row) if row is not None else None

    def list_tickets(self, status: str | None = None, limit: int = 100) -> list[TriggerTicket]:
        """按状态 (可选) 列票据, 默认最近 100 条。"""
        conn = get_connection()
        if status is None:
            rows = conn.execute(
                f"SELECT {_TICKET_COLUMNS} FROM trigger_tickets ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_TICKET_COLUMNS} FROM trigger_tickets WHERE status=? "
                "ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [_row_to_ticket(r) for r in rows]

    def stats(self) -> dict[str, int]:
        """按 status 统计条数 (四个键恒存在, 缺省补 0)。"""
        conn = get_connection()
        counts = {"pending": 0, "running": 0, "done": 0, "failed": 0}
        for row in conn.execute(
            "SELECT status, COUNT(*) AS c FROM trigger_tickets GROUP BY status"
        ).fetchall():
            if row["status"] in counts:
                counts[row["status"]] = row["c"]
        return counts


__all__ = ["TriggerQueue"]
