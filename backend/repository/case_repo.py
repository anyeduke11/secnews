"""v1.0 T08 Case 仓储层 (contracts §4).

要点
----
- 仅持久化 v1_cases 表 (judgment / action 关联表骨架由 098 迁移落库, 本类不写)
- create / get / list_by_status / list_by_subject / update_status (CAS 校验 expected_revision) /
  list_related_cases 全部走 get_connection() — conftest temp_db 注入, 默认 process-wide conn
- CAS: 不匹配不抛异常, 返回 False 由 service 层映射为 E_CONFLICT (与 contracts §0.6 一致)
- 不返回 Pydantic Case 对象 (与 secrets_repo 等老仓一致), 由 service 层做 enum / 字段映射,
  本类只做 row <-> dict 转换
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """row -> dict; *_json 字段反序列化回 list."""
    d = {k: row[k] for k in row.keys()}
    for k in (
        "tags_json",
        "related_subject_ids_json",
        "related_signal_ids_json",
        "related_case_ids_json",
    ):
        if d.get(k):
            try:
                d[k[:-5]] = json.loads(d[k])
            except (ValueError, TypeError):
                d[k[:-5]] = []
        else:
            d[k[:-5]] = []
    return d


@dataclass
class CaseRecord:
    """SQLite 行映射 — service 层转 Pydantic Case."""

    id: str
    title: str
    question: str
    goal: str | None
    scope: str | None
    priority: str
    status: str
    due_at: str | None
    subject_id: str | None
    owner_role: str
    revision: int
    closed_at: str | None
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)
    related_subject_ids: list[str] = field(default_factory=list)
    related_signal_ids: list[str] = field(default_factory=list)
    related_case_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CaseRecord:
        d = _row_to_dict(row)
        return cls(
            id=d["id"],
            title=d["title"],
            question=d["question"],
            goal=d.get("goal"),
            scope=d.get("scope"),
            priority=d["priority"],
            status=d["status"],
            due_at=d.get("due_at"),
            subject_id=d.get("subject_id"),
            owner_role=d.get("owner_role") or "user",
            revision=int(d["revision"]),
            closed_at=d.get("closed_at"),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            tags=d.get("tags", []) or [],
            related_subject_ids=d.get("related_subject_ids", []) or [],
            related_signal_ids=d.get("related_signal_ids", []) or [],
            related_case_ids=d.get("related_case_ids", []) or [],
        )


class CaseRepository:
    """Case CRUD + CAS 更新 + 列表查询."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn  # conftest.temp_db 注入

    def _connection(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    # ------------------------------------------------------------------
    # 创建 / 读取
    # ------------------------------------------------------------------
    def create(self, case: dict[str, Any]) -> CaseRecord:
        """插入一行. caller 负责生成 ULID (idempotency 由 service 层 V1EvidenceService 兜底).

        Required: id, title, question; 其它字段有默认.
        """
        now = _now_iso()
        row = self._connection().execute(
            "INSERT INTO v1_cases "
            "(id, title, question, goal, scope, priority, status, due_at, "
            " subject_id, owner_role, revision, closed_at, created_at, updated_at, "
            " tags_json, related_subject_ids_json, related_signal_ids_json, related_case_ids_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case["id"],
                case["title"],
                case["question"],
                case.get("goal"),
                case.get("scope"),
                case.get("priority", "p2"),
                case.get("status", "open"),
                case.get("due_at"),
                case.get("subject_id"),
                case.get("owner_role", "user"),
                int(case.get("revision", 1)),
                case.get("closed_at"),
                now,
                now,
                json.dumps(case.get("tags") or []),
                json.dumps(case.get("related_subject_ids") or []),
                json.dumps(case.get("related_signal_ids") or []),
                json.dumps(case.get("related_case_ids") or []),
            ),
        )
        self._connection().commit()
        fetched = self.get(case["id"])
        assert fetched is not None, "case vanished after insert"
        return fetched

    def get(self, case_id: str) -> CaseRecord | None:
        row = self._connection().execute(
            "SELECT * FROM v1_cases WHERE id = ?", (case_id,)
        ).fetchone()
        return CaseRecord.from_row(row) if row else None

    def list_by_status(
        self,
        statuses: list[str] | None = None,
        priorities: list[str] | None = None,
        owner_role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CaseRecord]:
        """过滤 status / priority / owner_role; 排序 priority asc → updated_at desc."""
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ",".join("?" * len(statuses))
            where.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if priorities:
            placeholders = ",".join("?" * len(priorities))
            where.append(f"priority IN ({placeholders})")
            params.extend(priorities)
        if owner_role:
            where.append("owner_role = ?")
            params.append(owner_role)
        sql = "SELECT * FROM v1_cases"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += (
            " ORDER BY CASE priority WHEN 'p0' THEN 0 WHEN 'p1' THEN 1 "
            "WHEN 'p2' THEN 2 WHEN 'p3' THEN 3 ELSE 4 END, "
            "updated_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = self._connection().execute(sql, params).fetchall()
        return [CaseRecord.from_row(r) for r in rows]

    def list_by_subject(
        self,
        subject_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CaseRecord]:
        """按 subject_id 过滤 (主索引 idx_v1_case_subject)."""
        rows = self._connection().execute(
            "SELECT * FROM v1_cases WHERE subject_id = ? "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (subject_id, limit, offset),
        ).fetchall()
        return [CaseRecord.from_row(r) for r in rows]

    def list_related_cases(self, case_id: str, limit: int = 50) -> list[CaseRecord]:
        """列 related_case_ids 引用的其它 case (related_case_ids_json 含 case_id)."""
        rows = self._connection().execute(
            "SELECT * FROM v1_cases WHERE related_case_ids_json LIKE ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (f'%"{case_id}"%', limit),
        ).fetchall()
        return [CaseRecord.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # CAS 更新
    # ------------------------------------------------------------------
    def update_status(
        self,
        case_id: str,
        new_status: str,
        expected_revision: int,
        *,
        closed_at: str | None = None,
    ) -> CaseRecord | None:
        """CAS update: 仅当 revision == expected_revision 才写入并自增.

        Returns
        -------
        更新后 CaseRecord; None 表示 id 不存在或 CAS 失败.
        caller 区分: id 不存在 → 404; CAS 不匹配 → E_CONFLICT.
        """
        now = _now_iso()
        cur = self._connection().execute(
            "UPDATE v1_cases SET status = ?, revision = revision + 1, "
            "updated_at = ?, closed_at = COALESCE(?, closed_at) "
            "WHERE id = ? AND revision = ?",
            (new_status, now, closed_at, case_id, expected_revision),
        )
        self._connection().commit()
        if cur.rowcount == 0:
            return None
        return self.get(case_id)

    def update_metadata(
        self,
        case_id: str,
        expected_revision: int,
        updates: dict[str, Any],
    ) -> CaseRecord | None:
        """CAS update metadata (title/question/goal/scope/priority/due_at/tags/related_*).

        status / closed_at 由 update_status 单独管; 此方法不接 status.
        Returns 同 update_status.
        """
        allowed = {
            "title",
            "question",
            "goal",
            "scope",
            "priority",
            "due_at",
            "subject_id",
            "tags",
            "related_subject_ids",
            "related_signal_ids",
            "related_case_ids",
        }
        sets: list[str] = []
        params: list[Any] = []
        for k, v in updates.items():
            if k not in allowed:
                continue
            sets.append(f"{k} = ?")
            params.append(v)
        if not sets:
            return self.get(case_id)
        sets.append("revision = revision + 1")
        sets.append("updated_at = ?")
        params.append(_now_iso())
        params.extend([case_id, expected_revision])
        cur = self._connection().execute(
            f"UPDATE v1_cases SET {', '.join(sets)} WHERE id = ? AND revision = ?",
            params,
        )
        self._connection().commit()
        if cur.rowcount == 0:
            return None
        return self.get(case_id)