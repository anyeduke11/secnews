"""
v1.0 领域模型 (单一真相源).

codegen_v1_ts.py 读取本模块生成 frontend/src/domain/v1_0.ts.
下游 CI --check 确保 TS 与 Pydantic 同步。

参见 docs/v1.0/contracts.md §1-§9 + DEVELOPMENT_PLAN §5.4 §1.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 通用枚举 (contracts §0.1 + §1-§9)
# ---------------------------------------------------------------------------

class SubjectEntityType(str, Enum):
    product = "product"
    vendor = "vendor"
    cve = "cve"
    technique = "technique"
    regulation = "regulation"
    person = "person"
    org = "org"
    custom = "custom"


class SubjectImportance(str, Enum):
    critical = "critical"
    high = "high"
    normal = "normal"
    low = "low"
    watchlist = "watchlist"


class Confidence(str, Enum):
    verified = "verified"
    likely = "likely"
    unverified = "unverified"
    retracted = "retracted"


class JudgmentConfidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    proved = "proved"


class JudgmentStatus(str, Enum):
    draft = "draft"
    published = "published"
    superseded = "superseded"
    retracted = "retracted"


class ClaimType(str, Enum):
    finding = "finding"
    assessment = "assessment"
    recommendation = "recommendation"
    warning = "warning"
    hypothesis = "hypothesis"


class CasePriority(str, Enum):
    p0 = "p0"
    p1 = "p1"
    p2 = "p2"
    p3 = "p3"


class CaseStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    blocked = "blocked"
    closed = "closed"
    archived = "archived"


class CaseOwnerRole(str, Enum):
    user = "user"
    system = "system"
    shared = "shared"


class ActionStatus(str, Enum):
    planned = "planned"
    approved = "approved"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    rejected = "rejected"


class RunProtocol(str, Enum):
    dsh = "dsh"
    pi = "pi"
    direct = "direct"
    mock = "mock"


class RunTriggerSource(str, Enum):
    user = "user"
    agent = "agent"
    system = "system"
    scheduled = "scheduled"
    webhook = "webhook"


class RunStatus(str, Enum):
    queued = "queued"
    claimed = "claimed"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class StepStatus(str, Enum):
    ok = "ok"
    error = "error"
    skipped = "skipped"


class ArtifactKind(str, Enum):
    report = "report"
    file = "file"
    data = "data"
    chart = "chart"
    code_patch = "code_patch"
    message = "message"


class ArtifactStatus(str, Enum):
    pending = "pending"
    verified = "verified"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"


class ArtifactFormat(str, Enum):
    md = "md"
    json = "json"
    csv = "csv"
    png = "png"
    pdf = "pdf"
    txt = "txt"
    zip = "zip"


class VerificationResult(str, Enum):
    pass_ = "pass"
    fail = "fail"
    warn = "warn"


class KnowledgeKind(str, Enum):
    principle = "principle"
    pattern = "pattern"
    anti_pattern = "anti_pattern"
    reference = "reference"
    playbook = "playbook"
    checklist = "checklist"


class KnowledgeStatus(str, Enum):
    draft = "draft"
    published = "published"
    deprecated = "deprecated"
    retracted = "retracted"


class SignalStatus(str, Enum):
    unverified = "unverified"
    likely = "likely"
    verified = "verified"
    retracted = "retracted"
    superseded = "superseded"


# ---------------------------------------------------------------------------
# 内嵌结构
# ---------------------------------------------------------------------------

class EvidenceRef(BaseModel):
    """Judgment / Knowledge 引用证据 (contracts §5.2)."""
    model_config = ConfigDict(frozen=True)

    material_id: str = Field(description="Material 稳定 ID")
    signal_id: str | None = Field(default=None, description="可选 Signal 锚点")
    chunk_id: str | None = Field(default=None, description="chunk 投影 ID")
    offset: list[int] | None = Field(default=None, description="[start, end] 字符偏移")
    hash: str = Field(description="sha256, 须与 material.hash 一致")
    quote: str | None = Field(default=None, description="≤ 500 字符引用")


class Step(BaseModel):
    """Run 执行步骤 (contracts §7.2)."""
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    tool: str
    started_at: datetime
    finished_at: datetime | None = None
    input_hash: str
    output_hash: str | None = None
    status: StepStatus
    error: str | None = None
    duration_ms: int = Field(ge=0)


# ---------------------------------------------------------------------------
# 9 域对象
# ---------------------------------------------------------------------------

class Subject(BaseModel):
    """关注对象 (contracts §1)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$", description="ULID Crockford Base32")
    entity_type: SubjectEntityType
    name: str = Field(max_length=200)
    aliases: list[str] = Field(default_factory=list)
    importance: SubjectImportance = Field(default=SubjectImportance.normal)
    revision: int = Field(ge=1, default=1)
    context_revision: int | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    # 时间戳 (服务端写, 客户端不传)
    created_at: datetime
    updated_at: datetime

    # 通用响应字段 (contracts §0.3)
    allowed_actions: list[str] = Field(default_factory=list)
    reason: str | None = None


class Material(BaseModel):
    """原始资料 (contracts §2) — 不可变, 修正走新 revision."""
    model_config = ConfigDict(populate_by_name=True, frozen=False)

    id: str = Field(description="sha256(source+url+first_seen_at)[:26]")
    source: str
    url: str
    title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    first_seen_at: datetime
    hash: str
    parser_version: str
    snapshot_path: str | None = None
    revision: int = Field(ge=1, default=1)
    extra: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    is_fallback: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime

    # 派生
    allowed_actions: list[str] = Field(default_factory=list)
    reason: str | None = None


class Signal(BaseModel):
    """情报事件 (contracts §3)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    subject_id: str | None = None
    material_id: str
    summary: str = Field(max_length=500)
    occurred_at: datetime
    admission_rule_version: str
    admission_reason: str | None = None
    supersedes_signal_id: str | None = None
    confidence: Confidence = Field(default=Confidence.unverified)
    revision: int = Field(ge=1, default=1)
    status: SignalStatus = Field(default=SignalStatus.unverified)
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


class Case(BaseModel):
    """工作事项 (contracts §4) — **首切对象**."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    title: str = Field(max_length=120)
    question: str = Field(max_length=500)
    goal: str | None = None
    scope: str | None = None
    priority: CasePriority = Field(default=CasePriority.p2)
    status: CaseStatus = Field(default=CaseStatus.open)
    due_at: datetime | None = None
    subject_id: str | None = None
    related_subject_ids: list[str] = Field(default_factory=list)
    related_signal_ids: list[str] = Field(default_factory=list)
    related_case_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    owner_role: CaseOwnerRole = Field(default=CaseOwnerRole.user)
    revision: int = Field(ge=1, default=1)
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # 通用响应字段
    allowed_actions: list[str] = Field(default_factory=list)
    reason: str | None = None


class Judgment(BaseModel):
    """判断 (contracts §5)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    case_id: str
    subject_id: str | None = None
    claim_type: ClaimType
    claim: str = Field(max_length=10_000)
    conditions: str | None = None
    confidence: JudgmentConfidence = Field(default=JudgmentConfidence.medium)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    counter_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    status: JudgmentStatus = Field(default=JudgmentStatus.draft)
    revision: int = Field(ge=1, default=1)
    wiki_path: str | None = None
    content_hash: str | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


class Action(BaseModel):
    """行动 (contracts §6)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    case_id: str
    judgment_id: str
    title: str = Field(max_length=200)
    scope: str | None = None
    plan: str = Field(max_length=50_000)
    plan_hash: str
    tool_versions: dict[str, str] = Field(default_factory=dict)
    expected_artifacts: list[str] = Field(default_factory=list)
    success_criteria: str | None = None
    expires_at: datetime | None = None
    status: ActionStatus = Field(default=ActionStatus.planned)
    approved_by: str | None = None
    approved_at: datetime | None = None
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


class Run(BaseModel):
    """执行运行 (contracts §7)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^run_[A-Z2-7]{26}$")
    action_id: str
    attempt: int = Field(ge=1, default=1)
    skill_id: str | None = None
    protocol: RunProtocol
    trigger_source: RunTriggerSource
    idempotency_key: str
    status: RunStatus = Field(default=RunStatus.queued)
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    budget_tokens: int | None = None
    budget_seconds: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    result_excerpt: str | None = None
    error: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


class Artifact(BaseModel):
    """产物 (contracts §8)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    run_id: str
    kind: ArtifactKind
    title: str = Field(max_length=200)
    content_ref: str | None = None
    content_hash: str
    format: ArtifactFormat
    size_bytes: int = Field(ge=0)
    verified_by: str | None = None
    verified_at: datetime | None = None
    verified_result: VerificationResult | None = None
    accepted_by: str | None = None
    accepted_at: datetime | None = None
    accepted_note: str | None = None
    status: ArtifactStatus = Field(default=ArtifactStatus.pending)
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


class Knowledge(BaseModel):
    """经验 (contracts §9)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    kind: KnowledgeKind
    title: str = Field(max_length=200)
    body: str = Field(max_length=100_000)
    prerequisites: list[str] = Field(default_factory=list)
    counter_examples: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    expiry_at: datetime | None = None
    review_at: datetime | None = None
    reuse_count: int = Field(ge=0, default=0)
    last_reused_at: datetime | None = None
    status: KnowledgeStatus = Field(default=KnowledgeStatus.draft)
    revision: int = Field(ge=1, default=1)
    wiki_path: str | None = None
    content_hash: str | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    allowed_actions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 快捷索引 (codegen 用)
# ---------------------------------------------------------------------------

DOMAIN_MODELS: list[type[BaseModel]] = [
    Subject,
    Material,
    Signal,
    Case,
    Judgment,
    Action,
    Run,
    Artifact,
    Knowledge,
]

# 按 contracts 约定输出的文件名映射 (model class name → filename stem)
_MODEL_OUTPUT_ORDER: list[str] = [
    "Subject",
    "Material",
    "Signal",
    "Case",
    "Judgment",
    "Action",
    "Run",
    "Artifact",
    "Knowledge",
    "EvidenceRef",
    "Step",
]


def get_model_by_name(name: str) -> type[BaseModel] | None:
    for m in DOMAIN_MODELS:
        if m.__name__ == name:
            return m
    return None
