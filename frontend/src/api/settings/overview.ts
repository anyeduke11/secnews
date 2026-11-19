/**
 * api/settings/overview.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 系统总览 / 模式 (brief / scan / deep / organize) / 能力门禁 (feature gates)
 */
import { apiFetch, getJSON } from '../../lib/api';
import type { ApiFetchOptions } from '../../lib/api';

// ---------------------------------------------------------------------------
// 系统总览
// ---------------------------------------------------------------------------

/** GET /api/health */
export function getHealth<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/health');
}

/** GET /api/stats */
export function getStats<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/stats');
}

/** GET /api/sources/health */
export function getSourcesHealth<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/sources/health');
}

/** GET /api/secrets/status 响应 (字段宽松, 各消费点按需读) */
export interface SecretsStatusPayload {
  setup?: boolean;
  initialized?: boolean;
  unlocked?: boolean;
  remaining_seconds?: number;
  total?: number;
  source?: string;
}

/** GET /api/secrets/status — 可传 signal; T 供 hook 声明强类型视图 */
export function getSecretsStatus<T = SecretsStatusPayload>(options?: ApiFetchOptions): Promise<T> {
  return getJSON<T>('/api/secrets/status', options);
}

// ---------------------------------------------------------------------------
// 模式 (brief / scan / deep / organize)
// ---------------------------------------------------------------------------

/** GET /api/mode/current */
export function getCurrentMode(): Promise<{ mode?: string | null }> {
  return getJSON<{ mode?: string | null }>('/api/mode/current');
}

/** GET /api/mode/modes */
export function getModes(): Promise<{ modes?: string[] }> {
  return getJSON<{ modes?: string[] }>('/api/mode/modes');
}

/** PUT /api/mode/switch?mode= */
export function switchMode(mode: string): Promise<{ mode?: string }> {
  return apiFetch<{ mode?: string }>(`/api/mode/switch?mode=${encodeURIComponent(mode)}`, {
    method: 'PUT',
  });
}

// ---------------------------------------------------------------------------
// 能力门禁 (feature gates)
// ---------------------------------------------------------------------------

export interface FeatureGate {
  name: string;
  enabled: boolean;
  source: 'default' | 'toml' | 'env';
  effective_scope: 'runtime' | 'startup';
}

/** GET /api/settings/feature-gates */
export function getFeatureGates(): Promise<{ items?: FeatureGate[] }> {
  return getJSON<{ items?: FeatureGate[] }>('/api/settings/feature-gates');
}

/** PUT /api/settings/feature-gates/{name} */
export function putFeatureGate(name: string, enabled: boolean): Promise<{ note?: string }> {
  return apiFetch<{ note?: string }>(`/api/settings/feature-gates/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });
}
