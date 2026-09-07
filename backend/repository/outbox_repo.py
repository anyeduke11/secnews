"""v1.0 C11 R18: 业务事件 outbox 持久层。

设计目标
--------
- 业务事务写 outbox 行 (与主表 INSERT/UPDATE 在同一 connection 通过 SAVEPOINT 隔离)
- 后台 dispatcher 轮询 ``delivered_at IS NULL`` 段, 广播后置 delivered_at
- SSE 客户端用 ``last_id`` 续传 (list_since 严格按 id 单调)
- 重复/错序事件不直接删除, 通过 delivered_at + payload_hash 让前端去重

与 events.py 的关系
------------------
events.py 进程内订阅者队列保留 (零延迟广播) — outbox 负责持久化+重放, 不替代。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.repo.outbox")

_AGGREGATE_TYPES = {
    "case", "judgment", "action", "run", "artifact", "knowledge", "signal",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OutboxRepo:
    """C11 R18: 业务事件 outbox 持久层。"""

    # ------------------------------------------------------------------
    # enqueue
    # ------------------------------------------------------------------
    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        revision: int = 0,
        trace_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """写入 outbox 行, 返回 id。

        与业务 INSERT/UPDATE 在同一 connection 时, 调用方应已开启事务 (BEGIN
        或外层 wrapper) — 本方法在 autocommit 下也能直接执行 (自身一行
        auto-commit)。
        """
        if aggregate_type not in _AGGREGATE_TYPES:
            raise ValueError(
                f"outbox.enqueue: invalid aggregate_type={aggregate_type!r} "
                f"(expected one of {sorted(_AGGREGATE_TYPES)})"
            )
        if not event_type or not aggregate_id or not trace_id:
            raise ValueError(
                "outbox.enqueue: event_type, aggregate_id, trace_id are required"
            )
        own_conn = conn is None
        c = conn if conn is not None else get_connection()
        try:
            cur = c.execute(
                "INSERT INTO v1_outbox "
                "(event_type, aggregate_type, aggregate_id, revision, "
                "payload_json, trace_id, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    int(revision),
                    json.dumps(payload, ensure_ascii=False, default=str),
                    trace_id,
                    _now_iso(),
                ),
            )
            new_id = cur.lastrowid
            if new_id is None or new_id <= 0:
                # SQLite AUTOINCREMENT 一定返 lastrowid, NULL 视为 schema 异常
                raise RuntimeError(
                    "outbox.enqueue: AUTOINCREMENT returned no id (schema broken?)"
                )
            return int(new_id)
        finally:
            if own_conn:
                # autocommit: pass
                pass

    # ------------------------------------------------------------------
    # query / mark
    # ------------------------------------------------------------------
    def list_since(self, last_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        """返回 id > last_id 的行, 严格按 id 升序 (重放不漏不重)。

        last_id=0 → 拉全部未广播 + 已广播段 (重连时可能含已 delivered 的, 让
        客户端按 id 去重)。
        """
        if last_id < 0:
            last_id = 0
        if limit <= 0 or limit > 500:
            limit = 100
        c = get_connection()
        rows = c.execute(
            "SELECT id, event_type, aggregate_type, aggregate_id, revision, "
            "       payload_json, trace_id, occurred_at, delivered_at "
            "FROM v1_outbox WHERE id > ? "
            "ORDER BY id ASC LIMIT ?",
            (int(last_id), int(limit)),
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_undelivered(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """dispatcher 用: 拉未广播的窗口 (delivered_at IS NULL)。"""
        if limit <= 0 or limit > 500:
            limit = 50
        c = get_connection()
        rows = c.execute(
            "SELECT id, event_type, aggregate_type, aggregate_id, revision, "
            "       payload_json, trace_id, occurred_at, delivered_at "
            "FROM v1_outbox WHERE delivered_at IS NULL "
            "ORDER BY id ASC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [self._row(r) for r in rows]

    def mark_delivered(self, ids: list[int]) -> int:
        """批量置 delivered_at = now。返回更新行数。"""
        if not ids:
            return 0
        # 防 SQL 注入: 仅允许正整数
        clean = [int(i) for i in ids if isinstance(i, int) and i > 0]
        if not clean:
            return 0
        c = get_connection()
        placeholders = ",".join("?" * len(clean))
        cur = c.execute(
            f"UPDATE v1_outbox SET delivered_at = ? "
            f"WHERE id IN ({placeholders}) AND delivered_at IS NULL",
            [_now_iso(), *clean],
        )
        return int(cur.rowcount or 0)

    def count_pending(self) -> int:
        """诊断/监控用: 未广播行数。"""
        c = get_connection()
        row = c.execute(
            "SELECT COUNT(*) FROM v1_outbox WHERE delivered_at IS NULL"
        ).fetchone()
        return int(row[0] or 0)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row(r: sqlite3.Row | tuple) -> dict[str, Any]:
        keys = (
            "id", "event_type", "aggregate_type", "aggregate_id", "revision",
            "payload_json", "trace_id", "occurred_at", "delivered_at",
        )
        if isinstance(r, sqlite3.Row):
            d = {k: r[k] for k in keys}
        else:
            d = dict(zip(keys, r, strict=True))
        # payload 解析 (失败保留原文, 标记 parse_error 不抛)
        try:
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
        except Exception:
            d["payload"] = {}
            d["payload_parse_error"] = True
        return d


__all__ = ["OutboxRepo"]
