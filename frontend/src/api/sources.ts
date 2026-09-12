/**
 * Sources / 系统健康 域 API 客户端。
 *
 * 与后端 backend/api/sources.py (prefix /api/sources) + backend/api/health.py
 * (GET /api/health) 对齐。复用 lib/api 统一封装 (apiFetch / getJSON / postJSON),
 * 错误透传后端 message。
 *
 * 当前前端消费方: useRefreshInterval (getHealth 的 collect_interval_seconds)。
 * 其余端点为信源管理 (custom CRUD / health 巡检 / 告警 / 统计) 的标准客户端,
 * 供组件层后续迁移裸 fetch 时复用。
 */

import { getJSON, postJSON, apiFetch } from '../lib/api';

// ---------------------------------------------------------------------------
// 端点常量 (URL 字面量统一收敛于此, 杜绝散落)
// ---------------------------------------------------------------------------
const SOURCES_URL = '/api/sources';
const HEALTH_URL = '/api/health';

// ---------------------------------------------------------------------------
// 类型 (后端返回为宽松 dict, 这里只声明前端消费的字段 + 索引兜底)
// ---------------------------------------------------------------------------

/** GET /api/health 系统健康 (useRefreshInterval 只读 collect_interval_seconds) */
export interface SystemHealth {
  collect_interval_seconds?: number;
  [key: string]: unknown;
}

/** GET /api/sources/custom — 自定义信源条目 (后端 to_dict, 字段宽松) */
export type CustomSource = Record<string, unknown>;

export interface CustomSourceListResponse {
  sources: CustomSource[];
}

export interface AddCustomSourceRequest {
  url: string;
  name?: string;
  /** None = 后端按 URL/标题自动分类 */
  category?: string | null;
}

export interface AddCustomSourceResponse {
  status: string;
  id: number;
  url: string;
  category: string;
  probe: Record<string, unknown>;
}

export interface DeleteCustomSourceResponse {
  status: string;
  deleted: number;
}

export interface ToggleCustomSourceResponse {
  status: string;
  id: number;
  enabled: boolean;
}

export interface ReprobeSourceResponse {
  status: string;
  probe: Record<string, unknown>;
}

/** 信源健康/统计/告警/趋势载荷 (后端 Phase 3/9 dict, 字段宽松) */
export type SourceHealthPayload = Record<string, unknown>;

// ---------------------------------------------------------------------------
// 系统健康
// ---------------------------------------------------------------------------

export function getHealth(): Promise<SystemHealth> {
  return getJSON<SystemHealth>(HEALTH_URL);
}

// ---------------------------------------------------------------------------
// 自定义信源 CRUD (/api/sources/custom)
// ---------------------------------------------------------------------------

export function listCustomSources(): Promise<CustomSourceListResponse> {
  return getJSON<CustomSourceListResponse>(`${SOURCES_URL}/custom`);
}

/** 添加自定义信源 (后端先探测; SSRF 黑名单 / 探测失败 / URL 重复 均 4xx 抛错) */
export function addCustomSource(body: AddCustomSourceRequest): Promise<AddCustomSourceResponse> {
  return postJSON<AddCustomSourceResponse>(`${SOURCES_URL}/custom`, body);
}

export function deleteCustomSource(sid: number): Promise<DeleteCustomSourceResponse> {
  return apiFetch<DeleteCustomSourceResponse>(
    `${SOURCES_URL}/custom/${encodeURIComponent(String(sid))}`,
    { method: 'DELETE' },
  );
}

/** 重新探测单个自定义信源 */
export function reprobeCustomSource(sid: number): Promise<ReprobeSourceResponse> {
  return postJSON<ReprobeSourceResponse>(
    `${SOURCES_URL}/custom/${encodeURIComponent(String(sid))}/probe`,
    undefined,
  );
}

/** 启用/停用自定义信源 */
export function toggleCustomSource(sid: number, enabled: boolean): Promise<ToggleCustomSourceResponse> {
  return postJSON<ToggleCustomSourceResponse>(
    `${SOURCES_URL}/custom/${encodeURIComponent(String(sid))}/toggle?enabled=${enabled}`,
    undefined,
  );
}

// ---------------------------------------------------------------------------
// 信源健康巡检 (/api/sources/health*)
// ---------------------------------------------------------------------------

export function getSourceHealth(category?: string): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(
    `${SOURCES_URL}/health${category ? `?category=${encodeURIComponent(category)}` : ''}`,
  );
}

export function getSourceHealthV2(): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(`${SOURCES_URL}/health/v2`);
}

export function getSourceHealthTrend(): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(`${SOURCES_URL}/health/trend`);
}

export function getSourceHealthTrendBySource(source: string): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(
    `${SOURCES_URL}/health/trend/${encodeURIComponent(source)}`,
  );
}

export function getSourceHealthBySource(
  category: string,
  sourceName: string,
): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(
    `${SOURCES_URL}/health/by-source/${encodeURIComponent(category)}/${encodeURIComponent(sourceName)}`,
  );
}

export function resetSourceHealth(category: string, sourceName: string): Promise<SourceHealthPayload> {
  return postJSON<SourceHealthPayload>(
    `${SOURCES_URL}/health/by-source/${encodeURIComponent(category)}/${encodeURIComponent(sourceName)}/reset`,
    undefined,
  );
}

export function markSourceDead(category: string, sourceName: string): Promise<SourceHealthPayload> {
  return postJSON<SourceHealthPayload>(
    `${SOURCES_URL}/health/by-source/${encodeURIComponent(category)}/${encodeURIComponent(sourceName)}/dead`,
    undefined,
  );
}

// ---------------------------------------------------------------------------
// 统计 / 告警 / 手动探测
// ---------------------------------------------------------------------------

export function getSourceStats(): Promise<SourceHealthPayload> {
  return getJSON<SourceHealthPayload>(`${SOURCES_URL}/stats`);
}

export interface SourceAlertsQuery {
  source_id?: string;
  level?: string;
  since?: string;
  page?: number;
  page_size?: number;
}

export function getSourceAlerts(q: SourceAlertsQuery = {}): Promise<SourceHealthPayload> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return getJSON<SourceHealthPayload>(`${SOURCES_URL}/alerts${qs ? `?${qs}` : ''}`);
}

/** 对任意信源 (source_id) 发起手动探测 */
export function probeSource(sourceId: string): Promise<SourceHealthPayload> {
  return postJSON<SourceHealthPayload>(
    `${SOURCES_URL}/${encodeURIComponent(sourceId)}/probe`,
    undefined,
  );
}
