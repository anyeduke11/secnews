"""KL Queue DAO — kl_queue table operations.

Design notes:
- ISO-8601 UTC strings for datetime columns (matches hotspot_repo pattern).
- Autocommit mode: explicit BEGIN/COMMIT/ROLLBACK.
- enqueue_unique is idempotent via UNIQUE(item_id, stage).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from backend.repository.db import get_connection

# Stage ordering for advancement.
STAGES = ("kl:raw", "kl:refine", "kl:link", "kl:structure", "kl:publish")

# 失败重试退避基数 (秒): 第 n 次尝试后等 BASE * 2^(n-1)
RETRY_BACKOFF_BASE_S = 300


class KLQueue:
    """DAO for the ``kl_queue`` table."""

    def __init__(self, db: sqlite3.Connection | None = None) -> None:
        self._db = db

    @property
    def db(self) -> sqlite3.Connection:
        return self._db if self._db is not None else get_connection()

    def enqueue_unique(self, item_id: str, stage: str, next_run: datetime) -> bool:
        """Idempotent enqueue.

        Returns True when the row was newly inserted **or** an existing
        ``error`` row was re-armed for another attempt. A plain ``pending``
        row only gets its ``next_run_at`` nudged and returns False —
        otherwise :meth:`backend.kl_pipeline.engine.KLPipeline.sweep` would
        report an ordinary re-schedule as a self-heal.

        撞 UNIQUE 后原本带 ``AND status = 'pending'`` 的 UPDATE 对 error 行恒为
        no-op → error 任务既不会被重试也不会被兜底重排救回。现在 error 行会被
        重新武装 (清 last_error), 正在 running 的行不动, 避免抢占执行中的任务。
        """
        next_run_iso = next_run.isoformat()
        try:
            self.db.execute(
                "INSERT INTO kl_queue (item_id, stage, next_run_at) VALUES (?, ?, ?)",
                (item_id, stage, next_run_iso),
            )
            return True
        except sqlite3.IntegrityError:
            recovered = self.db.execute(
                "UPDATE kl_queue SET next_run_at = ?, status = 'pending', "
                "last_error = NULL, updated_at = datetime('now') "
                "WHERE item_id = ? AND stage = ? AND status = 'error'",
                (next_run_iso, item_id, stage),
            )
            if recovered.rowcount > 0:
                return True
            self.db.execute(
                "UPDATE kl_queue SET next_run_at = ?, updated_at = datetime('now') "
                "WHERE item_id = ? AND stage = ? AND status = 'pending'",
                (next_run_iso, item_id, stage),
            )
            return False

    def due(self, limit: int = 20) -> list[dict]:
        """Return tasks where status=pending AND next_run_at <= now."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self.db.execute(
            "SELECT id, item_id, stage, attempts, max_attempts, next_run_at "
            "FROM kl_queue "
            "WHERE status = 'pending' AND next_run_at <= ? "
            "ORDER BY priority DESC, next_run_at ASC "
            "LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_run(self, queue_id: int) -> None:
        self.db.execute(
            "UPDATE kl_queue SET status = 'running', attempts = attempts + 1, "
            "updated_at = datetime('now') WHERE id = ?",
            (queue_id,),
        )

    def mark_done(self, queue_id: int) -> None:
        """Completed — delete the row."""
        self.db.execute("DELETE FROM kl_queue WHERE id = ?", (queue_id,))

    def mark_error(self, queue_id: int, error: str) -> str:
        """Record a failure. Returns ``"retry"`` or ``"terminal"``.

        失败必须有出口。历史实现只写 ``status='error'`` 且不动 ``next_run_at``,
        而 :meth:`due` 只取 ``status='pending'`` → 出错任务永久搁死 (实测 2 项卡
        2-3 天, ``attempts`` 永远停在 1/5, ``max_attempts`` 从未被任何非测试代码
        比较过)。现在:

        - ``attempts < max_attempts`` → 回 pending, 按指数退避推迟 next_run_at
        - ``attempts >= max_attempts`` → error 终态, 由调用方落死信待人工处理
        """
        row = self.db.execute(
            "SELECT attempts, max_attempts FROM kl_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
        attempts = int(dict(row)["attempts"]) if row else 0
        max_attempts = int(dict(row)["max_attempts"]) if row else 5

        if attempts < max_attempts:
            delay_s = RETRY_BACKOFF_BASE_S * (2 ** max(0, attempts - 1))
            next_run = (datetime.now(timezone.utc) + timedelta(seconds=delay_s)).isoformat()
            self.db.execute(
                "UPDATE kl_queue SET status = 'pending', last_error = ?, "
                "next_run_at = ?, updated_at = datetime('now') WHERE id = ?",
                (error, next_run, queue_id),
            )
            return "retry"

        self.db.execute(
            "UPDATE kl_queue SET status = 'error', last_error = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (error, queue_id),
        )
        return "terminal"

    def stats(self) -> dict:
        """Count by status."""
        rows = self.db.execute(
            "SELECT status, COUNT(*) as cnt FROM kl_queue GROUP BY status"
        ).fetchall()
        result = {"pending": 0, "running": 0, "error": 0}
        for r in rows:
            result[r["status"]] = r["cnt"]
        return result

    def errors(self, limit: int = 50) -> list[dict]:
        """Return error tasks for the dead-letter view."""
        rows = self.db.execute(
            "SELECT id, item_id, stage, attempts, last_error, updated_at "
            "FROM kl_queue WHERE status = 'error' "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def reset_errors(self, wiki_id: str | None = None) -> int:
        """Reset error tasks to pending — returns count reset."""
        if wiki_id:
            cur = self.db.execute(
                "UPDATE kl_queue SET status = 'pending', last_error = NULL, "
                "next_run_at = datetime('now'), updated_at = datetime('now') "
                "WHERE status = 'error' AND item_id = ?",
                (wiki_id,),
            )
        else:
            cur = self.db.execute(
                "UPDATE kl_queue SET status = 'pending', last_error = NULL, "
                "next_run_at = datetime('now'), updated_at = datetime('now') "
                "WHERE status = 'error'"
            )
        return cur.rowcount
