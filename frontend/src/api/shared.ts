/**
 * 跨域共用 API 客户端 (前端重构 V1 · B3 数据层收敛)。
 *
 * 覆盖: 标签 / 事件法(topic-technique 审核) / 收藏 / 内容日历与草稿发布 /
 * 刷新间隔偏好 / 知识导入(kl) / feature flags。
 *
 * 密钥保险箱 / skills / skill-registry / sync 已分别收敛到 `api/settings.ts`
 * 与 `api/skills.ts` (唯一来源), 本文件不再保留同端点副本。函数体只做 lib/api 薄封装。
 */
import { apiFetch, getJSON, postJSON } from '../lib/api';
import type { ApiFetchOptions } from '../lib/api';

// ---------------------------------------------------------------------------
// 标签
// ---------------------------------------------------------------------------

/** GET /api/tags?type= — 标签列表 ({items}) */
export function listTags<T = unknown>(
  type?: string,
  options?: ApiFetchOptions,
): Promise<{ items?: T[] }> {
  const qs = type ? `?type=${encodeURIComponent(type)}` : '';
  return getJSON<{ items?: T[] }>(`/api/tags${qs}`, options);
}

/** POST /api/tags — 新建标签 */
export function createTag<T = unknown>(body: {
  id: string;
  label: string;
  type: string;
}): Promise<T> {
  return postJSON<T>('/api/tags', body);
}

/** DELETE /api/tags/{id} — 删除标签 */
export function deleteTag(id: string): Promise<void> {
  return apiFetch<void>(`/api/tags/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** GET /api/tags/suggest?q= — 标签联想 */
export function suggestTags<T = unknown>(q: string): Promise<T> {
  return getJSON<T>(`/api/tags/suggest?q=${encodeURIComponent(q)}`);
}

// ---------------------------------------------------------------------------
// 事件法 (event-technique 审核)
// ---------------------------------------------------------------------------

/** GET /api/event-technique/event-types — 事件类型列表 ({items}) */
export function listEventTypes<T = unknown>(options?: ApiFetchOptions): Promise<{ items?: T[] }> {
  return getJSON<{ items?: T[] }>('/api/event-technique/event-types', options);
}

/** GET /api/event-technique/candidates?event_type_id=&owner_status= — 候选列表 ({items}) */
export function listEventCandidates<T = unknown>(
  eventTypeId: string | number,
  ownerStatus = 'pending',
  options?: ApiFetchOptions,
): Promise<{ items?: T[] }> {
  return getJSON<{ items?: T[] }>(
    `/api/event-technique/candidates?event_type_id=${encodeURIComponent(String(eventTypeId))}&owner_status=${encodeURIComponent(ownerStatus)}`,
    options,
  );
}

/** POST /api/event-technique/candidates/{id}/approve — 通过候选 */
export function approveEventCandidate(id: string | number): Promise<unknown> {
  return postJSON(`/api/event-technique/candidates/${id}/approve`, {});
}

/** POST /api/event-technique/candidates/{id}/reject — 拒绝候选 */
export function rejectEventCandidate(id: string | number, reason: string): Promise<unknown> {
  return postJSON(`/api/event-technique/candidates/${id}/reject`, { reason });
}

/** POST /api/event-technique/event-types/{id}/batch-approve — 批量通过 */
export function batchApproveEventTypes(
  id: string | number,
  minConfidence = 0.7,
): Promise<{ approved_count?: number; skipped_count?: number }> {
  return postJSON<{ approved_count?: number; skipped_count?: number }>(
    `/api/event-technique/event-types/${id}/batch-approve`,
    { min_confidence: minConfidence },
  );
}

// ---------------------------------------------------------------------------
// 收藏
// ---------------------------------------------------------------------------

/** GET /api/favorites?limit= — 收藏列表 */
export function listFavorites<T = unknown>(limit = 1000): Promise<T> {
  return getJSON<T>(`/api/favorites?limit=${limit}`);
}

/** POST /api/favorites — 新增收藏 ({status, created, item}) */
export function addFavorite<T = unknown>(body: {
  hotspot_id: string;
  category?: string;
  title?: string;
  source?: string;
  url?: string;
}): Promise<T> {
  return postJSON<T>('/api/favorites', body);
}

/** DELETE /api/favorites/{hotspot_id} — 删除收藏 ({status, removed}) */
export function deleteFavorite<T = void>(id: string | number): Promise<T> {
  return apiFetch<T>(`/api/favorites/${encodeURIComponent(String(id))}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// 内容日历 / 草稿 / 发布
// ---------------------------------------------------------------------------

/** GET /api/content/calendar?month=YYYY-MM — 日历条目 ({entries}) */
export function listContentCalendar<T = unknown>(month: string): Promise<{ entries?: T[] }> {
  return getJSON<{ entries?: T[] }>(`/api/content/calendar?month=${month}`);
}

/** POST /api/content/calendar — 新增日历条目 */
export function createContentCalendarEntry(body: {
  date: string;
  topic: string;
  type: string;
  platform: string;
}): Promise<unknown> {
  return postJSON('/api/content/calendar', body);
}

/** DELETE /api/content/calendar/{id} — 删除日历条目 */
export function deleteContentCalendarEntry(id: string | number): Promise<void> {
  return apiFetch<void>(`/api/content/calendar/${id}`, { method: 'DELETE' });
}

/** GET /api/content/drafts — 草稿列表 ({drafts}) */
export function listContentDrafts<T = unknown>(): Promise<{ drafts?: T[] }> {
  return getJSON<{ drafts?: T[] }>('/api/content/drafts');
}

/** GET /api/content/drafts/{id} — 草稿正文 ({content}) */
export function getContentDraftContent(id: string | number): Promise<{ content?: string }> {
  return getJSON<{ content?: string }>(`/api/content/drafts/${id}`);
}

/** POST /api/content/drafts — 新建草稿 */
export function createContentDraft(body: { title: string; content: string }): Promise<unknown> {
  return postJSON('/api/content/drafts', body);
}

/** DELETE /api/content/drafts/{id} — 删除草稿 */
export function deleteContentDraft(id: string | number): Promise<void> {
  return apiFetch<void>(`/api/content/drafts/${id}`, { method: 'DELETE' });
}

/** GET /api/knowledge/skills/{name}/validate — 发布前平台 skill 校验 */
export function validateKnowledgeSkill<T = { valid: boolean; reason?: string }>(
  skillName: string,
): Promise<T> {
  return getJSON<T>(`/api/knowledge/skills/${encodeURIComponent(skillName)}/validate`);
}

/** POST /api/content/drafts/{id}/publish — 创建发布任务 */
export function publishContentDraft<T = unknown>(
  draftId: string | number,
  body: { platform: string; skill_name: string; options: { dry_run: boolean; tags: string[] } },
): Promise<T> {
  return postJSON<T>(`/api/content/drafts/${draftId}/publish`, body);
}

// ---------------------------------------------------------------------------
// 刷新间隔偏好 / 知识导入 (kl)
// ---------------------------------------------------------------------------

/** GET /api/settings/refresh-interval — 当前采集间隔 ({interval_minutes}) */
export function getRefreshIntervalSetting(): Promise<{ interval_minutes?: number } | null> {
  return getJSON<{ interval_minutes?: number } | null>('/api/settings/refresh-interval');
}

/** POST /api/settings/refresh-interval — 保存采集间隔 */
export function saveRefreshInterval(minutes: number): Promise<unknown> {
  return postJSON('/api/settings/refresh-interval', { minutes });
}

/** POST /api/kl/import/url — 按 URL 导入知识 */
export function importKlUrl(url: string): Promise<{ id?: string }> {
  return postJSON<{ id?: string }>('/api/kl/import/url', { url });
}

// ---------------------------------------------------------------------------
// Feature flags
// ---------------------------------------------------------------------------

/** GET /api/settings/features — 扩展 gate 运行时视图 (字段宽松, 由消费方归一) */
export function getFeatureFlagsRaw(): Promise<Record<string, unknown>> {
  return getJSON<Record<string, unknown>>('/api/settings/features');
}