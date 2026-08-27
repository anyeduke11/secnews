/**
 * PipelineView — 工作台管线视图 (Phase 4 v0.6.1)
 *
 * 展示 KL 管线五阶段漏斗 + 队列/错误 + token 台账 + 书签存活三态。
 * 数据源: GET /api/kl/pipeline/stats
 */
import { useEffect, useState } from 'react';

interface PipelineStats {
  funnel: Array<{ stage: string; count: number }>;
  queue: { pending: number; running: number; error: number };
  errors: Array<{
    id: number;
    item_id: string;
    stage: string;
    attempts: number;
    last_error: string;
    updated_at: string;
  }>;
  alive: { total: number; alive: number; dead: number; unknown: number };
  ledger: Array<{ model: string; calls: number; total_tokens: number }>;
}

export function PipelineView() {
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const r = await fetch('/api/kl/pipeline/stats');
        if (!r.ok) return;
        if (!cancelled) setStats(await r.json());
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    };
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  if (loading && !stats) {
    return <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>;
  }

  return (
    <div className="space-y-3 max-w-5xl">
      {/* 漏斗 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          漏斗 · 5 阶段
        </h3>
        <div className="flex flex-wrap items-end gap-2">
          {(stats?.funnel ?? []).map((f, i) => {
            const maxCount = Math.max(...(stats?.funnel ?? []).map(x => x.count), 1);
            const width = `${Math.max(8, (f.count / maxCount) * 100)}%`;
            return (
              <div key={f.stage} className="flex-1 min-w-[80px]">
                <div className="text-[10px] font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                  {f.stage}
                </div>
                <div className="h-2 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                  <div className="h-2 rounded transition-all" style={{
                    width,
                    backgroundColor: i === (stats?.funnel?.length ?? 0) - 1 ? 'var(--color-success)' : 'var(--accent)',
                  }} />
                </div>
                <div className="text-base font-mono font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {f.count}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 队列 + 错误 */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
          <div className="text-base font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{stats?.queue?.pending ?? 0}</div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>pending</div>
        </div>
        <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
          <div className="text-base font-mono font-bold" style={{ color: 'var(--accent)' }}>{stats?.queue?.running ?? 0}</div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>running</div>
        </div>
        <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
          <div className="text-base font-mono font-bold" style={{ color: (stats?.queue?.error ?? 0) > 0 ? 'var(--color-error)' : 'var(--text-primary)' }}>
            {stats?.queue?.error ?? 0}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>error</div>
        </div>
      </section>

      {/* 书签存活 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>书签存活三态</h3>
        <div className="grid grid-cols-4 gap-2 text-center">
          <div>
            <div className="text-base font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{stats?.alive?.total ?? 0}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>总</div>
          </div>
          <div>
            <div className="text-base font-mono font-bold" style={{ color: 'var(--color-success)' }}>{stats?.alive?.alive ?? 0}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>alive</div>
          </div>
          <div>
            <div className="text-base font-mono font-bold" style={{ color: 'var(--color-warning)' }}>{stats?.alive?.unknown ?? 0}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>unknown</div>
          </div>
          <div>
            <div className="text-base font-mono font-bold" style={{ color: 'var(--color-error)' }}>{stats?.alive?.dead ?? 0}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>dead</div>
          </div>
        </div>
      </section>

      {/* 错误队列 */}
      {stats && stats.errors.length > 0 && (
        <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
          <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--color-error)' }}>
            错误队列 · {stats.errors.length}
          </h3>
          <ul className="text-[10px] font-mono space-y-1">
            {stats.errors.slice(0, 5).map(e => (
              <li key={e.id} className="flex items-start gap-2">
                <span style={{ color: 'var(--text-muted)' }}>#{e.id}</span>
                <span style={{ color: 'var(--text-secondary)' }} className="truncate flex-1">
                  {e.item_id} [{e.stage}] ×{e.attempts}
                </span>
                <span style={{ color: 'var(--color-error)' }} className="truncate max-w-[60%]">{e.last_error}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Token 台账 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>token 台账 (本日)</h3>
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="text-left" style={{ color: 'var(--text-muted)' }}>
              <th className="pb-1">model</th>
              <th className="pb-1 text-right">calls</th>
              <th className="pb-1 text-right">tokens</th>
            </tr>
          </thead>
          <tbody>
            {(stats?.ledger ?? []).map((row, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--border-light)' }}>
                <td className="py-1" style={{ color: 'var(--text-secondary)' }}>{row.model}</td>
                <td className="py-1 text-right" style={{ color: 'var(--text-primary)' }}>{row.calls}</td>
                <td className="py-1 text-right" style={{ color: 'var(--accent)' }}>{row.total_tokens.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(stats?.ledger ?? []).length === 0 && (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无用量数据</p>
        )}
      </section>
    </div>
  );
}