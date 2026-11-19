/**
 * api/settings/models.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 模型 (状态 / 模型池 / 场景模型)
 */
import { getJSON, postJSON } from '../../lib/api';

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
