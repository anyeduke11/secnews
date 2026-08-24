"""Token ledger — record and query LLM token usage per task.

Records every LLM call's token consumption in the token_ledger table
for cost tracking and budget enforcement.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


class TokenLedger:
    """DAO for the ``token_ledger`` table."""

    def __init__(self, db: sqlite3.Connection | None = None) -> None:
        self._db = db

    @property
    def db(self) -> sqlite3.Connection:
        return self._db if self._db is not None else get_connection()

    def record(
        self,
        *,
        task_id: int | None = None,
        item_id: str | None = None,
        model: str = "",
        provider: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Record a single LLM call's token usage."""
        total = prompt_tokens + completion_tokens
        self.db.execute(
            "INSERT INTO token_ledger "
            "(task_id, item_id, model, provider, prompt_tokens, completion_tokens, total_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, item_id, model, provider, prompt_tokens, completion_tokens, total),
        )

    def query(
        self,
        item_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query token usage records."""
        if item_id:
            rows = self.db.execute(
                "SELECT * FROM token_ledger WHERE item_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (item_id, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM token_ledger ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict:
        """Aggregate token usage by model."""
        rows = self.db.execute(
            "SELECT model, provider, "
            "COUNT(*) as calls, "
            "SUM(prompt_tokens) as total_prompt, "
            "SUM(completion_tokens) as total_completion, "
            "SUM(total_tokens) as total_tokens "
            "FROM token_ledger GROUP BY model, provider"
        ).fetchall()
        return [dict(r) for r in rows]
