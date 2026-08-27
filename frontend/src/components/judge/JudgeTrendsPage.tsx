/**
 * JudgeTrendsPage — 判断层趋势分析页
 *
 * Phase 3: 将 TrendChart 扩展到完整页面，支持多时间范围切换。
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { Icon } from '../Icon';
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

  const bgElevated = colors['bg-elevated'] || 'var(--bg-elevated)';
  const textPrimary = colors['text-primary'] || 'var(--text-primary)';
  const textMuted = colors['text-muted'] || 'var(--text-muted)';
  const textSec = colors['text-secondary'] || 'var(--text-secondary)';
  const border = colors['border-color'] || 'var(--border-color)';

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
        <h2 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>
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
            <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
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
