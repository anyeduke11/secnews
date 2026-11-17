/**
 * 设置域 · 质量侧 API (前端重构 V1 · B3 数据层收敛的第二个文件)。
 *
 * 分组: 质量规则 / 自定义规则 / 拒收日志 / LLM provider 切换。
 * 视图层私有类型 (CustomRule / GateInfo / DryRunResult / QualityRule) 仍由
 * 对应组件持有, 本模块用泛型参数承接, 避免两处重复定义。
 */
import { apiFetch, getJSON } from '../lib/api';

// ---------------------------------------------------------------------------
// 质量规则
// ---------------------------------------------------------------------------

/** GET /api/quality/rules */
export function getQualityRules<T = { rules?: Array<Record<string, any>> }>(): Promise<T> {
  return getJSON<T>('/api/quality/rules');
}

/** PUT /api/quality/rules */
export function putQualityRules(rules: Record<string, any>): Promise<{
  status?: string;
  updated?: string[];
  message?: string;
}> {
  return apiFetch<{ status?: string; updated?: string[]; message?: string }>('/api/quality/rules', {
    method: 'PUT',
    body: JSON.stringify({ rules }),
  });
}

// ---------------------------------------------------------------------------
// 自定义质量规则
// ---------------------------------------------------------------------------

/** GET /api/quality/custom-rules */
export function getCustomRules<T = { rules: Array<Record<string, any>> }>(): Promise<T> {
  return getJSON<T>('/api/quality/custom-rules');
}

/** GET /api/quality/custom-rules/gates */
export function getCustomRuleGates<T = { gates: Array<Record<string, any>> }>(): Promise<T> {
  return getJSON<T>('/api/quality/custom-rules/gates');
}

/** POST /api/quality/custom-rules */
export function createCustomRule(payload: unknown): Promise<unknown> {
  return apiFetch('/api/quality/custom-rules', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** PUT /api/quality/custom-rules/{id} */
export function updateCustomRule(id: number, payload: unknown): Promise<unknown> {
  return apiFetch(`/api/quality/custom-rules/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

/** DELETE /api/quality/custom-rules/{id} */
export function deleteCustomRule(id: number): Promise<unknown> {
  return apiFetch(`/api/quality/custom-rules/${id}`, { method: 'DELETE' });
}

/** POST /api/quality/custom-rules/dry-run */
export function dryRunCustomRules<T>(payload: {
  limit: number;
  with_semantic: boolean;
}): Promise<T> {
  return apiFetch<T>('/api/quality/custom-rules/dry-run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// 拒收日志
// ---------------------------------------------------------------------------

export interface RejectionLogItem {
  id: number;
  source_id: string;
  item_title: string;
  item_url: string;
  rejected_by: string;
  reason: string;
  explain: string | null;
  created_at: string;
}

/** GET /api/quality/rejection-log?page=&page_size= */
export function getRejectionLog(
  page: number,
  pageSize: number,
): Promise<{ items?: RejectionLogItem[]; total?: number }> {
  return getJSON<{ items?: RejectionLogItem[]; total?: number }>(
    `/api/quality/rejection-log?page=${page}&page_size=${pageSize}`,
  );
}

// ---------------------------------------------------------------------------
// LLM provider 切换
// ---------------------------------------------------------------------------

/** POST /api/settings/llm-provider */
export function postLlmProvider(provider: string): Promise<{
  status?: string;
  old_provider?: string;
  new_provider?: string;
  message?: string;
}> {
  return apiFetch<{
    status?: string;
    old_provider?: string;
    new_provider?: string;
    message?: string;
  }>('/api/settings/llm-provider', {
    method: 'POST',
    body: JSON.stringify({ provider, actor: 'web' }),
  });
}