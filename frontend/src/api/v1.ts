/**
 * v1.0 Case 端到端 API 客户端 (T08) + Judgment 客户端 (T11).
 *
 * 与后端 backend/api/case_api.py + judgment_api.py 对齐.
 * 路径前缀 /api/v1/cases + /api/v1/judgments.
 * 复用 lib/api 统一封装 (apiFetch / getJSON / postJSON), 错误透传后端 message.
 *
 * 类型从 domain/v1_0.ts 引 (与 Pydantic Case/Judgment 模型 codegen 一致).
 */

import type {
  Case, CasePriority, CaseStatus, CaseOwnerRole,
  Judgment, EvidenceRef,
} from '../domain/v1_0';
import { getJSON, postJSON, apiFetch } from '../lib/api';

// ---------------------------------------------------------------------------
// Response shapes (后端 {version, item} / {items, total})
// ---------------------------------------------------------------------------
export interface ApiVersioned<T> {
  version: string;
  item: T;
}

export interface ApiList<T> {
  version: string;
  items: T[];
  total: number;
}

// ---------------------------------------------------------------------------
// Request body
// ---------------------------------------------------------------------------
export interface CreateCaseBody {
  title: string;
  question: string;
  goal?: string;
  scope?: string;
  priority?: CasePriority;
  due_at?: string;
  subject_id?: string;
  owner_role?: CaseOwnerRole;
  tags?: string[];
  related_subject_ids?: string[];
  related_signal_ids?: string[];
  related_case_ids?: string[];
  source?: string;
}

export interface UpdateCaseBody {
  expected_revision: number;
  status?: CaseStatus;
  title?: string;
  question?: string;
  goal?: string;
  scope?: string;
  priority?: CasePriority;
  due_at?: string;
  tags?: string[];
  related_subject_ids?: string[];
  related_signal_ids?: string[];
  related_case_ids?: string[];
  reason?: string;
}

export interface CloseCaseBody {
  expected_revision: number;
}

// ---------------------------------------------------------------------------
// List query (多 status / priority 用 FastAPI Query 重复键)
// ---------------------------------------------------------------------------
export interface ListCasesQuery {
  status?: CaseStatus[];
  priority?: CasePriority[];
  owner_role?: CaseOwnerRole;
  subject_id?: string;
  limit?: number;
  offset?: number;
}

function buildQuery(q: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

// ---------------------------------------------------------------------------
// 5 端点
// ---------------------------------------------------------------------------
export function listCases(q: ListCasesQuery = {}): Promise<ApiList<Case>> {
  return getJSON<ApiList<Case>>(`/api/v1/cases${buildQuery(q as Record<string, unknown>)}`);
}

export function getCase(id: string): Promise<ApiVersioned<Case>> {
  return getJSON<ApiVersioned<Case>>(`/api/v1/cases/${encodeURIComponent(id)}`);
}

export function createCase(body: CreateCaseBody): Promise<ApiVersioned<Case>> {
  return postJSON<ApiVersioned<Case>>('/api/v1/cases', body);
}

export function updateCase(id: string, body: UpdateCaseBody): Promise<ApiVersioned<Case>> {
  return apiFetch<ApiVersioned<Case>>(`/api/v1/cases/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function closeCase(id: string, body: CloseCaseBody): Promise<ApiVersioned<Case>> {
  return postJSON<ApiVersioned<Case>>(`/api/v1/cases/${encodeURIComponent(id)}/close`, body);
}

// ===========================================================================
// T11 Judgment 端到端 (SK-02 cve-impact-brief)
// ===========================================================================

// 证据资料 (cve-impact-brief 提交方传入; service 校验 hash)
export interface EvidenceMaterial {
  id: string;
  title?: string;
  content_hash: string;
  summary?: string;
}

export interface GenerateJudgmentBody {
  case_id: string;
  cve_id: string;
  subject_name: string;
  evidence_materials: EvidenceMaterial[];
  submitted_by?: string;
}

export interface GenerateJudgmentResponse {
  version: string;
  item: Judgment;
  idempotent_replay: boolean;
}

export interface ListJudgmentsQuery {
  case_id: string;
  status?: 'draft' | 'published' | 'superseded' | 'retracted';
  claim_type?: 'finding' | 'assessment' | 'recommendation' | 'warning' | 'hypothesis';
  limit?: number;
  offset?: number;
}

export interface PublishJudgmentBody {
  expected_revision: number;
}

export function listJudgments(q: ListJudgmentsQuery): Promise<ApiList<Judgment>> {
  // v1.0 C04 R13 修复: URLSearchParams 一次构建, 避免 `?case_id=ID?limit=50` 双 ?
  // 旧实现: `?case_id=${case_id}${buildQuery(rest)}` → `?case_id=ID?limit=50`
  //   (buildQuery 返 `?limit=50`, 与 `?case_id=ID` 拼出双 `?`)
  // 修复: case_id 与 rest 一起入 URLSearchParams.set, 一次 toString 出单 `?`
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  return getJSON<ApiList<Judgment>>(`/api/v1/judgments?${params.toString()}`);
}

export function getJudgment(id: string): Promise<ApiVersioned<Judgment>> {
  return getJSON<ApiVersioned<Judgment>>(`/api/v1/judgments/${encodeURIComponent(id)}`);
}

export function generateJudgment(body: GenerateJudgmentBody): Promise<GenerateJudgmentResponse> {
  return postJSON<GenerateJudgmentResponse>('/api/v1/judgments/generate', body);
}

export function publishJudgment(
  id: string, body: PublishJudgmentBody
): Promise<ApiVersioned<Judgment>> {
  return postJSON<ApiVersioned<Judgment>>(
    `/api/v1/judgments/${encodeURIComponent(id)}/publish`, body
  );
}

// ===========================================================================
// T12 Action / Run / Artifact 端到端 (SK-03 inspection-materials + 验收)
// ===========================================================================

// Action
export type ActionStatus =
  | 'planned' | 'approved' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'rejected';

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
  status: ActionStatus;
  approved_by?: string | null;
  approved_at?: string | null;
  rejection_reason?: string | null;
  revision: number;
  allowed_actions?: string[];
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

export type RunStatus = 'queued' | 'claimed' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out';
export type RunProtocol = 'dsh' | 'pi' | 'direct' | 'mock';
export type RunTriggerSource = 'user' | 'agent' | 'system' | 'scheduled' | 'webhook';

export interface RunStep {
  seq: number;
  tool: string;
  started_at: string;
  finished_at?: string | null;
  input_hash: string;
  output_hash?: string | null;
  status: 'ok' | 'error' | 'skipped';
  error?: string | null;
  duration_ms: number;
}

export interface Run {
  id: string;
  action_id: string;
  attempt: number;
  skill_id?: string | null;
  protocol: RunProtocol;
  trigger_source: RunTriggerSource;
  idempotency_key: string;
  status: RunStatus;
  inputs?: Record<string, unknown>;
  steps?: RunStep[];
  budget_tokens?: number | null;
  budget_seconds?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  result_excerpt?: string | null;
  error?: string | null;
  artifact_ids?: string[];
  revision: number;
  allowed_actions?: string[];
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

export type ArtifactStatus = 'pending' | 'verified' | 'accepted' | 'rejected' | 'superseded';
export type ArtifactKind = 'report' | 'file' | 'data' | 'chart' | 'code_patch' | 'message';
export type ArtifactFormat = 'md' | 'json' | 'csv' | 'png' | 'pdf' | 'txt' | 'html' | 'xml';
export type VerificationResult = 'pass' | 'fail' | 'warn';

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
  status: ArtifactStatus;
  revision: number;
  allowed_actions?: string[];
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateActionBody {
  case_id: string;
  judgment_id: string;
  title: string;
  subject_name: string;
  cve_id: string;
  scope?: string;
  evidence_materials?: EvidenceMaterial[];
  submitted_by?: string;
}

export interface GenerateActionResponse {
  version: string;
  item: Action;
  idempotent_replay: boolean;
}

export interface ListActionsQuery {
  case_id: string;
  status?: ActionStatus;
  judgment_id?: string;
  limit?: number;
  offset?: number;
}

export interface StateChangeBody {
  expected_revision: number;
}

export interface StartActionBody extends StateChangeBody {
  idempotency_key: string;
  protocol?: RunProtocol;
  trigger_source?: RunTriggerSource;
  skill_id?: string;
}

export interface StartActionResponse {
  version: string;
  item: Action;
  run: Run;
  replayed: boolean;
}

export interface ListRunsQuery {
  action_id: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}

export interface CreateArtifactBody {
  run_id: string;
  kind: ArtifactKind;
  title: string;
  content: string;
  format?: ArtifactFormat;
  content_ref?: string;
}

export interface VerifyArtifactBody {
  verified_by: string;
  verified_result?: VerificationResult;
}

export interface AcceptArtifactBody {
  accepted_by: string;
  accepted_note?: string;
}

export interface RejectArtifactBody {
  rejected_by: string;
  reason: string;
}

export interface ListArtifactsQuery {
  run_id: string;
  status?: ArtifactStatus;
  limit?: number;
  offset?: number;
}

export function listActions(q: ListActionsQuery): Promise<ApiList<Action>> {
  // v1.0 C04 R13 修复: 同 listJudgments, 走 URLSearchParams 一次构建
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  return getJSON<ApiList<Action>>(`/api/v1/actions?${params.toString()}`);
}

export function getAction(id: string): Promise<ApiVersioned<Action>> {
  return getJSON<ApiVersioned<Action>>(`/api/v1/actions/${encodeURIComponent(id)}`);
}

export function generateAction(body: GenerateActionBody): Promise<GenerateActionResponse> {
  return postJSON<GenerateActionResponse>('/api/v1/actions/generate', body);
}

export function approveAction(id: string, body: StateChangeBody): Promise<ApiVersioned<Action>> {
  return postJSON<ApiVersioned<Action>>(`/api/v1/actions/${encodeURIComponent(id)}/approve`, body);
}

export function startAction(id: string, body: StartActionBody): Promise<StartActionResponse> {
  return postJSON<StartActionResponse>(`/api/v1/actions/${encodeURIComponent(id)}/start`, body);
}

export function cancelAction(id: string, body: StateChangeBody): Promise<ApiVersioned<Action>> {
  return postJSON<ApiVersioned<Action>>(`/api/v1/actions/${encodeURIComponent(id)}/cancel`, body);
}

export function listRuns(q: ListRunsQuery): Promise<ApiList<Run>> {
  // v1.0 C04 R13 修复: 同 listJudgments, 走 URLSearchParams 一次构建
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  return getJSON<ApiList<Run>>(`/api/v1/runs?${params.toString()}`);
}

export function getRun(id: string): Promise<ApiVersioned<Run>> {
  return getJSON<ApiVersioned<Run>>(`/api/v1/runs/${encodeURIComponent(id)}`);
}

export function listArtifacts(q: ListArtifactsQuery): Promise<ApiList<Artifact>> {
  // v1.0 C04 R13 修复: 同 listJudgments, 走 URLSearchParams 一次构建
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  return getJSON<ApiList<Artifact>>(`/api/v1/artifacts?${params.toString()}`);
}

export function getArtifact(id: string): Promise<ApiVersioned<Artifact>> {
  return getJSON<ApiVersioned<Artifact>>(`/api/v1/artifacts/${encodeURIComponent(id)}`);
}

export function createArtifact(body: CreateArtifactBody): Promise<ApiVersioned<Artifact>> {
  return postJSON<ApiVersioned<Artifact>>('/api/v1/artifacts', body);
}

export function verifyArtifact(id: string, body: VerifyArtifactBody): Promise<ApiVersioned<Artifact>> {
  return postJSON<ApiVersioned<Artifact>>(`/api/v1/artifacts/${encodeURIComponent(id)}/verify`, body);
}

export function acceptArtifact(id: string, body: AcceptArtifactBody): Promise<ApiVersioned<Artifact>> {
  return postJSON<ApiVersioned<Artifact>>(`/api/v1/artifacts/${encodeURIComponent(id)}/accept`, body);
}

export function rejectArtifact(id: string, body: RejectArtifactBody): Promise<ApiVersioned<Artifact>> {
  return postJSON<ApiVersioned<Artifact>>(`/api/v1/artifacts/${encodeURIComponent(id)}/reject`, body);
}

// ===========================================================================
// T13 Knowledge 端到端 (SK-04/05/06 知识发布/复用/复查)
// ===========================================================================

// Knowledge
export type KnowledgeKind = 'principle' | 'pattern' | 'anti_pattern' | 'reference' | 'playbook' | 'checklist';
export type KnowledgeStatus = 'draft' | 'published' | 'deprecated' | 'retracted';

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
  status: KnowledgeStatus;
  revision: number;
  wiki_path?: string | null;
  content_hash?: string | null;
  published_at?: string | null;
  deprecation_reason?: string | null;
  replacement_knowledge_id?: string | null;
  retraction_reason?: string | null;
  allowed_actions?: string[];
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateKnowledgeBody {
  case_id: string;
  judgment_id: string;
  action_id: string;
  subject_name: string;
  cve_id: string;
  kind: KnowledgeKind;
  evidence_materials?: EvidenceMaterial[];
  submitted_by?: string;
}

export interface GenerateKnowledgeResponse {
  version: string;
  item: Knowledge;
  idempotent_replay: boolean;
}

export interface ListKnowledgeQuery {
  case_id?: string;  // T15.5: 可选, None 走 listAll 全局
  status?: KnowledgeStatus;
  kind?: KnowledgeKind;
  limit?: number;
  offset?: number;
}

export interface DeprecateKnowledgeBody extends StateChangeBody {
  reason: string;
  replacement_knowledge_id?: string;
}

export interface RetractKnowledgeBody extends StateChangeBody {
  reason: string;
}

export interface ReuseReceipt {
  total: number;
  by_judgment: number;
  by_action: number;
  recent_30d: number;
}

export interface ReuseReceiptResponse {
  version: string;
  knowledge_id: string;
  receipt: ReuseReceipt;
}

export function listKnowledge(q: ListKnowledgeQuery): Promise<ApiList<Knowledge>> {
  // v1.0 C04 R13 修复: URLSearchParams 一次构建, 处理 case_id 可选 (T15.5)
  // 旧实现: 字面拼 `?case_id=ID` + buildQuery(rest) 返 `?limit=50` → 双 `?`
  // 修复: case_id 与 rest 一起入 URLSearchParams, 自动处理可选
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      v.forEach((item) => params.append(k, String(item)));
    } else {
      params.set(k, String(v));
    }
  }
  const qs = params.toString();
  return getJSON<ApiList<Knowledge>>(`/api/v1/knowledge${qs ? "?" + qs : ""}`);
}

export function getKnowledge(id: string): Promise<ApiVersioned<Knowledge>> {
  return getJSON<ApiVersioned<Knowledge>>(`/api/v1/knowledge/${encodeURIComponent(id)}`);
}

export function getKnowledgeReuse(id: string): Promise<ReuseReceiptResponse> {
  return getJSON<ReuseReceiptResponse>(`/api/v1/knowledge/${encodeURIComponent(id)}/reuse`);
}

export function generateKnowledge(body: GenerateKnowledgeBody): Promise<GenerateKnowledgeResponse> {
  return postJSON<GenerateKnowledgeResponse>('/api/v1/knowledge/generate', body);
}

export function publishKnowledge(id: string, body: StateChangeBody): Promise<ApiVersioned<Knowledge>> {
  return postJSON<ApiVersioned<Knowledge>>(`/api/v1/knowledge/${encodeURIComponent(id)}/publish`, body);
}

export function deprecateKnowledge(id: string, body: DeprecateKnowledgeBody): Promise<ApiVersioned<Knowledge>> {
  return postJSON<ApiVersioned<Knowledge>>(`/api/v1/knowledge/${encodeURIComponent(id)}/deprecate`, body);
}

export function retractKnowledge(id: string, body: RetractKnowledgeBody): Promise<ApiVersioned<Knowledge>> {
  return postJSON<ApiVersioned<Knowledge>>(`/api/v1/knowledge/${encodeURIComponent(id)}/retract`, body);
}

// ===========================================================================
// T14 Skill Registry v1 (6 SK 受管能力包 + 旧 20 ID 状态)
// ===========================================================================

export type SkillV1Status = 'v1_active' | 'legacy_v0' | 'deprecated';

export interface SkillV1Target {
  type: 'ServiceTarget' | 'ApiTarget';
  module?: string;
  class_name?: string | null;
  method?: string | null;
  path?: string | null;
}

export interface SkillV1 {
  id: string;
  name: string;
  desc: string;
  category: 'operations' | 'compliance' | 'analysis' | 'report';
  skill_type: 'A' | 'B' | 'C' | 'D' | 'E';
  target: SkillV1Target | null;
  prompt_template?: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  runner: 'builtin' | 'pi' | 'claude-code' | 'codex';
  timeout_seconds: number;
  feature_gate: string;
  default_enabled: boolean;
  requires_gate_check: string[] | null;
  version: string;
  status: SkillV1Status;
  manifest_path: string | null;
}

export interface ListV1SkillsQuery {
  status?: SkillV1Status;
  category?: 'operations' | 'compliance' | 'analysis' | 'report';
}

export function listV1Skills(q: ListV1SkillsQuery = {}): Promise<ApiList<SkillV1>> {
  return getJSON<ApiList<SkillV1>>(`/api/skill-registry/v1${buildQuery(q as Record<string, unknown>)}`);
}

export function getV1Skill(id: string): Promise<ApiVersioned<SkillV1>> {
  return getJSON<ApiVersioned<SkillV1>>(`/api/skill-registry/v1/${encodeURIComponent(id)}`);
}

// ===========================================================================
// T15 Signal API (Intel 入口真实化, 复用 T05 v1_signals)
// ===========================================================================

export interface V1Signal {
  id: string;
  subject_id: string;
  material_id: string;
  summary: string;
  occurred_at: string;
  confidence: 'verified' | 'likely' | 'unverified' | 'retracted';
  status: 'verified' | 'likely' | 'unverified';
  subject_name?: string;
}

export interface ListSignalsQuery {
  case_id?: string;
  days?: number;
  limit?: number;
}

export function listSignals(q: ListSignalsQuery = {}): Promise<ApiList<V1Signal>> {
  return getJSON<ApiList<V1Signal>>(`/api/v1/signals${buildQuery(q as Record<string, unknown>)}`);
}

// ===========================================================================
// C11 R19: Case 聚合端点 (1 次拉齐 case + judgments + actions + runs + artifacts)
// 替代旧 N+1 模式 (getCase + listJudgments + listActions + N×listRuns + N×M×listArtifacts)
// 旧实现每次打开 CaseDetail 触发 1+1+1+N+N×M = 3+N+N×M 次请求, 业务规模下 50 个 action + 5 runs/action
// 触发 50+250=300 次往返. 新模式固定 1 次, 服务端聚合 + 异常隔离 (单 run 拉取失败不阻断其他).
// ===========================================================================

export interface GetCaseAggregateQuery {
  judgments_limit?: number;
  actions_limit?: number;
  runs_per_action?: number;
  artifacts_per_run?: number;
}

export interface CaseAggregate {
  version: string;
  case: Case;
  judgments: Judgment[];
  actions: Action[];
  runs: Run[];
  artifacts: Artifact[];
}

export function getCaseAggregate(
  caseId: string,
  q: GetCaseAggregateQuery = {},
): Promise<CaseAggregate> {
  // C11 R19: URLSearchParams 一次构建 (与 listJudgments/listActions 同模式)
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<CaseAggregate>(
    `/api/v1/cases/${encodeURIComponent(caseId)}/aggregate${qs ? "?" + qs : ""}`
  );
}