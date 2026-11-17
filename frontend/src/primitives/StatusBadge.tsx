/**
 * StatusBadge — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 五种语义状态, **必带文字标签** (§3 纪律: 不靠颜色单独传义)。
 * 无业务依赖, 颜色全部取自 tokens。
 */
import React from 'react';

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

const TONE_COLOR: Record<StatusTone, string> = {
  ok: 'var(--mint)',
  warn: 'var(--amber)',
  risk: 'var(--red)',
  info: 'var(--color-info)',
  neutral: 'var(--text-muted)',
};

export function StatusBadge({ tone, children, dot = false, count, title }: StatusBadgeProps) {
  const color = TONE_COLOR[tone];
  return (
    <span
      data-tone={tone}
      title={title}
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-[var(--radius-sm)] border px-1.5 py-0.5 text-[11px] leading-[1.35]"
      style={{
        color,
        borderColor: 'var(--line)',
        backgroundColor: 'var(--bg-card)',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
        />
      )}
      <span>{children}</span>
      {typeof count === 'number' && (
        <span style={{ color: 'var(--text-muted)' }}>{count}</span>
      )}
    </span>
  );
}