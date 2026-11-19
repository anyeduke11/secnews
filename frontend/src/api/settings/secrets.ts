/**
 * api/settings/secrets.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 密钥保险箱
 */
import { apiFetch, getJSON } from '../../lib/api';
import type { ApiFetchOptions } from '../../lib/api';

// ---------------------------------------------------------------------------
// 密钥保险箱
// ---------------------------------------------------------------------------

export interface SecretsListResponse {
  items?: Array<Record<string, any>>;
}

/** GET /api/secrets[?limit=N] — 可传 signal (hook 视图) */
export function getSecrets<T = SecretsListResponse>(
  limit?: number,
  options?: ApiFetchOptions,
): Promise<T> {
  return apiFetch<T>(limit ? `/api/secrets?limit=${limit}` : '/api/secrets', options);
}

/** POST /api/secrets/setup — 初始化主密钥 */
export function setupSecretsMasterKey(masterKey: string): Promise<unknown> {
  return apiFetch('/api/secrets/setup', {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey, role: 'admin' }),
  });
}

/** POST /api/secrets — 新建密钥 ({item}) */
export function createSecret<T = unknown, B = unknown>(body: B): Promise<{ item: T }> {
  return apiFetch<{ item: T }>('/api/secrets', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** PATCH /api/secrets/{id} — 更新密钥 ({item}) */
export function updateSecret<T = unknown, B = unknown>(
  id: number,
  body: B,
): Promise<{ item: T }> {
  return apiFetch<{ item: T }>(`/api/secrets/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/secrets/{id} — 删除密钥 */
export function deleteSecret(id: number): Promise<void> {
  return apiFetch<void>(`/api/secrets/${id}`, { method: 'DELETE' });
}

/** POST /api/secrets/unlock — 解锁 (后端 role 默认 admin) */
export function unlockSecrets<T = unknown>(masterKey: string): Promise<T> {
  return apiFetch<T>('/api/secrets/unlock', {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey }),
  });
}

/** POST /api/secrets/lock — 锁定保险箱 */
export function lockSecrets(): Promise<void> {
  return apiFetch<void>('/api/secrets/lock', { method: 'POST' });
}

/** POST /api/secrets/{id}/reveal — 查看明文 */
export function revealSecret<T = { api_key: string }>(
  id: number,
  masterKey: string,
): Promise<T> {
  return apiFetch<T>(`/api/secrets/${id}/reveal`, {
    method: 'POST',
    body: JSON.stringify({ master_key: masterKey }),
  });
}

/** POST /api/secrets/{id}/test — 连接测试 */
export function testSecret<T = { ok?: boolean; error?: string }>(id: number): Promise<T> {
  return apiFetch<T>(`/api/secrets/${id}/test`, { method: 'POST' });
}

/** GET /api/secrets/export?master_key= — 导出加密包 (blob) */
export function exportSecretsBlob(masterKey: string): Promise<Blob> {
  return apiFetch<Blob>(`/api/secrets/export?master_key=${encodeURIComponent(masterKey)}`, {
    parse: 'blob',
  });
}

/** POST /api/secrets/import — 导入加密包 */
export function importSecretsB64<T = unknown>(
  payloadB64: string,
  masterKey: string,
): Promise<T> {
  return apiFetch<T>('/api/secrets/import', {
    method: 'POST',
    body: JSON.stringify({ payload_b64: payloadB64, master_key: masterKey }),
  });
}

/** GET /api/secrets/oauth-config — OAuth 解锁配置 */
export function getSecretOAuthConfig<T = unknown>(): Promise<T> {
  return apiFetch<T>('/api/secrets/oauth-config', { method: 'GET' });
}

/** GET /api/secrets/rotation-status — 密钥轮换状态 */
export function getSecretRotationStatus<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/secrets/rotation-status');
}

/** POST /api/secrets/unlock-with-oauth — OAuth 解锁 */
export function unlockSecretsWithOAuth<T = unknown>(
  token: string,
  role = 'admin',
): Promise<T> {
  return apiFetch<T>('/api/secrets/unlock-with-oauth', {
    method: 'POST',
    body: JSON.stringify({ token, role }),
  });
}
