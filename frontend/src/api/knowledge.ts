/**
 * Knowledge 域 API 客户端 (Batch 5 / R5 "同一端点唯一 hook owner" — /api/knowledge/* 调用面收敛)。
 *
 * 以 api/v1.ts 为样板, 复用 lib/api 统一封装, 错误走 getApiErrorMessage 友好化。
 * 只覆盖消费方实际用到的端点 (契约对齐 backend/api/knowledge_items.py /
 * knowledge_chunks_api.py / knowledge_concepts.py):
 *   - GET    /api/knowledge/items        → listKnowledgeItems (筛选 + 分页)
 *   - GET    /api/knowledge/items/{id}   → getKnowledgeItem (单条 + markdown content)
 *   - PATCH  /api/knowledge/items/{id}   → updateKnowledgeItem (分类 / tags / mastery)
 *   - DELETE /api/knowledge/items/{id}   → deleteKnowledgeItem
 *   - GET    /api/knowledge/concepts     → listKnowledgeConcepts
 *   - GET    /api/knowledge/chunks/{id}  → getKnowledgeItemChunks
 * 以及 knowledgeItemPath (「源资讯」外链 href, 与 GET 单条同路径)。
 *
 * 注意: 与 /api/v1/knowledge (v1.0 Knowledge 聚合端点, 见 api/v1.ts) 是两套端点, 勿混淆。
 */

import { apiFetch, getApiErrorMessage, getJSON, postJSON } from '../lib/api';
import type { KnowledgeItem, KnowledgeHealth, TaskItem, SkillConfig } from '../types';

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

/** 单条详情 = 列表行 + markdown 正文 (后端 get_item 附带 content 字段) */
export type KnowledgeItemDetail = KnowledgeItem & { content?: string };

/** 对齐 list_items 的 Query 参数 (未传走后端默认值; limit 后端 Query(50, ge=1, le=200)) */
export interface KnowledgeItemsQuery {
  domain?: string;
  source?: string;
  compiled?: boolean;
  topic?: string;
  type?: string;
  difficulty?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

/** GET /items 响应: {items, total} (total 为 domain 维度全量计数) */
export interface KnowledgeItemsResponse {
  items: KnowledgeItem[];
  total: number;
}

/** PATCH /items/{id} 请求体 (后端 updatable 白名单: domain/topic/type/difficulty/tags/concepts/mastery) */
export interface KnowledgeItemPatch {
  domain?: string | null;
  topic?: string | null;
  type?: string | null;
  difficulty?: string | null;
  tags?: string[];
  concepts?: string[];
  mastery?: number;
}

/** GET /concepts 单行 */
export interface KnowledgeConcept {
  slug: string;
  name: string;
  item_count: number;
}

export interface KnowledgeConceptsResponse {
  concepts: KnowledgeConcept[];
}

/** GET /chunks/{id} 单行 */
export interface KnowledgeChunk {
  id: number;
  item_id: string;
  chunk_index: number;
  content: string;
  char_start: number;
  char_end: number;
  summary: string;
  created_at: string;
}

export interface KnowledgeChunksResponse {
  chunks: KnowledgeChunk[];
}

/**
 * 带 HTTP status 的错误 — getKnowledgeItem 的 404 语义 (DeepReadMode「条目未找到」)
 * 需要区分状态码, 而 apiFetch 抛的 Error 不携带 status。
 */
export class KnowledgeApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'KnowledgeApiError';
    this.status = status;
  }
}

/** 构建 query string: 跳过 undefined / null / 空串 */
function buildQuery(q: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === '') continue;
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

// ---------------------------------------------------------------------------
// 端点函数
// ---------------------------------------------------------------------------

/** GET /api/knowledge/items — 列表 ({items, total}) */
export function listKnowledgeItems(q: KnowledgeItemsQuery = {}): Promise<KnowledgeItemsResponse> {
  return getJSON<KnowledgeItemsResponse>(`/api/knowledge/items${buildQuery(q as Record<string, unknown>)}`);
}

/**
 * 与 apiFetch 同语义, 但错误附带 HTTP status (仅 getKnowledgeItem 的 404 分支需要)。
 * 错误 message 仍走 getApiErrorMessage 统一友好化。
 */
async function getJSONWithStatus<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!resp.ok) {
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch {
      /* 非 JSON 错误响应体 */
    }
    throw new KnowledgeApiError(
      resp.status,
      getApiErrorMessage(body) || resp.statusText || `HTTP ${resp.status}`,
    );
  }
  return (await resp.json()) as T;
}

/** GET /api/knowledge/items/{id} — 单条详情 (404 抛 KnowledgeApiError, status=404) */
export function getKnowledgeItem(id: string): Promise<KnowledgeItemDetail> {
  return getJSONWithStatus<KnowledgeItemDetail>(`/api/knowledge/items/${encodeURIComponent(id)}`);
}

/** PATCH /api/knowledge/items/{id} — 更新分类 / tags / mastery, 返回更新后条目 */
export function updateKnowledgeItem(id: string, body: KnowledgeItemPatch): Promise<KnowledgeItem> {
  return apiFetch<KnowledgeItem>(`/api/knowledge/items/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/knowledge/items/{id} — 后端返回 {deleted: id} */
export function deleteKnowledgeItem(id: string): Promise<{ deleted: string }> {
  return apiFetch<{ deleted: string }>(`/api/knowledge/items/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

/** GET /api/knowledge/concepts — 概念列表 ({concepts}) */
export function listKnowledgeConcepts(): Promise<KnowledgeConceptsResponse> {
  return getJSON<KnowledgeConceptsResponse>('/api/knowledge/concepts');
}

/** GET /api/knowledge/concepts/{slug} 详情 — 比列表行多 title / domain / items */
export type KnowledgeConceptDetail = KnowledgeConcept & {
  title: string;
  domain?: string | null;
  updated_at?: string | null;
  local_wiki_ref?: string | null;
  entity_type?: string | null;
  external_id?: string | null;
  external_ref?: string | null;
  source_items?: string[];
  items?: Array<{ id: string; title: string; domain?: string | null }>;
};

/** GET /api/knowledge/concepts/{slug} — 概念详情; 404 抛 KnowledgeApiError (SentinelGraphPage 区分「后端无该概念」) */
export function getKnowledgeConceptDetail(slug: string): Promise<KnowledgeConceptDetail> {
  return getJSONWithStatus<KnowledgeConceptDetail>(`/api/knowledge/concepts/${encodeURIComponent(slug)}`);
}

/** GET /api/knowledge/graph 响应 — 概念同现图谱 (KnowledgeGraph / SentinelGraphPage 共用; wiki 对齐 GraphData 枚举) */
export interface KnowledgeGraphPayload {
  nodes: Array<{ id: string; label: string; domain: string | null; count: number; wiki: 'hotspot' | 'local'; type: string }>;
  edges: Array<{ source: string; target: string; weight: number; type: 'related' | 'federated' }>;
}

/** GET /api/knowledge/graph — 概念同现图谱 (可选 domain 服务端过滤; 未列出的域后端缓存路径返回 0) */
export function getKnowledgeGraph(domain?: string): Promise<KnowledgeGraphPayload> {
  return getJSON<KnowledgeGraphPayload>(
    `/api/knowledge/graph${domain ? `?domain=${encodeURIComponent(domain)}` : ''}`,
  );
}

/** GET /api/knowledge/chunks/{id} — 条目分块 ({chunks}) */
export function getKnowledgeItemChunks(id: string): Promise<KnowledgeChunksResponse> {
  return getJSON<KnowledgeChunksResponse>(`/api/knowledge/chunks/${encodeURIComponent(id)}`);
}

/** 「源资讯」外链 href (ProjectDetail); 与 GET 单条同路径, 浏览器打开返回 JSON */
export function knowledgeItemPath(id: string): string {
  return `/api/knowledge/items/${id}`;
}

// ---------------------------------------------------------------------------
// health / tasks (Batch 5 裸 fetch 清扫: HealthDashboard / KnowledgePage / TaskMonitor / TaskSubmitDialog 收敛)
// ---------------------------------------------------------------------------

/** GET /api/knowledge/health — 知识库健康度 (HealthDashboard / KnowledgePage 共用) */
export function getKnowledgeHealth(): Promise<KnowledgeHealth> {
  return getJSON<KnowledgeHealth>('/api/knowledge/health');
}

/** GET /api/knowledge/tasks 响应 — 后端可能返回 {items:[...]} / {tasks:[...]} / 裸数组 (调用方三形态兼容) */
export type KnowledgeTasksResponse = { items?: TaskItem[]; tasks?: TaskItem[] } | TaskItem[];

/** GET /api/knowledge/tasks — 编译任务列表 (TaskMonitor) */
export function listKnowledgeTasks(limit = 20): Promise<KnowledgeTasksResponse> {
  return getJSON<KnowledgeTasksResponse>(`/api/knowledge/tasks?limit=${limit}`);
}

/** POST /api/knowledge/tasks 请求体 */
export interface KnowledgeTaskCreateBody {
  task_type: string;
  params: Record<string, unknown>;
}

/** POST /api/knowledge/tasks 响应 — 后端可能返回 {task_id} 或 {id} */
export interface KnowledgeTaskCreateResponse {
  task_id?: number;
  id?: number;
}

/** POST /api/knowledge/tasks — 创建知识库任务 (TaskSubmitDialog) */
export function createKnowledgeTask(
  body: KnowledgeTaskCreateBody,
): Promise<KnowledgeTaskCreateResponse> {
  return postJSON<KnowledgeTaskCreateResponse>('/api/knowledge/tasks', body);
}

/** GET /api/knowledge/skills 响应 ({skills}) */
export interface KnowledgeSkillsResponse {
  skills?: SkillConfig[];
}

/** GET /api/knowledge/skills — baoyu skill 配置列表 (SkillEntryGrid / SkillConfigDialog 共用) */
export function listKnowledgeSkills(): Promise<KnowledgeSkillsResponse> {
  return getJSON<KnowledgeSkillsResponse>('/api/knowledge/skills');
}

// ---------------------------------------------------------------------------
// 注意力埋点 (Batch 5 裸 fetch 清扫: DeepReadMode POST ×3 · AttentionHeatmap GET 共用)
// ---------------------------------------------------------------------------

/** POST /api/attention/events 请求体 (契约见 backend attention_scorer) */
export interface AttentionEventPayload {
  item_id: string;
  event_type: 'view' | 'scroll' | 'dwell';
  detail_json: Record<string, unknown>;
}

/** POST /api/attention/events — 阅读埋点 (fire-and-forget, 调用方自行 .catch 静默) */
export function postAttentionEvent(body: AttentionEventPayload): Promise<unknown> {
  return apiFetch('/api/attention/events', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** GET /api/attention/events?days=N — 注意力事件聚合 (响应为数组或 {events|data}) */
export function listAttentionEvents<T = Record<string, unknown>>(days = 30): Promise<T> {
  return getJSON<T>(`/api/attention/events?days=${days}`);
}
