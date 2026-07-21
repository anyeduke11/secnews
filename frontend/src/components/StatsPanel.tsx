import React from 'react';
import { CATEGORIES, getCategoryColor } from '../types';

interface StatsPanelProps {
  categoryCounts: Record<string, number>;
  total: number;
}

export function StatsPanel({ categoryCounts, total }: StatsPanelProps) {
  const filteredCats = CATEGORIES.filter(c => c.id !== 'all');

  return (
    <div className="card-base p-4 mb-5">
      <div className="flex items-center justify-between mb-3">
        <h3
          className="text-xs font-semibold uppercase tracking-[0.08em] font-mono"
          style={{ color: 'var(--text-secondary)' }}
        >
          <span style={{ color: 'var(--color-ai)', marginRight: 6 }}>▮</span>
          数据统计
        </h3>
        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          total:{' '}
          <span
            className="font-mono tabular-nums"
            style={{ color: 'var(--color-ai)', fontWeight: 600 }}
          >
            {total}
          </span>{' '}
          条
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-4 gap-y-3">
        {filteredCats.map((cat) => {
          const count = categoryCounts[cat.id] || 0;
          const color = getCategoryColor(cat.id);
          const maxCount = Math.max(...Object.values(categoryCounts), 1);
          const barWidth = maxCount > 0 ? (count / maxCount) * 100 : 0;

          return (
            <div key={cat.id}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="flex items-center gap-1.5 text-sm">
                  <span
                    className="dot-indicator"
                    style={{ backgroundColor: color }}
                  />
                  <span style={{ color: 'var(--text-secondary)' }} className="truncate">{cat.label}</span>
                </span>
                <span className="text-sm font-mono font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
              <div
                className="w-full h-1.5 rounded-full overflow-hidden"
                style={{ backgroundColor: 'var(--bg-hover)' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-500 ease-out"
                  style={{
                    width: `${barWidth}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
