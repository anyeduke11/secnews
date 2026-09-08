"""T12 ArtifactService 单元测试 (10 个)."""
from __future__ import annotations

import pytest

from backend.repository.db import get_connection
from backend.services.action_service import ActionService
from backend.services.artifact_service import (
    ArtifactConflictError,
    ArtifactNotFoundError,
    ArtifactService,
    ArtifactValidationError,
)
from backend.services.run_service import RunService


def _seed_published_judgment(judgment_id: str = "J" * 26) -> None:
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments "
        "(id, case_id, claim_type, claim, conditions, confidence, "
        " evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, "
        " content_hash, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (judgment_id, "C" * 26, "finding", "X", "", "high",
         "[]", "[]", "[]", "published", "h" * 64, 1, now, now),
    )
    conn.commit()


def _seed_action_run() -> tuple[str, str]:
    """建 published judgment + action(planned) + run(succeeded); 返 (action_id, run_id)."""
    _seed_published_judgment()
    a_svc = ActionService(dsh_caller=lambda _p: '{"plan": "# p", "expected_artifacts": ["r"], "success_criteria": "y", "tool_versions": {}, "unknowns": []}')
    a = a_svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    a_svc.approve(a["id"], expected_revision=1, approved_by="user")
    r_svc = RunService()
    run = r_svc.create_or_replay(
        action_id=a["id"], idempotency_key="idem-r", attempt=1, protocol="direct",
    )["run"]
    return a["id"], run["id"]


# ---------------------------------------------------------------------------
# create (4 测试)
# ---------------------------------------------------------------------------
def _write_body(tmp_path, content: str) -> str:
    """v1.0 C08 R08: content_ref 必传 + 文件已落盘; 写 tmp_path 文件并返回路径."""
    p = tmp_path / "body.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_create_artifact_pending(tmp_path, temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="修复报告",
        content="# 修复\n1. 升级到 7.2.0", format="md",
        content_ref=_write_body(tmp_path, "# 修复\n1. 升级到 7.2.0"),
    )
    assert a["status"] == "pending"
    assert a["content_hash"]  # sha256 已算
    assert a["size_bytes"] > 0
    assert "verify" in a["allowed_actions"]


def test_create_artifact_invalid_kind_raises(temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="invalid kind"):
        svc.create(run_id=rid, kind="wrong", title="x", content="x")


def test_create_artifact_invalid_format_raises(temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="invalid format"):
        svc.create(run_id=rid, kind="report", title="x", content="x", format="wrong")


def test_create_artifact_empty_title_raises(temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="title must be non-empty"):
        svc.create(run_id=rid, kind="report", title="", content="x")


# ---------------------------------------------------------------------------
# verify (1 测试)
# ---------------------------------------------------------------------------
def test_verify_pending_to_verified(tmp_path, temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="r", content="x",
        content_ref=_write_body(tmp_path, "x"),
    )
    out = svc.verify(a["id"], verified_by="ci-bot", verified_result="pass")
    assert out["status"] == "verified"
    assert out["verified_result"] == "pass"


# ---------------------------------------------------------------------------
# accept (2 测试)
# ---------------------------------------------------------------------------
def test_accept_verified_to_accepted(tmp_path, temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="r", content="x",
        content_ref=_write_body(tmp_path, "x"),
    )
    svc.verify(a["id"], verified_by="ci-bot")
    out = svc.accept(a["id"], accepted_by="user", accepted_note="ok")
    assert out["status"] == "accepted"
    assert out["accepted_by"] == "user"


def test_accept_non_verified_raises_409(tmp_path, temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="r", content="x",
        content_ref=_write_body(tmp_path, "x"),
    )
    with pytest.raises(ArtifactConflictError, match="status=pending"):
        svc.accept(a["id"], accepted_by="user")


# ---------------------------------------------------------------------------
# reject (1 测试)
# ---------------------------------------------------------------------------
def test_reject_pending_to_rejected(tmp_path, temp_db) -> None:
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="r", content="x",
        content_ref=_write_body(tmp_path, "x"),
    )
    out = svc.reject(a["id"], rejected_by="user", reason="内容不达标")
    assert out["status"] == "rejected"


# ---------------------------------------------------------------------------
# 防重传蒙混 (contracts §8.3) (2 测试)
# ---------------------------------------------------------------------------
def test_resubmit_after_reject_same_hash_raises_409(tmp_path, temp_db) -> None:
    """contracts §8.3: rejected 后同 content_hash 不可再 accept (防重传蒙混)."""
    _, rid = _seed_action_run()
    svc = ArtifactService()
    a = svc.create(
        run_id=rid, kind="report", title="r", content="bad content",
        content_ref=_write_body(tmp_path, "bad content"),
    )
    svc.verify(a["id"], verified_by="ci-bot", verified_result="fail")
    # 第二次创建同 content (同 hash) → reject verify 后 accept 应抛 409
    b = svc.create(
        run_id=rid, kind="report", title="r2", content="bad content",
        content_ref=_write_body(tmp_path, "bad content"),
    )
    svc.verify(b["id"], verified_by="ci-bot", verified_result="pass")  # 第二次 verify pass
    with pytest.raises(ArtifactConflictError, match="rejected"):
        svc.accept(b["id"], accepted_by="user")


def test_get_not_found_raises() -> None:
    svc = ArtifactService()
    with pytest.raises(ArtifactNotFoundError):
        svc.get("NOSUCHARTIFACT0000000000")
