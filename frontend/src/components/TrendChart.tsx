import React, { useState, useEffect, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell,
} from 'recharts';
import { TrendPoint, TrendResponse } from '../types';

const CATEGORY_KEYS = ['ai', 'security', 'finance', 'startup', 'bid', 'github'] as const;
type CatKey = typeof CATEGORY_KEYS[number];

const CATEGORY_CONFIG: Record<CatKey, { color: string; label: string }> = {
  ai: { color: '#00bcd4', label: '科技 / AI' },
  security: { color: '#e85d5d', label: '网络安全' },
  finance: { color: '#f0c929', label: '金融' },
  startup: { color: '#7c6aff', label: '创业' },
  bid: { color: '#e8891a', label: '招标' },
  github: { color: '#8b5cf6', label: 'GitHub' },
};

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function formatHourLabel(isoString: string): string {
  const d = new Date(isoString);
  return `${pad2(d.getHours())}:00`;
}

export function TrendChart() {
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  useEffect(() => {
    fetch('/api/trends')
      .then(r => r.json())
      .then((d: TrendResponse) => {
        setData(d.trends || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const sampled = useMemo(
    () => data.filter((_, i) => i % 3 === 0 || i === data.length - 1),
    [data]
  );

  // 总计 (24h 内)
  const totalsByCat = useMemo(() => {
    const out: Record<CatKey, number> = { ai: 0, security: 0, finance: 0, startup: 0, bid: 0, github: 0 };
    for (const pt of data) for (const k of CATEGORY_KEYS) out[k] += pt[k] || 0;
    return out;
  }, [data]);

  if (loading) {
    return (
      <section className="card-base p-4 mb-4" aria-label="趋势图">
        <div className="flex items-baseline justify-between mb-4">
          <div className="h-3 w-20 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
          <div className="h-3 w-16 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
        </div>
        <div className="h-44 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
      </section>
    );
  }

  if (data.length === 0) return null;

  // ─── Custom Tooltip ───
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;
    const total = payload.reduce((s: number, p: any) => s + (p.value || 0), 0);
    return (
      <div
        className="px-3 py-2.5 font-mono shadow-lg"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-sm)',
          minWidth: 160,
        }}
      >
        <div
          className="flex items-center justify-between gap-3 mb-1.5 pb-1.5"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <span className="text-[10px] uppercase tracking-[0.08em]" style={{ color: 'var(--text-muted)' }}>
            {label}
          </span>
          <span className="text-[10px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            Σ {total}
          </span>
        </div>
        {payload
          .filter((p: any) => p.value > 0)
          .sort((a: any, b: any) => b.value - a.value)
          .map((entry: any) => {
            const cfg = CATEGORY_CONFIG[entry.dataKey as CatKey];
            return (
              <div key={entry.dataKey} className="flex items-center gap-2 text-[11px] py-px">
                <span
                  className="dot-indicator"
                  style={{ backgroundColor: cfg?.color || entry.color }}
                />
                <span className="flex-1 truncate" style={{ color: 'var(--text-secondary)' }}>
                  {cfg?.label || entry.dataKey}
                </span>
                <span className="font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>
                  {entry.value}
                </span>
              </div>
            );
          })}
      </div>
    );
  };

  return (
    <section className="card-base p-4 mb-4" aria-label="24小时热度趋势">
      <header className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h2 className="section-overline">24h 热度趋势</h2>
        <div className="flex items-center gap-3 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          <span>每小时聚合</span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">{data.length} 个时间点</span>
        </div>
      </header>

      {/* Inline legend (Recharts Legend looks dated) */}
      <ul className="flex items-center flex-wrap gap-x-3 gap-y-1.5 mb-3" aria-label="分类图例">
        {CATEGORY_KEYS.map((key) => {
          const cfg = CATEGORY_CONFIG[key];
          const total = totalsByCat[key];
          return (
            <li
              key={key}
              className="flex items-center gap-1.5 text-[11px]"
              title={`${cfg.label}: 24h 共 ${total} 条`}
            >
              <span
                className="dot-indicator"
                style={{ backgroundColor: cfg.color, opacity: total > 0 ? 1 : 0.3 }}
                aria-hidden="true"
              />
              <span style={{ color: 'var(--text-secondary)' }}>{cfg.label}</span>
              <span
                className="font-mono tabular-nums text-[10px] px-1.5 py-0.5 rounded-full"
                style={{
                  color: total > 0 ? cfg.color : 'var(--text-muted)',
                  backgroundColor: total > 0 ? `${cfg.color}1A` : 'var(--bg-hover)',
                  fontWeight: 600,
                }}
              >
                {total}
              </span>
            </li>
          );
        })}
      </ul>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={sampled}
            barGap={1}
            barCategoryGap="22%"
            margin={{ top: 4, right: 0, left: -20, bottom: 0 }}
            onMouseMove={(state: any) => {
              if (state?.activeTooltipIndex !== undefined) setHoverIdx(state.activeTooltipIndex);
            }}
            onMouseLeave={() => setHoverIdx(null)}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={{ stroke: 'var(--border-color)' }}
              tickLine={false}
              interval="preserveStartEnd"
              tickFormatter={formatHourLabel}
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={32}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: 'var(--bg-hover)', opacity: 0.5 }}
            />
            {CATEGORY_KEYS.map((key) => (
              <Bar
                key={key}
                dataKey={key}
                stackId="a"
                fill={CATEGORY_CONFIG[key].color}
                maxBarSize={14}
                radius={0}
              >
                {sampled.map((_, idx) => (
                  <Cell
                    key={idx}
                    fillOpacity={hoverIdx === null || hoverIdx === idx ? 0.95 : 0.35}
                  />
                ))}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
