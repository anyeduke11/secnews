"""v1.0 证据引擎五表仓储 — v1_subjects / v1_materials / v1_signals /
v1_subject_identifiers / v1_evidence_receipts (migration 096 schema).

设计目标 (Batch 3 任务 A — v1 证据引擎写路径唯一化):

  - 覆盖原 v1_evidence_service / signal_service 对这五张表的全部
    SELECT / INSERT / UPDATE (裸 SQL 归零), service 层只保留业务编排
    (事务边界 / 幂等键判断 / 异常类型 / 审计), 语义逐字不变。
  - **事务归调用方**: 本 repo 的写方法**不** commit / rollback —
    v1_evidence_service 的 ``_tx()`` 上下文负责 commit/rollback,
    repo 只在其注入的连接上执行语句。与 judgment_repo 等 "repo 自提交"
    风格不同, 原因: intent 生命周期要求 实体行 + receipt UPDATE 在同一
    事务内原子提交, 拆开 commit 会破坏 "任何阶段中断不留半截数据" 语义。
  - **幂等 UNIQUE 语义**: v1_evidence_receipts 上
    ``uniq_v1_recv_key_hash (submission_key, body_hash)`` 由 DB 兜底;
    service 层先读后判 (find_latest_receipt → IdempotentReplay /
    IntentExistsError) 的次序保持不变。
  - v1_subject_identifiers 当前无 Python 调用方 (schema-only), 这里补
    最小读写入口 (INSERT OR IGNORE 幂等), 供后续 admission 批次使用。

连接一律经 ``backend.repository.db.get_connection`` (thread-local),
或由调用方注入 (conftest temp_db / 单测)。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class V1EvidenceRepository:
    """v1 证据引擎五表仓储 (receipts + subjects + materials + signals + identifiers).

    所有方法在 ``self._conn or get_connection()`` 上执行, 不 commit —
    事务边界归调用方 (v1_evidence_service._tx)。
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    # ------------------------------------------------------------------
    # v1_evidence_receipts — intent 生命周期
    # ------------------------------------------------------------------
    def find_latest_receipt(self, submission_key: str) -> sqlite3.Row | None:
        """同 submission_key 最新一条 receipt (幂等键判定输入).

        原 v1_evidence_service.create_intent 内 SELECT。
        """
        return self._c().execute(
            "SELECT id, body_hash, status, entity_id, intent_id "
            "FROM v1_evidence_receipts WHERE submission_key = ? "
            "ORDER BY id DESC LIMIT 1",
            (submission_key,),
        ).fetchone()

    def insert_pending_receipt(
        self,
        submission_key: str,
        body_hash: str,
        entity_type: str,
        intent_id: str,
        submitted_by: str,
        extra_json: str,
    ) -> None:
        """receipt 以 status=pending 落库, entity_id 占位 intent_id.

        原 v1_evidence_service.create_intent 内 INSERT。
        """
        self._c().execute(
            "INSERT INTO v1_evidence_receipts "
            "(submission_key, body_hash, entity_type, entity_id, "
            " submitted_by, intent_id, status, extra_json) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                submission_key, body_hash, entity_type, intent_id,
                submitted_by, intent_id, extra_json,
            ),
        )

    def find_pending_receipt(self, intent_id: str) -> sqlite3.Row | None:
        """按 intent_id 取 pending receipt (commit 阶段输入).

        原 v1_evidence_service.commit_intent 内 SELECT。
        """
        return self._c().execute(
            "SELECT id, body_hash, entity_type, submission_key, extra_json "
            "FROM v1_evidence_receipts WHERE intent_id = ? AND status = 'pending'",
            (intent_id,),
        ).fetchone()

    def get_receipt_body_hash(self, intent_id: str) -> str | None:
        """case 兜底路径读取 body_hash (v1_cases stub title 截断用).

        原 v1_evidence_service.commit_intent case 分支内 SELECT。
        """
        row = self._c().execute(
            "SELECT body_hash FROM v1_evidence_receipts WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        return row[0] if row is not None else None

    def update_receipt_committed(
        self, receipt_id: int, entity_id: str, extra_json: str,
    ) -> None:
        """receipt → committed + 真实 entity_id.

        原 v1_evidence_service.commit_intent 内 UPDATE。
        """
        self._c().execute(
            "UPDATE v1_evidence_receipts SET entity_id = ?, status = ?, "
            "extra_json = ? WHERE id = ?",
            (entity_id, "committed", extra_json, receipt_id),
        )

    def update_receipt_rolled_back_by_intent(
        self, intent_id: str, extra_json: str,
    ) -> int:
        """pending receipt → rolled_back (按 intent_id); 返 rowcount.

        原 v1_evidence_service.rollback_intent 内 UPDATE。
        """
        cur = self._c().execute(
            "UPDATE v1_evidence_receipts SET status = ?, extra_json = ? "
            "WHERE intent_id = ? AND status = 'pending'",
            ("rolled_back", extra_json, intent_id),
        )
        return cur.rowcount

    def list_expired_pending_intents(self, timeout_sec: float) -> list[sqlite3.Row]:
        """扫描超时未 commit 的 pending intent (reap 输入).

        原 v1_evidence_service.reap_expired_intents 内 SELECT。
        """
        return self._c().execute(
            "SELECT id, intent_id, entity_type, submission_key, submitted_at "
            "FROM v1_evidence_receipts "
            "WHERE status = 'pending' "
            "AND (julianday('now') - julianday(submitted_at)) * 86400 > ?",
            (timeout_sec,),
        ).fetchall()

    def update_receipt_rolled_back_by_id(
        self, receipt_id: int, extra_json: str,
    ) -> None:
        """reap 循环内逐条标 rolled_back (按 receipt 主键).

        原 v1_evidence_service.reap_expired_intents 内 UPDATE。
        """
        self._c().execute(
            "UPDATE v1_evidence_receipts SET status = ?, extra_json = ? "
            "WHERE id = ?",
            ("rolled_back", extra_json, receipt_id),
        )

    # ------------------------------------------------------------------
    # v1_subjects / v1_materials / v1_signals — 实体行 INSERT
    # (默认值 coalescing 逐字对齐原 _insert_* ; 失败审计留在 service 层)
    # ------------------------------------------------------------------
    def insert_subject(
        self, body: dict[str, Any], entity_id: str, body_hash: str,
    ) -> None:
        """v1.0 C05 R01: 真 INSERT v1_subjects (body 必含 id/entity_type/canonical_name).

        原 v1_evidence_service._insert_subject 内 INSERT (含默认值)。
        """
        now_iso = _utcnow_iso()
        self._c().execute(
            "INSERT INTO v1_subjects "
            "(id, entity_type, canonical_name, aliases_json, importance, "
            " tags_json, related_subject_ids_json, first_seen_at, last_seen_at, "
            " revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.get("id", entity_id),
                body.get("entity_type", "other"),
                body.get("canonical_name", body.get("id", entity_id)),
                body.get("aliases_json", "[]"),
                body.get("importance", "normal"),
                body.get("tags_json", "[]"),
                body.get("related_subject_ids_json", "[]"),
                body.get("first_seen_at", now_iso),
                body.get("last_seen_at", now_iso),
                int(body.get("revision", 1)),
                now_iso,
                now_iso,
            ),
        )

    def insert_material(
        self, body: dict[str, Any], entity_id: str, body_hash: str,
    ) -> None:
        """v1.0 C05 R01: 真 INSERT v1_materials.

        原 v1_evidence_service._insert_material 内 INSERT (含默认值)。
        """
        now_iso = _utcnow_iso()
        self._c().execute(
            "INSERT INTO v1_materials "
            "(id, source_kind, url, title, content_hash, content_length, "
            " content_ref, summary, published_at, fetched_at, fetched_by, "
            " subject_ids_json, metadata_json, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.get("id", entity_id),
                body.get("source_kind", "url"),
                body.get("url"),
                body.get("title", body.get("id", entity_id)),
                body.get("content_hash", body_hash),
                int(body.get("content_length", 0)),
                body.get("content_ref"),
                body.get("summary"),
                body.get("published_at"),
                body.get("fetched_at", now_iso),
                body.get("fetched_by"),
                body.get("subject_ids_json", "[]"),
                body.get("metadata_json", "{}"),
                int(body.get("revision", 1)),
                now_iso,
                now_iso,
            ),
        )

    def insert_signal(
        self, body: dict[str, Any], entity_id: str, body_hash: str,
    ) -> None:
        """v1.0 C05 R01: 真 INSERT v1_signals (FK subject/material 必须已存在).

        原 v1_evidence_service._insert_signal 内 INSERT (含默认值)。
        """
        now_iso = _utcnow_iso()
        self._c().execute(
            "INSERT INTO v1_signals "
            "(id, subject_id, material_id, summary, occurred_at, "
            " admission_rule_version, admission_reason, supersedes_signal_id, "
            " confidence, status, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.get("id", entity_id),
                body.get("subject_id", ""),
                body.get("material_id", ""),
                body.get("summary", ""),
                body.get("occurred_at", now_iso),
                body.get("admission_rule_version", "v1"),
                body.get("admission_reason", ""),
                body.get("supersedes_signal_id"),
                body.get("confidence", "unverified"),
                body.get("status", "unverified"),
                int(body.get("revision", 1)),
                now_iso,
                now_iso,
            ),
        )

    # ------------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------------
    def case_evidence_materials(self, case_id: str) -> list[dict[str, Any]]:
        """v0.8.5 D1.2: 立项携带证据 — v1_case_materials JOIN v1_materials.

        原 v1_evidence_service.case_evidence_materials 内 SELECT。
        """
        rows = self._c().execute(
            "SELECT m.id, m.title, m.url, m.content_hash, m.source_kind, "
            "       m.summary, cm.signal_id, cm.created_at AS bound_at "
            "FROM v1_case_materials cm "
            "JOIN v1_materials m ON m.id = cm.material_id "
            "WHERE cm.case_id = ? ORDER BY cm.created_at DESC",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_recent_signals(
        self,
        days: int = 7,
        *,
        case_id: str | None = None,
        limit: int = 50,
        subject_id: str | None = None,
    ) -> list[sqlite3.Row]:
        """v1_signals 近 N 天 + LEFT JOIN v1_subjects (subject_name).

        subject_id / case_id 过滤分支与原 signal_service.list_recent_signals
        逐字对齐 (case_id 过滤: 走 v1_actions → judgment_id → case_id 关联
        (T08 case_action); 当前 v1_actions 表无 case_id 字段 (T12+ 才加),
        暂走 material_id 经 v1_case_materials 反查)。
        """
        if subject_id:
            return self._c().execute(
                "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
                "       s.confidence, s.status, sub.canonical_name AS subject_name "
                "FROM v1_signals s "
                "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
                "WHERE s.occurred_at >= datetime('now', ?) "
                "AND s.subject_id = ? "
                "ORDER BY s.occurred_at DESC LIMIT ?",
                (f"-{days} days", subject_id, limit),
            ).fetchall()
        if case_id:
            return self._c().execute(
                "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
                "       s.confidence, s.status, sub.canonical_name AS subject_name "
                "FROM v1_signals s "
                "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
                "WHERE s.occurred_at >= datetime('now', ?) "
                "AND s.material_id IN ( "
                "  SELECT DISTINCT material_id FROM v1_case_materials WHERE case_id = ? "
                ") "
                "ORDER BY s.occurred_at DESC LIMIT ?",
                (f"-{days} days", case_id, limit),
            ).fetchall()
        return self._c().execute(
            "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
            "       s.confidence, s.status, sub.canonical_name AS subject_name "
            "FROM v1_signals s "
            "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
            "WHERE s.occurred_at >= datetime('now', ?) "
            "ORDER BY s.occurred_at DESC LIMIT ?",
            (f"-{days} days", limit),
        ).fetchall()

    # ------------------------------------------------------------------
    # v1_subject_identifiers — 提交键 (schema-only, 暂无 service 调用方)
    # ------------------------------------------------------------------
    def find_subject_identifier(
        self, source: str, external_id: str,
    ) -> sqlite3.Row | None:
        """按 (source, external_id) 主键查提交键."""
        return self._c().execute(
            "SELECT subject_id, source, external_id, first_seen_at "
            "FROM v1_subject_identifiers WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()

    def insert_subject_identifier(
        self, subject_id: str, source: str, external_id: str,
        first_seen_at: str | None = None,
    ) -> int:
        """插入提交键 (幂等: PK (source, external_id) 冲突时忽略).

        返 rowcount — 0 表示同源同 external_id 已存在 (幂等命中)。
        """
        cur = self._c().execute(
            "INSERT OR IGNORE INTO v1_subject_identifiers "
            "(subject_id, source, external_id, first_seen_at) "
            "VALUES (?, ?, ?, ?)",
            (subject_id, source, external_id, first_seen_at or _utcnow_iso()),
        )
        return cur.rowcount
