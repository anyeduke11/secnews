/**
 * api/settings/core.ts — 设置域 API 子模块 (前端重构 V1 · B9-a, 2026-11-19)
 *
 * 由原 api/settings.ts (847 行) 按章节边界拆分 (B8-c), 本批按业务域合并为 5 个模块;
 * 函数体 / 接口体 / 端点 URL / method / body 逐字保留, 零改写。
 * 聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 合并来源: overview / sync
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';
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

// ---------------------------------------------------------------------------
// 同步 (设置页摘要 + 冲突)
// ---------------------------------------------------------------------------

export interface SyncStatusSummary {
  configured?: boolean;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  auto_sync_enabled?: boolean;
  webdav_url?: string;
}

/** GET /api/sync/status (兼容 {status: {...}} 与扁平两种返回; hook 可传 signal) */
export function getSyncStatus<T = { status?: SyncStatusSummary } & SyncStatusSummary>(
  options?: ApiFetchOptions,
): Promise<T> {
  return getJSON<T>('/api/sync/status', options);
}

/** POST /api/sync/auto — 自动同步开关 (hook 视图: 可传 signal) */
export function setSyncAuto<T = unknown>(enabled: boolean, options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>('/api/sync/auto', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
    ...options,
  });
}

/** GET /api/sync/history?limit= */
export function fetchSyncHistory<T = unknown>(limit: number, options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>(`/api/sync/history?limit=${limit}`, options);
}

/** GET /api/sync/bundle/preview — 本机 bundle 字段预览 */
export function fetchSyncPreview<T = unknown>(options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>('/api/sync/bundle/preview', options);
}

/** POST /api/sync/test — 测试 WebDAV 连接 */
export function testSyncConnection<T = unknown, B = unknown>(
  body: B,
  options?: ApiFetchOptions,
): Promise<T> {
  return apiFetch<T>('/api/sync/test', {
    method: 'POST',
    body: JSON.stringify(body),
    ...options,
  });
}

/** POST /api/sync/config — 保存 WebDAV 配置 */
export function saveSyncConfig<T = unknown, B = unknown>(
  body: B,
  options?: ApiFetchOptions,
): Promise<T> {
  return apiFetch<T>('/api/sync/config', {
    method: 'POST',
    body: JSON.stringify(body),
    ...options,
  });
}

/** DELETE /api/sync/config — 清除 WebDAV 配置 */
export function clearSyncConfig<T = unknown>(options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>('/api/sync/config', { method: 'DELETE', ...options });
}

/** POST /api/sync/push — 推送到远端 */
export function pushSync<T = unknown>(masterKey: string, options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>('/api/sync/push', {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey }),
    ...options,
  });
}

/** POST /api/sync/pull — 从远端拉取 */
export function pullSync<T = unknown>(masterKey: string, options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>('/api/sync/pull', {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey }),
    ...options,
  });
}

/** POST /api/sync/bidirectional — 双向同步 */
export function bidirectionalSync<T = unknown>(
  masterKey: string,
  options?: ApiFetchOptions,
): Promise<T> {
  return apiFetch<T>('/api/sync/bidirectional', {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey }),
    ...options,
  });
}

/** GET /api/sync/conflicts */
export function getSyncConflicts<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/sync/conflicts');
}

/** POST /api/sync/conflicts/auto-resolve */
export function resolveSyncConflict(recordType: string, choice: string): Promise<unknown> {
  return postJSON('/api/sync/conflicts/auto-resolve', { record_type: recordType, choice });
}
