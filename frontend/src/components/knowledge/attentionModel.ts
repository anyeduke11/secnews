/**
 * attentionModel — 注意力热力图的纯类型 / 常量 / 计算 (B5 续拆: 从 AttentionHeatmap 抽出)
 *
 * 只放无 React 依赖的内容; 网格展示区块见 AttentionHeatmapGrid.tsx。
 */

// ── 类型 ────────────────────────────────────────────────────

export interface AttentionDataPoint {
  date: string;
  hour: number;
  count: number;
}

export interface TooltipState {
  date: string;
  hour: number;
  count: number;
  x: number;
  y: number;
}

/** GET /api/attention/events 响应: 裸数组或 {events|data} 包裹 */
export type AttentionEventsResponse = AttentionDataPoint[] | { events?: AttentionDataPoint[]; data?: AttentionDataPoint[] };

// ── 常量 ────────────────────────────────────────────────────

export const HOURS = 24;
export const CELL_SIZE = 12;
export const CELL_SIZE_COMPACT = 8;
export const GRID_GAP = 2;
export const LABEL_COL_WIDTH = 64;
export const LABEL_COL_WIDTH_COMPACT = 52;
export const HEADER_ROW_HEIGHT = 20;
export const HEADER_ROW_HEIGHT_COMPACT = 16;

// ── 工具函数 ────────────────────────────────────────────────

/** 生成最近 N 天的日期字符串数组 (YYYY-MM-DD) */
export function getLastDays(n: number): string[] {
  const result: string[] = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    result.push(`${y}-${m}-${day}`);
  }
  return result;
}

/** 格式化日期为 "Mon 7/14" 样式 */
export function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  return `${dayNames[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`;
}

/**
 * 根据 count / maxCount 比率计算单元格颜色。
 * 0 → 透明底 (border-subtle)
 * 低 → 浅橙 hsl(28, 70%, 58%)
 * 高 → 深红 hsl(0, 100%, 30%)
 */
export function getCellColor(count: number, maxCount: number): string {
  if (count === 0) return 'transparent';
  const t = Math.min(count / maxCount, 1);
  const hue = Math.round(28 - t * 28);
  const sat = Math.round(70 + t * 30);
  const lit = Math.round(58 - t * 28);
  return `hsl(${hue}, ${sat}%, ${lit}%)`;
}

/** 构建 `date|hour` → count 网格 (无数据的小时保持 0) */
export function buildGrid(dates: string[], data: AttentionDataPoint[]): Map<string, number> {
  const grid = new Map<string, number>();
  for (const date of dates) {
    for (let h = 0; h < HOURS; h++) {
      grid.set(`${date}|${h}`, 0);
    }
  }
  for (const point of data) {
    const key = `${point.date}|${point.hour}`;
    if (grid.has(key)) {
      grid.set(key, point.count);
    }
  }
  return grid;
}
