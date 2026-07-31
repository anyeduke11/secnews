import React from 'react';
import { CATEGORIES, getCategoryColorVar } from '../types';

interface StatsPanelProps {
  categoryCounts: Record<string, number>;
  total: number;
}

export function StatsPanel({ categoryCounts, total }: StatsPanelProps) {
  const filteredCats = CATEGORIES.filter(c => c.id !== 'all');

  return (
    <div className="mb-6">
      {/* v1.9 Editorial: 侧栏版块 — 栏目小标 + 上边粗线, 去卡片盒 */}
      <div className="flex items-center justify-between pb-2 mb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h3 className="text-xs font-bold tracking-[0.12em] uppercase" style={{ color: 'var(--text-primary)' }}>
          数据统计
        </h3>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          共{' '}
          <span className="font-mono tabular-nums font-semibold" style={{ color: 'var(--text-primary)' }}>
            {total}
          </span>{' '}
          条
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-1 gap-x-4 gap-y-3">
        {filteredCats.map((cat) => {
          const count = categoryCounts[cat.id] || 0;
          const color = getCategoryColorVar(cat.id);
          const maxCount = Math.max(...Object.values(categoryCounts), 1);
          const barWidth = maxCount > 0 ? (count / maxCount) * 100 : 0;

          return (
            <div key={cat.id}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="flex items-center gap-1.5 text-xs">
                  <span className="dot-indicator" style={{ backgroundColor: color }} />
                  <span style={{ color: 'var(--text-secondary)' }} className="truncate">{cat.label}</span>
                </span>
                <span className="text-xs font-mono font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
              <div className="w-full h-1 overflow-hidden" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div
                  className="h-full transition-all duration-500 ease-out"
                  style={{ width: `${barWidth}%`, backgroundColor: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
