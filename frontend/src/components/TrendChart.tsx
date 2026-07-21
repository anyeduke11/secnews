/**
 * TrendChart — 24h 热度趋势堆叠柱状图。
 *
 * Phase 2: 分类色全部走 CSS 变量 (通过 useThemeColors 读取),
 *          暗/亮主题自动切换, 主题色无硬编码 hex。
 */
import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend
} from 'recharts';
import { TrendPoint, TrendResponse } from '../types';
import { useThemeColors, ThemeColorKey } from '../hooks/useThemeColors';

// chart 用的分类色 token key + 中文 label
const CATEGORY_CONFIG: Array<{ key: string; token: ThemeColorKey; label: string }> = [
  { key: 'ai', token: 'color-ai', label: '科技/AI' },
  { key: 'security', token: 'color-security', label: '安全' },
  { key: 'finance', token: 'color-finance', label: '金融' },
  { key: 'startup', token: 'color-startup', label: '创业' },
  { key: 'bid', token: 'color-bid', label: '招标' },
  { key: 'github', token: 'color-ai', label: 'GitHub 项目' }, // github 借用 --color-ai 蓝
];

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

  const colors = useThemeColors([
    'bg-elevated',
    'border-color',
    'text-primary',
    'text-secondary',
    'text-muted',
    'color-ai',
  ]);

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
            backgroundColor: colors['bg-elevated'] || 'var(--bg-elevated)',
            border: `1px solid ${colors['border-color'] || 'var(--border-color)'}`,
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <p style={{ color: colors['text-secondary'] || 'var(--text-secondary)' }} className="mb-1.5">{label}</p>
          {payload.map((entry: any) => (
            <div key={entry.name} className="flex items-center gap-2 mb-0.5">
              <span className="dot-indicator" style={{ backgroundColor: entry.color }} />
              <span style={{ color: colors['text-primary'] || 'var(--text-primary)' }}>{entry.name}: </span>
              <span className="font-semibold" style={{ color: colors['text-primary'] || 'var(--text-primary)' }}>{entry.value}</span>
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
    <div className="card-base p-4 mb-5">
      <div className="flex items-center justify-between mb-3.5">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: textSec }}>
          24小时热度趋势
        </h3>
        <span className="text-[11px]" style={{ color: textMuted }}>
          每小时热点分布
        </span>
      </div>

      <div className="h-44">
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
