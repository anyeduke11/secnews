/**
 * ActiveAlertsBanner — v0.7 Batch ④ 活跃告警横幅.
 *
 * 顶部红/黄条展示当前活跃 (acked=0) 的告警, 每条带 ack 按钮.
 * 数据源: GET /api/observability/alerts/active + POST /alerts/{id}/ack.
 * 30s 自动刷新 (与 StatusBar 同频).
 */
import { useEffect, useState } from 'react';

interface AlertItem {
  id: number;
  level: 'warn' | 'critical';
  metric: string;
  value: number;
  threshold: number;
  window_minutes: number;
  detail: string | null;
  fired_at: string;
  cooldown_until: string;
}

interface ActiveAlertsResp {
  items: AlertItem[];
  critical_count: number;
  warn_count: number;
  as_of: string;
}

const REFRESH_MS = 30_000;

const LEVEL_BG: Record<string, string> = {
  critical: 'var(--color-error-soft, rgba(239,68,68,0.15))',
  warn: 'var(--color-warning-soft, rgba(245,158,11,0.15))',
};

const LEVEL_FG: Record<string, string> = {
  critical: 'var(--color-error)',
  warn: 'var(--color-warning)',
};

export function ActiveAlertsBanner() {
  const [data, setData] = useState<ActiveAlertsResp | null>(null);
  const [ackingId, setAckingId] = useState<number | null>(null);
  const [ackError, setAckError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const r = await fetch('/api/observability/alerts/active');
      if (r.ok) setData(await r.json());
    } catch { /* 静默降级 */ }
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  const handleAck = async (id: number) => {
    setAckingId(id);
    setAckError(null);
    try {
      const r = await fetch(`/api/observability/alerts/${id}/ack`, { method: 'POST' });
      if (!r.ok) throw new Error(`ack failed: ${r.status}`);
      await refresh();
    } catch (e) {
      setAckError(e instanceof Error ? e.message : String(e));
    } finally {
      setAckingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-1" data-testid="active-alerts-banner">
      {ackError && (
        <div
          className="px-3 py-1 rounded text-xs font-mono"
          style={{ backgroundColor: LEVEL_BG.critical, color: LEVEL_FG.critical }}
        >
          {ackError}
        </div>
      )}
      {items.map((a) => (
        <div
          key={a.id}
          className="flex items-center justify-between gap-2 px-3 py-2 rounded text-xs font-mono"
          style={{ backgroundColor: LEVEL_BG[a.level], color: LEVEL_FG[a.level] }}
        >
          <span className="flex items-center gap-2 truncate">
            <span className="font-semibold uppercase">[{a.level}]</span>
            <span style={{ color: 'var(--text-primary)' }}>{a.metric}</span>
            <span style={{ color: 'var(--text-secondary)' }}>
              {a.value.toFixed(1)} ≥ {a.threshold} ({a.window_minutes}m window)
            </span>
          </span>
          <button
            className="px-2 py-0.5 rounded text-xs font-mono"
            style={{
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-light)',
            }}
            onClick={() => handleAck(a.id)}
            disabled={ackingId === a.id}
            data-testid={`ack-button-${a.id}`}
          >
            {ackingId === a.id ? 'acking…' : 'ack'}
          </button>
        </div>
      ))}
    </div>
  );
}