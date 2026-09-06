"""v1.0 T12 RunRepository — v1_runs 主表CRUD + 幂等检索."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class RunRepository:
    """Run 仓储 — 对齐 contracts §7 字段 + 三层幂等 (§7.4)."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(self, r: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO v1_runs "
            "(id, action_id, attempt, skill_id, protocol, trigger_source, "
            " idempotency_key, status, inputs_json, steps_json, "
            " budget_tokens, budget_seconds, started_at, finished_at, duration_ms, "
            " result_excerpt, error, artifact_ids_json, "
            " revision, created_at, updated_at, allowed_actions_json, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["id"], r["action_id"], r.get("attempt", 1), r.get("skill_id"),
                r["protocol"], r["trigger_source"], r["idempotency_key"],
                r.get("status", "queued"),
                json.dumps(r.get("inputs", {}), ensure_ascii=False),
                json.dumps(r.get("steps", []), ensure_ascii=False),
                r.get("budget_tokens"), r.get("budget_seconds"),
                r.get("started_at"), r.get("finished_at"), r.get("duration_ms"),
                r.get("result_excerpt"), r.get("error"),
                json.dumps(r.get("artifact_ids", []), ensure_ascii=False),
                r.get("revision", 1),
                r.get("created_at"), r.get("updated_at"),
                json.dumps(r.get("allowed_actions", [])),
                r.get("reason"),
            ),
        )
        self._c().commit()

    def get(self, run_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_runs WHERE id = ?", (run_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def find_by_idem(self, action_id: str, idempotency_key: str) -> dict[str, Any] | None:
        """contracts §7.4: (action_id, idempotency_key) 命中已存在 → 200 + replayed."""
        row = self._c().execute(
            "SELECT * FROM v1_runs WHERE action_id = ? AND idempotency_key = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (action_id, idempotency_key),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def find_by_action_attempt(self, action_id: str, attempt: int) -> dict[str, Any] | None:
        """contracts §7.4: 同一 (action_id, attempt) 只 1 Run (UNIQUE INDEX 也保证)."""
        row = self._c().execute(
            "SELECT * FROM v1_runs WHERE action_id = ? AND attempt = ?",
            (action_id, attempt),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_by_action(
        self, action_id: str, *, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ["action_id = ?"]
        params: list[Any] = [action_id]
        if status:
            where.append("status = ?")
            params.append(status)
        sql_where = " AND ".join(where)
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_runs WHERE {sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT * FROM v1_runs WHERE {sql_where} ORDER BY attempt ASC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def update_status(
        self, run_id: str, new_status: str, *,
        finished_at: str | None = None, duration_ms: int | None = None,
        result_excerpt: str | None = None, error: str | None = None,
        artifact_ids: list[str] | None = None,
        allowed_actions: list[str] | None = None, reason: str | None = None,
    ) -> int:
        sets = ["status = ?", "revision = revision + 1", "updated_at = datetime('now', 'localtime')"]
        params: list[Any] = [new_status]
        if finished_at is not None:
            sets.append("finished_at = ?")
            params.append(finished_at)
        if duration_ms is not None:
            sets.append("duration_ms = ?")
            params.append(duration_ms)
        if result_excerpt is not None:
            sets.append("result_excerpt = ?")
            params.append(result_excerpt)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if artifact_ids is not None:
            sets.append("artifact_ids_json = ?")
            params.append(json.dumps(artifact_ids))
        if allowed_actions is not None:
            sets.append("allowed_actions_json = ?")
            params.append(json.dumps(allowed_actions))
        if reason is not None:
            sets.append("reason = ?")
            params.append(reason)
        params.append(run_id)
        cur = self._c().execute(
            f"UPDATE v1_runs SET {', '.join(sets)} WHERE id = ?", params,
        )
        self._c().commit()
        return cur.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("inputs", "steps", "artifact_ids", "allowed_actions"):
            json_key = f"{k}_json"
            if json_key in d and d[json_key] is not None:
                try:
                    d[k] = json.loads(d[json_key])
                except (json.JSONDecodeError, TypeError):
                    d[k] = [] if k != "inputs" else {}
            else:
                d[k] = [] if k != "inputs" else {}
        return d
