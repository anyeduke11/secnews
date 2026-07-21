// HealthDashboard — 知识库健康度卡片
// Phase 5A: coverage <50% 改用 --color-error token (替换硬编码 var(--color-error))
import React, { useState, useEffect } from 'react';
import type { KnowledgeHealth } from '../types';

export function HealthDashboard() {
  const [health, setHealth] = useState<KnowledgeHealth | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  if (!health) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  const metrics = [
    { label: '总条目', value: health.total_items },
    { label: '已编译', value: health.compiled_count },
    { label: '孤立条目', value: health.orphan_items },
    { label: '过期概念', value: health.stale_concepts },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        {metrics.map(m => (
          <div key={m.label} className="text-center p-2 rounded-[var(--radius-sm)]"
               style={{ backgroundColor: 'var(--bg-hover)' }}>
            <div className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>{m.value}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{m.label}</div>
          </div>
        ))}
      </div>
      {health.gap_analysis && health.gap_analysis.length > 0 && (
        <div>
          <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>领域覆盖</p>
          {health.gap_analysis.map(g => (
            <div key={g.domain} className="flex items-center gap-2 text-[10px] mb-1">
              <span style={{ color: 'var(--text-primary)', minWidth: '60px' }}>{g.domain}</span>
              <div className="flex-1 rounded-full" style={{ backgroundColor: 'var(--bg-hover)', height: '4px' }}>
                <div className="rounded-full"
                     style={{ width: `${g.coverage * 100}%`, height: '4px', backgroundColor: 'var(--color-ai)' }} />
              </div>
              <span style={{ color: g.coverage >= 0.5 ? 'var(--text-muted)' : 'var(--color-error)' }}>
                {Math.round(g.coverage * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
