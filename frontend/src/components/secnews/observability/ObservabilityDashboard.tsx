/**
 * ObservabilityDashboard — v0.7 Batch ③ API 观测面板
 *
 * 三卡片网格:
 *  - 1h 概览 (total / errors / error_rate / p95)
 *  - Top 5 慢路径 (按 p95 排序)
 *  - 实时 events (recent 倒序, 5s 刷新)
 *
 * 数据源: GET /api/observability/{summary,recent,timeseries}
 * Batch ④ 落 alerts/thresholds 后, 顶部加告警横幅 + 阈值编辑折叠面板。
 */
import { useEffect, useState } from 'react';

interface SummaryResp {
  total: number;
  errors: number;
  error_rate_pct: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  max_latency_ms: number;
  top_slow_paths: Array<{
    path_template: string;
    total: number;
    p50_ms: number;
    p95_ms: number;
    max_ms: number;
  }>;
}

interface RecentEvent {
  trace_id: string;
  method: string;
  path_template: string;
  status: number;
  duration_ms: number;
  error: string | null;
  occurred_at: string;
}

const REFRESH_MS = 5_000;

export function ObservabilityDashboard() {
  const [summary, setSummary] = useState<SummaryResp | null>(null);
  const [recent, setRecent] = useState<RecentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let sse: EventSource | null = null;
    let timer: number | undefined;

    const refresh = async () => {
      try {
        const [sRes, rRes] = await Promise.all([
          fetch('/api/observability/summary'),
          fetch('/api/observability/recent?limit=20'),
        ]);
        if (cancelled) return;
        if (sRes.ok) setSummary(await sRes.json());
        if (rRes.ok) {
          const data = await rRes.json();
          setRecent(data.items ?? []);
        }
        setError(null);
      } catch (e) {
        if (!cancelled) setError(`观测数据获取失败: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    refresh();

    // D3 (Batch ⑧): SSE 接入 — 收到 "observability.update" / "observability.breach" 即刷新
    // polling 降级为兜底 (SSE 断开时仍能拿到最新数据)
    try {
      sse = new EventSource('/api/events');
      sse.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload?.type === 'observability.update' || payload?.type === 'observability.breach') {
            void refresh();
          }
        } catch {
          // 忽略解析错误
        }
      };
      sse.onerror = () => {
        // SSE 断开, polling 兜底 (浏览器会自动重连, 但这里额外 timer 防失效)
        if (!cancelled && timer === undefined) {
          timer = window.setInterval(refresh, REFRESH_MS);
        }
      };
    } catch {
      // EventSource 不可用 (老浏览器) → 仅 polling
      timer = window.setInterval(refresh, REFRESH_MS);
    }

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
      if (sse) sse.close();
    };
  }, []);

  if (loading) {
    return (
      <div className="p-4 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
        正在加载观测数据…
      </div>
    );
  }

  const errorRateColor =
    (summary?.error_rate_pct ?? 0) >= 15 ? 'var(--color-error)' :
    (summary?.error_rate_pct ?? 0) >= 5 ? 'var(--color-warning)' :
    'var(--color-success)';

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div
          className="px-3 py-2 rounded text-xs font-mono"
          style={{ backgroundColor: 'var(--color-error-soft, rgba(239,68,68,0.1))', color: 'var(--color-error)' }}
        >
          {error}
        </div>
      )}

      <div className="text-sm font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
        观测面板 — 实时 API 健康度
      </div>

      {/* 1h 概览 */}
      <section
        className="p-4 rounded"
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-light)' }}
      >
        <div className="text-xs font-mono mb-3" style={{ color: 'var(--text-muted)' }}>
          最近 1 小时
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="总请求" value={summary?.total ?? 0} />
          <Stat label="5xx 错误" value={summary?.errors ?? 0} />
          <Stat
            label="错误率"
            value={`${(summary?.error_rate_pct ?? 0).toFixed(1)}%`}
            color={errorRateColor}
          />
          <Stat label="p50 延迟" value={`${summary?.p50_latency_ms ?? 0} ms`} />
          <Stat label="p95 延迟" value={`${summary?.p95_latency_ms ?? 0} ms`} />
        </div>
      </section>

      {/* Top 5 慢路径 */}
      <section
        className="p-4 rounded"
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-light)' }}
      >
        <div className="text-xs font-mono mb-3" style={{ color: 'var(--text-muted)' }}>
          Top 5 慢路径 (按 p95)
        </div>
        {(summary?.top_slow_paths ?? []).length === 0 ? (
          <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            暂无数据
          </div>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th className="text-left py-1">路径</th>
                <th className="text-right py-1">total</th>
                <th className="text-right py-1">p50</th>
                <th className="text-right py-1">p95</th>
                <th className="text-right py-1">max</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.top_slow_paths ?? []).map((row) => (
                <tr key={row.path_template}>
                  <th
                    className="text-left py-1 font-normal truncate max-w-[280px]"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {row.path_template}
                  </th>
                  <th className="text-right py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                    {row.total}
                  </th>
                  <th className="text-right py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                    {row.p50_ms}ms
                  </th>
                  <th
                    className="text-right py-1 font-normal"
                    style={{ color: row.p95_ms >= 800 ? 'var(--color-warning)' : 'var(--text-primary)' }}
                  >
                    {row.p95_ms}ms
                  </th>
                  <th className="text-right py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                    {row.max_ms}ms
                  </th>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* 实时 events */}
      <section
        className="p-4 rounded"
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-light)' }}
      >
        <div className="text-xs font-mono mb-3" style={{ color: 'var(--text-muted)' }}>
          最近 20 条 (5s 自动刷新)
        </div>
        {recent.length === 0 ? (
          <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            暂无事件
          </div>
        ) : (
          <div className="overflow-auto max-h-80">
            <table className="w-full text-xs font-mono">
              <thead className="sticky top-0" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                <tr style={{ color: 'var(--text-muted)' }}>
                  <th className="text-left py-1">时间</th>
                  <th className="text-left py-1">方法</th>
                  <th className="text-left py-1">路径</th>
                  <th className="text-right py-1">状态</th>
                  <th className="text-right py-1">耗时</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((ev, i) => (
                  <tr key={`${ev.trace_id}-${i}`}>
                    <th className="text-left py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                      {new Date(ev.occurred_at).toLocaleTimeString()}
                    </th>
                    <th className="text-left py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                      {ev.method}
                    </th>
                    <th
                      className="text-left py-1 font-normal truncate max-w-[280px]"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {ev.path_template}
                    </th>
                    <th
                      className="text-right py-1 font-normal"
                      style={{
                        color: ev.status >= 500 ? 'var(--color-error)' :
                               ev.status >= 400 ? 'var(--color-warning)' :
                               'var(--text-secondary)',
                      }}
                    >
                      {ev.status}
                    </th>
                    <th className="text-right py-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                      {ev.duration_ms}ms
                    </th>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
      <div className="text-lg font-mono" style={{ color: color ?? 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}