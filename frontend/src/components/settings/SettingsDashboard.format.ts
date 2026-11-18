/**
 * settings/SettingsDashboard — 数值/时长格式化纯函数。
 *
 * 拆分自 SettingsDashboard.tsx, 无状态、无副作用.
 */

export function fmtUptime(s?: number): string {
  if (typeof s !== 'number' || s < 0) return '—';
  const days = Math.floor(s / 86400);
  const hrs = Math.floor((s % 86400) / 3600);
  if (days > 0) return `${days}d ${hrs}h`;
  const mins = Math.floor((s % 3600) / 60);
  return `${hrs}h ${mins}m`;
}

export function fmtPct(v?: number): string {
  if (typeof v !== 'number') return '—';
  return `${(v * 100).toFixed(1)}%`;
}

export function fmtInt(v?: number): string {
  if (typeof v !== 'number') return '—';
  return v.toLocaleString('en-US');
}

export function fmtMs(v?: number): string {
  if (typeof v !== 'number') return '—';
  return `${Math.round(v)} ms`;
}