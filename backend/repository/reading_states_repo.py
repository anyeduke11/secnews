"""v1.7 Phase 1 阅读状态仓库 — reading_states 表.

PRD §3.2.5 / §6.5

职责:
- record_open: 打开次数 +1, 更新 last_read_at
- record_dwell: 累加停留时长 (毫秒)
- get: 读取单条阅读状态
- list_recent: 按 last_read_at 倒序, 供"最近阅读"用
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.repository.db import get_connection


@dataclass
class ReadingState:
    entity_type: str
    entity_id: str
    opened_count: int
    dwell_ms: int
    last_read_at: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "opened_count": self.opened_count,
            "dwell_ms": self.dwell_ms,
            "last_read_at": self.last_read_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReadingStateRepository:
    """reading_states 仓库."""

    def get(self, entity_type: str, entity_id: str) -> Optional[ReadingState]:
        row = (
            get_connection()
            .execute(
                "SELECT * FROM reading_states WHERE entity_type=? AND entity_id=?",
                (entity_type, entity_id),
            )
            .fetchone()
        )
        return ReadingState(**dict(row)) if row else None

    def record_open(self, entity_type: str, entity_id: str) -> None:
        """记录一次打开: opened_count +1, last_read_at = now."""
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            """INSERT INTO reading_states
               (entity_type, entity_id, opened_count, dwell_ms, last_read_at, created_at, updated_at)
               VALUES (?, ?, 1, 0, ?, ?, ?)
               ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                   opened_count = opened_count + 1,
                   last_read_at = excluded.last_read_at,
                   updated_at = excluded.updated_at""",
            (entity_type, entity_id, now, now, now),
        )

    def record_dwell(self, entity_type: str, entity_id: str, ms: int) -> None:
        """累加停留时长 (毫秒), 不改变 opened_count."""
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            """INSERT INTO reading_states
               (entity_type, entity_id, opened_count, dwell_ms, last_read_at, created_at, updated_at)
               VALUES (?, ?, 0, ?, ?, ?, ?)
               ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                   dwell_ms = dwell_ms + excluded.dwell_ms,
                   updated_at = excluded.updated_at""",
            (entity_type, entity_id, ms, now, now, now),
        )

    def list_recent(
        self,
        entity_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[ReadingState]:
        sql = "SELECT * FROM reading_states WHERE last_read_at IS NOT NULL"
        params: list = []
        if entity_type:
            sql += " AND entity_type=?"
            params.append(entity_type)
        sql += " ORDER BY last_read_at DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [ReadingState(**dict(r)) for r in rows]
