"""CommandRepository — command_log (M4 命令栏) 持久化。

v0.8.6 P1-4。命令的 run record: 每条用户命令一行 (原始输入/意图判定/
动作引用/outcome), PRD 用例 B "每次执行写 run record" 的落点; 行动类
命令经审批后再产生 v1_runs (proposal.run_id 关联)。
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.repository.db import get_connection


class CommandRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(
        self, *, cmd_id: str, input_text: str, intent: str | None,
        action_ref: str | None = None, run_id: str | None = None,
        outcome: str | None = None,
    ) -> None:
        self._c().execute(
            "INSERT INTO command_log "
            "(id, input_text, intent, action_ref, run_id, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cmd_id, input_text, intent, action_ref, run_id, outcome),
        )
        self._c().commit()

    def list_commands(
        self, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        total = self._c().execute(
            "SELECT COUNT(*) FROM command_log",
        ).fetchone()[0]
        rows = self._c().execute(
            "SELECT id, input_text, intent, action_ref, run_id, outcome, "
            "created_at FROM command_log "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows], total


# 模块级单例 (与 proposal_repo 同模式)
command_repo = CommandRepository()
