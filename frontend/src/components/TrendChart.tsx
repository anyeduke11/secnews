import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend
} from 'recharts';
import { TrendPoint, TrendResponse } from '../types';

const CATEGORY_CONFIG: Record<string, { color: string; label: string }> = {
  ai: { color: '#00bcd4', label: '科技/AI' },
  security: { color: '#e85d5d', label: '安全' },
  finance: { color: '#f0c929', label: '金融' },
  startup: { color: '#7c6aff', label: '创业' },
  bid: { color: '#e8891a', label: '招标' },
  github: { color: '#8b5cf6', label: 'GitHub 项目' },
};

export function TrendChart() {
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/trends')
      .then(r => r.json())
      .then((d: TrendResponse) => {
        setData(d.trends || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="card-base p-4 mb-5">
        <div className="h-3.5 w-28 rounded mb-4" style={{ backgroundColor: 'var(--bg-hover)' }} />
        <div className="h-36 rounded" style={{ backgroundColor: 'var(--bg-hover)' }} />
      </div>
    );
  }

  if (data.length === 0) return null;

  const sampled = data.filter((_, i) => i % 3 === 0 || i === data.length - 1);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div
          className="p-3 text-xs shadow-lg"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <p style={{ color: 'var(--text-secondary)' }} className="mb-1.5">{label}</p>
          {payload.map((entry: any) => (
            <div key={entry.name} className="flex items-center gap-2 mb-0.5">
              <span className="dot-indicator" style={{ backgroundColor: entry.color }} />
              <span style={{ color: 'var(--text-primary)' }}>{entry.name}: </span>
              <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{entry.value}</span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="card-base p-4 mb-5">
      <div className="flex items-center justify-between mb-3.5">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--text-secondary)' }}>
          24小时热度趋势
        </h3>
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          每小时热点分布
        </span>
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sampled} barGap={2} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={{ stroke: 'var(--border-color)' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--border-subtle)' }} />
            <Legend
              wrapperStyle={{ fontSize: '10px', color: 'var(--text-secondary)', paddingTop: '8px' }}
              iconType="circle"
              iconSize={7}
            />
            {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
              <Bar
                key={key}
                dataKey={key}
                name={cfg.label}
                fill={cfg.color}
                stackId="a"
                radius={[2, 2, 0, 0]}
                maxBarSize={18}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
