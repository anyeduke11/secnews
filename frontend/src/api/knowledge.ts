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
import type { ApiFetchOptions } from '../lib/api';
import type {
  KnowledgeItem,
  KnowledgeHealth,
  TaskItem,
  DeepReadResponse,
  ImportedResponse,
  BookmarkImportResult,
  CompilePreview,
} from '../types';

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

export interface KnowledgeConceptsResponse<T = KnowledgeConcept> {
  concepts: T[];
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

/** GET /api/knowledge/items — 列表 ({items, total}); T 供调用方声明宽松行形状 */
export function listKnowledgeItems<T = KnowledgeItem>(
  q: KnowledgeItemsQuery = {},
): Promise<{ items: T[]; total: number }> {
  return getJSON<{ items: T[]; total: number }>(
    `/api/knowledge/items${buildQuery(q as Record<string, unknown>)}`,
  );
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

/** GET /api/knowledge/progress — 概念掌握进度 ({progress}) */
export function getKnowledgeProgress<T = unknown>(): Promise<{ progress?: T[] }> {
  return getJSON<{ progress?: T[] }>('/api/knowledge/progress');
}

/** GET /api/wiki/read?path= — wiki_tools 白名单读文件 (形状由消费方声明) */
export function readWikiDoc<T = unknown>(path: string): Promise<T> {
  return getJSON<T>(`/api/wiki/read?path=${encodeURIComponent(path)}`);
}

/** GET /api/knowledge/concepts — 概念列表 ({concepts}) */
export function listKnowledgeConcepts<T = KnowledgeConcept>(): Promise<KnowledgeConceptsResponse<T>> {
  return getJSON<KnowledgeConceptsResponse<T>>('/api/knowledge/concepts');
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
export function getKnowledgeConceptDetail<T = KnowledgeConceptDetail>(slug: string): Promise<T> {
  return getJSONWithStatus<T>(`/api/knowledge/concepts/${encodeURIComponent(slug)}`);
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

// ---------------------------------------------------------------------------
// 笔记 (annotations) — useAnnotations / ItemDetailDialog 共用
// ---------------------------------------------------------------------------

/** 笔记单行 (GET /api/annotations 列表项) */
export interface Annotation {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  range_start: number | null;
  range_end: number | null;
  created_at: string;
  updated_at: string;
}

/** GET /api/annotations?entity_type=&entity_id= — 按实体加载笔记 ({items} 或历史 {annotations}) */
export function listAnnotations<T = Annotation>(
  entityType: string,
  entityId: string,
  options?: ApiFetchOptions,
): Promise<{ items?: T[]; annotations?: T[] }> {
  const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
  return getJSON<{ items?: T[]; annotations?: T[] }>(`/api/annotations?${params}`, options);
}

/** POST /api/annotations — 新建笔记 ({item}) */
export function createAnnotation<T = Annotation>(body: {
  entity_type: string;
  entity_id: string;
  content: string;
  quote?: string;
  range_start?: number | null;
  range_end?: number | null;
}): Promise<{ item: T }> {
  return postJSON<{ item: T }>('/api/annotations', body);
}

/** PUT /api/annotations/{id} — 更新笔记 ({item}) */
export function updateAnnotation<T = Annotation>(
  id: string,
  body: Record<string, unknown>,
): Promise<{ item: T }> {
  return apiFetch<{ item: T }>(`/api/annotations/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/annotations/{id} — 删除笔记 */
export function deleteAnnotation(id: string): Promise<void> {
  return apiFetch<void>(`/api/annotations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// 深度解读 / 简报 / 导入列表 / 推荐 / Cubox·Obsidian (B3 知识域收敛)
// ---------------------------------------------------------------------------

/** POST /api/deep-read/{type}/{id}?force=&framework= — 深读 (cache 命中则瞬时返回) */
export function postDeepRead<T = DeepReadResponse>(
  entityType: string,
  entityId: string,
  opts: { force?: boolean; framework?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const force = opts.force === false ? '0' : '1';
  const fw = opts.framework ? `&framework=${encodeURIComponent(opts.framework)}` : '';
  return apiFetch<T>(
    `/api/deep-read/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?force=${force}${fw}`,
    { method: 'POST', signal: opts.signal },
  );
}

/** 简报单行 (GET /api/digests/latest) */
export interface Digest {
  id: string;
  period: string;
  summary: string;
  /** Phase 5: LLM 生成的 Markdown 叙事摘要; 为空时前端 fallback 到 summary */
  summary_md?: string | null;
  item_ids: string[];
  created_at: string;
  count?: number;
}

/** GET /api/digests/latest — 最新简报 (无简报时后端 404, 调用方按 message 判定) */
export function getLatestDigest<T = Digest>(): Promise<{ item?: T | null; digest?: T | null }> {
  return getJSON<{ item?: T | null; digest?: T | null }>('/api/digests/latest');
}

/** POST /api/digests/generate — 手动生成简报 (body 可选: {item_ids, summary}) */
export function generateDigest<T = Digest>(body?: unknown): Promise<T | { item: T }> {
  return postJSON<T | { item: T }>('/api/digests/generate', body);
}

/** PUT /api/digests/read — 标记已读 */
export function markDigestRead(): Promise<void> {
  return apiFetch<void>('/api/digests/read', { method: 'PUT' });
}

/** GET /api/knowledge/imported?type=&keyword=&since=&until=&page=&page_size= — 已导入条目 */
export function listImportedKnowledge(params: {
  type?: string;
  keyword?: string;
  since?: string;
  until?: string;
  page?: number;
  pageSize?: number;
}): Promise<ImportedResponse> {
  const sp = new URLSearchParams();
  if (params.type) sp.set('type', params.type);
  if (params.keyword) sp.set('keyword', params.keyword);
  if (params.since) sp.set('since', params.since);
  if (params.until) sp.set('until', params.until);
  sp.set('page', String(params.page ?? 1));
  sp.set('page_size', String(params.pageSize ?? 20));
  return apiFetch<ImportedResponse>(`/api/knowledge/imported?${sp.toString()}`);
}

/** GET /api/knowledge/hub-stats — 知识 Hub 统计 (形状由消费方声明) */
export function getKnowledgeHubStats<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/knowledge/hub-stats');
}

/** GET /api/knowledge/topics?domain= — 主题列表 ({topics}) */
export function listKnowledgeTopics(domain?: string): Promise<{ topics?: string[] }> {
  const qs = domain ? `?domain=${encodeURIComponent(domain)}` : '';
  return getJSON<{ topics?: string[] }>(`/api/knowledge/topics${qs}`);
}

/** GET /api/recommend/knowledge/{id}?limit= — 相关推荐 */
export function getRecommendedKnowledge<T = unknown>(id: string, limit = 5): Promise<T> {
  return getJSON<T>(`/api/recommend/knowledge/${encodeURIComponent(id)}?limit=${limit}`);
}

/** POST /api/knowledge/sync?source= — 触发多源同步 ({task_id}) */
export function syncKnowledgeSource(source = 'cubox'): Promise<{ task_id?: string }> {
  return postJSON<{ task_id?: string }>(
    `/api/knowledge/sync?source=${encodeURIComponent(source)}`,
    undefined,
  );
}

/** POST /api/knowledge/obsidian/open — 打开 Obsidian (返回 obsidian:// url) */
export function openObsidianVault(): Promise<{ url?: string }> {
  return postJSON<{ url?: string }>('/api/knowledge/obsidian/open', undefined);
}

/** GET /api/knowledge/obsidian/conflicts — 冲突文件列表 ({conflicts}) */
export function getObsidianConflicts(): Promise<{
  conflicts?: Array<{ filename: string; size: number; mtime: number }>;
}> {
  return getJSON('/api/knowledge/obsidian/conflicts');
}

/** POST /api/knowledge/cubox/import-cards — cubox CLI 导出卡片导入 */
export function importCuboxCards(body: { cards: unknown[] }): Promise<{
  imported?: number;
  new?: number;
  merged?: number;
}> {
  return postJSON('/api/knowledge/cubox/import-cards', body);
}

/** POST /api/knowledge/cubox/import-dir — 本地目录兜底导入 */
export function importCuboxDir(body: { path: string }): Promise<{
  imported?: number;
  cards?: number;
  new?: number;
  merged?: number;
}> {
  return postJSON('/api/knowledge/cubox/import-dir', body);
}

/** GET /api/knowledge/tasks/{id} — 任务进度 (形状由消费方声明) */
export function getKnowledgeTask<T = unknown>(taskId: string | number): Promise<T> {
  return getJSON<T>(`/api/knowledge/tasks/${encodeURIComponent(String(taskId))}`);
}

// ---------------------------------------------------------------------------
// 编译 / 学习计划 / 搜索 / 导入 (B3 收敛: CompileTrigger / LearningPanel /
// KnowledgeSearchBar / UnifiedSearchPage / BookmarkImport / HistoryPage)
// ---------------------------------------------------------------------------

/** GET /api/knowledge/compile/preview — 编译预览 */
export function getKnowledgeCompilePreview<T = CompilePreview>(): Promise<T> {
  return getJSON<T>('/api/knowledge/compile/preview');
}

/** POST /api/knowledge/compile — 触发编译 ({task_id} / {id}) */
export function triggerKnowledgeCompile<T = { task_id?: number; id?: number }>(): Promise<T> {
  return apiFetch<T>('/api/knowledge/compile', { method: 'POST' });
}

/** GET /api/knowledge/plans?status= — 学习计划列表 */
export function listLearningPlans<T = { plans?: unknown[] }>(status = 'active'): Promise<T> {
  return getJSON<T>(`/api/knowledge/plans?status=${encodeURIComponent(status)}`);
}

/** POST /api/knowledge/plans/generate — 生成学习计划 ({task_id} / {task}) */
export function generateLearningPlans<T = { task_id?: number; status?: string }>(
  domains: string[] = [],
): Promise<T> {
  return postJSON<T>('/api/knowledge/plans/generate', { domains });
}

/** GET /api/knowledge/search?q=&limit= — 知识库搜索 (KnowledgeSearchBar) */
export function searchKnowledge<T = { results?: unknown[] }>(
  q: string,
  limit = 20,
): Promise<T> {
  const qs = new URLSearchParams({ q, limit: String(limit) });
  return getJSON<T>(`/api/knowledge/search?${qs}`);
}

/** GET /api/search?q=&sources=&limit= — 全局统一搜索 (UnifiedSearchPage) */
export function searchGlobal<T = unknown>(
  q: string,
  sources?: string[],
  limit = 50,
): Promise<T> {
  const srcs = sources && sources.length > 0 ? `&sources=${sources.join(',')}` : '';
  return getJSON<T>(`/api/search?q=${encodeURIComponent(q)}${srcs}&limit=${limit}`);
}

/** POST /api/wiki/search — wiki 分块检索 */
export function searchWikiChunks<T = unknown>(q: string, limit = 20): Promise<T> {
  return postJSON<T>('/api/wiki/search', { q, limit });
}

/** POST /api/knowledge/import-from-history — 历史条目归档为知识条目 ({errors}) */
export function importFromHistory<T = { errors?: Array<{ error: string }> }>(
  itemIds: Array<string | number>,
): Promise<T> {
  return postJSON<T>('/api/knowledge/import-from-history', { item_ids: itemIds });
}

/** POST /api/knowledge/bookmarks/import?validate= — 浏览器书签导入 */
export function importBookmarks(
  payload: { bookmarks?: unknown } | { html?: string },
  validate: boolean,
): Promise<BookmarkImportResult> {
  return apiFetch<BookmarkImportResult>(
    `/api/knowledge/bookmarks/import?validate=${validate ? 'true' : 'false'}`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

/** POST /api/extract/preview — 标签提取预览 (不持久化) */
export function previewExtractTags<T = { items?: unknown[] }>(body: {
  title: string;
  text: string;
  category: string;
}): Promise<T> {
  return postJSON<T>('/api/extract/preview', body);
}

/** POST /api/extract/{kind}/{id} — 按热点/知识条目触发提取并关联 */
export function runTagExtraction<T = unknown>(
  kind: 'hotspot' | 'knowledge',
  id: string,
): Promise<T> {
  return postJSON<T>(`/api/extract/${kind}/${encodeURIComponent(id)}`, undefined);
}
