/**
 * JudgeTrendsPage — 判断层趋势分析页
 *
 * Phase 3: 将 TrendChart 扩展到完整页面，支持多时间范围切换。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from 'recharts';
import { useThemeColors, ThemeColorKey } from '../../hooks/useThemeColors';
import type { TrendPoint, TrendResponse } from '../../types';

const TIME_RANGES = [
  { key: '24h', label: '24 小时' },
  { key: '72h', label: '72 小时' },
  { key: '7d',  label: '7 天' },
  { key: '30d', label: '30 天' },
];

const CATEGORY_CONFIG: Array<{ key: string; token: ThemeColorKey; label: string }> = [
  { key: 'ai',       token: 'color-ai',       label: '科技/AI' },
  { key: 'security', token: 'color-security',  label: '安全' },
  { key: 'finance',  token: 'color-finance',   label: '金融' },
  { key: 'startup',  token: 'color-startup',   label: '创业' },
  { key: 'bid',      token: 'color-bid',       label: '招标' },
  { key: 'github',   token: 'color-ai',        label: 'GitHub 项目' },
];

export function JudgeTrendsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('24h');

  const loadTrends = useCallback(async (hours: string) => {
    setLoading(true);
    try {
      const r = await fetch(`/api/trends?hours=${hours}`);
      if (!r.ok) return;
      const d: TrendResponse = await r.json();
      setData(d.trends || []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    const hoursMap: Record<string, string> = { '24h': '24', '72h': '72', '7d': '168', '30d': '720' };
    loadTrends(hoursMap[timeRange] || '24');
  }, [timeRange, loadTrends]);

  const colors = useThemeColors([
    'bg-elevated', 'border-color', 'text-primary', 'text-secondary', 'text-muted',
    'color-ai', 'color-security', 'color-finance', 'color-startup', 'color-bid',
  ]);

  const sampled = data.filter((_, i) => {
    if (data.length <= 48) return true;
    const step = Math.max(1, Math.floor(data.length / 48));
    return i % step === 0 || i === data.length - 1;
  });

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div
          className="p-3 text-xs shadow-lg"
          style={{
            backgroundColor: colors['bg-elevated'] || 'var(--bg-elevated)',
            border: `1px solid ${colors['border-color'] || 'var(--border-color)'}`,
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <p className="mb-1.5 font-mono" style={{ color: colors['text-secondary'] || 'var(--text-secondary)' }}>{label}</p>
          {payload.map((entry: any) => (
            <div key={entry.name} className="flex items-center gap-2 mb-0.5">
              <span className="dot-indicator" style={{ backgroundColor: entry.color }} />
              <span style={{ color: colors['text-primary'] || 'var(--text-primary)' }}>{entry.name}: </span>
              <span className="font-semibold font-mono" style={{ color: colors['text-primary'] || 'var(--text-primary)' }}>{entry.value}</span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  const textMuted = colors['text-muted'] || 'var(--text-muted)';
  const textSec = colors['text-secondary'] || 'var(--text-secondary)';
  const border = colors['border-color'] || 'var(--border-color)';

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/judge')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回判断层"
          aria-label="返回判断层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-serif text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          趋势分析
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          判断层 · 领域热度趋势
        </span>
      </div>

      {/* 时间范围切换 */}
      <div className="flex items-center gap-2 mb-4">
        {TIME_RANGES.map(tr => {
          const active = tr.key === timeRange;
          return (
            <button
              key={tr.key}
              onClick={() => setTimeRange(tr.key)}
              className="ink-chip focus-ring transition-colors"
              style={{
                padding: '3px 9px',
                color: active ? 'var(--text-on-light)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                borderColor: active ? 'var(--accent)' : 'var(--border-color)',
                fontWeight: active ? 600 : 400,
              }}
              aria-current={active ? 'page' : undefined}
            >
              {tr.label}
            </button>
          );
        })}
      </div>

      {/* 趋势图 */}
      {loading ? (
        <div className="h-64 animate-shimmer rounded-[var(--radius-md)]" />
      ) : data.length === 0 ? (
        <div className="py-12 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          暂无趋势数据
        </div>
      ) : (
        <div
          className="p-4 rounded-[var(--radius-md)]"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sampled} barGap={2} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke={border} vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={{ stroke: border }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--border-subtle)' }} />
                <Legend
                  wrapperStyle={{ fontSize: '10px', color: textSec, paddingTop: '8px' }}
                  iconType="circle"
                  iconSize={7}
                />
                {CATEGORY_CONFIG.map(({ key, token, label }) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    name={label}
                    fill={colors[token] || 'var(--color-ai)'}
                    stackId="a"
                    maxBarSize={18}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 领域统计摘要 */}
      {!loading && data.length > 0 && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {CATEGORY_CONFIG.map(({ key, label }) => {
            const total = data.reduce((sum, p) => sum + ((p as any)[key] || 0), 0);
            return (
              <div
                key={key}
                className="p-3 rounded-[var(--radius-md)] text-center"
                style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
              >
                <div className="text-[10px] font-bold" style={{ color: 'var(--text-muted)' }}>{label}</div>
                <div className="text-lg font-bold font-mono tabular-nums mt-1" style={{ color: 'var(--text-primary)' }}>
                  {total}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}