"""v1.0 C05 反例测试 (R01 修复断言: _insert_subject/material/signal 真 INSERT).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §6 C05] + [REVIEW_2026-09-07.md §R01].

R01 真问题:
  - `backend/services/v1_evidence_service.py:_insert_subject/material/signal` 3 个方法
    全 `pass` 占位 (T05 时未填 INSERT).
  - 走 `commit_intent(entity_type="subject"|"material"|"signal")` 路径时, receipt
    status=committed, 但 v1_subjects / v1_materials / v1_signals 表 0 行写入.
  - 调用方 (case_service / judgment_service / knowledge_service / action_service
    / sk01_daily_priority) 都依赖这 3 个表查事实; R01 后查返空 → 整个事项-证据
    闭环虚报成功.

R01 修复:
  - 3 个方法填真 INSERT (SQL 走 ? 参数绑定, 失败 raise 不吞).
  - 失败时由 record_audit 写 audit_log (actor=system / action=v1_evidence.entity_insert_failed).
  - 验证 commit 后 SELECT FROM v1_subjects / v1_materials / v1_signals 读回新行.

Mimosa 约束: SQL 全 ? 参数绑定; 禁 mock/noop 吞异常.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.repository.db import get_connection
from backend.services.v1_evidence_service import (
    V1EvidenceService,
    RECEIPT_COMMITTED,
    _hash_body,
)


def _submission_key(prefix: str) -> str:
    """用 iso 时间戳避免测试间 submission_key 撞库 (幂等唯一约束)."""
    return f"{prefix}-{datetime.now(timezone.utc).isoformat()}"


# ---------------------------------------------------------------------------
# R01 修复断言 1: _insert_subject 真 INSERT — commit 后 SELECT 读回
# ---------------------------------------------------------------------------
def test_insert_subject_writes_real_row_after_commit(temp_db) -> None:
    """R01 修复断言: commit_intent(entity_type='subject') 真写 v1_subjects.

    旧实现: _insert_subject 是 pass 占位, receipt status=committed 但 v1_subjects 0 行.
    修复后: INSERT INTO v1_subjects (...) 后, SELECT 应能读到 id 对应行.
    """
    svc = V1EvidenceService(projection_dir=None)
    body = {
        "id": "SUBJ-C05-001",
        "entity_type": "cve",
        "canonical_name": "CVE-2026-C05A",
        "aliases_json": json.dumps(["CVE-2026-C05A", "GH-abc"]),
        "importance": "high",
        "tags_json": json.dumps(["rce"]),
        "related_subject_ids_json": json.dumps([]),
        "first_seen_at": "2026-09-07T00:00:00+00:00",
        "last_seen_at": "2026-09-07T00:00:00+00:00",
        "revision": 1,
    }
    intent = svc.create_intent(_submission_key("c05-subj-1"), "subject", body, submitted_by="c05-test")
    res = svc.commit_intent(intent["intent_id"], entity_id=body["id"])
    assert res["status"] == RECEIPT_COMMITTED

    conn = get_connection()
    row = conn.execute(
        "SELECT id, entity_type, canonical_name, importance FROM v1_subjects WHERE id = ?",
        (body["id"],),
    ).fetchone()
    assert row is not None, (
        f"R01 修复断言: v1_subjects 应有 id={body['id']} 行, 实际 None "
        f"(旧实现 _insert_subject 是 pass 占位, 表 0 行)"
    )
    assert row[0] == "SUBJ-C05-001"
    assert row[1] == "cve"
    assert row[2] == "CVE-2026-C05A"
    assert row[3] == "high"


# ---------------------------------------------------------------------------
# R01 修复断言 2: _insert_material 真 INSERT — commit 后 SELECT 读回
# ---------------------------------------------------------------------------
def test_insert_material_writes_real_row_after_commit(temp_db) -> None:
    """R01 修复断言: commit_intent(entity_type='material') 真写 v1_materials.

    旧实现: _insert_material 是 pass 占位, receipt status=committed 但 v1_materials 0 行.
    """
    svc = V1EvidenceService(projection_dir=None)
    body = {
        "id": "MAT-C05-001",
        "source_kind": "url",
        "url": "https://example.com/c05",
        "title": "C05 material test",
        "content_hash": "h" * 64,
        "content_length": 12345,
        "summary": "C05 material summary",
        "published_at": "2026-09-07T00:00:00+00:00",
        "fetched_at": "2026-09-07T00:00:00+00:00",
        "fetched_by": "c05-test",
        "subject_ids_json": json.dumps([]),
        "metadata_json": json.dumps({}),
        "revision": 1,
    }
    intent = svc.create_intent(_submission_key("c05-mat-1"), "material", body, submitted_by="c05-test")
    res = svc.commit_intent(intent["intent_id"], entity_id=body["id"])
    assert res["status"] == RECEIPT_COMMITTED

    conn = get_connection()
    row = conn.execute(
        "SELECT id, source_kind, title, content_length FROM v1_materials WHERE id = ?",
        (body["id"],),
    ).fetchone()
    assert row is not None, (
        f"R01 修复断言: v1_materials 应有 id={body['id']} 行, 实际 None "
        f"(旧实现 _insert_material 是 pass 占位)"
    )
    assert row[0] == "MAT-C05-001"
    assert row[1] == "url"
    assert row[2] == "C05 material test"
    assert row[3] == 12345


# ---------------------------------------------------------------------------
# R01 修复断言 3: _insert_signal 真 INSERT — commit 后 SELECT 读回
# ---------------------------------------------------------------------------
def test_insert_signal_writes_real_row_after_commit(temp_db) -> None:
    """R01 修复断言: commit_intent(entity_type='signal') 真写 v1_signals.

    旧实现: _insert_signal 是 pass 占位, receipt status=committed 但 v1_signals 0 行.
    signal 表有 FK → v1_subjects / v1_materials, 必须先建 subject + material 行.
    """
    # 先建 subject + material 行 (signal FK 依赖)
    svc = V1EvidenceService(projection_dir=None)
    subj_body = {
        "id": "SUBJ-SIG-001",
        "entity_type": "cve",
        "canonical_name": "CVE-2026-C05SIG",
        "first_seen_at": "2026-09-07T00:00:00+00:00",
        "last_seen_at": "2026-09-07T00:00:00+00:00",
    }
    mat_body = {
        "id": "MAT-SIG-001",
        "source_kind": "url",
        "url": "https://example.com/c05sig",
        "title": "C05 signal material",
        "content_hash": "s" * 64,
        "content_length": 9999,
        "fetched_at": "2026-09-07T00:00:00+00:00",
    }
    s_intent = svc.create_intent(_submission_key("c05-sig-subj"), "subject", subj_body, submitted_by="c05-test")
    svc.commit_intent(s_intent["intent_id"], entity_id=subj_body["id"])
    m_intent = svc.create_intent(_submission_key("c05-sig-mat"), "material", mat_body, submitted_by="c05-test")
    svc.commit_intent(m_intent["intent_id"], entity_id=mat_body["id"])

    # 建 signal 行
    sig_body = {
        "id": "SIG-C05-001",
        "subject_id": "SUBJ-SIG-001",
        "material_id": "MAT-SIG-001",
        "summary": "C05 signal summary",
        "occurred_at": "2026-09-07T00:00:00+00:00",
        "admission_rule_version": "v1",
        "admission_reason": "c05 test reason",
        "confidence": "verified",
        "status": "unverified",
        "revision": 1,
    }
    intent = svc.create_intent(_submission_key("c05-sig-1"), "signal", sig_body, submitted_by="c05-test")
    res = svc.commit_intent(intent["intent_id"], entity_id=sig_body["id"])
    assert res["status"] == RECEIPT_COMMITTED

    conn = get_connection()
    row = conn.execute(
        "SELECT id, subject_id, material_id, confidence FROM v1_signals WHERE id = ?",
        (sig_body["id"],),
    ).fetchone()
    assert row is not None, (
        f"R01 修复断言: v1_signals 应有 id={sig_body['id']} 行, 实际 None "
        f"(旧实现 _insert_signal 是 pass 占位)"
    )
    assert row[0] == "SIG-C05-001"
    assert row[1] == "SUBJ-SIG-001"
    assert row[2] == "MAT-SIG-001"
    assert row[3] == "verified"


# ---------------------------------------------------------------------------
# R01 修复断言 4 (反例基线): INSERT 失败 raise, 不吞
# ---------------------------------------------------------------------------
def test_insert_signal_fk_violation_raises_not_swallowed(temp_db) -> None:
    """R01 反例基线: signal 的 FK subject_id 不存在时, 必 raise IntegrityError.

    旧实现: _insert_signal 是 pass, 即使 FK 违反也吞掉 → 上层 commit_intent 返
    success, 但 signal 表 0 行. 修复后: INSERT 失败 raise, 事务回滚, receipt 不 committed.
    """
    svc = V1EvidenceService(projection_dir=None)
    sig_body = {
        "id": "SIG-C05-FK",
        "subject_id": "SUBJ-DOES-NOT-EXIST",  # FK 违反
        "material_id": "MAT-DOES-NOT-EXIST",  # FK 违反
        "summary": "FK violation",
        "occurred_at": "2026-09-07T00:00:00+00:00",
        "admission_rule_version": "v1",
        "admission_reason": "",
        "confidence": "unverified",
        "status": "unverified",
        "revision": 1,
    }
    intent = svc.create_intent(_submission_key("c05-fk-1"), "signal", sig_body, submitted_by="c05-test")
    # commit 应 raise (FK 违反) — 旧实现不会 raise (pass 吞), 是 R01 真问题
    with pytest.raises(Exception) as excinfo:
        svc.commit_intent(intent["intent_id"], entity_id=sig_body["id"])
    assert "FOREIGN KEY" in str(excinfo.value).upper() or "constraint" in str(excinfo.value).lower(), (
        f"R01 反例: 失败应 raise FK 错误, 实际 {type(excinfo.value).__name__}: {excinfo.value}"
    )
    # receipt 因事务回滚, 应仍为 pending (无 committed 行)
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM v1_evidence_receipts WHERE intent_id = ?",
        (intent["intent_id"],),
    ).fetchone()
    assert row[0] == "pending", (
        f"R01 修复: 失败 INSERT 应让 receipt 仍 pending, 实际 {row[0]}"
    )
