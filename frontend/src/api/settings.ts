/**
 * 设置域 API 客户端 (前端重构 V1 · B3 数据层收敛)。
 *
 * 契约: 组件不得直接 import getJSON/postJSON/apiFetch, 所有取数经本模块具名函数。
 * 本文件只做「调用点搬家」: URL / method / body / 错误语义与原直调逐字一致,
 * 不新增缓存、不再包装 hooks (批 B4/B5 处理)。
 *
 * 端点分组: 系统总览 / 模式 / 能力门禁 / 同步 / 代理 / 兴趣画像 / 内容偏好 /
 *          MCP / 模型 (status + pool + 场景) / 密钥保险箱 / 自动入管 / 运维 / SOUL。
 * 质量规则与 LLM provider 切换见 ./settingsQuality。
 */
import { apiFetch, getJSON, postJSON } from '../lib/api';
import type { ApiFetchOptions } from '../lib/api';
import type { SoulData } from '../types';

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

// ---------------------------------------------------------------------------
// 兴趣画像 (实践域)
// ---------------------------------------------------------------------------

export interface InterestsResponse {
  domains: string[];
  valid_domains: string[];
  labels: Record<string, string>;
}

export interface DomainRecommendationsResponse {
  recommended: string[];
  reasons: Record<string, string>;
  cached_at: string | null;
  note: string;
}

export interface InterestWeightEntry {
  explicit_selected: number;
  behavioral_score: number;
  blended_score: number;
  events_30d: number;
  last_event_at: string | null;
}

export interface InterestDrift {
  detected: boolean;
  behavioral_top: string[];
  explicit_domains: string[];
  overlap: number;
  overlap_min: number;
}

export interface InterestWeightsResponse {
  weights: Record<string, InterestWeightEntry>;
  domains: string[];
  drift?: InterestDrift;
}

/** GET /api/settings/interests */
export function getInterests(options?: ApiFetchOptions): Promise<InterestsResponse> {
  return apiFetch<InterestsResponse>('/api/settings/interests', options);
}

/** PATCH /api/settings/interests */
export function patchInterests(domains: string[]): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/api/settings/interests', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domains }),
  });
}

/** GET /api/interest/weights */
export function getInterestWeights(): Promise<InterestWeightsResponse> {
  return apiFetch<InterestWeightsResponse>('/api/interest/weights');
}

/** GET /api/interest/domains/recommendations */
export function getDomainRecommendations(force = false): Promise<DomainRecommendationsResponse> {
  return apiFetch<DomainRecommendationsResponse>(
    `/api/interest/domains/recommendations${force ? '?force=1' : ''}`,
  );
}

/** POST /api/interest/reset */
export function resetInterestBehavior(): Promise<unknown> {
  return apiFetch('/api/interest/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
}

// ---------------------------------------------------------------------------
// 内容偏好
// ---------------------------------------------------------------------------

export type ContentPrefLevel = 'more' | 'normal' | 'less';
export type ContentPrefAxis = 'categories' | 'sources';
export type ContentPrefTable = Record<string, ContentPrefLevel>;

export interface ContentPrefs {
  categories: ContentPrefTable;
  sources: ContentPrefTable;
}

export interface ContentPrefsResponse {
  preferences: Partial<ContentPrefs>;
  auto_preferences: Partial<ContentPrefs>;
  valid_categories: string[];
  available_sources: { source: string; count: number }[];
  levels: ContentPrefLevel[];
}

export interface ContentSuggestionsResponse {
  categories: Record<string, 'more' | 'less'>;
  sources: Record<string, 'more' | 'less'>;
  reasons: Record<string, string>;
  cached_at: string | null;
  note: string;
}

/** GET /api/settings/content-preferences */
export function getContentPreferences(options?: ApiFetchOptions): Promise<ContentPrefsResponse> {
  return apiFetch<ContentPrefsResponse>('/api/settings/content-preferences', options);
}

/** PATCH /api/settings/content-preferences */
export function patchContentPreferences(next: ContentPrefs): Promise<ContentPrefsResponse> {
  return apiFetch<ContentPrefsResponse>('/api/settings/content-preferences', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ categories: next.categories, sources: next.sources }),
  });
}

/** GET /api/interest/content-prefs/recommendations */
export function getContentSuggestions(force = false): Promise<ContentSuggestionsResponse> {
  return apiFetch<ContentSuggestionsResponse>(
    `/api/interest/content-prefs/recommendations${force ? '?force=1' : ''}`,
  );
}

// ---------------------------------------------------------------------------
// MCP
// ---------------------------------------------------------------------------

export interface MCPTool {
  name: string;
  category: 'read' | 'write';
  description: string;
  enabled: boolean;
}

export interface MCPConfigResponse {
  stdio?: { mcpServers?: Record<string, unknown> };
  sse?: { mcpServers?: Record<string, { url?: string }> };
}

/** GET /api/mcp/status */
export function getMCPStatus(): Promise<{ enabled?: boolean }> {
  return getJSON<{ enabled?: boolean }>('/api/mcp/status');
}

/** GET /api/mcp/tools */
export function getMCPTools(): Promise<{ tools?: MCPTool[] }> {
  return getJSON<{ tools?: MCPTool[] }>('/api/mcp/tools');
}

/** GET /api/settings/mcp/config */
export function getMCPConfig(): Promise<MCPConfigResponse> {
  return getJSON<MCPConfigResponse>('/api/settings/mcp/config');
}

/** PUT /api/settings/mcp/enabled */
export function putMCPEnabled(enabled: boolean): Promise<unknown> {
  return apiFetch('/api/settings/mcp/enabled', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });
}

// ---------------------------------------------------------------------------
// 模型 (状态 / 模型池 / 场景模型)
// ---------------------------------------------------------------------------

export interface LlmStatus {
  providers?: Record<string, { status?: string; model?: string }>;
  effective_provider?: string | null;
  config_source?: string | null;
  key_source?: string;
  gate_detect_available?: boolean;
}

/** GET /api/llm/status */
export function getLlmStatus(): Promise<LlmStatus> {
  return getJSON<LlmStatus>('/api/llm/status');
}

export interface PoolPlatform {
  name: string;
  label: string;
  base_url: string;
  key_env: string;
  configured: boolean;
  key_source: string;
  available: boolean | null;
  models: string[];
  model_count: number;
  latency_ms: number | null;
  error: string | null;
}

export interface PoolSnapshot {
  platforms: PoolPlatform[];
  agent_channels: Array<{ name: string; kind: string; desc: string }>;
  probed: boolean;
}

export interface PoolRouting {
  routing?: Record<string, { label: string; provider: string | null; model: string | null }>;
  error?: string | null;
}

/** GET /api/llm/pool[?probe=1] */
export function getLlmPool(probe = false): Promise<PoolSnapshot> {
  return getJSON<PoolSnapshot>(`/api/llm/pool${probe ? '?probe=1' : ''}`);
}

/** GET /api/llm/pool?probe=1&only={platform} */
export function getLlmPoolPlatform(platform: string): Promise<PoolSnapshot> {
  return getJSON<PoolSnapshot>(`/api/llm/pool?probe=1&only=${platform}`);
}

/** GET /api/llm/pool/routing */
export function getLlmPoolRouting(): Promise<PoolRouting> {
  return getJSON<PoolRouting>('/api/llm/pool/routing');
}

/** POST /api/llm/pool/route */
export function putLlmPoolRoute(payload: {
  override_key: string;
  provider: string;
  model: string;
  force: boolean;
}): Promise<{ status?: string; message?: string }> {
  return postJSON<{ status?: string; message?: string }>('/api/llm/pool/route', payload);
}

export interface ScenarioModelResult {
  status?: string;
  old_model?: string;
  new_model?: string;
  message?: string;
}

/** POST /api/settings/scenario-model */
export function postScenarioModel(scenario: string, model: string): Promise<ScenarioModelResult> {
  return postJSON<ScenarioModelResult>('/api/settings/scenario-model', {
    scenario,
    model,
    actor: 'web',
  });
}

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
// 自动入管
// ---------------------------------------------------------------------------

export interface AutoIntakeConfig {
  enabled: boolean;
  min_quality_score: number;
  daily_limit: number;
  require_domain_hit: boolean;
  today_intaken: number;
}

/** GET /api/settings/auto-intake */
export function getAutoIntake(): Promise<AutoIntakeConfig> {
  return apiFetch<AutoIntakeConfig>('/api/settings/auto-intake');
}

/** PATCH /api/settings/auto-intake */
export function patchAutoIntake(next: AutoIntakeConfig): Promise<AutoIntakeConfig> {
  return apiFetch<AutoIntakeConfig>('/api/settings/auto-intake', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enabled: next.enabled,
      min_quality_score: next.min_quality_score,
      daily_limit: next.daily_limit,
      require_domain_hit: next.require_domain_hit,
    }),
  });
}

// ---------------------------------------------------------------------------
// 运维 (数据库维护 / 缓存)
// ---------------------------------------------------------------------------

export interface MaintenanceHealth {
  size_mb?: number;
  fragmentation_pct?: number;
  journal_mode?: string;
}

/** GET /api/maintenance/health */
export function getMaintenanceHealth<T = MaintenanceHealth>(): Promise<T> {
  return getJSON<T>('/api/maintenance/health');
}

/** GET /api/maintenance/table-stats */
export function getMaintenanceTableStats(): Promise<{ tables?: Array<Record<string, any>> }> {
  return getJSON<{ tables?: Array<Record<string, any>> }>('/api/maintenance/table-stats');
}

/** GET /api/maintenance/dirty-report */
export function getMaintenanceDirtyReport<T = Record<string, any>>(): Promise<T> {
  return getJSON<T>('/api/maintenance/dirty-report');
}

/** GET /api/maintenance/index-health — 索引健康 */
export function getMaintenanceIndexHealth<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/maintenance/index-health');
}

/** GET /api/maintenance/quality-log-tiers?days= — 质量日志分档 (保留窗口) */
export function getMaintenanceQualityLogTiers<T = unknown>(days: number): Promise<T> {
  return getJSON<T>(`/api/maintenance/quality-log-tiers?days=${days}`);
}

/** GET /api/maintenance/duplicates */
export function getMaintenanceDuplicates(): Promise<{
  hotspots?: any[];
  knowledge_items?: any[];
} | null> {
  return getJSON<{ hotspots?: any[]; knowledge_items?: any[] } | null>('/api/maintenance/duplicates');
}

/** POST /api/maintenance/vacuum — body 由调用方决定 (不传即无 body) */
export function runMaintenanceVacuum<T = { status?: string; total_seconds?: number }>(
  body?: unknown,
): Promise<T> {
  return postJSON<T>('/api/maintenance/vacuum', body);
}

/** POST /api/maintenance/cleanup-quality-logs (dry_run=false 为既有行为) */
export function cleanupQualityLogs<
  T = { rows_to_delete?: number; rows_remaining_after?: number },
>(days: number): Promise<T> {
  return postJSON<T>(`/api/maintenance/cleanup-quality-logs?days=${days}&dry_run=false`, undefined);
}

/** POST /api/maintenance/cleanup-duplicates (dry_run=false 为既有行为) */
export function cleanupDuplicates(): Promise<{
  total_deleted?: number;
  hotspots?: { total_deleted?: number };
  knowledge_items?: { total_deleted?: number };
}> {
  return postJSON<{
    total_deleted?: number;
    hotspots?: { total_deleted?: number };
    knowledge_items?: { total_deleted?: number };
  }>('/api/maintenance/cleanup-duplicates?dry_run=false', undefined);
}

/** POST /api/maintenance/cleanup (dry_run=false 为既有行为) */
export function cleanupHistory(days: number): Promise<{ total_rows?: number }> {
  return postJSON<{ total_rows?: number }>(
    `/api/maintenance/cleanup?days=${days}&dry_run=false`,
    undefined,
  );
}

/** POST /api/cache/clear */
export function clearCache(): Promise<{ status?: string }> {
  return postJSON<{ status?: string }>('/api/cache/clear', undefined);
}

/** GET /api/ops/runs?hours=&limit=&status= (任务失败面板) */
export function getOpsRuns<T = unknown>(status: string, hours = 24, limit = 50): Promise<T> {
  return getJSON<T>(
    `/api/ops/runs?hours=${hours}&limit=${limit}&status=${encodeURIComponent(status)}`,
  );
}

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
// 历史批次 (HistoryPage)
// ---------------------------------------------------------------------------

/** GET /api/history/batches?limit= — 批次列表 */
export function listHistoryBatches<T = unknown>(limit = 100): Promise<T> {
  return getJSON<T>(`/api/history/batches?limit=${limit}`);
}

/** GET /api/history/batches/{batchNo}/items?<query> — 批次条目 (query 由调用方拼好) */
export function listHistoryBatchItems<T = unknown>(batchNo: number, query: string): Promise<T> {
  return getJSON<T>(`/api/history/batches/${batchNo}/items?${query}`);
}

/** GET /api/history/batches/{batchNo}/summary — 批次摘要 */
export function getHistoryBatchSummary<T = unknown>(batchNo: number): Promise<T> {
  return getJSON<T>(`/api/history/batches/${batchNo}/summary`);
}

// ---------------------------------------------------------------------------
// 联邦状态
// ---------------------------------------------------------------------------

/** GET /api/knowledge/federation — 联邦同步状态 */
export function getFederationStatus<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/knowledge/federation');
}

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