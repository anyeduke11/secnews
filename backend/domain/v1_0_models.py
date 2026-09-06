"""
v1.0 领域模型 (单一真相源).

codegen_v1_ts.py 读取本模块生成 frontend/src/domain/v1_0.ts.
下游 CI --check 确保 TS 与 Pydantic 同步。

参见 docs/v1.0/contracts.md §1-§9 + DEVELOPMENT_PLAN §5.4 §1.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    signal_id: Optional[str] = Field(default=None, description="可选 Signal 锚点")
    chunk_id: Optional[str] = Field(default=None, description="chunk 投影 ID")
    offset: Optional[List[int]] = Field(default=None, description="[start, end] 字符偏移")
    hash: str = Field(description="sha256, 须与 material.hash 一致")
    quote: Optional[str] = Field(default=None, description="≤ 500 字符引用")


class Step(BaseModel):
    """Run 执行步骤 (contracts §7.2)."""
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    tool: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    input_hash: str
    output_hash: Optional[str] = None
    status: StepStatus
    error: Optional[str] = None
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
    aliases: List[str] = Field(default_factory=list)
    importance: SubjectImportance = Field(default=SubjectImportance.normal)
    revision: int = Field(ge=1, default=1)
    context_revision: Optional[int] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    # 时间戳 (服务端写, 客户端不传)
    created_at: datetime
    updated_at: datetime

    # 通用响应字段 (contracts §0.3)
    allowed_actions: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class Material(BaseModel):
    """原始资料 (contracts §2) — 不可变, 修正走新 revision."""
    model_config = ConfigDict(populate_by_name=True, frozen=False)

    id: str = Field(description="sha256(source+url+first_seen_at)[:26]")
    source: str
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    first_seen_at: datetime
    hash: str
    parser_version: str
    snapshot_path: Optional[str] = None
    revision: int = Field(ge=1, default=1)
    extra: Dict[str, Any] = Field(default_factory=dict)
    quality_flags: List[str] = Field(default_factory=list)
    is_fallback: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime

    # 派生
    allowed_actions: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class Signal(BaseModel):
    """情报事件 (contracts §3)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    subject_id: Optional[str] = None
    material_id: str
    summary: str = Field(max_length=500)
    occurred_at: datetime
    admission_rule_version: str
    admission_reason: Optional[str] = None
    supersedes_signal_id: Optional[str] = None
    confidence: Confidence = Field(default=Confidence.unverified)
    revision: int = Field(ge=1, default=1)
    status: SignalStatus = Field(default=SignalStatus.unverified)
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


class Case(BaseModel):
    """工作事项 (contracts §4) — **首切对象**."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    title: str = Field(max_length=120)
    question: str = Field(max_length=500)
    goal: Optional[str] = None
    scope: Optional[str] = None
    priority: CasePriority = Field(default=CasePriority.p2)
    status: CaseStatus = Field(default=CaseStatus.open)
    due_at: Optional[datetime] = None
    subject_id: Optional[str] = None
    related_subject_ids: List[str] = Field(default_factory=list)
    related_signal_ids: List[str] = Field(default_factory=list)
    related_case_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    owner_role: CaseOwnerRole = Field(default=CaseOwnerRole.user)
    revision: int = Field(ge=1, default=1)
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # 通用响应字段
    allowed_actions: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class Judgment(BaseModel):
    """判断 (contracts §5)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    case_id: str
    subject_id: Optional[str] = None
    claim_type: ClaimType
    claim: str = Field(max_length=10_000)
    conditions: Optional[str] = None
    confidence: JudgmentConfidence = Field(default=JudgmentConfidence.medium)
    evidence_refs: List[EvidenceRef] = Field(min_length=1)
    counter_evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    status: JudgmentStatus = Field(default=JudgmentStatus.draft)
    revision: int = Field(ge=1, default=1)
    wiki_path: Optional[str] = None
    content_hash: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


class Action(BaseModel):
    """行动 (contracts §6)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    case_id: str
    judgment_id: str
    title: str = Field(max_length=200)
    scope: Optional[str] = None
    plan: str = Field(max_length=50_000)
    plan_hash: str
    tool_versions: Dict[str, str] = Field(default_factory=dict)
    expected_artifacts: List[str] = Field(default_factory=list)
    success_criteria: Optional[str] = None
    expires_at: Optional[datetime] = None
    status: ActionStatus = Field(default=ActionStatus.planned)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


class Run(BaseModel):
    """执行运行 (contracts §7)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^run_[A-Z2-7]{26}$")
    action_id: str
    attempt: int = Field(ge=1, default=1)
    skill_id: Optional[str] = None
    protocol: RunProtocol
    trigger_source: RunTriggerSource
    idempotency_key: str
    status: RunStatus = Field(default=RunStatus.queued)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step] = Field(default_factory=list)
    budget_tokens: Optional[int] = None
    budget_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    result_excerpt: Optional[str] = None
    error: Optional[str] = None
    artifact_ids: List[str] = Field(default_factory=list)
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


class Artifact(BaseModel):
    """产物 (contracts §8)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    run_id: str
    kind: ArtifactKind
    title: str = Field(max_length=200)
    content_ref: Optional[str] = None
    content_hash: str
    format: ArtifactFormat
    size_bytes: int = Field(ge=0)
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_result: Optional[VerificationResult] = None
    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    accepted_note: Optional[str] = None
    status: ArtifactStatus = Field(default=ArtifactStatus.pending)
    revision: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


class Knowledge(BaseModel):
    """经验 (contracts §9)."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=r"^[A-Z2-7]{26}$")
    kind: KnowledgeKind
    title: str = Field(max_length=200)
    body: str = Field(max_length=100_000)
    prerequisites: List[str] = Field(default_factory=list)
    counter_examples: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    expiry_at: Optional[datetime] = None
    review_at: Optional[datetime] = None
    reuse_count: int = Field(ge=0, default=0)
    last_reused_at: Optional[datetime] = None
    status: KnowledgeStatus = Field(default=KnowledgeStatus.draft)
    revision: int = Field(ge=1, default=1)
    wiki_path: Optional[str] = None
    content_hash: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    allowed_actions: List[str] = Field(default_factory=list)


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
