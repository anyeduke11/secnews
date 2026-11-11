import type { CSSProperties } from 'react';

/**
 * 四段执行指挥台共享排版 (R-15)。
 * 全部走 sentinel.css 语义令牌 (--sn-*), 不引入裸色值/裸间距。
 * 语义三色: ok=--sn-mint / warn=--sn-amber / idle=--sn-ink-3; 红色 (--sn-red) 专属漏洞告警。
 */

export const STAGE: CSSProperties = {
  borderTop: '1px solid var(--sn-line)',
  marginTop: 'var(--space-4, 14px)',
  paddingTop: 'var(--space-4, 14px)',
};

export const STAGE_HEAD: CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 8,
  marginBottom: 8,
};

export const STAGE_TITLE: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: '.02em',
  color: 'var(--sn-ink)',
};

export const STAGE_COUNT: CSSProperties = {
  fontSize: 11,
  color: 'var(--sn-ink-3)',
  fontVariantNumeric: 'tabular-nums',
};

export const STAGE_EMPTY: CSSProperties = {
  fontSize: 12,
  lineHeight: 1.6,
  color: 'var(--sn-ink-3)',
  margin: 0,
};

export const ITEM_ROW: CSSProperties = {
  border: '1px solid var(--sn-line)',
  borderRadius: 'var(--radius-md, 8px)',
  padding: '8px 10px',
  background: 'var(--sn-bg-panel)',
};

export const TONE_OK = 'var(--sn-mint)';
export const TONE_WARN = 'var(--sn-amber)';
export const TONE_IDLE = 'var(--sn-ink-3)';
export const TONE_ACCENT = 'var(--sn-accent)';