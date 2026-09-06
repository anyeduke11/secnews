/**
 * v1.0 域模型 — 由 scripts/codegen_v1_ts.py 自动生成 (Pydantic → TS).
 *
 * 单一真相源: backend/domain/v1_0_models.py
 * 字段命名: snake_case (与后端 Pydantic model_dump(mode='json') 对齐).
 * 时间字段: 全部 string (ISO 8601 UTC, 服务端写, 客户端只读).
 * 禁止手动编辑本文件; 改 Pydantic 模型后重新运行 codegen.
 */


export type ActionStatus = 'planned' | 'approved' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'rejected';

export type ArtifactFormat = 'md' | 'json' | 'csv' | 'png' | 'pdf' | 'txt' | 'zip';

export type ArtifactKind = 'report' | 'file' | 'data' | 'chart' | 'code_patch' | 'message';

export type ArtifactStatus = 'pending' | 'verified' | 'accepted' | 'rejected' | 'superseded';

export type CaseOwnerRole = 'user' | 'system' | 'shared';

export type CasePriority = 'p0' | 'p1' | 'p2' | 'p3';

export type CaseStatus = 'open' | 'in_progress' | 'blocked' | 'closed' | 'archived';

export type ClaimType = 'finding' | 'assessment' | 'recommendation' | 'warning' | 'hypothesis';

export type Confidence = 'verified' | 'likely' | 'unverified' | 'retracted';

export type JudgmentConfidence = 'low' | 'medium' | 'high' | 'proved';

export type JudgmentStatus = 'draft' | 'published' | 'superseded' | 'retracted';

export type KnowledgeKind = 'principle' | 'pattern' | 'anti_pattern' | 'reference' | 'playbook' | 'checklist';

export type KnowledgeStatus = 'draft' | 'published' | 'deprecated' | 'retracted';

export type RunProtocol = 'dsh' | 'pi' | 'direct' | 'mock';

export type RunStatus = 'queued' | 'claimed' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out';

export type RunTriggerSource = 'user' | 'agent' | 'system' | 'scheduled' | 'webhook';

export type SignalStatus = 'unverified' | 'likely' | 'verified' | 'retracted' | 'superseded';

export type StepStatus = 'ok' | 'error' | 'skipped';

export type SubjectEntityType = 'product' | 'vendor' | 'cve' | 'technique' | 'regulation' | 'person' | 'org' | 'custom';

export type SubjectImportance = 'critical' | 'high' | 'normal' | 'low' | 'watchlist';

export type VerificationResult = 'pass' | 'fail' | 'warn';

export interface EvidenceRef {
  /** Material 稳定 ID */
  material_id: string;
  /** 可选 Signal 锚点 */
  signal_id?: string | null;
  /** chunk 投影 ID */
  chunk_id?: string | null;
  /** [start, end] 字符偏移 */
  offset?: number[] | null;
  /** sha256, 须与 material.hash 一致 */
  hash: string;
  /** ≤ 500 字符引用 */
  quote?: string | null;
}

export interface Step {
  seq: number;
  tool: string;
  started_at: string;
  finished_at?: string | null;
  input_hash: string;
  output_hash?: string | null;
  status: StepStatus;
  error?: string | null;
  duration_ms: number;
}

export interface Subject {
  /** ULID Crockford Base32 */
  id: string;
  entity_type: SubjectEntityType;
  name: string;
  aliases?: string[];
  importance?: SubjectImportance;
  revision?: number;
  context_revision?: number | null;
  tags?: string[];
  notes?: string | null;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
  reason?: string | null;
}

export interface Material {
  /** sha256(source+url+first_seen_at)[:26] */
  id: string;
  source: string;
  url: string;
  title?: string | null;
  author?: string | null;
  published_at?: string | null;
  first_seen_at: string;
  hash: string;
  parser_version: string;
  snapshot_path?: string | null;
  revision?: number;
  extra?: Record<string, unknown>;
  quality_flags?: string[];
  is_fallback?: boolean;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
  reason?: string | null;
}

export interface Signal {
  id: string;
  subject_id?: string | null;
  material_id: string;
  summary: string;
  occurred_at: string;
  admission_rule_version: string;
  admission_reason?: string | null;
  supersedes_signal_id?: string | null;
  confidence?: Confidence;
  revision?: number;
  status?: SignalStatus;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}

export interface Case {
  id: string;
  title: string;
  question: string;
  goal?: string | null;
  scope?: string | null;
  priority?: CasePriority;
  status?: CaseStatus;
  due_at?: string | null;
  subject_id?: string | null;
  related_subject_ids?: string[];
  related_signal_ids?: string[];
  related_case_ids?: string[];
  tags?: string[];
  owner_role?: CaseOwnerRole;
  revision?: number;
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
  reason?: string | null;
}

export interface Judgment {
  id: string;
  case_id: string;
  subject_id?: string | null;
  claim_type: ClaimType;
  claim: string;
  conditions?: string | null;
  confidence?: JudgmentConfidence;
  evidence_refs: EvidenceRef[];
  counter_evidence_refs?: EvidenceRef[];
  unknowns?: string[];
  status?: JudgmentStatus;
  revision?: number;
  wiki_path?: string | null;
  content_hash?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}

export interface Action {
  id: string;
  case_id: string;
  judgment_id: string;
  title: string;
  scope?: string | null;
  plan: string;
  plan_hash: string;
  tool_versions?: Record<string, string>;
  expected_artifacts?: string[];
  success_criteria?: string | null;
  expires_at?: string | null;
  status?: ActionStatus;
  approved_by?: string | null;
  approved_at?: string | null;
  revision?: number;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}

export interface Run {
  id: string;
  action_id: string;
  attempt?: number;
  skill_id?: string | null;
  protocol: RunProtocol;
  trigger_source: RunTriggerSource;
  idempotency_key: string;
  status?: RunStatus;
  inputs?: Record<string, unknown>;
  steps?: Step[];
  budget_tokens?: number | null;
  budget_seconds?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  result_excerpt?: string | null;
  error?: string | null;
  artifact_ids?: string[];
  revision?: number;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}

export interface Artifact {
  id: string;
  run_id: string;
  kind: ArtifactKind;
  title: string;
  content_ref?: string | null;
  content_hash: string;
  format: ArtifactFormat;
  size_bytes: number;
  verified_by?: string | null;
  verified_at?: string | null;
  verified_result?: VerificationResult | null;
  accepted_by?: string | null;
  accepted_at?: string | null;
  accepted_note?: string | null;
  status?: ArtifactStatus;
  revision?: number;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}

export interface Knowledge {
  id: string;
  kind: KnowledgeKind;
  title: string;
  body: string;
  prerequisites?: string[];
  counter_examples?: string[];
  evidence_refs?: EvidenceRef[];
  expiry_at?: string | null;
  review_at?: string | null;
  reuse_count?: number;
  last_reused_at?: string | null;
  status?: KnowledgeStatus;
  revision?: number;
  wiki_path?: string | null;
  content_hash?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
  allowed_actions?: string[];
}
