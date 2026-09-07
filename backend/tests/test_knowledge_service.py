"""T13 KnowledgeService 单元测试 (14 个)."""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.services.action_service import ActionService
from backend.services.artifact_service import ArtifactService
from backend.services.knowledge_service import (
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeService,
    KnowledgeValidationError,
)
from backend.services.run_service import RunService


def _dsh_response() -> str:
    return json.dumps({
        "title": "FastGate 7.2.0 升级 playbook",
        "body": (
            "## 步骤\n1. 升级到 7.2.0\n2. 验证\n3. 监控 7 天\n\n"
            "## 适用边界\n- 暴露在公网\n- 固件 < 7.2.0"
        ),
        "prerequisites": ["FastGate 3200/4200 系列", "固件 < 7.2.0"],
        "counter_examples": ["内网部署且无对外接口"],
        "evidence_refs": [{"material_id": "MAT-K1", "hash": "k" * 64, "quote": "NVD 公告"}],
        "review_at": "2026-12-01T00:00:00+00:00",
    })


def _seed_material(material_id: str = "MAT-K1", content_hash: str = "k" * 64) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials "
        "(id, source_kind, url, title, content_hash, content_length, fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        (material_id, f"https://example.com/{material_id}", content_hash),
    )
    conn.commit()


def _make_draft() -> str:
    _seed_material()
    # 同步 seed v1_actions + v1_judgments + v1_cases (refs 需 INNER JOIN 命中)
    from backend.repository.db import get_connection
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments (id, case_id, claim_type, claim, conditions, confidence, "
        "evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, content_hash, "
        "revision, created_at, updated_at) "
        "VALUES (?, ?, 'finding', 'X', '', 'high', '[]', '[]', '[]', 'published', ?, 1, ?, ?)",
        ("J" * 26, "C" * 26, "h" * 64, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_actions (id, case_id, judgment_id, title, plan, plan_hash, "
        "expected_artifacts_json, status, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, 't', '# p', ?, '[\"r\"]', 'planned', 1, ?, ?)",
        ("A" * 26, "C" * 26, "J" * 26, "h" * 64, now, now),
    )
    conn.commit()
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    out = svc.create_with_dsh(
        case_id="C" * 26, judgment_id="J" * 26, action_id="A" * 26,
        subject_name="网关", cve_id="CVE-2026-31337", kind="playbook",
        evidence_materials=[],
    )
    return out["knowledge"]["id"]


# ---------------------------------------------------------------------------
# 校验链 (3 测试)
# ---------------------------------------------------------------------------
def test_validate_create_payload_empty_prerequisites_raises() -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeValidationError, match="prerequisites must be non-empty"):
        svc._validate_create_payload(
            kind="playbook", title="t", body="b",
            prerequisites=[], counter_examples=[], evidence_refs=[{"material_id": "x", "hash": "h" * 64}],
            review_at="2026-12-01T00:00:00+00:00", expiry_at=None,
        )


def test_validate_create_payload_empty_evidence_refs_raises() -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeValidationError, match="evidence_refs must be non-empty"):
        svc._validate_create_payload(
            kind="playbook", title="t", body="b",
            prerequisites=["p"], counter_examples=[], evidence_refs=[],
            review_at="2026-12-01T00:00:00+00:00", expiry_at=None,
        )


def test_validate_create_payload_missing_review_at_raises() -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeValidationError, match="review_at required"):
        svc._validate_create_payload(
            kind="playbook", title="t", body="b",
            prerequisites=["p"], counter_examples=[], evidence_refs=[{"material_id": "x", "hash": "h" * 64}],
            review_at=None, expiry_at=None,
        )


# ---------------------------------------------------------------------------
# evidence hash 校验 (2 测试)
# ---------------------------------------------------------------------------
def test_evidence_hash_mismatch_raises(temp_db) -> None:
    _seed_material("MAT-K1", "k" * 64)
    svc = KnowledgeService()
    with pytest.raises(KnowledgeValidationError, match="hash mismatch"):
        svc._validate_evidence_hashes([{"material_id": "MAT-K1", "hash": "z" * 64}])


def test_evidence_material_not_found_raises(temp_db) -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeValidationError, match="not found"):
        svc._validate_evidence_hashes([{"material_id": "MAT-MISSING", "hash": "x" * 64}])


# ---------------------------------------------------------------------------
# create_with_dsh (1 测试)
# ---------------------------------------------------------------------------
def test_create_with_dsh_draft_inserts(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    k = svc.get(kid)
    assert k["status"] == "draft"
    assert k["kind"] == "playbook"
    assert k["title"] == "FastGate 7.2.0 升级 playbook"
    assert k["revision"] == 1
    assert k["content_hash"]  # sha256 已算
    assert "publish" in k["allowed_actions"]


# ---------------------------------------------------------------------------
# 状态机 (4 测试)
# ---------------------------------------------------------------------------
def test_publish_draft_to_published(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    out = svc.publish(kid, expected_revision=1)
    assert out["status"] == "published"
    assert out["wiki_path"] == f"items/knowledge_{kid}.md"
    assert "create_revision" in out["allowed_actions"]
    assert "deprecate" in out["allowed_actions"]


def test_publish_cas_revision_mismatch_raises(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    with pytest.raises(KnowledgeConflictError, match="revision mismatch"):
        svc.publish(kid, expected_revision=999)


def test_deprecate_published_to_deprecated(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    svc.publish(kid, expected_revision=1)
    out = svc.deprecate(kid, expected_revision=2, reason="有更优方案")
    assert out["status"] == "deprecated"
    assert out["deprecation_reason"] == "有更优方案"
    assert "revive" in out["allowed_actions"]


def test_retract_published_to_retracted_terminal(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    svc.publish(kid, expected_revision=1)
    out = svc.retract(kid, expected_revision=2, reason="发现重大错误")
    assert out["status"] == "retracted"
    assert out["allowed_actions"] == []  # 终态


# ---------------------------------------------------------------------------
# 复用 + 复查 (4 测试)
# ---------------------------------------------------------------------------
def test_reuse_receipt_derives_by_source_type(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    receipt = svc.get_reuse_receipt(kid)
    assert receipt["by_judgment"] == 1
    assert receipt["by_action"] == 1
    assert receipt["total"] == 2
    assert receipt["recent_30d"] == 2


def test_list_by_case_returns_knowledge_for_case(temp_db) -> None:
    kid = _make_draft()
    svc = KnowledgeService()
    out = svc.list_by_case("C" * 26, status="draft", limit=10)
    assert out["total"] == 1
    assert out["items"][0]["id"] == kid


def test_scan_review_due_returns_published_with_review_past(temp_db) -> None:
    """SK-06: 扫 review_at <= now + status=published."""
    kid = _make_draft()
    svc = KnowledgeService()
    svc.publish(kid, expected_revision=1)
    # 把 review_at 倒拨到 1 小时前
    conn = get_connection()
    past = "2026-01-01T00:00:00+00:00"
    conn.execute("UPDATE v1_knowledge SET review_at = ? WHERE id = ?", (past, kid))
    conn.commit()
    items = svc.scan_review_due("2026-12-01T00:00:00+00:00")
    assert any(i["id"] == kid for i in items)


def test_mark_case_blocker_adds_tag(temp_db) -> None:
    """SK-06: 挂 blocker 到 case (v1_cases.tags_json 加 marker)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, tags_json) "
        "VALUES (?, 'T', 'Q', 1, datetime('now'), datetime('now'), '[]')",
        ("C" * 26,),
    )
    conn.commit()
    kid = _make_draft()
    svc = KnowledgeService()
    ok = svc.mark_case_blocker("C" * 26, kid)
    assert ok is True
    row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", ("C" * 26,)).fetchone()
    tags = json.loads(row[0])
    assert any(f"knowledge_review_due:{kid}" == t for t in tags)


# ---------------------------------------------------------------------------
# not found (1 测试)
# ---------------------------------------------------------------------------
def test_get_not_found_raises() -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeNotFoundError):
        svc.get("NOSUCHKNOWLEDGE0000000000")
