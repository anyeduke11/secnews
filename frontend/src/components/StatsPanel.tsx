import { CATEGORIES, getCategoryColorVar } from '../types';

interface StatsPanelProps {
  categoryCounts: Record<string, number>;
  total: number;
}

export function StatsPanel({ categoryCounts, total }: StatsPanelProps) {
  const filteredCats = CATEGORIES.filter(c => c.id !== 'all');

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between pb-2 mb-2" style={{ borderBottom: '1px solid var(--border-color)' }}>
        <h3 className="text-[11px] font-bold tracking-[0.1em] uppercase" style={{ color: 'var(--text-primary)' }}>
          数据统计
        </h3>
        <span className="text-[11px] font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
          共 <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{total}</span> 条
        </span>
      </div>

      <div className="flex flex-col gap-2.5">
        {filteredCats.map((cat) => {
          const count = categoryCounts[cat.id] || 0;
          const color = getCategoryColorVar(cat.id);
          const maxCount = Math.max(...Object.values(categoryCounts), 1);
          const barWidth = maxCount > 0 ? (count / maxCount) * 100 : 0;

          return (
            <div key={cat.id}>
              <div className="flex items-center justify-between mb-1">
                <span className="flex items-center gap-1.5 text-[11px]">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <span style={{ color: 'var(--text-secondary)' }} className="truncate">{cat.label}</span>
                </span>
                <span className="text-[11px] font-mono font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
              <div className="w-full h-[3px] overflow-hidden rounded-full" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div
                  className="h-full rounded-full transition-all duration-500 ease-out"
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
