/**
 * api/settings/ops.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 运维 (数据库维护 / 缓存) / 历史批次 (HistoryPage)
 */
import { getJSON, postJSON } from '../../lib/api';

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
