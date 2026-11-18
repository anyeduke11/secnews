/**
 * actionModel — 行动层「今日行动」(/action) 的类型 / 常量 / 纯函数 (B5 从 SentinelActionPage 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见 ActionFloorHeader.tsx / ReviewStackPanel.tsx /
 * JudgingQueuePanel.tsx, 状态与写操作仍归容器 SentinelActionPage.tsx。
 */

/* ---------------------------------------------------------------------
 * 接口响应类型 (与 backend/api/{kl_planning_api,reviews}.py 对齐)
 * ------------------------------------------------------------------- */
export type ActionStatus = 'pending' | 'in_progress' | 'completed' | 'dismissed';

export interface PlanningAction {
  id: number;
  item_id: string;
  action_type: string;
  priority: number;
  title: string;
  description: string | null;
  current_stage: string | null;
  target_stage: string | null;
  status: ActionStatus | string;
  created_at: string | null;
  completed_at: string | null;
  dismissed_at: string | null;
}

export interface ReviewRow {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  /** migration 120 enrich 字段 (未命中/未 enrich 时为 undefined) */
  title?: string | null;
  url?: string | null;
  category?: string | null;
  excerpt?: string | null;
}

/** 评分即时反馈态: 显示 "下次 N 天后见" + 5 秒撤销窗 */
export interface JustGraded {
  key: string;
  entityType: string;
  entityId: string;
  title: string;
  interval: number | null;
}

export interface ReviewStats {
  total: number;
  due: number;
  avg_easiness: number;
}

/** 每行写入态: saving / fail / ok; 判读待办另带 done|dismissed */
export type WriteState = 'saving' | 'fail' | 'ok' | 'done' | 'dismissed';

/** 卡片主行: enrich 命中显示真实标题, 否则如实渲染裸 entity_id */
export function reviewTitle(row: ReviewRow): string {
  return row.title || row.entity_id;
}

/** planning_actions 接口单次固定返回 50 条, 本屏按优先级取前 N 条呈现 */
export const ACTION_SHOWN = 8;
/** 复习栈视觉层数 (顶层可操作, 其后为队列中的真实后续卡) */
export const STACK_DEPTH = 3;

/* ---------------------------------------------------------------------
 * 纯函数 helpers
 * ------------------------------------------------------------------- */

/** API 来源的 href 白名单: 只放行 http/https, 其余 (javascript:/data:) 一律不渲染链接 */
export function safeHref(url?: string | null): string | null {
  if (!url) return null;
  return /^https?:\/\//i.test(url.trim()) ? url.trim() : null;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function stamp(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

export function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

/** SM-2 自评三档 → grade (0-2 未记住, 3-5 记住) */
export const GRADE_DEFS: { label: string; grade: number; hint: string }[] = [
  { label: '忘光', grade: 1, hint: '回到判断层重读原文' },
  { label: '模糊', grade: 3, hint: '间隔缩短, 近日再见' },
  { label: '记得牢', grade: 5, hint: '间隔拉长, 明日再见' },
];

export const ACTION_TYPE_LABEL: Record<string, string> = {
  read: '深读',
  refine: '精读入库',
  link: '建立关联',
  publish: '产出输出',
  review: '复看',
};
