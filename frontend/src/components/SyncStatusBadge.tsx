import React from 'react';

interface StatusBadgeProps {
  status?: string | null;
}

const COLOR_MAP: Record<string, { bg: string; fg: string; label: string }> = {
  success: { bg: 'color-mix(in srgb, var(--color-success) 12%, transparent)', fg: 'var(--color-success)', label: '成功' },
  error: { bg: 'color-mix(in srgb, var(--color-error) 12%, transparent)', fg: 'var(--color-error)', label: '失败' },
  skipped: { bg: 'color-mix(in srgb, var(--color-warning) 12%, transparent)', fg: 'var(--color-warning)', label: '跳过' },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const s = status || 'unknown';
  const cfg = COLOR_MAP[s] || { bg: 'color-mix(in srgb, var(--text-muted) 12%, transparent)', fg: 'var(--text-muted)', label: s };
  return (
    <span
      className="px-2 py-0.5 rounded text-[10px] font-medium"
      style={{ backgroundColor: cfg.bg, color: cfg.fg }}
    >
      {cfg.label}
    </span>
  );
}