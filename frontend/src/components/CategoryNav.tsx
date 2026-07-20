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

  const allTotal = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <nav
      className="category-nav flex items-center gap-1 mb-3 -mx-1 px-1 overflow-x-auto"
      aria-label="分类筛选"
    >
      {CATEGORIES.map((cat) => {
        const isActive = active === cat.id;
        const color = getCategoryColor(cat.id);
        const count = cat.id === 'all' ? allTotal : (counts[cat.id] || 0);
        const drift = driftMap[cat.id];
        const isAll = cat.id === 'all';

        return (
          <button
            key={cat.id}
            onClick={() => onChange(cat.id)}
            className="cat-chip focus-ring"
            aria-pressed={isActive}
            style={
              isActive
                ? {
                    color: color,
                    backgroundColor: 'var(--bg-hover)',
                    borderColor: color,
                    boxShadow: `inset 0 0 0 1px ${color}40`,
                  }
                : {
                    color: 'var(--text-secondary)',
                    borderColor: 'var(--border-color)',
                  }
            }
          >
            <span
              className="cat-chip-stripe"
              style={{ backgroundColor: isActive ? color : 'transparent' }}
              aria-hidden="true"
            />
            <span
              className="cat-chip-dot"
              style={{ backgroundColor: color, opacity: isAll ? 0.7 : 1 }}
              aria-hidden="true"
            />
            <span className="cat-chip-label">{cat.label}</span>
            <span
              className="cat-chip-count"
              style={
                isActive
                  ? { color: color, backgroundColor: `${color}1F` }
                  : { color: 'var(--text-muted)', backgroundColor: 'var(--bg-card)' }
              }
            >
              {count}
            </span>
            {drift && (
              <span
                className="cat-chip-drift"
                title={`缓存 ${drift.cached} ≠ DB ${drift.db}${drift.note ? ` (${drift.note})` : ''}`}
                aria-label="数据不一致"
              >
                !
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
