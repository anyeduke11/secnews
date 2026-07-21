/**
 * SyncStatusBadge — 共享的同步状态徽章。
 *
 * 在 SyncStatusPanel / SyncHistory 中复用, 单独抽出避免循环依赖。
 * Phase 1B: 拆自原 SyncPage.tsx 内联组件。
 */
import React from 'react';

interface StatusBadgeProps {
  status?: string | null;
}

const COLOR_MAP: Record<string, { bg: string; fg: string; label: string }> = {
  success: { bg: 'color-mix(in srgb, var(--color-success) 15%, transparent)', fg: 'var(--color-success)', label: '成功' },
  error: { bg: 'color-mix(in srgb, var(--color-error) 15%, transparent)', fg: 'var(--color-error)', label: '失败' },
  skipped: { bg: 'color-mix(in srgb, var(--color-warning) 15%, transparent)', fg: 'var(--color-warning)', label: '跳过' },
  unknown: { bg: 'color-mix(in srgb, var(--text-muted) 15%, transparent)', fg: 'var(--text-muted)', label: '未知' },
};

export function SyncStatusBadge({ status }: StatusBadgeProps) {
  const s = status || 'unknown';
  const c = COLOR_MAP[s] || COLOR_MAP.unknown;
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded"
      style={{ background: c.bg, color: c.fg }}
    >
      {c.label}
    </span>
  );
}
