/**
 * StatusBadge — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4 / redesign-v1 R-2)
 *
 * 五种语义状态, **必带文字标签** (§3 纪律: 不靠颜色单独传义)。
 * 视觉走 design/redesign-v1 §6 的 `.badge` + `.b-*` 词汇; 颜色仍全部取自 tokens。
 *
 * B10 (2026-11-19): 设置域自建的 `st-chip` 四态徽章族 (76 站点) 收敛到本原子 —— 语气映射
 * 与 st-chip 一一对应: ok→ok / warn→warn / bad→risk / mute→neutral / 无后缀→neutral。
 * `dot` 前置圆点沿用 st-chip 的 `<i>` 语义, `blink` 保留 st-chip 告警圆点的闪烁提示
 * (默认关 —— 避免改变既有 sync 页徽章行为)。
 */
import React from 'react';
import './primitives.css';

export type StatusTone = 'ok' | 'warn' | 'risk' | 'info' | 'neutral';

export interface StatusBadgeProps {
  tone: StatusTone;
  children: React.ReactNode;
  /** 前缀圆点, 纯装饰 */
  dot?: boolean;
  /** 告警圆点闪烁 (沿用 st-chip 行为, 需配合 dot) */
  blink?: boolean;
  /** 右侧次要计数 */
  count?: number;
  title?: string;
  className?: string;
  style?: React.CSSProperties;
  'aria-label'?: string;
  'data-testid'?: string;
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

export function StatusBadge({
  tone,
  children,
  dot = false,
  blink = false,
  count,
  title,
  className = '',
  style,
  'aria-label': ariaLabel,
  'data-testid': testId,
}: StatusBadgeProps) {
  return (
    <span
      data-tone={tone}
      title={title}
      aria-label={ariaLabel}
      data-testid={testId}
      className={`badge ${TONE_CLASS[tone]} ${className}`.trim()}
      style={style}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={`badge-dot${blink ? ' is-blink' : ''}`}
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