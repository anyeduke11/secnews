/**
 * 行动域 API 客户端 (前端重构 V1 · B3)。
 *
 * 覆盖消费方实际用到的端点: 复习 (SM-2) 全族 / 判读待办 (planning_actions) /
 * 优先简报 (digests/priority) / 全局检索 (search)。
 * 函数体保持 lib/api 薄封装, URL 原样搬运。
 */

import { apiFetch, getJSON, postJSON } from '../lib/api';

// ---------------------------------------------------------------------------
// 复习 (reviews)
// ---------------------------------------------------------------------------

/** 复习项 (GET /api/reviews/due 单行) */
export interface ReviewItem {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewStats {
  total: number;
  due: number;
  avg_easiness: number;
}

/** GET /api/reviews/due?limit=&enrich= — 到期复习队列 ({items}) */
export function listDueReviews<T = ReviewItem>(
  limit = 50,
  opts: { enrich?: boolean; signal?: AbortSignal } = {},
): Promise<{ items?: T[] }> {
  const enrich = opts.enrich ? '&enrich=1' : '';
  return getJSON<{ items?: T[] }>(`/api/reviews/due?limit=${limit}${enrich}`, {
    signal: opts.signal,
  });
}

/** GET /api/reviews/stats — 复习统计 ({stats}) */
export function getReviewStats<T = ReviewStats>(): Promise<{ stats?: T | null }> {
  return getJSON<{ stats?: T | null }>('/api/reviews/stats');
}

/** POST /api/reviews/{type}/{id}/grade — 提交评分 (0-5) */
export function submitReviewGrade<T = unknown>(
  entityType: string,
  entityId: string,
  grade: number,
): Promise<T> {
  return postJSON<T>(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/grade`,
    { grade },
  );
}

/** POST /api/reviews/{type}/{id}/undo — 撤销上一次评分 */
export function undoReviewGrade<T = unknown>(entityType: string, entityId: string): Promise<T> {
  return postJSON<T>(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/undo`,
    {},
  );
}

/** POST /api/reviews/{type}/{id}?interval_days= — 创建首条复习 (409=已存在) */
export function createReview(
  entityType: string,
  entityId: string,
  intervalDays = 1,
): Promise<unknown> {
  return apiFetch(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?interval_days=${intervalDays}`,
    { method: 'POST' },
  );
}

/** PATCH /api/reviews/{type}/{id} — 更新复习项 (如暂停 suspended) */
export function updateReview<T = unknown>(
  entityType: string,
  entityId: string,
  body: { suspended?: boolean },
): Promise<T> {
  return apiFetch<T>(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
}

/** DELETE /api/reviews/{type}/{id} — 删除复习项 */
export function deleteReview(entityType: string, entityId: string): Promise<void> {
  return apiFetch<void>(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { method: 'DELETE' },
  );
}

/** POST /api/reviews/{type}/{id} — 直接创建复习项 (ReviewOverlay 数据视图入口) */
export function createReviewItem<T = unknown>(entityType: string, entityId: string): Promise<T> {
  return postJSON<T>(
    `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    {},
  );
}

/** GET /api/reviews/cards?limit= — 复习卡片 */
export function listReviewCards<T = unknown>(limit = 200): Promise<T> {
  return getJSON<T>(`/api/reviews/cards?limit=${limit}`);
}

/** GET /api/reviews/forecast?days= — 复习预测 */
export function getReviewForecast<T = unknown>(days = 7): Promise<T> {
  return getJSON<T>(`/api/reviews/forecast?days=${days}`);
}

/** GET /api/reviews/history?limit= — 复习历史 */
export function listReviewHistory<T = unknown>(limit = 50): Promise<T> {
  return getJSON<T>(`/api/reviews/history?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// 判读待办 (planning_actions)
// ---------------------------------------------------------------------------

/** 判读待办单行 (GET /api/kl/planning-actions 顶层数组) */
export interface PlanningAction {
  id: number;
  entity_type: string;
  entity_id: string;
  action_type: string;
  title?: string;
  description?: string | null;
  status: string;
  created_at?: string;
  updated_at?: string;
}

/** GET /api/kl/planning-actions?status= — 待办列表 (顶层数组, 接口固定上限 50) */
export function listPlanningActions<T = PlanningAction>(status = 'pending'): Promise<T[]> {
  return getJSON<T[]>(`/api/kl/planning-actions?status=${encodeURIComponent(status)}`);
}

/** PUT /api/kl/planning-actions/{id}/status — 推进待办状态 */
export function updatePlanningActionStatus(id: number, status: string): Promise<unknown> {
  return apiFetch(`/api/kl/planning-actions/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });
}

/** 通用动作按钮分发 — endpoint 由按钮配置提供, method 默认 POST */
export function postActionEndpoint<T = unknown>(
  endpoint: string,
  method = 'POST',
  body?: unknown,
): Promise<T> {
  return apiFetch<T>(endpoint, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// 优先简报 / 全局检索
// ---------------------------------------------------------------------------

/** GET /api/digests/priority?force= — 优先简报 (后端 5min TTL) */
export function getPriorityDigest<T = unknown>(force = false): Promise<T> {
  return apiFetch<T>(`/api/digests/priority${force ? '?force=true' : ''}`);
}

/** GET /api/search?q=&sources=&limit= — 全局检索 */
export function searchAll<T = unknown>(
  q: string,
  opts: { sources?: string; limit?: number } = {},
): Promise<T> {
  const sources = opts.sources ?? 'hotspot,knowledge';
  const limit = opts.limit ?? 10;
  return getJSON<T>(
    `/api/search?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&limit=${limit}`,
  );
}