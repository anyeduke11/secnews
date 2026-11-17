/**
 * Report 域 API 客户端 (日报 / 周报 / 月报)。
 *
 * 契约对齐 backend/api/reports*.py, 路径前缀 /api/reports。
 * 复用 lib/api 统一封装, 非 2xx 抛 ApiError。
 *
 *   - GET /api/reports/daily/overview          → getDailyOverview
 *   - GET /api/reports/weekly/available        → getWeeklyAvailable
 *   - GET /api/reports/weekly/overview?week_start= → getWeeklyOverview
 *   - GET /api/reports/monthly/available       → getMonthlyAvailable
 *   - GET /api/reports/monthly/overview?offset=  → getMonthlyOverview
 *
 * 返回形状由组件侧 types (components/report/types.ts) 声明, 此处仅作泛型透传。
 */

import { getJSON } from '../lib/api';

/** GET /api/reports/daily/overview — 日报概览 */
export function getDailyOverview<T = unknown>(): Promise<T> {
  return getJSON<T>('/api/reports/daily/overview');
}

/** GET /api/reports/weekly/available — 可选周列表 ({weeks}) */
export function getWeeklyAvailable<T = { weeks?: unknown[] }>(): Promise<T> {
  return getJSON<T>('/api/reports/weekly/available');
}

/** GET /api/reports/weekly/overview?week_start= — 周报概览 */
export function getWeeklyOverview<T = unknown>(weekStart: string): Promise<T> {
  return getJSON<T>(`/api/reports/weekly/overview?week_start=${weekStart}`);
}

/** GET /api/reports/monthly/available — 可选月份列表 ({months}) */
export function getMonthlyAvailable<T = { months?: unknown[] }>(): Promise<T> {
  return getJSON<T>('/api/reports/monthly/available');
}

/** GET /api/reports/monthly/overview?offset= — 月报概览 */
export function getMonthlyOverview<T = unknown>(offset: number): Promise<T> {
  return getJSON<T>(`/api/reports/monthly/overview?offset=${offset}`);
}