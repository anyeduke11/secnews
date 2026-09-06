"""v1.0 T12 ActionRepository — v1_actions 主表 CRUD + CAS + 多对多."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class ActionRepository:
    """Action 仓储 — 对齐 contracts §6 字段 + 状态机."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(self, a: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO v1_actions "
            "(id, case_id, judgment_id, title, scope, plan, plan_hash, "
            " tool_versions_json, expected_artifacts_json, success_criteria, expires_at, "
            " status, approved_by, approved_at, rejection_reason, "
            " revision, created_at, updated_at, allowed_actions_json, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                a["id"], a["case_id"], a["judgment_id"], a["title"], a.get("scope"),
                a["plan"], a["plan_hash"],
                json.dumps(a.get("tool_versions", {}), ensure_ascii=False),
                json.dumps(a.get("expected_artifacts", []), ensure_ascii=False),
                a.get("success_criteria"), a.get("expires_at"),
                a.get("status", "planned"),
                a.get("approved_by"), a.get("approved_at"),
                a.get("rejection_reason"),
                a.get("revision", 1),
                a.get("created_at"), a.get("updated_at"),
                json.dumps(a.get("allowed_actions", [])),
                a.get("reason"),
            ),
        )
        self._c().commit()

    def get(self, action_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_actions WHERE id = ?", (action_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_case(
        self, case_id: str, *, status: str | None = None, judgment_id: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ["case_id = ?"]
        params: list[Any] = [case_id]
        if status:
            where.append("status = ?")
            params.append(status)
        if judgment_id:
            where.append("judgment_id = ?")
            params.append(judgment_id)
        sql_where = " AND ".join(where)
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_actions WHERE {sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT * FROM v1_actions WHERE {sql_where} "
            f"ORDER BY COALESCE(approved_at, created_at) DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def update_status_cas(
        self, action_id: str, new_status: str, *,
        expected_revision: int, approved_by: str | None = None,
        approved_at: str | None = None, rejection_reason: str | None = None,
        allowed_actions: list[str] | None = None, reason: str | None = None,
        updated_at: str | None = None,
    ) -> int:
        sets = ["status = ?", "revision = revision + 1"]
        params: list[Any] = [new_status]
        if approved_by is not None:
            sets.append("approved_by = ?")
            params.append(approved_by)
        if approved_at is not None:
            sets.append("approved_at = ?")
            params.append(approved_at)
        if rejection_reason is not None:
            sets.append("rejection_reason = ?")
            params.append(rejection_reason)
        if allowed_actions is not None:
            sets.append("allowed_actions_json = ?")
            params.append(json.dumps(allowed_actions))
        if reason is not None:
            sets.append("reason = ?")
            params.append(reason)
        if updated_at is not None:
            sets.append("updated_at = ?")
            params.append(updated_at)
        else:
            sets.append("updated_at = datetime('now', 'localtime')")
        params.extend([action_id, expected_revision])
        cur = self._c().execute(
            f"UPDATE v1_actions SET {', '.join(sets)} WHERE id = ? AND revision = ?",
            params,
        )
        self._c().commit()
        return cur.rowcount

    def link_to_case(self, case_id: str, action_id: str) -> None:
        """v1_case_actions 关联 (多对多)."""
        self._c().execute(
            "INSERT OR IGNORE INTO v1_case_actions (case_id, action_id, created_at) "
            "VALUES (?, ?, datetime('now', 'localtime'))",
            (case_id, action_id),
        )
        self._c().commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("tool_versions", "expected_artifacts", "allowed_actions"):
            json_key = f"{k}_json"
            if json_key in d and d[json_key] is not None:
                try:
                    d[k] = json.loads(d[json_key])
                except (json.JSONDecodeError, TypeError):
                    d[k] = [] if k != "tool_versions" else {}
            else:
                d[k] = [] if k != "tool_versions" else {}
        return d
