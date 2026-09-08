"""v1.0 9 域对象 Pydantic 模型基础契约测试.

锁定 contracts.md §1-§9 的字段 / 必填 / 状态机 / allowed_actions.
新增域对象时本测试必须扩展; 删除时同步删除对应段 (与 contracts.md 同步).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.domain.v1_0_models import (
    DOMAIN_MODELS,
    Action,
    ActionStatus,
    Artifact,
    ArtifactFormat,
    ArtifactKind,
    ArtifactStatus,
    Case,
    CasePriority,
    CaseStatus,
    ClaimType,
    Confidence,
    EvidenceRef,
    Judgment,
    JudgmentConfidence,
    JudgmentStatus,
    Knowledge,
    KnowledgeKind,
    KnowledgeStatus,
    Material,
    Run,
    RunProtocol,
    RunStatus,
    RunTriggerSource,
    Signal,
    SignalStatus,
    Step,
    StepStatus,
    Subject,
    SubjectEntityType,
    SubjectImportance,
    VerificationResult,
)


def _ulid() -> str:
    """26 字符 ID 满足 pattern=^[A-Z2-7]{26}$ (Crockford Base32 subset)."""
    # 字符集: A-Z (26) + 2-7 (6) = 32 chars, 与 ULID 一致
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(alphabet[i % 32] for i in range(26))


def _ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 枚举覆盖
# ---------------------------------------------------------------------------
def test_enum_values_locked() -> None:
    """枚举值与 contracts.md §0.1 对齐; 任何漂移都说明契约变更."""
    assert CaseStatus.open.value == "open"
    assert CaseStatus.in_progress.value == "in_progress"
    assert CaseStatus.blocked.value == "blocked"
    assert CaseStatus.closed.value == "closed"
    assert CaseStatus.archived.value == "archived"
    assert SubjectEntityType.cve.value == "cve"
    assert SubjectEntityType.product.value == "product"
    assert SignalStatus.verified.value == "verified"
    assert SignalStatus.likely.value == "likely"
    assert SignalStatus.unverified.value == "unverified"
    assert JudgmentStatus.draft.value == "draft"
    assert JudgmentStatus.published.value == "published"
    assert ActionStatus.planned.value == "planned"
    assert ActionStatus.approved.value == "approved"
    assert ActionStatus.running.value == "running"
    assert ActionStatus.succeeded.value == "succeeded"
    assert ActionStatus.failed.value == "failed"
    assert RunStatus.queued.value == "queued"
    assert RunStatus.running.value == "running"
    assert ArtifactStatus.accepted.value == "accepted"
    assert ArtifactStatus.rejected.value == "rejected"
    assert KnowledgeKind.playbook.value == "playbook"
    assert KnowledgeKind.anti_pattern.value == "anti_pattern"


# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------
def test_subject_minimal_required() -> None:
    s = Subject(
        id=_ulid(),
        entity_type=SubjectEntityType.cve,
        name="CVE-2026-31337",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert s.revision == 1
    assert s.importance == SubjectImportance.normal
    assert s.allowed_actions == []
    assert s.aliases == []


def test_subject_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        Subject(
            id="lowercase-fails-12345678",
            entity_type=SubjectEntityType.cve,
            name="x",
            created_at=_ts(),
            updated_at=_ts(),
        )


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------
def test_material_minimal_required() -> None:
    m = Material(
        id="a" * 26,
        source="rss",
        url="https://example.com/feed",
        first_seen_at=_ts(),
        hash="h" * 64,
        parser_version="v1",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert m.title is None
    assert m.revision == 1
    assert m.extra == {}


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------
def test_signal_minimal_required() -> None:
    s = Signal(
        id=_ulid(),
        material_id="M" * 26,
        summary="x",
        occurred_at=_ts(),
        admission_rule_version="v1",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert s.confidence == Confidence.unverified
    assert s.status == SignalStatus.unverified
    assert s.subject_id is None


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------
def test_case_minimal_required() -> None:
    c = Case(
        id=_ulid(),
        title="t",
        question="q",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert c.priority == CasePriority.p2
    assert c.status == CaseStatus.open


# ---------------------------------------------------------------------------
# Judgment
# ---------------------------------------------------------------------------
def test_judgment_minimal_required() -> None:
    j = Judgment(
        id=_ulid(),
        case_id="C" * 26,
        subject_id="S" * 26,
        claim_type=ClaimType.finding,
        claim="x",
        evidence_refs=[EvidenceRef(material_id="M" * 26, hash="h" * 64)],
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert j.confidence == JudgmentConfidence.medium
    assert j.status == JudgmentStatus.draft
    assert j.counter_evidence_refs == []


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------
def test_action_minimal_required() -> None:
    a = Action(
        id=_ulid(),
        case_id="C" * 26,
        judgment_id="J" * 26,
        title="x",
        plan="# x",
        plan_hash="h" * 64,
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert a.status == ActionStatus.planned


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def test_run_minimal_required() -> None:
    r = Run(
        id=f"run_{_ulid()}",
        action_id="A" * 26,
        attempt=1,
        skill_id="patch-deploy",
        protocol=RunProtocol.direct,
        trigger_source=RunTriggerSource.user,
        idempotency_key="key-001",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert r.status == RunStatus.queued


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------
def test_artifact_minimal_required() -> None:
    a = Artifact(
        id=_ulid(),
        run_id="R" * 26,
        kind=ArtifactKind.report,
        title="x",
        content_hash="h" * 64,
        format=ArtifactFormat.pdf,
        size_bytes=1024,
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert a.status == ArtifactStatus.pending


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------
def test_knowledge_minimal_required() -> None:
    k = Knowledge(
        id=_ulid(),
        kind=KnowledgeKind.playbook,
        title="x",
        body="# x",
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert k.status == KnowledgeStatus.draft


# ---------------------------------------------------------------------------
# EvidenceRef (frozen)
# ---------------------------------------------------------------------------
def test_evidence_ref_frozen() -> None:
    ref = EvidenceRef(material_id="M" * 26, hash="h" * 64)
    with pytest.raises(ValidationError):
        ref.material_id = "X" * 26  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Step (extra=forbid)
# ---------------------------------------------------------------------------
def test_step_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Step(
            seq=0,
            tool="x",
            started_at=_ts(),
            input_hash="h" * 64,
            status=StepStatus.ok,
            duration_ms=0,
            extra="nope",  # type: ignore[call-arg]
        )


def test_step_minimal_required() -> None:
    s = Step(
        seq=0,
        tool="x",
        started_at=_ts(),
        input_hash="h" * 64,
        status=StepStatus.ok,
        duration_ms=0,
    )
    assert s.finished_at is None
    assert s.output_hash is None


# ---------------------------------------------------------------------------
# DOMAIN_MODELS 列表契约
# ---------------------------------------------------------------------------
def test_domain_models_exports_all_nine() -> None:
    """DOMAIN_MODELS 列表应包含 9 域对象 (Subject/Material/Signal/Case/Judgment/Action/Run/Artifact/Knowledge)."""
    names = {m.__name__ for m in DOMAIN_MODELS}
    expected = {"Subject", "Material", "Signal", "Case", "Judgment", "Action", "Run", "Artifact", "Knowledge"}
    assert names == expected, f"missing: {expected - names}, extra: {names - expected}"


# ---------------------------------------------------------------------------
# round-trip JSON 序列/反序列化
# ---------------------------------------------------------------------------
def test_case_round_trip_json() -> None:
    cid = _ulid()
    c = Case(
        id=cid, title="t", question="q",
        status=CaseStatus.in_progress, priority=CasePriority.p0,
        created_at=_ts(), updated_at=_ts(),
    )
    js = c.model_dump_json()
    c2 = Case.model_validate_json(js)
    assert c2.id == cid
    assert c2.status == CaseStatus.in_progress
    assert c2.priority == CasePriority.p0


def test_evidence_ref_in_judgment_serialization() -> None:
    j = Judgment(
        id=_ulid(),
        case_id="C" * 26,
        subject_id="S" * 26,
        claim_type=ClaimType.assessment,
        claim="x",
        evidence_refs=[EvidenceRef(material_id="M" * 26, hash="h" * 64, quote="text")],
        created_at=_ts(),
        updated_at=_ts(),
    )
    js = j.model_dump_json()
    j2 = Judgment.model_validate_json(js)
    assert len(j2.evidence_refs) == 1
    assert j2.evidence_refs[0].quote == "text"


# ---------------------------------------------------------------------------
# VerificationResult 枚举
# ---------------------------------------------------------------------------
def test_verification_result_enum() -> None:
    assert VerificationResult.pass_.value == "pass"
    assert VerificationResult.fail.value == "fail"
    assert VerificationResult.warn.value == "warn"


# ---------------------------------------------------------------------------
# 字段约束
# ---------------------------------------------------------------------------
def test_case_priority_enum_members() -> None:
    """CasePriority 4 档 (p0/p1/p2/p3)."""
    assert {p.value for p in CasePriority} == {"p0", "p1", "p2", "p3"}


def test_subject_importance_enum_members() -> None:
    assert {p.value for p in SubjectImportance} == {"critical", "high", "normal", "low", "watchlist"}


def test_case_title_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        Case(
            id=_ulid(), title="x" * 200, question="q",
            created_at=_ts(), updated_at=_ts(),
        )  # max_length=120


def test_signal_summary_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        Signal(
            id=_ulid(), material_id="M" * 26, summary="x" * 600,
            occurred_at=_ts(), admission_rule_version="v1",
            created_at=_ts(), updated_at=_ts(),
        )  # max_length=500


def test_run_attempt_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Run(
            id=_ulid(), action_id="A" * 26, attempt=0,
            skill_id="x", protocol=RunProtocol.direct,
            trigger_source=RunTriggerSource.user, idempotency_key="k",
        )


def test_judgment_confidence_4_levels() -> None:
    """JudgmentConfidence 4 档 (low/medium/high/proved)."""
    assert {c.value for c in JudgmentConfidence} == {"low", "medium", "high", "proved"}

