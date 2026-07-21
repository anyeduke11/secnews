import React from 'react';
import { CATEGORIES, getCategoryColor, ConsistencyDrift } from '../types';

interface CategoryNavProps {
  active: string;
  onChange: (category: string) => void;
  counts: Record<string, number>;
  consistencyDrift?: ConsistencyDrift[];
}

export function CategoryNav({ active, onChange, counts, consistencyDrift = [] }: CategoryNavProps) {
  // Build a map for O(1) lookup
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
            className="focus-ring"
            style={{
              padding: '6px 14px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: isActive ? 600 : 500,
              backgroundColor: isActive ? `${color}14` : 'transparent',
              border: `1px solid ${isActive ? `${color}50` : 'var(--border-color)'}`,
              color: isActive ? color : 'var(--text-secondary)',
              transition: 'all 0.15s ease',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'transparent';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }
            }}
          >
            <span className="flex items-center gap-1.5">
              <span
                className="dot-indicator"
                style={{ backgroundColor: color }}
              />
              {cat.label}
              {count > 0 && (
                <span
                  className="text-[10px] px-1.5 py-px rounded-full"
                  style={{
                    backgroundColor: isActive ? `${color}20` : 'var(--bg-hover)',
                    color: isActive ? color : 'var(--text-muted)',
                  }}
                >
                  {count}
                </span>
              )}
              {/* Phase 6: 一致性警告角标 */}
              {drift && (
                <span
                  className="text-[10px] px-1 py-px rounded-full"
                  title={`数据不一致：缓存显示 ${drift.cached} 条，DB 实际 ${drift.db} 条${drift.note ? `（${drift.note}）` : ''}`}
                  style={{
                    backgroundColor: 'color-mix(in srgb, var(--color-error) 15%, transparent)',
                    color: 'var(--color-error)',
                    border: '1px solid color-mix(in srgb, var(--color-error) 30%, transparent)',
                    marginLeft: 2,
                  }}
                >
                  ⚠️
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
