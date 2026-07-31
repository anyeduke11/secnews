import React from 'react';
import { CATEGORIES, getCategoryColorVar, ConsistencyDrift } from '../types';

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
        const color = getCategoryColorVar(cat.id);
        const count = cat.id === 'all'
          ? Object.values(counts).reduce((a, b) => a + b, 0)
          : (counts[cat.id] || 0);
        const drift = driftMap[cat.id];

        return (
          <button
            key={cat.id}
            onClick={() => onChange(cat.id)}
            className={`cat-pill focus-ring ${isActive ? 'active' : ''}`}
          >
            <span className="flex items-center gap-1.5">
              {/* v1.9 Editorial: 激活反色 (cat-pill.active 墨底纸字), dot 用色变量随主题切换 */}
              <span
                className="dot-indicator"
                style={{ backgroundColor: isActive ? 'var(--bg-primary)' : color, width: 6, height: 6 }}
              />
              {cat.label}
              {count > 0 && (
                <span
                  className="text-[10px] font-mono font-medium tabular-nums"
                  style={{ color: isActive ? 'inherit' : 'var(--text-muted)', opacity: isActive ? 0.75 : 1 }}
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
