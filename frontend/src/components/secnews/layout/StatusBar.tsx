/**
 * StatusBar — SecNews 底部状态栏 (原 workbench/StatusBar 并入 SecNews 壳)
 *
 * 实时显示: dsh 连接状态 + 管线健康度 + 今日 token 用量 (30s 轮询)。
 * 数据源: GET /api/dsh/health · GET /api/kl/pipeline/stats
 * dsh gate 关闭时 /api/dsh/health 404 → 指示灯显示 unknown, 属如实降级。
 */
import { useEffect, useState } from 'react';

interface DshHealth {
  status?: string;
  fallback?: string;
  endpoint?: string;
}

interface PipelineStats {
  queue?: { pending?: number; running?: number; error: number };
  ledger?: Array<{ model: string; calls: number; total_tokens: number }>;
}

// v0.7 Batch ③: 观测面板 1h 摘要, 状态栏追加节
interface ObsSummary {
  total: number;
  error_rate_pct: number;
  p95_latency_ms: number;
}

// v0.7 Batch ④: 活跃告警 (status_bar 通道)
interface ActiveAlertsMini {
  critical_count: number;
  warn_count: number;
}

export function StatusBar() {
  const [dsh, setDsh] = useState<DshHealth | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [obs, setObs] = useState<ObsSummary | null>(null);
  const [alerts, setAlerts] = useState<ActiveAlertsMini | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const [dRes, pRes, oRes, aRes] = await Promise.all([
          fetch('/api/dsh/health'),
          fetch('/api/kl/pipeline/stats'),
          fetch('/api/observability/summary'),
          fetch('/api/observability/alerts/active'),
        ]);
        if (cancelled) return;
        if (dRes.ok) setDsh(await dRes.json());
        if (pRes.ok) {
          const data = await pRes.json();
          setPipeline({
            queue: data.queue,
            ledger: data.ledger,
          });
        }
        if (oRes.ok) setObs(await oRes.json());
        if (aRes.ok) {
          const a = await aRes.json();
          setAlerts({ critical_count: a.critical_count ?? 0, warn_count: a.warn_count ?? 0 });
        }
      } catch { /* 状态栏轮询失败保持上次值, 指示灯显示 unknown */ }
    };
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const dshColor =
    dsh?.status === 'connected' ? 'var(--color-success)' :
    dsh?.status === 'disconnected' ? 'var(--color-warning)' :
    'var(--color-error)';

  const queueError = pipeline?.queue?.error ?? 0;
  const queueColor =
    queueError === 0 ? 'var(--color-success)' :
    queueError < 5 ? 'var(--color-warning)' :
    'var(--color-error)';

  const totalTokens = (pipeline?.ledger ?? []).reduce(
    (sum, row) => sum + (row.total_tokens ?? 0), 0,
  );

  // v0.7 Batch ③: obs 节染色 — 错误率 ≥ 5% 黄, ≥ 15% 红 (与 Dashboard 一致)
  const obsErrorRate = obs?.error_rate_pct ?? 0;
  const obsErrorColor =
    obsErrorRate >= 15 ? 'var(--color-error)' :
    obsErrorRate >= 5 ? 'var(--color-warning)' :
    'var(--text-secondary)';

  return (
    <div
      className="flex items-center gap-3 px-4 py-1.5 text-[10px] font-mono"
      style={{ backgroundColor: 'var(--bg-secondary)', borderTop: '1px solid var(--border-light)' }}
    >
      {/* dsh 指示灯 */}
      <div className="flex items-center gap-1.5">
        <span
          className="w-1.5 h-1.5 rounded-full inline-block"
          style={{ backgroundColor: dshColor }}
        />
        <span style={{ color: 'var(--text-secondary)' }}>
          dsh: {dsh?.status ?? 'unknown'}
          {dsh?.fallback && dsh.fallback !== 'none' && (
            <span style={{ color: 'var(--text-muted)' }}> · fallback {dsh.fallback}</span>
          )}
        </span>
      </div>

      <span style={{ color: 'var(--text-muted)' }}>·</span>

      {/* 管线队列 */}
      <div className="flex items-center gap-1.5">
        <span style={{ color: 'var(--text-secondary)' }}>管线队列:</span>
        <span style={{ color: 'var(--text-primary)' }}>
          {pipeline?.queue?.pending ?? '–'}/{pipeline?.queue?.running ?? '–'}
        </span>
        {queueError > 0 && (
          <span style={{ color: queueColor }}>
            [err {queueError}]
          </span>
        )}
      </div>

      <span style={{ color: 'var(--text-muted)' }}>·</span>

      {/* token 日用量 */}
      <div className="flex items-center gap-1.5">
        <span style={{ color: 'var(--text-secondary)' }}>token 日用量:</span>
        <span style={{ color: 'var(--text-primary)' }}>
          {totalTokens.toLocaleString()}
        </span>
      </div>

      <span style={{ color: 'var(--text-muted)' }}>·</span>

      {/* v0.7 Batch ③: obs 1h 摘要 */}
      <div className="flex items-center gap-1.5" data-testid="statusbar-obs">
        <span style={{ color: 'var(--text-secondary)' }}>obs 1h:</span>
        <span style={{ color: 'var(--text-primary)' }}>
          {obs?.total ?? '–'} req
        </span>
        <span style={{ color: 'var(--text-muted)' }}>·</span>
        <span style={{ color: obsErrorColor }}>
          {obs ? `${obsErrorRate.toFixed(1)}% err` : '–'}
        </span>
        <span style={{ color: 'var(--text-muted)' }}>·</span>
        <span style={{ color: 'var(--text-primary)' }}>
          {obs?.p95_latency_ms ?? '–'}ms p95
        </span>
      </div>

      {/* v0.7 Batch ④: 告警角标 — critical 红 / warn 黄, 0 时不显示 */}
      {(alerts?.critical_count ?? 0) > 0 && (
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-mono"
          style={{ backgroundColor: 'var(--color-error)', color: '#fff' }}
          data-testid="statusbar-alert-critical"
        >
          🚨 {alerts?.critical_count} critical
        </span>
      )}
      {(alerts?.warn_count ?? 0) > 0 && (
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-mono"
          style={{ backgroundColor: 'var(--color-warning)', color: '#1f2937' }}
          data-testid="statusbar-alert-warn"
        >
          ⚠ {alerts?.warn_count} warn
        </span>
      )}
    </div>
  );
}
