/**
 * SettingsView — 工作台设置视图 (Phase 4 v0.6.1)
 *
 * 模型档位 + dsh 连接 + 采集源 + token 预算统一面板。
 * 数据源: GET /api/llm/status · GET /api/dsh/health · GET /api/sources/health
 */
import { useEffect, useState } from 'react';

interface LLMStatus {
  enabled?: boolean;
  default_provider?: string;
  providers?: Record<string, { status?: string; model?: string; tier?: string }>;
}

interface DshHealth {
  status?: string;
  fallback?: string;
  endpoint?: string;
}

interface SourceHealth {
  category: string;
  source_name: string;
  status: string;
  total_items: number;
}

export function SettingsView() {
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const [dsh, setDsh] = useState<DshHealth | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [budgetPct] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/api/llm/status').then(r => r.ok ? r.json() : null),
      fetch('/api/dsh/health').then(r => r.ok ? r.json() : null),
      fetch('/api/sources/health').then(r => r.ok ? r.json() : { sources: [] }),
    ]).then(([l, d, s]) => {
      if (cancelled) return;
      setLlm(l);
      setDsh(d);
      setSources(s.sources || []);
      setLoading(false);
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const dshColor =
    dsh?.status === 'connected' ? 'var(--color-success)' :
    dsh?.status === 'disconnected' ? 'var(--color-warning)' :
    'var(--color-error)';

  return (
    <div className="space-y-3 max-w-4xl">
      {/* LLM 模型档位 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>模型档位</h3>
        {loading && <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>}
        {llm && (
          <div className="text-[10px] font-mono space-y-1">
            <div className="flex justify-between">
              <span style={{ color: 'var(--text-secondary)' }}>总开关</span>
              <span style={{ color: llm.enabled ? 'var(--color-success)' : 'var(--color-error)' }}>
                {llm.enabled ? 'ON' : 'OFF'}
              </span>
            </div>
            {llm.default_provider && (
              <div className="flex justify-between">
                <span style={{ color: 'var(--text-secondary)' }}>默认 provider</span>
                <span style={{ color: 'var(--accent)' }}>{llm.default_provider}</span>
              </div>
            )}
            {llm.providers && Object.entries(llm.providers).map(([name, p]) => (
              <div key={name} className="flex justify-between">
                <span style={{ color: 'var(--text-muted)' }}>{name}</span>
                <span style={{
                  color: p.status === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
                }}>
                  {p.model ?? name} [{p.status ?? '?'}]
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* dsh 连接 */}
      <section className="p-3 rounded-[var(--radius-sm])" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>dsh 连接</h3>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: dshColor }} />
          <span style={{ color: 'var(--text-primary)' }}>{dsh?.status ?? 'unknown'}</span>
          {dsh?.fallback && dsh.fallback !== 'none' && (
            <span style={{ color: 'var(--text-muted)' }}>fallback: {dsh.fallback}</span>
          )}
        </div>
        {dsh?.endpoint && (
          <p className="text-[10px] font-mono mt-1" style={{ color: 'var(--text-muted)' }}>{dsh.endpoint}</p>
        )}
      </section>

      {/* 采集源 */}
      <section className="p-3 rounded-[var(--radius-sm])" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>采集源 · {sources.length}</h3>
        {sources.length === 0 ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无源</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1">
            {sources.slice(0, 18).map(s => (
              <div key={`${s.category}-${s.source_name}`} className="text-[10px] font-mono flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full inline-block" style={{
                  backgroundColor: s.status === 'active' ? 'var(--color-success)' :
                    s.status === 'stale' ? 'var(--color-warning)' : 'var(--color-error)',
                }} />
                <span style={{ color: 'var(--text-secondary)' }} className="truncate">{s.source_name}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* token 预算 */}
      <section className="p-3 rounded-[var(--radius-sm])" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>token 预算</h3>
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {budgetPct !== null ? `本月已用 ${budgetPct}%` : '暂无预算配置（v0.6.1 留白, Phase 5 实装）'}
        </p>
      </section>
    </div>
  );
}