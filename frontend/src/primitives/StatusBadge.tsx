/**
 * StatusBadge — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4 / redesign-v1 R-2)
 *
 * 五种语义状态, **必带文字标签** (§3 纪律: 不靠颜色单独传义)。
 * 视觉走 design/redesign-v1 §6 的 `.badge` + `.b-*` 词汇; 颜色仍全部取自 tokens。
 */
import React from 'react';
import './primitives.css';

export type StatusTone = 'ok' | 'warn' | 'risk' | 'info' | 'neutral';

export interface StatusBadgeProps {
  tone: StatusTone;
  children: React.ReactNode;
  /** 前缀圆点, 纯装饰 */
  dot?: boolean;
  /** 右侧次要计数 */
  count?: number;
  title?: string;
}

/** 语义色 (圆点用) */
const TONE_COLOR: Record<StatusTone, string> = {
  ok: 'var(--mint)',
  warn: 'var(--amber)',
  risk: 'var(--red)',
  info: 'var(--info)',
  neutral: 'var(--text-muted)',
};

/** 徽章描边/底色档位 (design/redesign-v1 §6) */
const TONE_CLASS: Record<StatusTone, string> = {
  ok: 'b-ok',
  warn: 'b-none',
  risk: 'b-red',
  info: 'b-part',
  neutral: 'b-disc',
};

export function StatusBadge({ tone, children, dot = false, count, title }: StatusBadgeProps) {
  return (
    <span data-tone={tone} title={title} className={`badge ${TONE_CLASS[tone]}`}>
      {dot && (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: TONE_COLOR[tone] }}
        />
      )}
      <span>{children}</span>
      {typeof count === 'number' && (
        <span className="num" style={{ color: 'var(--text-muted)' }}>
          {count}
        </span>
      )}
    </span>
  );
}