/**
 * reviewModel — 复习栈弹层 (ReviewOverlay) 的类型 / 常量 / 纯函数 (B5 从 ReviewOverlay 抽出)
 *
 * 只放无 React 依赖的内容; 三视图区块见 ReviewSessionView.tsx / ReviewDataView.tsx /
 * ReviewManageView.tsx, 弹层壳 (tab 切换 + Escape 关闭) 仍归容器 ReviewOverlay.tsx。
 */

export type RvView = 'session' | 'data' | 'manage';

export const RV_TABS: { key: RvView; label: string }[] = [
  { key: 'session', label: '会话' },
  { key: 'data', label: '数据' },
  { key: 'manage', label: '管理' },
];

/** 面板同款三档自评 (grade 1/3/5) */
export const RV_GRADES = [
  { grade: 1, label: '忘光' },
  { grade: 3, label: '模糊' },
  { grade: 5, label: '记得牢' },
] as const;

/** search 来源 → 复习卡 entity_type 映射 */
export function sourceToReviewType(t: string): string {
  return t === 'knowledge' ? 'knowledge_item' : 'hotspot';
}

export function rvTitle(row: { title?: string | null; entity_id: string }): string {
  return row.title || row.entity_id;
}

export function fmtDay(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '--'
    : `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
}

/* ---------------------------------------------------------------------
 * 接口响应类型 (与 backend/api/{reviews,reviews_manage,search}.py 对齐)
 * ------------------------------------------------------------------- */
export interface RvRow {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  suspended?: number;
  title?: string | null;
  url?: string | null;
  category?: string | null;
  excerpt?: string | null;
}

export interface ForecastItem { date: string; count: number }

export interface HistoryItem {
  id: number;
  entity_type: string;
  entity_id: string;
  grade: number;
  new_interval: number;
  reverted: number;
  created_at: string;
}

export interface RvStats {
  total: number;
  due: number;
  avg_easiness: number;
  retention_30d: number | null;
  grade_distribution: Record<string, number>;
  suspended_count: number;
}

export interface SearchItem {
  entity_type: string;
  entity_id: string;
  title: string;
  category?: string | null;
}

/** 会话视图评分结果 (汇总页逐张撤销用) */
export interface SessionResult {
  key: string;
  row: RvRow;
  grade: number;
  nextInterval: number | null;
}

/** 键盘事件目标守卫: 输入控件内不抢按键 */
export function isEditableTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toUpperCase();
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}
