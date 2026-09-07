"""v1.0 T11 JudgmentRepository — v1_judgments 主表 CRUD + CAS.

对应 contracts.md §5.1 字段 + §5.3 状态机 + §5.4 不变量.
不写业务校验 (业务校验在 judgment_service.py).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class JudgmentRepository:
    """Judgment 主表 + case 关联的轻量仓储."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def insert(self, j: dict[str, Any]) -> None:
        """插入 judgment 行 (id 已由 service 生成, 字段对齐 contracts §5.1)."""
        self._c().execute(
            "INSERT INTO v1_judgments "
            "(id, case_id, subject_id, claim_type, claim, conditions, confidence, "
            " evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, "
            " content_hash, wiki_path, revision, published_at, "
            " allowed_actions_json, reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                j["id"], j["case_id"], j.get("subject_id"), j["claim_type"], j["claim"],
                j.get("conditions", ""), j.get("confidence", "medium"),
                json.dumps(j.get("evidence_refs", []), ensure_ascii=False, sort_keys=True),
                json.dumps(j.get("counter_evidence_refs", []), ensure_ascii=False, sort_keys=True),
                json.dumps(j.get("unknowns", []), ensure_ascii=False),
                j.get("status", "draft"), j.get("content_hash"), j.get("wiki_path"),
                j.get("revision", 1), j.get("published_at"),
                json.dumps(j.get("allowed_actions", [])),
                j.get("reason"),
                j.get("created_at"), j.get("updated_at"),
            ),
        )
        self._c().commit()

    def get(self, judgment_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_judgments WHERE id = ?", (judgment_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_by_case(
        self, case_id: str, *, status: str | None = None, claim_type: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """列 judgment (按 case_id 过滤, 可选 status/claim_type)."""
        where = ["case_id = ?"]
        params: list[Any] = [case_id]
        if status:
            where.append("status = ?")
            params.append(status)
        if claim_type:
            where.append("claim_type = ?")
            params.append(claim_type)
        sql_where = " AND ".join(where)
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_judgments WHERE {sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT * FROM v1_judgments WHERE {sql_where} "
            f"ORDER BY COALESCE(published_at, updated_at) DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def has_published_for_case_type(self, case_id: str, claim_type: str, exclude_id: str | None = None) -> bool:
        """contracts §5.3 L359: 同一 case + claim_type 同时只 1 published. 不含已 superseded/retracted."""
        sql = "SELECT 1 FROM v1_judgments WHERE case_id = ? AND claim_type = ? AND status = 'published'"
        params: list[Any] = [case_id, claim_type]
        if exclude_id:
            sql += " AND id != ?"
            params.append(exclude_id)
        return self._c().execute(sql, params).fetchone() is not None

    def update_status_cas(
        self, judgment_id: str, new_status: str, *,
        expected_revision: int, old_status: str | None = None,
        published_at: str | None = None,
        wiki_path: str | None = None, allowed_actions: list[str] | None = None,
        reason: str | None = None,
    ) -> int:
        """CAS update: 期望 revision 匹配才改 status; 返 rowcount (0 = 失败).

        v1.0 C08 R09 修复: 额外支持 old_status 守卫, 拒绝 stale status 覆盖.
        """
        sets = ["status = ?", "revision = revision + 1", "updated_at = datetime('now', 'localtime')"]
        params: list[Any] = [new_status]
        if published_at is not None:
            sets.append("published_at = ?")
            params.append(published_at)
        if wiki_path is not None:
            sets.append("wiki_path = ?")
            params.append(wiki_path)
        if allowed_actions is not None:
            sets.append("allowed_actions_json = ?")
            params.append(json.dumps(allowed_actions))
        if reason is not None:
            sets.append("reason = ?")
            params.append(reason)
        where = ["id = ?", "revision = ?"]
        wparams: list[Any] = [judgment_id, expected_revision]
        if old_status is not None:
            where.append("status = ?")
            wparams.append(old_status)
        cur = self._c().execute(
            f"UPDATE v1_judgments SET {', '.join(sets)} WHERE {' AND '.join(where)}",
            (*params, *wparams),
        )
        self._c().commit()
        return cur.rowcount

    def link_to_case(self, case_id: str, judgment_id: str) -> None:
        """v1_case_judgments 关联 (多对多). 已存在则忽略 (idempotent)."""
        self._c().execute(
            "INSERT OR IGNORE INTO v1_case_judgments (case_id, judgment_id, created_at) "
            "VALUES (?, ?, datetime('now', 'localtime'))",
            (case_id, judgment_id),
        )
        self._c().commit()

    # ------------------------------------------------------------------
    # row -> dict (对齐 contracts §5.1 字段名)
    # ------------------------------------------------------------------
    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        # JSON 字段反序列化
        for k in ("evidence_refs", "counter_evidence_refs", "unknowns", "allowed_actions"):
            json_key = f"{k}_json"
            if json_key in d and d[json_key] is not None:
                try:
                    d[k] = json.loads(d[json_key])
                except (json.JSONDecodeError, TypeError):
                    d[k] = []
            else:
                d[k] = []
        return d
