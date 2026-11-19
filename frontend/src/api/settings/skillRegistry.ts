/**
 * api/settings/skillRegistry.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: Skill registry 读侧 (/api/skill-registry; 执行/反馈见 ./skills)
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';
import type { ApiFetchOptions } from '../../lib/api';

// ---------------------------------------------------------------------------
// Skill registry 读侧 (/api/skill-registry; 执行/反馈见 ./skills)
// ---------------------------------------------------------------------------

/** GET /api/skill-registry — 控制台概览扁平列表 ({skills}) */
export function getSkillRegistrySummary<T = unknown>(): Promise<{ skills: T[] }> {
  return getJSON<{ skills: T[] }>('/api/skill-registry');
}

/** GET /api/skill-registry/v1?category= — 注册表列表 ({version, items, total}) */
export function getSkillRegistry<T = unknown>(
  category?: string,
  options?: ApiFetchOptions,
): Promise<{ version: string; items: T[]; total: number }> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : '';
  return apiFetch<{ version: string; items: T[]; total: number }>(
    `/api/skill-registry/v1${qs}`,
    options,
  );
}

/** GET /api/skill-registry/{id} — 技能详情 */
export function getSkillRegistryDetail<T = unknown>(
  skillId: string,
  options?: ApiFetchOptions,
): Promise<T> {
  return apiFetch<T>(`/api/skill-registry/${encodeURIComponent(skillId)}`, options);
}

/** GET /api/skill-registry/{id}/runs?limit= — 运行历史 (顶层数组) */
export function listSkillRegistryRuns<T = unknown>(
  skillId: string,
  limit = 20,
  options?: ApiFetchOptions,
): Promise<T[]> {
  return apiFetch<T[]>(
    `/api/skill-registry/${encodeURIComponent(skillId)}/runs?limit=${limit}`,
    options,
  );
}

/** POST /api/skill-registry/{id}/enable|disable — 启停技能 */
export function toggleSkillRegistry(skillId: string, next: boolean): Promise<unknown> {
  return postJSON(
    `/api/skill-registry/${encodeURIComponent(skillId)}/${next ? 'enable' : 'disable'}`,
    {},
  );
}
