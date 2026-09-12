/**
 * Hotspot 域 API 客户端 (Batch 5 / R5 "同一端点唯一 hook owner" — /api/hotspots 调用面收敛)。
 *
 * 以 api/v1.ts 为样板, 复用 lib/api 统一封装 (getJSON / postJSON), 错误透传后端 message。
 * 端点契约对齐 backend/api/hotspots.py + backend/api/refresh.py:
 *   - GET  /api/hotspots        → listHotspots (cursor 分页 + 分类/时间窗/关键词/来源筛选)
 *   - GET  /api/hotspots/{id}   → getHotspot (单条详情)
 *   - POST /api/refresh         → triggerRefresh (同步触发一轮 run_once() 采集)
 *
 * 命名纪律 (DEV-0167 refetch vs refresh 语义分离):
 *   - refetch = 只读重拉本地缓存失效的第 1 页, 绝不触发后端采集 → 属于 hook 层
 *     (useHotspotData.refetch), 本文件不提供;
 *   - triggerRefresh = 用户显式点击「立即采集」才允许调用, 会同步跑一轮采集。
 *     组件不得用 triggerRefresh 充当数据刷新手段, 否则会复现
 *     "采集 → collect_done → POST /api/refresh → 再采集" 自激。
 *
 * 类型复用 types/index.ts (HotspotResponse 与后端 list_hotspots 响应逐字段一致)。
 */

import { getJSON, postJSON } from '../lib/api';
import type { GetHotspotResponse, HotspotResponse } from '../types';

// ---------------------------------------------------------------------------
// Query (对齐 list_hotspots 的 Query 参数; 未传时走后端默认值)
// ---------------------------------------------------------------------------
export interface ListHotspotsQuery {
  /** 分类筛选: 'all' 或具体分类值 (后端默认 all) */
  category?: string;
  /** 时间窗: 24h / 3d / 7d / 30d (后端默认 7d, 7d 为本周周一 00:00 起) */
  time_range?: string;
  /** 游标分页 (首次为空) */
  cursor?: string;
  /** 每页条数 (后端 Query(50, ge=1, le=200), 300/400 会被拒 422) */
  limit?: number;
  /** 关键词搜索 */
  keyword?: string;
  /** v1.9.1: 来源精确筛选 */
  source?: string;
  /** DEV-0175: 排除单一分类 */
  exclude_category?: string;
  /** v1.7: 逗号分隔 tag id, 触发标签筛选 */
  tags?: string;
  /** v1.7: 标签筛选模式 */
  tag_mode?: 'and' | 'or';
}

export interface ListHotspotsOptions {
  /** AbortController 透传 (调用方持有 signal, 自行管理取消) */
  signal?: AbortSignal;
}

/** 构建 query string: 跳过 undefined / null / 空串 (后端空串等价默认值) */
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

/** GET /api/hotspots — cursor 分页列表 (items / total / next_cursor / category_counts 等) */
export function listHotspots(
  q: ListHotspotsQuery = {},
  opts: ListHotspotsOptions = {},
): Promise<HotspotResponse> {
  return getJSON<HotspotResponse>(
    `/api/hotspots${buildQuery(q as Record<string, unknown>)}`,
    { signal: opts.signal },
  );
}

/** GET /api/hotspots/{id} — 单条详情 ({version, item}) */
export function getHotspot(id: string): Promise<GetHotspotResponse> {
  return getJSON<GetHotspotResponse>(`/api/hotspots/${encodeURIComponent(id)}`);
}

/**
 * POST /api/refresh 响应 — CollectionReport 核心字段。
 * 业务失败也是 HTTP 200 + ok=false + error (非 HTTP 错误), 调用方须检查 ok。
 */
export interface RefreshReport {
  ok: boolean;
  error?: string;
  total?: number;
  success_count?: number;
  failed_count?: number;
  fallback_count?: number;
  duration_ms?: number;
  started_at?: string | null;
  finished_at?: string | null;
  failures?: unknown;
}

/**
 * POST /api/refresh — 手动触发完整采集, 同步等待结果 (trigger 采集语义, 见文件头纪律)。
 * 只读重拉请用 useHotspotData().refetch, 不要用本函数。
 */
export function triggerRefresh(): Promise<RefreshReport> {
  return postJSON<RefreshReport>('/api/refresh', undefined);
}
