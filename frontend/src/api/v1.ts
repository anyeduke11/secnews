/**
 * v1.0 Case 端到端 API 客户端 (T08).
 *
 * 与后端 backend/api/case_api.py 对齐 — 路径前缀 /api/v1/cases.
 * 复用 lib/api 统一封装 (apiFetch / getJSON / postJSON), 错误透传后端 message.
 *
 * 类型从 domain/v1_0.ts 引 (与 Pydantic Case 模型 codegen 一致).
 */

import type { Case, CasePriority, CaseStatus, CaseOwnerRole } from '../domain/v1_0';
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

function buildQuery(q: ListCasesQuery): string {
  const params = new URLSearchParams();
  if (q.status) q.status.forEach((s) => params.append('status', s));
  if (q.priority) q.priority.forEach((p) => params.append('priority', p));
  if (q.owner_role) params.set('owner_role', q.owner_role);
  if (q.subject_id) params.set('subject_id', q.subject_id);
  if (q.limit !== undefined) params.set('limit', String(q.limit));
  if (q.offset !== undefined) params.set('offset', String(q.offset));
  const s = params.toString();
  return s ? `?${s}` : '';
}

// ---------------------------------------------------------------------------
// 5 端点
// ---------------------------------------------------------------------------
export function listCases(q: ListCasesQuery = {}): Promise<ApiList<Case>> {
  return getJSON<ApiList<Case>>(`/api/v1/cases${buildQuery(q)}`);
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