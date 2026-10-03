"""ProposalRepository — v1_proposals (M1 提案) CRUD。

v0.8.6 P1-1。提案是人主律的唯一入口: AI/命令/副驾产出的候选动作或结论,
未经人审批前不得成为事实。枚举校验在 RunLedgerService, 仓储只做持久化。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class ProposalRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(self, p: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO v1_proposals "
            "(id, case_id, source, kind, payload_json, evidence_ids_json, "
            " prompt_version, status, error_msg, reject_reason, "
            " reviewed_by, reviewed_at, run_id, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, "
            "datetime('now','localtime'), datetime('now','localtime'))",
            (
                p["id"], p.get("case_id"), p["source"], p["kind"],
                json.dumps(p.get("payload", {}), ensure_ascii=False),
                json.dumps(p.get("evidence_ids", []), ensure_ascii=False),
                p.get("prompt_version"),
                p.get("status", "draft"),
                p.get("error_msg"), p.get("reject_reason"),
                p.get("reviewed_by"), p.get("reviewed_at"), p.get("run_id"),
            ),
        )
        self._c().commit()

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_proposals WHERE id = ?", (proposal_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_proposals(
        self, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = ?")
            params.append(status)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        sql_where = (" WHERE " + " AND ".join(where)) if where else ""
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_proposals{sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT * FROM v1_proposals{sql_where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def update_decision(
        self, proposal_id: str, status: str, *,
        reviewed_by: str | None = None, reviewed_at: str | None = None,
        reject_reason: str | None = None, run_id: str | None = None,
        error_msg: str | None = None,
    ) -> int:
        sets = ["status = ?", "revision = revision + 1",
                "updated_at = datetime('now','localtime')"]
        params: list[Any] = [status]
        for col, val in (
            ("reviewed_by", reviewed_by), ("reviewed_at", reviewed_at),
            ("reject_reason", reject_reason), ("run_id", run_id),
            ("error_msg", error_msg),
        ):
            if val is not None:
                sets.append(f"{col} = ?")
                params.append(val)
        params.append(proposal_id)
        cur = self._c().execute(
            f"UPDATE v1_proposals SET {', '.join(sets)} WHERE id = ?", params,
        )
        self._c().commit()
        return cur.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for json_col, key, default in (
            ("payload_json", "payload", {}),
            ("evidence_ids_json", "evidence_ids", []),
        ):
            raw = d.get(json_col)
            try:
                d[key] = json.loads(raw) if raw is not None else default
            except (json.JSONDecodeError, TypeError):
                d[key] = default
        return d
