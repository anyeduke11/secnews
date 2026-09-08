"""T12 ActionService 单元测试 (12 个)."""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.services.action_service import (
    ActionConflictError,
    ActionNotFoundError,
    ActionService,
    ActionValidationError,
)


# ---------------------------------------------------------------------------
# fake dsh
# ---------------------------------------------------------------------------
def _fake_dsh_factory(responses: list[str]):
    it = iter(responses)

    def caller(_p: str) -> str:
        try:
            return next(it)
        except StopIteration:
            return json.dumps({
                "plan": "# fallback plan",
                "expected_artifacts": ["report"],
                "success_criteria": "fallback",
                "tool_versions": {},
                "unknowns": ["fallback"],
            })
    return caller


def _dsh_response() -> str:
    return json.dumps({
        "plan": "# Plan\n1. 升级\n2. 验证",
        "expected_artifacts": ["checklist", "report"],
        "success_criteria": "升级完成 + 验证通过",
        "tool_versions": {"patcher": "1.0"},
        "unknowns": ["缺文档"],
    })


def _seed_published_judgment(judgment_id: str) -> None:
    """v1_judgments + 标 published (T11 模式)."""
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


# ---------------------------------------------------------------------------
# 校验链 (3 测试)
# ---------------------------------------------------------------------------
def test_validate_create_payload_empty_plan_raises() -> None:
    svc = ActionService()
    with pytest.raises(ActionValidationError, match="plan must be non-empty"):
        svc._validate_create_payload(
            case_id="C" * 26, judgment_id="J" * 26, title="x", plan="",
            success_criteria="y", expected_artifacts=["r"],
        )


def test_validate_create_payload_plan_too_long_raises() -> None:
    svc = ActionService()
    with pytest.raises(ActionValidationError, match="exceeds"):
        svc._validate_create_payload(
            case_id="C" * 26, judgment_id="J" * 26, title="x", plan="p" * 50_001,
            success_criteria="y", expected_artifacts=["r"],
        )


def test_validate_create_payload_empty_expected_artifacts_raises() -> None:
    svc = ActionService()
    with pytest.raises(ActionValidationError, match="expected_artifacts must be non-empty"):
        svc._validate_create_payload(
            case_id="C" * 26, judgment_id="J" * 26, title="x", plan="plan",
            success_criteria="y", expected_artifacts=[],
        )


# ---------------------------------------------------------------------------
# judgment_id 引用校验 (contracts §10.1) (2 测试)
# ---------------------------------------------------------------------------
def test_create_with_dsh_requires_published_judgment(temp_db) -> None:
    """judgment 状态 = draft → 422 (action.judgment_id 必引 published)."""
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    jid = "D" * 26
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments "
        "(id, case_id, claim_type, claim, conditions, confidence, "
        " evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, "
        " content_hash, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (jid, "C" * 26, "finding", "X", "", "high",
         "[]", "[]", "[]", "draft", "h" * 64, 1, now, now),
    )
    conn.commit()
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    with pytest.raises(ActionValidationError, match="must reference published judgment"):
        svc.create_with_dsh(
            case_id="C" * 26, judgment_id=jid, title="t", subject_name="X",
            cve_id="CVE-X", scope="y", evidence_materials=[],
        )


def test_create_with_dsh_judgment_not_found_raises(temp_db) -> None:
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    with pytest.raises(ActionValidationError, match="not found"):
        svc.create_with_dsh(
            case_id="C" * 26, judgment_id="NOSUCHJUDG0000000000000",
            title="t", subject_name="X", cve_id="CVE-X", scope="y", evidence_materials=[],
        )


# ---------------------------------------------------------------------------
# create_with_dsh 正常路径 (1 测试)
# ---------------------------------------------------------------------------
def test_create_with_dsh_draft_inserts(temp_db) -> None:
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    out = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="升级",
        subject_name="网关", cve_id="CVE-2026-31337", scope="生产",
        evidence_materials=[],
    )
    assert out["idempotent_replay"] is False
    a = out["action"]
    assert a["status"] == "planned"
    assert a["title"] == "升级"
    assert a["plan_hash"]  # 已算
    assert a["revision"] == 1
    assert "approve" in a["allowed_actions"]


# ---------------------------------------------------------------------------
# 状态机 (4 测试)
# ---------------------------------------------------------------------------
def test_approve_planned_to_approved(temp_db) -> None:
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    a = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    out = svc.approve(a["id"], expected_revision=1, approved_by="user")
    assert out["status"] == "approved"
    assert out["approved_by"] == "user"
    assert "start" in out["allowed_actions"]


def test_approve_cas_revision_mismatch_raises(temp_db) -> None:
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    a = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    with pytest.raises(ActionConflictError, match="revision mismatch"):
        svc.approve(a["id"], expected_revision=999, approved_by="user")


def test_approve_non_planned_raises(temp_db) -> None:
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    a = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    svc.approve(a["id"], expected_revision=1, approved_by="user")
    with pytest.raises(ActionConflictError, match="status=approved"):
        svc.approve(a["id"], expected_revision=2, approved_by="user")


def test_start_approved_creates_run(temp_db) -> None:
    """approved → start → action=running, run=queued; 真实派发走 worker_pump C07 路径."""
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    a = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    svc.approve(a["id"], expected_revision=1, approved_by="user")
    # start 需 revision=2
    out = svc.start(
        a["id"], expected_revision=2,
        idempotency_key="idem-key-1", protocol="direct",
    )
    # v1.0 C07 R05 修复: 真实协议 (direct) 走 worker_pump 派发, action=running + run=queued
    assert out["action"]["status"] == "running"
    assert out["run"]["status"] == "queued"
    assert out["replayed"] is False


# ---------------------------------------------------------------------------
# list / get (2 测试)
# ---------------------------------------------------------------------------
def test_list_and_get(temp_db) -> None:
    _seed_published_judgment("J" * 26)
    svc = ActionService(dsh_caller=_fake_dsh_factory([_dsh_response()]))
    a = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    out = svc.list_by_case("C" * 26, status="planned", limit=10)
    assert out["total"] == 1
    assert out["items"][0]["id"] == a["id"]
    single = svc.get(a["id"])
    assert single["title"] == "t"


def test_get_not_found_raises() -> None:
    svc = ActionService()
    with pytest.raises(ActionNotFoundError):
        svc.get("NOSUCHACTION000000000000")
