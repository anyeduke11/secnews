/**
 * api/settings/knowledge.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: SOUL 画像 / 联邦状态
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
