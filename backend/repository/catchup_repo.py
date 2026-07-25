"""v1.8 Phase 8 — 追抓资讯历史仓库: catchup_runs CRUD.

设计要点
--------
- 独立于 collection_runs, 职责清晰: 实时采集 vs 用户主动追抓
- 状态机: running -> {success, partial, failed, aborted}
- 不允许从 terminal 状态回 running (校验在 service 层)
- 同步 DB 操作 (走 thread-local connection), 与 hotspot 项目其他 repo 一致
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
class CatchupStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"

    @property
    def is_terminal(self) -> bool:
        """终态: success / partial / failed / aborted"""
        return self in (CatchupStatus.SUCCESS, CatchupStatus.PARTIAL, CatchupStatus.FAILED, CatchupStatus.ABORTED)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------
@dataclass
class CatchupRun:
    id: int
    mode: str
    since_window: str
    until_window: Optional[str]
    categories: list[str]
    max_per_source: int
    started_at: str
    finished_at: Optional[str]
    status: str
    items_ingested: int = 0
    items_skipped: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    error_msg: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mode": self.mode,
            "since_window": self.since_window,
            "until_window": self.until_window,
            "categories": self.categories,
            "max_per_source": self.max_per_source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "items_ingested": self.items_ingested,
            "items_skipped": self.items_skipped,
            "sources_attempted": self.sources_attempted,
            "sources_succeeded": self.sources_succeeded,
            "error_msg": self.error_msg,
            "duration_ms": self.duration_ms,
            "duration_s": round(self.duration_ms / 1000, 1) if self.duration_ms else 0,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_run(row: sqlite3.Row) -> CatchupRun:
    return CatchupRun(
        id=int(row["id"]),
        mode=str(row["mode"]),
        since_window=str(row["since_window"]),
        until_window=str(row["until_window"]) if row["until_window"] else None,
        categories=json.loads(row["categories"]) if row["categories"] else [],
        max_per_source=int(row["max_per_source"]),
        started_at=str(row["started_at"]),
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
        status=str(row["status"]),
        items_ingested=int(row["items_ingested"]),
        items_skipped=int(row["items_skipped"]),
        sources_attempted=int(row["sources_attempted"]),
        sources_succeeded=int(row["sources_succeeded"]),
        error_msg=str(row["error_msg"]) if row["error_msg"] else None,
        duration_ms=int(row["duration_ms"]),
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class CatchupRepository:
    """对 ``catchup_runs`` 表的 CRUD."""

    def create(
        self,
        *,
        mode: str,
        since_window: str,
        until_window: Optional[str],
        categories: list[str],
        max_per_source: int,
    ) -> CatchupRun:
        """创建 running 状态行, 返回完整对象."""
        if mode not in ("auto", "manual"):
            raise ValueError(f"invalid mode: {mode}")
        now = _now_iso()
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO catchup_runs
                (mode, since_window, until_window, categories, max_per_source,
                 started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'running')
            """,
            (mode, since_window, until_window, json.dumps(categories), max_per_source, now),
        )
        new_id = int(cur.lastrowid)
        return CatchupRun(
            id=new_id,
            mode=mode,
            since_window=since_window,
            until_window=until_window,
            categories=categories,
            max_per_source=max_per_source,
            started_at=now,
            finished_at=None,
            status="running",
        )

    def get(self, run_id: int) -> Optional[CatchupRun]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM catchup_runs WHERE id = ?", (int(run_id),)
        ).fetchone()
        return _row_to_run(row) if row else None

    def get_current_running(self) -> Optional[CatchupRun]:
        """当前在跑的 (status='running'). 一次只允许一个 manual, 但 auto 优先级低, 可能共存."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM catchup_runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return _row_to_run(row) if row else None

    def list_recent(self, limit: int = 7) -> list[CatchupRun]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM catchup_runs ORDER BY started_at DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [_row_to_run(r) for r in rows]

    def update_progress(
        self,
        run_id: int,
        *,
        items_ingested: Optional[int] = None,
        items_skipped: Optional[int] = None,
        sources_attempted: Optional[int] = None,
        sources_succeeded: Optional[int] = None,
    ) -> None:
        """增量更新 progress, 状态保持 running."""
        conn = get_connection()
        sets = []
        params: list = []
        if items_ingested is not None:
            sets.append("items_ingested = ?")
            params.append(int(items_ingested))
        if items_skipped is not None:
            sets.append("items_skipped = ?")
            params.append(int(items_skipped))
        if sources_attempted is not None:
            sets.append("sources_attempted = ?")
            params.append(int(sources_attempted))
        if sources_succeeded is not None:
            sets.append("sources_succeeded = ?")
            params.append(int(sources_succeeded))
        if not sets:
            return
        params.append(int(run_id))
        conn.execute(
            f"UPDATE catchup_runs SET {', '.join(sets)} WHERE id = ? AND status = 'running'",
            tuple(params),
        )

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        items_ingested: int,
        items_skipped: int,
        sources_attempted: int,
        sources_succeeded: int,
        error_msg: Optional[str] = None,
    ) -> None:
        """终态化: status ∈ {success, partial, failed, aborted}."""
        if status not in ("success", "partial", "failed", "aborted"):
            raise ValueError(f"invalid terminal status: {status}")
        conn = get_connection()
        now = _now_iso()
        # 计算 duration_ms
        row = conn.execute(
            "SELECT started_at FROM catchup_runs WHERE id = ?", (int(run_id),)
        ).fetchone()
        if not row:
            return
        try:
            started = datetime.fromisoformat(row["started_at"])
            finished = datetime.fromisoformat(now)
            duration_ms = int((finished - started).total_seconds() * 1000)
        except Exception:
            duration_ms = 0
        conn.execute(
            """
            UPDATE catchup_runs SET
                finished_at = ?,
                status = ?,
                items_ingested = ?,
                items_skipped = ?,
                sources_attempted = ?,
                sources_succeeded = ?,
                error_msg = ?,
                duration_ms = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                now, status, int(items_ingested), int(items_skipped),
                int(sources_attempted), int(sources_succeeded),
                error_msg, duration_ms, int(run_id),
            ),
        )

    def abort(self, run_id: int) -> bool:
        """尝试中止一个 running run. 成功返回 True (status='aborted')."""
        conn = get_connection()
        now = _now_iso()
        cur = conn.execute(
            """
            UPDATE catchup_runs SET
                status = 'aborted', finished_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (now, int(run_id)),
        )
        return cur.rowcount > 0


__all__ = ["CatchupRepository", "CatchupRun", "CatchupStatus"]
