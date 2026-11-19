/**
 * api/settings/knowledge.ts — 设置域 API 子模块 (前端重构 V1 · B9-a, 2026-11-19)
 *
 * 由原 api/settings.ts (847 行) 按章节边界拆分 (B8-c), 本批按业务域合并为 5 个模块;
 * 函数体 / 接口体 / 端点 URL / method / body 逐字保留, 零改写。
 * 聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 合并来源: knowledge
 */
import { apiFetch, getJSON } from '../../lib/api';
import type { SoulData } from '../../types';

// ---------------------------------------------------------------------------
// SOUL 画像
// ---------------------------------------------------------------------------

/** GET /api/knowledge/soul */
export function getSoul(): Promise<SoulData> {
  return getJSON<SoulData>('/api/knowledge/soul');
}

/** POST /api/knowledge/soul/regenerate */
export function regenerateSoul(): Promise<unknown> {
  return apiFetch('/api/knowledge/soul/regenerate', { method: 'POST' });
}

// ---------------------------------------------------------------------------
// 联邦状态
// ---------------------------------------------------------------------------

/** GET /api/knowledge/federation — 联邦同步状态 */
export function getFederationStatus<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/knowledge/federation');
}
