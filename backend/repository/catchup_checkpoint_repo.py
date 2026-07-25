"""v1.9 Phase 9 — Per-source 断点续传仓库.

设计
----
- 复用 catchup_runs (run 级别), 追加 catchup_checkpoints (per-source 级别)
- 主键 (run_id, category, source_name) → 一源一行
- 状态: pending / done / failed / skipped
- 重试策略: 同一 source_name 在最近 N run 内 status='done' → 跳过

调用方
------
- catchup_service._execute_catchup_run: 每个 source 开始前 upsert(pending),
  完成后 upsert(done/failed).
- 续传查询: list_recent_done(category, source_name, since_run_id, limit) → 跨 run 续传.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from backend.repository.db import get_connection


class CheckpointStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # 跨 run 已 done, 本 run 跳过


@dataclass
class Checkpoint:
    id: int
    run_id: int
    category: str
    source_name: str
    status: str
    items_count: int
    started_at: Optional[str]
    finished_at: Optional[str]
    error_msg: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "category": self.category,
            "source_name": self.source_name,
            "status": self.status,
            "items_count": self.items_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_msg": self.error_msg,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> Checkpoint:
    return Checkpoint(
        id=int(row["id"]),
        run_id=int(row["run_id"]),
        category=str(row["category"]),
        source_name=str(row["source_name"]),
        status=str(row["status"]),
        items_count=int(row["items_count"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
        error_msg=str(row["error_msg"]) if row["error_msg"] else None,
    )


class CatchupCheckpointRepository:
    """catchup_checkpoints 表 CRUD."""

    def upsert(
        self,
        *,
        run_id: int,
        category: str,
        source_name: str,
        status: str,
        items_count: int = 0,
        error_msg: Optional[str] = None,
    ) -> int:
        """插入或更新一条 checkpoint.

        - 第一次: INSERT (status=pending, items_count=0, started_at=now)
        - 后续: UPDATE status/items_count/finished_at/error_msg
        - 返回 rowid (INSERT 时) 或已有 id (UPDATE 时)
        """
        if status not in ("pending", "done", "failed", "skipped"):
            raise ValueError(f"invalid checkpoint status: {status}")
        conn = get_connection()
        now = _now_iso()
        # 先查
        existing = conn.execute(
            """
            SELECT id FROM catchup_checkpoints
            WHERE run_id = ? AND category = ? AND source_name = ?
            """,
            (int(run_id), str(category), str(source_name)),
        ).fetchone()
        if existing is None:
            cur = conn.execute(
                """
                INSERT INTO catchup_checkpoints
                    (run_id, category, source_name, status, items_count,
                     started_at, finished_at, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(run_id), str(category), str(source_name), str(status),
                    int(items_count),
                    now if status != "pending" else now,
                    now if status in ("done", "failed", "skipped") else None,
                    error_msg,
                ),
            )
            return int(cur.lastrowid)
        # UPDATE
        finished_clause = ", finished_at = ?" if status in ("done", "failed", "skipped") else ""
        params: list = [str(status), int(items_count), error_msg]
        sql = f"""
            UPDATE catchup_checkpoints
            SET status = ?, items_count = ?, error_msg = ?
            {finished_clause}
            WHERE id = ?
        """
        if finished_clause:
            params.insert(2, now)  # error_msg 在 finished_at 之后? 调整顺序
        # 重写清晰版
        if status in ("done", "failed", "skipped"):
            conn.execute(
                """
                UPDATE catchup_checkpoints
                SET status = ?, items_count = ?, error_msg = ?, finished_at = ?
                WHERE id = ?
                """,
                (str(status), int(items_count), error_msg, now, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                UPDATE catchup_checkpoints
                SET status = ?, items_count = ?, error_msg = ?
                WHERE id = ?
                """,
                (str(status), int(items_count), error_msg, int(existing["id"])),
            )
        return int(existing["id"])

    def get(
        self, run_id: int, category: str, source_name: str
    ) -> Optional[Checkpoint]:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT * FROM catchup_checkpoints
            WHERE run_id = ? AND category = ? AND source_name = ?
            """,
            (int(run_id), str(category), str(source_name)),
        ).fetchone()
        return _row(row) if row else None

    def list_for_run(self, run_id: int) -> list[Checkpoint]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM catchup_checkpoints WHERE run_id = ? ORDER BY category, source_name",
            (int(run_id),),
        ).fetchall()
        return [_row(r) for r in rows]

    def count_for_run(self, run_id: int, status: Optional[str] = None) -> int:
        """统计某 run 的 checkpoint 数 (按 status 过滤)."""
        conn = get_connection()
        if status is None:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM catchup_checkpoints WHERE run_id = ?",
                (int(run_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM catchup_checkpoints WHERE run_id = ? AND status = ?",
                (int(run_id), str(status)),
            ).fetchone()
        return int(row["c"]) if row else 0

    def list_recent_done(
        self,
        category: str,
        source_name: str,
        *,
        since_iso: Optional[str] = None,
        limit: int = 1,
    ) -> list[Checkpoint]:
        """跨 run 查询: 找该源最近 N 条 status='done' 的 checkpoint.

        用途: 续传 — 同一 source 在前一个 run 已 done, 本 run 可跳过.
        since_iso: 限定只看 started_at >= since_iso (避免跳过 7 天前的旧 done).
        """
        conn = get_connection()
        if since_iso is None:
            rows = conn.execute(
                """
                SELECT * FROM catchup_checkpoints
                WHERE category = ? AND source_name = ? AND status = 'done'
                ORDER BY finished_at DESC LIMIT ?
                """,
                (str(category), str(source_name), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM catchup_checkpoints
                WHERE category = ? AND source_name = ? AND status = 'done'
                  AND finished_at >= ?
                ORDER BY finished_at DESC LIMIT ?
                """,
                (str(category), str(source_name), str(since_iso), int(limit)),
            ).fetchall()
        return [_row(r) for r in rows]

    def mark_done(
        self,
        run_id: int,
        category: str,
        source_name: str,
        items_count: int,
    ) -> None:
        """便捷方法: 标记 done."""
        self.upsert(
            run_id=run_id,
            category=category,
            source_name=source_name,
            status="done",
            items_count=items_count,
        )

    def mark_failed(
        self,
        run_id: int,
        category: str,
        source_name: str,
        error_msg: str,
    ) -> None:
        self.upsert(
            run_id=run_id,
            category=category,
            source_name=source_name,
            status="failed",
            error_msg=error_msg[:500],
        )

    def mark_skipped(
        self,
        run_id: int,
        category: str,
        source_name: str,
        reason: str = "resumed from prior run",
    ) -> None:
        self.upsert(
            run_id=run_id,
            category=category,
            source_name=source_name,
            status="skipped",
            error_msg=reason,
        )


__all__ = [
    "Checkpoint",
    "CheckpointStatus",
    "CatchupCheckpointRepository",
]
