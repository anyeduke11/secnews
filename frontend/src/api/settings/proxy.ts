/**
 * api/settings/proxy.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 代理
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';

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
