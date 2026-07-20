import React from 'react';
import { CATEGORIES, getCategoryColor } from '../types';

interface StatsPanelProps {
  categoryCounts: Record<string, number>;
  total: number;
}

export function StatsPanel({ categoryCounts, total }: StatsPanelProps) {
  const filteredCats = CATEGORIES.filter(c => c.id !== 'all');
  const maxCount = Math.max(...filteredCats.map(c => categoryCounts[c.id] || 0), 1);

  return (
    <section
      className="card-base p-4 mb-4"
      aria-label="分类统计"
    >
      <header className="flex items-baseline justify-between mb-3.5">
        <h2 className="section-overline">数据分布</h2>
        <div className="flex items-baseline gap-1.5 font-mono">
          <span className="text-[10px]" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
            TOTAL
          </span>
          <span
            className="text-[18px] font-bold leading-none tabular-nums"
            style={{ color: 'var(--color-ai)' }}
          >
            {total.toLocaleString()}
          </span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>条</span>
        </div>
      </header>

      <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-3.5 gap-y-3">
        {filteredCats.map((cat) => {
          const count = categoryCounts[cat.id] || 0;
          const color = getCategoryColor(cat.id);
          const ratio = (count / maxCount) * 100;
          const isEmpty = count === 0;

          return (
            <li key={cat.id} className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="flex items-center gap-1.5 min-w-0">
                  <span
                    className="dot-indicator shrink-0"
                    style={{ backgroundColor: color, opacity: isEmpty ? 0.3 : 1 }}
                    aria-hidden="true"
                  />
                  <span
                    className="text-[11px] truncate"
                    style={{ color: isEmpty ? 'var(--text-muted)' : 'var(--text-secondary)' }}
                  >
                    {cat.label}
                  </span>
                </span>
                <span
                  className="font-mono text-[12px] font-semibold tabular-nums shrink-0"
                  style={{ color: isEmpty ? 'var(--text-muted)' : 'var(--text-primary)' }}
                >
                  {count}
                </span>
              </div>
              <div
                className="relative h-[3px] rounded-full overflow-hidden"
                style={{ backgroundColor: 'var(--bg-hover)' }}
                role="progressbar"
                aria-valuenow={count}
                aria-valuemin={0}
                aria-valuemax={maxCount}
                aria-label={`${cat.label} ${count} 条`}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${ratio}%`,
                    backgroundColor: color,
                    opacity: isEmpty ? 0.2 : 0.85,
                    transition: 'width 480ms cubic-bezier(0.16, 1, 0.3, 1)',
                  }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
