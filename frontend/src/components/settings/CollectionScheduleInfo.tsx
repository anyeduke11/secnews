/**
 * settings/CollectionScheduleInfo — 采集调度信息。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 CollectionScheduleInfo (~461-496 行)。
 * 纯结构拆分: 状态与 fetch/渲染逻辑逐字迁移。
 */
import { useState, useEffect } from 'react';

export function CollectionScheduleInfo() {
  const [health, setHealth] = useState<{ collect_interval_seconds?: number; components?: { collectors?: any; scheduler?: any } } | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealth(d))
      .catch(() => {});
  }, []);

  const interval = health?.collect_interval_seconds ? Math.round(health.collect_interval_seconds / 60) : null;
  const lastRun = health?.components?.collectors?.last_run;
  const jobs = health?.components?.scheduler?.details?.length ?? 0;

  return (
    <div className="card-base">
      <div className="px-2.5 py-1.5">
        <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>采集调度</span>
        <div className="grid grid-cols-3 gap-1.5 mt-1.5 text-[9px]">
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">间隔</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{interval ? `${interval} 分钟` : '-'}</span>
          </div>
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">最近运行</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{lastRun ? lastRun.slice(0, 16).replace('T', ' ') : '未运行'}</span>
          </div>
          <div className="flex flex-col" style={{ color: 'var(--text-muted)' }}>
            <span className="font-mono">调度任务</span>
            <span className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{jobs} 个</span>
          </div>
        </div>
      </div>
    </div>
  );
}
