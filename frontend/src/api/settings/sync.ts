/**
 * api/settings/sync.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 同步 (设置页摘要 + 冲突)
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';
import type { ApiFetchOptions } from '../../lib/api';

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
