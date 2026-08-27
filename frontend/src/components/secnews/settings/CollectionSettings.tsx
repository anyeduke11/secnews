/**
 * CollectionSettings — 采集源管理 (S3-4)
 *
 * 展示 crawler_sources 状态汇总 + 源列表 + 启用/禁用切换。
 */
import { useState, useEffect, useCallback } from 'react';

interface SourceRow {
  id: string;
  name: string;
  category: string;
  status: string;
  enabled: boolean;
}

interface StatsSummary {
  total?: number; active?: number; grace?: number;
  stale?: number; dead?: number; unknown?: number; disabled?: number;
}

export function CollectionSettings() {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, hRes] = await Promise.all([
        fetch('/api/sources/stats'),
        fetch('/api/sources/health/v2'),
      ]);
      if (sRes.ok) setStats(await sRes.json());
      if (hRes.ok) {
        const d = await hRes.json();
        setSources((d?.sources ?? []).slice(0, 30));
      }
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-3">
      {stats && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5">
          {([
            ['total', '总数', ''], ['active', '活跃', 'var(--color-success)'],
            ['grace', '观察', ''], ['stale', '滞后', 'var(--color-warning)'],
            ['dead', '失效', 'var(--color-error)'], ['unknown', '待定', ''],
          ] as const).map(([key, label, color]) => (
            <div key={key} className="p-2 rounded-[var(--radius-sm)] text-center"
              style={{ border: '1px solid var(--border-color)' }}>
              <div className="text-lg font-mono font-bold"
                style={{ color: color || 'var(--text-primary)' }}>
                {(stats[key] ?? 0).toLocaleString()}
              </div>
              <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
            </div>
          ))}
        </div>
      )}
      <div className="rounded-[var(--radius-sm)] overflow-hidden" style={{ border: '1px solid var(--border-color)' }}>
        <div className="px-3 py-1.5 text-[10px] font-mono font-medium"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
          采集源列表 ({sources.length})
        </div>
        {loading && (
          <div className="px-3 py-4 text-xs text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
        )}
        <div className="max-h-[300px] overflow-y-auto">
          {sources.map(s => (
            <div key={s.id} className="flex items-center gap-2 px-3 py-1.5"
              style={{ borderBottom: '1px solid var(--border-color)' }}>
              <span className="text-[10px] font-mono flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                {s.name}
              </span>
              <span className="text-[9px] font-mono px-1 rounded"
                style={{
                  backgroundColor: s.status === 'active' ? 'color-mix(in srgb, var(--color-success) 12%, transparent)' : 'var(--bg-hover)',
                  color: s.status === 'active' ? 'var(--color-success)' : 'var(--text-muted)',
                }}>
                {s.status}
              </span>
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {s.enabled ? 'ON' : 'OFF'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
