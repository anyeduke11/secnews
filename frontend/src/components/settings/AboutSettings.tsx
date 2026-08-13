/**
 * settings/AboutSettings — 关于 / 系统信息。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 AboutSettings (~593-678 行)。
 * 纯结构拆分: 状态 (health) 与 fetch/渲染逻辑逐字迁移。
 */
import React, { useState, useEffect } from 'react';

export function AboutSettings() {
  const [health, setHealth] = useState<{
    version?: string;
    uptime_s?: number;
    status?: string;
    components?: { db?: any; scheduler?: any; collectors?: any; proxy?: any };
  } | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealth(d))
      .catch(() => {});
  }, []);

  const fmtUptime = (s?: number) => {
    if (!s) return '-';
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  const statusColor = (st?: string) => {
    switch (st) {
      case 'ok': return 'var(--color-success)';
      case 'degraded': return 'var(--color-warning)';
      default: return 'var(--color-error)';
    }
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>系统信息</span>
            {health?.status && (
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{
                backgroundColor: `color-mix(in srgb, ${statusColor(health.status)} 9%, transparent)`,
                color: statusColor(health.status),
              }}>
                {health.status === 'ok' ? '正常运行' : health.status === 'degraded' ? '部分降级' : '异常'}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-1 text-[9px]">
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">版本</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{health?.version || '-'}</span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">运行</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{fmtUptime(health?.uptime_s)}</span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">数据库</span>
              <span className="font-mono font-medium" style={{ color: health?.components?.db?.ok ? 'var(--color-success)' : 'var(--color-error)' }}>
                {health?.components?.db?.ok ? '正常' : '异常'}
                {health?.components?.db?.size_mb ? ` (${health.components.db.size_mb.toFixed(1)} MB)` : ''}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">调度器</span>
              <span className="font-mono font-medium" style={{ color: health?.components?.scheduler?.ok ? 'var(--color-general)' : 'var(--text-muted)' }}>
                {health?.components?.scheduler?.ok ? `${health.components.scheduler.details?.length || 0} 个任务` : '未启动'}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">采集器</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                {health?.components?.collectors?.last_run ? `最近 ${health.components.collectors.last_run.slice(0, 10)}` : '未运行'}
              </span>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
              <span className="font-mono">代理</span>
              <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                {health?.components?.proxy?.mode || '-'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
