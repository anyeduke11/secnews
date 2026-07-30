import React from 'react';
import { CATEGORIES, getCategoryColor, ConsistencyDrift } from '../types';

interface CategoryNavProps {
  active: string;
  onChange: (category: string) => void;
  counts: Record<string, number>;
  consistencyDrift?: ConsistencyDrift[];
}

export function CategoryNav({ active, onChange, counts, consistencyDrift = [] }: CategoryNavProps) {
  const driftMap: Record<string, ConsistencyDrift> = {};
  for (const d of consistencyDrift) driftMap[d.category] = d;

  return (
    <nav className="flex flex-wrap gap-1.5 mb-4">
      {CATEGORIES.map((cat) => {
        const isActive = active === cat.id;
        const color = getCategoryColor(cat.id);
        const count = cat.id === 'all'
          ? Object.values(counts).reduce((a, b) => a + b, 0)
          : (counts[cat.id] || 0);
        const drift = driftMap[cat.id];

        return (
          <button
            key={cat.id}
            onClick={() => onChange(cat.id)}
            className={`cat-pill focus-ring ${isActive ? 'active' : ''}`}
            style={{
              color: isActive ? color : undefined,
              borderColor: isActive ? `${color}50` : undefined,
            }}
          >
            <span className="flex items-center gap-1.5">
              <span
                className="dot-indicator"
                style={{ backgroundColor: color, width: 6, height: 6 }}
              />
              {cat.label}
              {count > 0 && (
                <span
                  className="text-[10px] font-mono font-medium px-1.5 py-px rounded-full tabular-nums"
                  style={{
                    backgroundColor: isActive ? `${color}18` : 'var(--bg-hover)',
                    color: isActive ? color : 'var(--text-muted)',
                  }}
                >
                  {count}
                </span>
              )}
              {drift && (
                <span
                  className="status-icon error"
                  title={`数据不一致：缓存 ${drift.cached} 条，DB ${drift.db} 条${drift.note ? `（${drift.note}）` : ''}`}
                >
                  !
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
}