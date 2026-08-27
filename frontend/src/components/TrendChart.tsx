/**
 * TrendChart — 24h 热度趋势堆叠柱状图。
 */
import { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { TrendPoint, TrendResponse } from '../types';
import { useThemeColors, ThemeColorKey } from '../hooks/useThemeColors';

const CATEGORY_CONFIG: Array<{ key: string; token: ThemeColorKey; label: string }> = [
  { key: 'ai', token: 'color-ai', label: '科技/AI' },
  { key: 'security', token: 'color-security', label: '安全' },
  { key: 'finance', token: 'color-finance', label: '金融' },
  { key: 'startup', token: 'color-startup', label: '创业' },
  { key: 'bid', token: 'color-bid', label: '招标' },
  { key: 'github', token: 'color-ai', label: 'GitHub 项目' },
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
    'color-security',
    'color-finance',
    'color-startup',
    'color-bid',
  ]);

  if (loading) {
    return (
      <div className="mb-6">
        <div className="h-3.5 w-28 mb-4 animate-shimmer" />
        <div className="h-36 animate-shimmer" />
      </div>
    );
  }

  if (data.length === 0) return null;

  const sampled = data.filter((_, i) => i % 3 === 0 || i === data.length - 1);

  const bgElevated = colors['bg-elevated'] || 'var(--bg-elevated)';
  const border = colors['border-color'] || 'var(--border-color)';
  const textPrimary = colors['text-primary'] || 'var(--text-primary)';
  const textSec = colors['text-secondary'] || 'var(--text-secondary)';
  const textMuted = colors['text-muted'] || 'var(--text-muted)';

  const tickStyle = {
    fill: textMuted,
    fontSize: 10,
    fontFamily: 'JetBrains Mono, monospace',
  };

  const option = {
    grid: { top: 8, left: 32, right: 8, bottom: 30 },
    xAxis: {
      type: 'category' as const,
      data: sampled.map(d => d.label),
      axisLabel: tickStyle,
      axisLine: { lineStyle: { stroke: border } },
      splitLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: tickStyle,
      axisLine: { show: false },
      axisTick: { show: false },
      minInterval: 1,
      splitLine: { lineStyle: { type: 'dashed' as const, color: border }, show: true },
    },
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const, shadowStyle: { color: 'var(--border-subtle)' } },
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params];
        if (!list.length) return '';
        const label = list[0].axisValue;
        let html = `<div class="p-3 text-xs shadow-lg" style="background-color:${bgElevated};border:1px solid ${border};border-radius:var(--radius-sm)">`;
        html += `<p class="mb-1.5 font-mono" style="color:${textSec}">${label}</p>`;
        for (const p of list) {
          html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">';
          html += `<span class="dot-indicator" style="background-color:${p.color}"></span>`;
          html += `<span style="color:${textPrimary}">${p.seriesName}: </span>`;
          html += `<span class="font-semibold font-mono" style="color:${textPrimary}">${p.value}</span>`;
          html += '</div>';
        }
        html += '</div>';
        return html;
      },
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 7,
      itemHeight: 7,
      textStyle: { fontSize: 10, color: textSec },
      data: CATEGORY_CONFIG.map(c => c.label),
    },
    series: CATEGORY_CONFIG.map(({ key, token, label }) => ({
      type: 'bar' as const,
      name: label,
      stack: 'total',
      barGap: 2,
      barCategoryGap: '20%',
      barMaxWidth: 18,
      itemStyle: { color: colors[token] || 'var(--color-ai)' },
      data: sampled.map(d => (d as any)[key]),
    })),
  };

  return (
    <div className="mb-6">
      {/* v1.9 Editorial: 侧栏版块 — 栏目小标 + 上边粗线, 去卡片盒 */}
      <div className="flex items-center justify-between pb-2 mb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h3 className="text-xs font-bold tracking-[0.12em] uppercase" style={{ color: 'var(--text-primary)' }}>
          24小时热度趋势
        </h3>
        <span className="text-[11px]" style={{ color: textMuted }}>
          每小时分布
        </span>
      </div>

      <div className="h-44">
        <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
      </div>
    </div>
  );
}
