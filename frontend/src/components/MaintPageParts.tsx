/**
 * MaintPage 共享小件 — 体积格式化 + 状态徽章取色 (从 MaintPage.tsx 拆出)。
 *
 * 纯函数, 无 hooks / 无状态; 供清理卡与索引卡共用.
 */

import type { ToolStatus } from './MaintPage.types';

export function fmtBytes(n: number): string {
  // avg 宽度估算展示 (后端口径: 文本列 SUM(LENGTH) + 数值列 ~10B/行)
  if (n <= 0) return '0 KB';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function statusBadge(t: (key: string) => string, s: ToolStatus): { bg: string; fg: string; text: string } {
  switch (s) {
    case 'running': return { bg: 'var(--bg-info, var(--bg-elevated))', fg: 'var(--text-on-info, var(--ink))', text: t('maint.status.running') };
    case 'ok': return { bg: 'var(--bg-success, var(--bg-elevated))', fg: 'var(--text-on-success, var(--mint))', text: t('maint.status.ok') };
    case 'error': return { bg: 'var(--bg-warning)', fg: 'var(--text-on-warning, var(--color-error))', text: t('maint.status.error') };
    default: return { bg: 'var(--bg-elevated)', fg: 'var(--ink-3)', text: t('maint.status.idle') };
  }
}