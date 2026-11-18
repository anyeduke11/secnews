/**
 * reviewModel — 间隔复习 (ReviewMode) 的纯类型 / 常量 / 工具 (B5 从 ReviewMode 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见同目录 Review*.tsx。
 */

// ── 类型定义 ──────────────────────────────────────────────────

export interface ReviewRecord {
  id: number;
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

export interface KnowledgeDetail {
  id: string;
  title: string;
  source: string;
  source_url: string;
  domain: string | null;
  tags: string[];
  concepts: string[];
  mastered: number;
  content?: string;
}

export interface GradeResponse {
  version: string;
  status: string;
  item: ReviewRecord;
}

// ── 评分按钮配置 ──────────────────────────────────────────────

export const GRADE_LABELS: { value: number; label: string; desc: string }[] = [
  { value: 0, label: '0', desc: '完全忘记' },
  { value: 1, label: '1', desc: '几乎想不起' },
  { value: 2, label: '2', desc: '有印象但模糊' },
  { value: 3, label: '3', desc: '勉强回忆' },
  { value: 4, label: '4', desc: '基本掌握' },
  { value: 5, label: '5', desc: '完全牢记' },
];

// ── 辅助函数 ──────────────────────────────────────────────────

/** 截断文本到指定长度，保留完整单词 */
export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).replace(/\s+\S*$/, '') + '…';
}
