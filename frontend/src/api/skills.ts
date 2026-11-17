/**
 * 技能域 API (前端重构 V1 · B3 数据层收敛)。
 *
 * 契约: 组件不得直接 import getJSON/postJSON/apiFetch; URL / method / body 原样搬运。
 * 技能列表读取走现有 hooks (useSkillRegistry), 不在本批改造范围内。
 */
import { apiFetch, getJSON, postJSON } from '../lib/api';
import type { ApiFetchOptions } from '../lib/api';
import type { SkillFeedback } from '../types/skill';

/** POST /api/skill-registry/{id}/run */
export function runSkill(skillId: string): Promise<{ ticket_id?: string }> {
  return postJSON<{ ticket_id?: string }>(
    `/api/skill-registry/${encodeURIComponent(skillId)}/run`,
    { inputs: null },
  );
}

/** POST /api/skill-registry/runs/{runId}/feedback */
export function submitSkillFeedback(runId: string, score: number): Promise<SkillFeedback> {
  return postJSON<SkillFeedback>(
    `/api/skill-registry/runs/${encodeURIComponent(runId)}/feedback`,
    { score, comment: '' },
  );
}

/** POST /api/skill-builder/validate */
export function validateSkillDraft(payload: unknown): Promise<{ ok: boolean; errors: string[] }> {
  return postJSON<{ ok: boolean; errors: string[] }>('/api/skill-builder/validate', { payload });
}

/** POST /api/skill-builder */
export function createSkill(draft: unknown): Promise<{ id: string }> {
  return postJSON<{ id: string }>('/api/skill-builder', draft);
}

// ---------------------------------------------------------------------------
// 技能条目 CRUD (/api/skills; 从 api/shared.ts 收敛, useSkills 唯一消费)
// ---------------------------------------------------------------------------

/** GET /api/skills?limit=&source=&tag=&keyword= — 技能列表 */
export function listSkills<T = unknown>(
  params: URLSearchParams,
  options?: ApiFetchOptions,
): Promise<T> {
  return getJSON<T>(`/api/skills?${params}`, options);
}

/** GET /api/skills/count_by_source — 按来源统计 */
export function getSkillCountsBySource<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/skills/count_by_source');
}

/** POST /api/skills — 新建技能 ({item}) */
export function createSkillItem<T = unknown, B = unknown>(body: B): Promise<{ item: T }> {
  return postJSON<{ item: T }>('/api/skills', body);
}

/** PATCH /api/skills/{id} — 更新技能 ({item}) */
export function updateSkillItem<T = unknown, B = unknown>(
  id: number,
  body: B,
): Promise<{ item: T }> {
  return apiFetch<{ item: T }>(`/api/skills/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/skills/{id} — 删除技能 */
export function deleteSkillItem(id: number): Promise<void> {
  return apiFetch<void>(`/api/skills/${id}`, { method: 'DELETE' });
}

/** PATCH /api/knowledge/skills/{id} */
export function updateKnowledgeSkill(id: number, body: Record<string, any>): Promise<unknown> {
  return apiFetch(`/api/knowledge/skills/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}