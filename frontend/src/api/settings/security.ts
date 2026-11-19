/**
 * api/settings/security.ts — 设置域 API 子模块 (前端重构 V1 · B9-a, 2026-11-19)
 *
 * 由原 api/settings.ts (847 行) 按章节边界拆分 (B8-c), 本批按业务域合并为 5 个模块;
 * 函数体 / 接口体 / 端点 URL / method / body 逐字保留, 零改写。
 * 聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 合并来源: secrets / proxy
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';
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

// ---------------------------------------------------------------------------
// 代理
// ---------------------------------------------------------------------------

export interface ProxyProbeResult {
  ok: boolean;
  status?: number;
  error?: string;
  ms?: number;
}

export interface ProxyTestResult {
  name: string;
  host: string;
  url: string;
  policy: 'proxy' | 'direct';
  direct: ProxyProbeResult;
  proxy: ProxyProbeResult | null;
  ok: boolean;
}

export interface ProxyHealth {
  circuit_open: boolean;
  open_remaining_seconds: number;
  consecutive_failures: number;
  fail_threshold: number;
  open_seconds: number;
  opened_count: number;
  total_failures: number;
  total_successes: number;
  last_error: string;
}

/** GET/PUT /api/proxy/settings 响应 */
export interface ProxySettingsResponse {
  status?: string;
  message?: string;
  settings?: { mode?: string; no_proxy?: string };
  effective_proxy?: string;
  builtin?: { proxy_url?: string };
  health?: ProxyHealth | null;
  detected_system_proxy?: Record<string, string> | null;
}

/** GET /api/proxy/settings */
export function getProxySettings(): Promise<ProxySettingsResponse> {
  return getJSON<ProxySettingsResponse>('/api/proxy/settings');
}

/** PUT /api/proxy/settings */
export function putProxySettings(mode: string, noProxy: string): Promise<ProxySettingsResponse> {
  return apiFetch<ProxySettingsResponse>('/api/proxy/settings', {
    method: 'PUT',
    body: JSON.stringify({ mode, no_proxy: noProxy }),
  });
}

export interface ProxyTestResponse {
  results?: ProxyTestResult[];
  status?: string;
  health?: ProxyHealth;
  summary?: string;
}

/** GET /api/proxy/test */
export function getProxyTest(): Promise<ProxyTestResponse> {
  return getJSON<ProxyTestResponse>('/api/proxy/test');
}

/** POST /api/proxy/health/reset */
export function resetProxyHealth(): Promise<{ health?: ProxyHealth }> {
  return postJSON<{ health?: ProxyHealth }>('/api/proxy/health/reset', undefined);
}
