/**
 * runStageModel — 第③段 Run 的常量 / 状态映射 / 内联样式 (B5 从 RunStage 抽出)
 *
 * 供 RunStage 与其行级子块 RunActionRow / RunFinishForm 共用, 避免映射表多处维护。
 */
import type { CSSProperties } from 'react';
import { TONE_OK, TONE_WARN, TONE_IDLE, TONE_ACCENT } from './stageStyles';

export const ACTION_STATUS: Record<string, string> = {
  planned: '待批准',
  approved: '已批准',
  running: '运行中',
  succeeded: '已成功',
  failed: '已失败',
  cancelled: '已取消',
  rejected: '已拒绝',
};

export const TERMINAL_RUN_STATUS = new Set(['succeeded', 'failed', 'cancelled', 'timed_out']);

export const OUTCOME_OPTIONS: { value: string; label: string }[] = [
  { value: 'done', label: '成功 (done)' },
  { value: 'failed', label: '失败 (failed)' },
  { value: 'cancelled', label: '取消 (cancelled)' },
  { value: 'timeout', label: '超时 (timeout)' },
  { value: 'needs_human', label: '需人工 (needs_human)' },
];

/** 人工回执登记结果请求体 (与 POST /api/v1/runs/{id}/finish 字段对齐) */
export type FinishRunBody = { outcome: string; error?: string | null; result_excerpt?: string | null };

export function outcomeOf(status?: string): { label: string; color: string } {
  switch (status) {
    case 'succeeded':
      return { label: '成功', color: TONE_OK };
    case 'failed':
      return { label: '失败', color: TONE_WARN };
    case 'timed_out':
      return { label: '超时失败', color: TONE_WARN };
    case 'cancelled':
      return { label: '已取消', color: TONE_IDLE };
    case 'running':
      return { label: '进行中', color: TONE_ACCENT };
    case 'queued':
    case 'claimed':
      return { label: '排队中', color: TONE_IDLE };
    default:
      return { label: '未知', color: TONE_IDLE };
  }
}

export const btnStyle: CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-bg)',
  background: 'var(--sn-accent)',
  border: 'none',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};

export const btnGhostStyle: CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-ink-2)',
  background: 'transparent',
  border: '1px solid var(--border-color, rgba(128,128,128,.4))',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};
