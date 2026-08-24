/**
 * AliveCard — 书签存活三态分布 (S1-3/S1-4)
 *
 * 展示 bookmark-import 条目的 alive/dead/unknown 分布, 支持手动触发批扫
 * (POST /api/kl/liveness/sweep), 完成后回调刷新观测台。
 */
import { useState } from 'react';

interface AliveCardProps {
  alive: { total: number; alive: number; dead: number; unknown: number };
  onSwept?: () => void;
}

const STATES = [
  { key: 'alive', label: '存活', color: 'var(--color-success)' },
  { key: 'dead', label: '失效', color: 'var(--color-error)' },
  { key: 'unknown', label: '未知', color: 'var(--color-warning)' },
] as const;

export function AliveCard({ alive, onSwept }: AliveCardProps) {
  const [sweeping, setSweeping] = useState(false);

  const runSweep = async () => {
    setSweeping(true);
    try {
      await fetch('/api/kl/liveness/sweep', { method: 'POST' });
      onSwept?.();
    } finally {
      setSweeping(false);
    }
  };

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
          书签存活检测
        </h3>
        <button
          onClick={runSweep}
          disabled={sweeping || alive.total === 0}
          className="text-[10px] font-mono px-2 py-0.5 rounded-[2px] disabled:opacity-40"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
        >
          {sweeping ? '批扫中...' : '立即批扫'}
        </button>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          共 <span className="font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>{alive.total}</span> 条书签
        </span>
        {STATES.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{s.label}</span>
            <span className="text-xs font-mono font-medium tabular-nums" style={{ color: 'var(--text-primary)' }}>
              {alive[s.key]}
            </span>
          </div>
        ))}
      </div>
      {alive.total > 0 && (
        <div className="mt-2 h-1.5 rounded-[2px] overflow-hidden flex" style={{ backgroundColor: 'var(--bg-secondary)' }}>
          {STATES.map(s => (
            <div
              key={s.key}
              className="h-full transition-all"
              style={{
                width: `${(alive[s.key] / Math.max(alive.total, 1)) * 100}%`,
                backgroundColor: s.color,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
