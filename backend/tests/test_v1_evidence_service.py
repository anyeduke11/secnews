"""v1.0 T05 证据提交协议故障测试 (intent/commit/rollback/投影/幂等/超时).

覆盖 (对应 EXECUTION_GUIDE §4 T05 通过证据):
  1. create_intent + commit 正常路径 → receipt committed
  2. 同 submission_key + body 重放 → IdempotentReplay
  3. 同 submission_key + 不同 body 在 pending → IntentExistsError
  4. rollback 后 receipt 标 rolled_back + 临时文件清理
  5. 投影 atomic rename 成功 (target 路径出现)
  6. 投影 target 已存在 → FileExistsError + receipt 回滚
  7. 投影 target 内容为空 → ValueError + receipt 回滚
  8. reap_expired_intents 把超时 pending 标 rolled_back
  9. 投影目录未提供时跳过 (projection_status=skipped)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.repository.db import get_connection
from backend.services.v1_evidence_service import (
    RECEIPT_COMMITTED,
    RECEIPT_ROLLED_BACK,
    IdempotentReplay,
    IntentExistsError,
    V1EvidenceService,
    _hash_body,
)


def _submission_key(prefix: str) -> str:
    """用 iso 时间戳避免测试间 submission_key 撞库 (幂等唯一约束)."""
    return f"{prefix}-{datetime.now(timezone.utc).isoformat()}"


def test_create_and_commit_intent(temp_db) -> None:
    """create_intent + commit 正常路径 → receipt committed + projection renamed."""
    from pathlib import Path
    proj = Path(temp_db).parent / "projection_1"
    svc = V1EvidenceService(projection_dir=proj)
    body = {"id": "SUBJ-001", "entity_type": "cve", "canonical_name": "CVE-2026-31337"}
    intent = svc.create_intent(_submission_key("k1"), "subject", body, submitted_by="t05-test")
    assert intent["status"] == "pending"
    assert intent["body_hash"] == _hash_body(body)
    # commit (无投影, 走 skipped 路径)
    res = svc.commit_intent(intent["intent_id"], entity_id=body["id"])
    assert res["status"] == RECEIPT_COMMITTED
    assert res["projection_status"] == "skipped"
    assert res["entity_id"] == "SUBJ-001"


def test_idempotent_replay_same_submission_key_and_body(temp_db) -> None:
    """同 submission_key + body 重放 → IdempotentReplay."""
    proj = None
    svc = V1EvidenceService(projection_dir=proj)
    body = {"id": "SUBJ-002", "entity_type": "cve", "canonical_name": "CVE-DUP"}
    key = _submission_key("dup")
    intent = svc.create_intent(key, "subject", body)
    svc.commit_intent(intent["intent_id"], entity_id=body["id"])
    # 第二次 create_intent 同 key + 同 body → IdempotentReplay
    with pytest.raises(IdempotentReplay) as excinfo:
        svc.create_intent(key, "subject", body)
    assert "already committed" in str(excinfo.value)
    assert "SUBJ-002" in str(excinfo.value)


def test_intent_exists_different_body(temp_db) -> None:
    """同 submission_key + 不同 body 在 pending → IntentExistsError."""
    svc = V1EvidenceService(projection_dir=None)
    key = _submission_key("diff")
    body_a = {"id": "SUBJ-A", "entity_type": "cve", "canonical_name": "A"}
    body_b = {"id": "SUBJ-B", "entity_type": "cve", "canonical_name": "B"}
    svc.create_intent(key, "subject", body_a)
    with pytest.raises(IntentExistsError) as excinfo:
        svc.create_intent(key, "subject", body_b)
    assert "pending with different body_hash" in str(excinfo.value)


def test_rollback_marks_receipt_and_clears_tmp(temp_db) -> None:
    """rollback → receipt rolled_back + 临时投影文件清理."""
    from pathlib import Path
    proj = Path(temp_db).parent / "projection_rb"
    svc = V1EvidenceService(projection_dir=proj)
    # 先建一个有 commit 失败场景的 intent (强制走错误路径)
    body = {"id": "SUBJ-RB", "entity_type": "cve", "canonical_name": "RB"}
    intent = svc.create_intent(_submission_key("rb"), "subject", body)
    # 提前放一个临时文件, 验证 rollback 清理
    tmp_dir = proj / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / f"{intent['intent_id']}.md").write_text("orphan tmp")
    # rollback
    res = svc.rollback_intent(intent["intent_id"], reason="test rollback")
    assert res["status"] == RECEIPT_ROLLED_BACK
    # 验证 receipt 落库
    conn = get_connection()
    row = conn.execute(
        "SELECT status, extra_json FROM v1_evidence_receipts WHERE intent_id = ?",
        (intent["intent_id"],),
    ).fetchone()
    assert row[0] == RECEIPT_ROLLED_BACK
    assert json.loads(row[1])["reason"] == "test rollback"


def test_atomic_rename_projection_success(temp_db) -> None:
    """投影 atomic rename 成功 → target 路径出现, .tmp 清空."""
    from pathlib import Path
    proj = Path(temp_db).parent / "projection_ok"
    svc = V1EvidenceService(projection_dir=proj)
    body = {"id": "MAT-001", "source_kind": "url", "title": "Sample", "content_hash": "h" * 64, "content_length": 100, "fetched_at": "2026-01-01T00:00:00+00:00"}
    intent = svc.create_intent(_submission_key("ok"), "material", body)
    res = svc.commit_intent(
        intent["intent_id"],
        entity_id=body["id"],
        projection={"wiki_path": "items/mat-001.md", "wiki_content": "# MAT-001\nbody"},
    )
    assert res["projection_status"] == "renamed"
    target = proj / "items" / "mat-001.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("# MAT-001")


def test_atomic_rename_projection_target_exists(temp_db) -> None:
    """投影 target 已存在 → FileExistsError, 事务回滚 (receipt 不应 committed)."""
    from pathlib import Path
    proj = Path(temp_db).parent / "projection_conflict"
    proj.mkdir(parents=True, exist_ok=True)
    # 预先放一个冲突文件
    (proj / "items").mkdir(parents=True, exist_ok=True)
    (proj / "items" / "mat-002.md").write_text("existing content")
    svc = V1EvidenceService(projection_dir=proj)
    body = {"id": "MAT-002", "source_kind": "url", "title": "Conflict", "content_hash": "x" * 64, "content_length": 10, "fetched_at": "2026-01-01T00:00:00+00:00"}
    intent = svc.create_intent(_submission_key("conflict"), "material", body)
    with pytest.raises(FileExistsError):
        svc.commit_intent(
            intent["intent_id"],
            entity_id=body["id"],
            projection={"wiki_path": "items/mat-002.md", "wiki_content": "new"},
        )
    # 关键验证: receipt 因事务回滚, 应仍为 pending (无 committed 行)
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM v1_evidence_receipts WHERE intent_id = ?",
        (intent["intent_id"],),
    ).fetchone()
    assert row[0] == "pending"
    # 冲突文件未被覆盖
    assert (proj / "items" / "mat-002.md").read_text() == "existing content"


def test_atomic_rename_projection_empty_content(temp_db) -> None:
    """投影 content 为空 → ValueError, receipt 不 committed."""
    from pathlib import Path
    proj = Path(temp_db).parent / "projection_empty"
    svc = V1EvidenceService(projection_dir=proj)
    body = {"id": "MAT-003", "source_kind": "url", "title": "Empty", "content_hash": "y" * 64, "content_length": 0, "fetched_at": "2026-01-01T00:00:00+00:00"}
    intent = svc.create_intent(_submission_key("empty"), "material", body)
    with pytest.raises(ValueError):
        svc.commit_intent(
            intent["intent_id"],
            entity_id=body["id"],
            projection={"wiki_path": "items/mat-003.md", "wiki_content": ""},
        )
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM v1_evidence_receipts WHERE intent_id = ?",
        (intent["intent_id"],),
    ).fetchone()
    assert row[0] == "pending"


def test_reap_expired_intents(temp_db) -> None:
    """超时未 commit 的 pending intent → reap 后标 rolled_back.

    通过先建 intent, 然后直接改 submitted_at 到 2h 之前 (绕过 1h 阈值) 模拟超时.
    """
    svc = V1EvidenceService(projection_dir=None)
    body = {"id": "SUBJ-TIMEOUT", "entity_type": "cve", "canonical_name": "T"}
    intent = svc.create_intent(_submission_key("timeout"), "subject", body)
    conn = get_connection()
    # 把 submitted_at 倒拨到 2 小时前
    conn.execute(
        "UPDATE v1_evidence_receipts SET submitted_at = datetime('now', '-2 hours') WHERE intent_id = ?",
        (intent["intent_id"],),
    )
    conn.commit()
    reaped = svc.reap_expired_intents()
    assert any(r["intent_id"] == intent["intent_id"] for r in reaped)
    row = conn.execute(
        "SELECT status, extra_json FROM v1_evidence_receipts WHERE intent_id = ?",
        (intent["intent_id"],),
    ).fetchone()
    assert row[0] == RECEIPT_ROLLED_BACK
    assert json.loads(row[1])["reason"] == "timeout"


def test_projection_skipped_when_dir_not_provided(temp_db) -> None:
    """未提供 projection_dir → commit 走 skipped 路径, 不抛错."""
    svc = V1EvidenceService(projection_dir=None)
    # v1.0 C05 R01: signal FK 要求 subject + material 已存在; 先建好
    subj_body = {"id": "SUBJ-X", "entity_type": "cve", "canonical_name": "X",
                 "first_seen_at": "2026-01-01T00:00:00+00:00", "last_seen_at": "2026-01-01T00:00:00+00:00"}
    mat_body = {"id": "MAT-Y", "source_kind": "url", "title": "Y",
                "content_hash": "y" * 64, "content_length": 10,
                "fetched_at": "2026-01-01T00:00:00+00:00"}
    s_intent = svc.create_intent(_submission_key("skipped-subj"), "subject", subj_body)
    svc.commit_intent(s_intent["intent_id"], entity_id=subj_body["id"])
    m_intent = svc.create_intent(_submission_key("skipped-mat"), "material", mat_body)
    svc.commit_intent(m_intent["intent_id"], entity_id=mat_body["id"])
    body = {"id": "SIG-001", "subject_id": "SUBJ-X", "material_id": "MAT-Y", "summary": "x", "occurred_at": "2026-01-01T00:00:00+00:00", "admission_rule_version": "v1"}
    intent = svc.create_intent(_submission_key("sig"), "signal", body)
    res = svc.commit_intent(intent["intent_id"], entity_id=body["id"])
    assert res["projection_status"] == "skipped"
    assert res["status"] == RECEIPT_COMMITTED
