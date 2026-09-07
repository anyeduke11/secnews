"""v1.0 T12 ArtifactRepository — v1_artifacts 主表CRUD + 5 态机 + 防重传蒙混."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class ArtifactRepository:
    """Artifact 仓储 — 对齐 contracts §8 字段 + 状态机 + §8.3 防蒙混."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(self, a: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO v1_artifacts "
            "(id, run_id, kind, title, content_ref, content_hash, format, size_bytes, "
            " verified_by, verified_at, verified_result, "
            " accepted_by, accepted_at, accepted_note, "
            " status, revision, created_at, updated_at, allowed_actions_json, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                a["id"], a["run_id"], a["kind"], a["title"], a.get("content_ref"),
                a["content_hash"], a["format"], a.get("size_bytes", 0),
                a.get("verified_by"), a.get("verified_at"), a.get("verified_result"),
                a.get("accepted_by"), a.get("accepted_at"), a.get("accepted_note"),
                a.get("status", "pending"),
                a.get("revision", 1),
                a.get("created_at"), a.get("updated_at"),
                json.dumps(a.get("allowed_actions", [])),
                a.get("reason"),
            ),
        )
        self._c().commit()

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_artifacts WHERE id = ?", (artifact_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_by_run(
        self, run_id: str, *, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ["run_id = ?"]
        params: list[Any] = [run_id]
        if status:
            where.append("status = ?")
            params.append(status)
        sql_where = " AND ".join(where)
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_artifacts WHERE {sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT * FROM v1_artifacts WHERE {sql_where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def has_rejected_with_same_hash(self, run_id: str, content_hash: str) -> bool:
        """contracts §8.3: rejected 后同 content_hash 不可再 accept; 命中即返回 True."""
        row = self._c().execute(
            "SELECT 1 FROM v1_artifacts WHERE run_id = ? AND content_hash = ? "
            "AND status = 'rejected' LIMIT 1",
            (run_id, content_hash),
        ).fetchone()
        return row is not None

    def update_status_cas(
        self, artifact_id: str, new_status: str, *,
        expected_revision: int | None = None,
        old_status: str | None = None,
        verified_by: str | None = None, verified_at: str | None = None,
        verified_result: str | None = None,
        accepted_by: str | None = None, accepted_at: str | None = None,
        accepted_note: str | None = None,
        allowed_actions: list[str] | None = None, reason: str | None = None,
    ) -> int:
        """v1.0 C08 R09 修复: 原子 CAS — WHERE 加 expected_revision + old_status.

        旧实现仅 WHERE id=?, 任何窗口交错 (verify+verify / accept+accept) 都会
        把后写覆盖先写, revision 连续 +2 但业务上第二次 submit 是 stale.

        新实现: caller 传 expected_revision + old_status, 任何一个不匹配 → rowcount=0
        (后写原地失败, 不抛, 由 service 解读为冲突 raise).
        """
        sets = ["status = ?", "revision = revision + 1", "updated_at = datetime('now', 'localtime')"]
        params: list[Any] = [new_status]
        if verified_by is not None:
            sets.append("verified_by = ?")
            params.append(verified_by)
        if verified_at is not None:
            sets.append("verified_at = ?")
            params.append(verified_at)
        if verified_result is not None:
            sets.append("verified_result = ?")
            params.append(verified_result)
        if accepted_by is not None:
            sets.append("accepted_by = ?")
            params.append(accepted_by)
        if accepted_at is not None:
            sets.append("accepted_at = ?")
            params.append(accepted_at)
        if accepted_note is not None:
            sets.append("accepted_note = ?")
            params.append(accepted_note)
        if allowed_actions is not None:
            sets.append("allowed_actions_json = ?")
            params.append(json.dumps(allowed_actions))
        if reason is not None:
            sets.append("reason = ?")
            params.append(reason)
        where = ["id = ?"]
        wparams: list[Any] = [artifact_id]
        if expected_revision is not None:
            where.append("revision = ?")
            wparams.append(expected_revision)
        if old_status is not None:
            where.append("status = ?")
            wparams.append(old_status)
        cur = self._c().execute(
            f"UPDATE v1_artifacts SET {', '.join(sets)} WHERE {' AND '.join(where)}",
            (*params, *wparams),
        )
        self._c().commit()
        return cur.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        json_key = "allowed_actions_json"
        if json_key in d and d[json_key] is not None:
            try:
                d["allowed_actions"] = json.loads(d[json_key])
            except (json.JSONDecodeError, TypeError):
                d["allowed_actions"] = []
        else:
            d["allowed_actions"] = []
        return d
