/**
 * api/settings/prefs.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 兴趣画像 (实践域) / 内容偏好
 */
import { apiFetch } from '../../lib/api';
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
