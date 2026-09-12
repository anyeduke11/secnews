"""v1_evidence_repo 单测 (Batch 3 任务 A — 写路径唯一化).

覆盖五表 repo 方法的关键语义 (业务语义由 service 层测试覆盖, 见
test_v1_evidence_service.py / test_signal_service.py — 那些用例在 repo
下沉后逐字保留, 本文件只补 repo 自身的直测):

  1. receipt 生命周期: insert pending → find pending → committed → rolled_back
  2. 幂等 UNIQUE: 同 (submission_key, body_hash) 二次插入 → IntegrityError
  3. 实体行 INSERT 默认值 (subject/material/signal)
  4. list_recent_signals 三分支 (默认 / subject_id / case_id)
  5. case_evidence_materials JOIN
  6. reap 查询 (超时 pending)
  7. v1_subject_identifiers INSERT OR IGNORE 幂等
"""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.repository.v1_evidence_repo import V1EvidenceRepository


@pytest.fixture()
def repo(temp_db) -> V1EvidenceRepository:  # temp_db 只为建表
    return V1EvidenceRepository()


def _seed_subject_material(conn) -> tuple[str, str]:
    """signal FK 前置: 先落 subject + material."""
    conn.execute(
        "INSERT INTO v1_subjects (id, entity_type, canonical_name, first_seen_at, last_seen_at) "
        "VALUES ('SUBJ-R', 'cve', 'CVE-R', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO v1_materials (id, source_kind, title, content_hash, content_length, fetched_at) "
        "VALUES ('MAT-R', 'url', 'R', '" + "h" * 64 + "', 1, '2026-01-01')"
    )
    conn.commit()
    return "SUBJ-R", "MAT-R"


# ---------------------------------------------------------------------------
# receipt 生命周期
# ---------------------------------------------------------------------------
def test_receipt_lifecycle(repo) -> None:
    conn = get_connection()
    repo.insert_pending_receipt(
        "key-life", "hash-life", "subject", "intent-life", "tester",
        json.dumps({"_intent": True, "_body": {}}),
    )
    row = repo.find_latest_receipt("key-life")
    assert row is not None and row["status"] == "pending"
    receipt_id = row["id"]

    pending = repo.find_pending_receipt("intent-life")
    assert pending is not None
    assert pending["submission_key"] == "key-life"

    repo.update_receipt_committed(receipt_id, "SUBJ-OK", json.dumps({"projection_status": "skipped"}))
    # committed 后不再是 pending
    assert repo.find_pending_receipt("intent-life") is None
    row = repo.find_latest_receipt("key-life")
    assert row["status"] == "committed" and row["entity_id"] == "SUBJ-OK"


def test_receipt_idempotent_unique(repo) -> None:
    """幂等 UNIQUE 约束: 同 (submission_key, body_hash) 二次插入 → IntegrityError."""
    import sqlite3 as _sq

    repo.insert_pending_receipt(
        "key-dup", "hash-dup", "subject", "intent-dup-1", "tester", "{}",
    )
    with pytest.raises(_sq.IntegrityError):
        repo.insert_pending_receipt(
            "key-dup", "hash-dup", "subject", "intent-dup-2", "tester", "{}",
        )


def test_rollback_rowcount_semantics(repo) -> None:
    """pending 才可 rollback; 重复 rollback rowcount=0."""
    repo.insert_pending_receipt("key-rb", "hash-rb", "subject", "intent-rb", "t", "{}")
    assert repo.update_receipt_rolled_back_by_intent("intent-rb", "{}") == 1
    assert repo.update_receipt_rolled_back_by_intent("intent-rb", "{}") == 0
    assert repo.find_latest_receipt("key-rb")["status"] == "rolled_back"


def test_reap_query_finds_only_expired(repo) -> None:
    conn = get_connection()
    repo.insert_pending_receipt("key-fresh", "h1", "subject", "intent-fresh", "t", "{}")
    repo.insert_pending_receipt("key-stale", "h2", "subject", "intent-stale", "t", "{}")
    conn.execute(
        "UPDATE v1_evidence_receipts SET submitted_at = datetime('now', '-2 hours') "
        "WHERE intent_id = 'intent-stale'"
    )
    conn.commit()
    rows = repo.list_expired_pending_intents(3600)
    assert [r["intent_id"] for r in rows] == ["intent-stale"]


# ---------------------------------------------------------------------------
# 实体行 INSERT (默认值)
# ---------------------------------------------------------------------------
def test_insert_subject_defaults(repo) -> None:
    conn = get_connection()
    repo.insert_subject({"id": "SUBJ-D", "entity_type": "cve", "canonical_name": "D"}, "SUBJ-D", "h")
    conn.commit()
    row = conn.execute("SELECT * FROM v1_subjects WHERE id = 'SUBJ-D'").fetchone()
    assert row["importance"] == "normal"
    assert row["aliases_json"] == "[]"
    assert row["revision"] == 1


def test_insert_material_defaults(repo) -> None:
    conn = get_connection()
    repo.insert_material(
        {"id": "MAT-D", "source_kind": "url", "title": "T",
         "content_length": 5, "fetched_at": "2026-01-01"},
        "MAT-D", "h" * 64,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM v1_materials WHERE id = 'MAT-D'").fetchone()
    assert row["content_hash"] == "h" * 64  # body 缺 content_hash → 回退 body_hash
    assert row["metadata_json"] == "{}"


def test_insert_signal_defaults(repo) -> None:
    conn = get_connection()
    _seed_subject_material(conn)
    repo.insert_signal(
        {"id": "SIG-D", "subject_id": "SUBJ-R", "material_id": "MAT-R", "summary": "s"},
        "SIG-D", "h",
    )
    conn.commit()
    row = conn.execute("SELECT * FROM v1_signals WHERE id = 'SIG-D'").fetchone()
    assert row["confidence"] == "unverified"
    assert row["status"] == "unverified"
    assert row["admission_rule_version"] == "v1"


# ---------------------------------------------------------------------------
# 只读查询
# ---------------------------------------------------------------------------
def test_list_recent_signals_branches(repo) -> None:
    conn = get_connection()
    _seed_subject_material(conn)
    conn.execute(
        "INSERT INTO v1_signals (id, subject_id, material_id, summary, occurred_at, "
        "admission_rule_version) VALUES ('SIG-L', 'SUBJ-R', 'MAT-R', 's', datetime('now'), 'v1')"
    )
    conn.commit()
    # 默认分支
    rows = repo.list_recent_signals(7, limit=50)
    assert len(rows) == 1
    assert rows[0]["subject_name"] == "CVE-R"
    # subject_id 分支
    assert len(repo.list_recent_signals(7, subject_id="SUBJ-R")) == 1
    assert repo.list_recent_signals(7, subject_id="OTHER") == []
    # case_id 分支 (无 case_materials → 空)
    assert repo.list_recent_signals(7, case_id="CASE-X") == []


def test_case_evidence_materials_join(repo) -> None:
    conn = get_connection()
    _seed_subject_material(conn)
    conn.execute(
        "INSERT INTO v1_case_materials (case_id, material_id, signal_id) "
        "VALUES ('CASE-J', 'MAT-R', 'SIG-R')"
    )
    conn.commit()
    items = repo.case_evidence_materials("CASE-J")
    assert len(items) == 1
    assert items[0]["id"] == "MAT-R"
    assert items[0]["signal_id"] == "SIG-R"
    assert repo.case_evidence_materials("CASE-NOPE") == []


# ---------------------------------------------------------------------------
# v1_subject_identifiers (schema-only, 幂等 INSERT OR IGNORE)
# ---------------------------------------------------------------------------
def test_subject_identifier_idempotent(repo) -> None:
    conn = get_connection()
    _seed_subject_material(conn)  # FK: v1_subject_identifiers.subject_id → v1_subjects.id
    assert repo.insert_subject_identifier("SUBJ-R", "nvd", "CVE-2026-1") == 1
    # 同 (source, external_id) 二次插入 → 幂等忽略, rowcount=0
    assert repo.insert_subject_identifier("SUBJ-R", "nvd", "CVE-2026-1") == 0
    row = repo.find_subject_identifier("nvd", "CVE-2026-1")
    assert row is not None and row["subject_id"] == "SUBJ-R"
    assert repo.find_subject_identifier("nvd", "nope") is None
