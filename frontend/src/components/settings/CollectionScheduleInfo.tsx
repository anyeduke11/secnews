/**
 * settings/CollectionScheduleInfo — 采集调度信息 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-cellgrid 替换原 grid-cols-3 + cellnote 行
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
    <section className="st-section" aria-label="采集调度" data-testid="collection-schedule-info">
      <h3>采集调度</h3>
      <p className="st-section-desc">当前调度间隔 / 最近一次采集 / 调度任务数 (来自 /api/health)。</p>
      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">间隔</span>
          <span className="st-cellv sm">{interval ? `${interval} 分钟` : '—'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">最近运行</span>
          <span className="st-cellv sm">{lastRun ? lastRun.slice(0, 16).replace('T', ' ') : '未运行'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">调度任务</span>
          <span className="st-cellv sm">{jobs} 个</span>
        </div>
      </div>
    </section>
  );
}

export default CollectionScheduleInfo;