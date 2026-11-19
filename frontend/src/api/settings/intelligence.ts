/**
 * api/settings/intelligence.ts — 设置域 API 子模块 (前端重构 V1 · B9-a, 2026-11-19)
 *
 * 由原 api/settings.ts (847 行) 按章节边界拆分 (B8-c), 本批按业务域合并为 5 个模块;
 * 函数体 / 接口体 / 端点 URL / method / body 逐字保留, 零改写。
 * 聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 合并来源: prefs / mcp / models
 */
import { apiFetch, getJSON, postJSON } from '../../lib/api';
import type { ApiFetchOptions } from '../../lib/api';

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
