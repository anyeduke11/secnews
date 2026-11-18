/**
 * ApprovalBadge — 审批收件箱的类型 / 发起方小徽标 (B5 从 ApprovalInbox 抽出)
 *
 * 待审卡与失败卡共用的纯展示原子; class 与内联色与拆分前逐字一致。
 */
import type { ReactNode } from 'react';

export function Badge({ children, tone }: { children: ReactNode; tone: 'info' | 'gray' }) {
  const fg = tone === 'info' ? 'var(--color-info)' : 'var(--text-secondary)';
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: `color-mix(in srgb, ${fg} 14%, transparent)`, color: fg }}
    >
      {children}
    </span>
  );
}
