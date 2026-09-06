"""v1.0 T13 V1KnowledgeRepository — v1_knowledge 主表 CRUD + CAS + 4 态机.

独立文件 (避免与 v0 knowledge_repo.py 冲突, 后者管 knowledge_items/concepts/tasks).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class V1KnowledgeRepository:
    """v1 Knowledge 仓储 — 对齐 contracts §9.1 字段 + §9.2 状态机 + §9.3 allowed_actions."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def insert(self, k: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO v1_knowledge "
            "(id, kind, title, body, prerequisites_json, counter_examples_json, evidence_refs_json, "
            " expiry_at, review_at, status, revision, wiki_path, content_hash, published_at, "
            " deprecation_reason, replacement_knowledge_id, retraction_reason, "
            " allowed_actions_json, reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                k["id"], k["kind"], k["title"], k["body"],
                json.dumps(k.get("prerequisites", []), ensure_ascii=False),
                json.dumps(k.get("counter_examples", []), ensure_ascii=False),
                json.dumps(k.get("evidence_refs", []), ensure_ascii=False, sort_keys=True),
                k.get("expiry_at"), k.get("review_at"),
                k.get("status", "draft"), k.get("revision", 1),
                k.get("wiki_path"), k.get("content_hash"), k.get("published_at"),
                k.get("deprecation_reason"), k.get("replacement_knowledge_id"),
                k.get("retraction_reason"),
                json.dumps(k.get("allowed_actions", [])),
                k.get("reason"),
                k.get("created_at"), k.get("updated_at"),
            ),
        )
        self._c().commit()

    def get(self, knowledge_id: str) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM v1_knowledge WHERE id = ?", (knowledge_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_by_case(
        self, case_id: str, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """通过 v1_knowledge_refs → v1_actions / v1_judgments → v1_cases 关联 (INNER JOIN 路径)."""
        # 1) 收集与本 case 相关的 knowledge_id (judgment + action 路径, INNER JOIN 避免 NULL)
        ids_subq = (
            "SELECT DISTINCT kr.knowledge_id FROM v1_knowledge_refs kr "
            "INNER JOIN v1_actions a ON kr.source_type='action' AND a.id = kr.source_id AND a.case_id = ? "
            "UNION "
            "SELECT DISTINCT kr.knowledge_id FROM v1_knowledge_refs kr "
            "INNER JOIN v1_judgments j ON kr.source_type='judgment' AND j.id = kr.source_id AND j.case_id = ?"
        )
        where = [f"k.id IN ({ids_subq})"]
        params: list[Any] = [case_id, case_id]
        if status:
            where.append("k.status = ?")
            params.append(status)
        if kind:
            where.append("k.kind = ?")
            params.append(kind)
        sql_where = " AND ".join(where)
        total = self._c().execute(
            f"SELECT COUNT(*) FROM v1_knowledge k WHERE {sql_where}", params,
        ).fetchone()[0]
        rows = self._c().execute(
            f"SELECT k.* FROM v1_knowledge k WHERE {sql_where} "
            f"ORDER BY k.published_at DESC NULLS LAST, k.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows], total

    def list_published_due_for_review(self, now_iso: str) -> list[dict[str, Any]]:
        """SK-06: review_due job 扫 review_at <= now AND status='published'."""
        rows = self._c().execute(
            "SELECT * FROM v1_knowledge "
            "WHERE status = 'published' AND review_at IS NOT NULL AND review_at <= ? "
            "ORDER BY review_at ASC",
            (now_iso,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_status_cas(
        self, knowledge_id: str, new_status: str, *,
        expected_revision: int, allowed_actions: list[str] | None = None,
        reason: str | None = None, published_at: str | None = None,
        wiki_path: str | None = None, deprecation_reason: str | None = None,
        replacement_knowledge_id: str | None = None, retraction_reason: str | None = None,
    ) -> int:
        sets = ["status = ?", "revision = revision + 1", "updated_at = datetime('now', 'localtime')"]
        params: list[Any] = [new_status]
        if allowed_actions is not None:
            sets.append("allowed_actions_json = ?")
            params.append(json.dumps(allowed_actions))
        if reason is not None:
            sets.append("reason = ?")
            params.append(reason)
        if published_at is not None:
            sets.append("published_at = ?")
            params.append(published_at)
        if wiki_path is not None:
            sets.append("wiki_path = ?")
            params.append(wiki_path)
        if deprecation_reason is not None:
            sets.append("deprecation_reason = ?")
            params.append(deprecation_reason)
        if replacement_knowledge_id is not None:
            sets.append("replacement_knowledge_id = ?")
            params.append(replacement_knowledge_id)
        if retraction_reason is not None:
            sets.append("retraction_reason = ?")
            params.append(retraction_reason)
        params.extend([knowledge_id, expected_revision])
        cur = self._c().execute(
            f"UPDATE v1_knowledge SET {', '.join(sets)} WHERE id = ? AND revision = ?",
            params,
        )
        self._c().commit()
        return cur.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("prerequisites", "counter_examples", "evidence_refs", "allowed_actions"):
            json_key = f"{k}_json"
            if json_key in d and d[json_key] is not None:
                try:
                    d[k] = json.loads(d[json_key])
                except (json.JSONDecodeError, TypeError):
                    d[k] = [] if k != "evidence_refs" else []
            else:
                d[k] = []
        return d
