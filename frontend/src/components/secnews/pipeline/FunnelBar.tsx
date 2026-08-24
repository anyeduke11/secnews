/**
 * FunnelBar — 五阶段横条图
 *
 * 展示 KL 管线各阶段条目数量的水平条形图。
 */
interface FunnelBarProps {
  funnel: Array<{ stage: string; count: number }>;
}

const STAGE_COLORS: Record<string, string> = {
  'kl:raw': 'var(--color-info)',
  'kl:refine': 'var(--color-warning)',
  'kl:link': 'var(--color-ai)',
  'kl:structure': 'var(--layer-judge)',
  'kl:publish': 'var(--color-success)',
};

export function FunnelBar({ funnel }: FunnelBarProps) {
  const max = Math.max(...funnel.map(f => f.count), 1);

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
        管线漏斗
      </h3>
      <div className="flex flex-col gap-1.5">
        {funnel.map(f => (
          <div key={f.stage} className="flex items-center gap-2">
            <span className="text-[10px] font-mono w-24 shrink-0" style={{ color: 'var(--text-muted)' }}>
              {f.stage.replace('kl:', '')}
            </span>
            <div className="flex-1 h-4 rounded-[2px] overflow-hidden" style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <div
                className="h-full rounded-[2px] transition-all"
                style={{
                  width: `${(f.count / max) * 100}%`,
                  backgroundColor: STAGE_COLORS[f.stage] ?? 'var(--accent)',
                  minWidth: f.count > 0 ? '4px' : '0',
                }}
              />
            </div>
            <span className="text-[10px] font-mono w-12 text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
              {f.count.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
