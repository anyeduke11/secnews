/**
 * KnowledgeCompoundingDashboard — 复利仪表盘 (Phase 13)
 *
 * 4 个卡片网格:
 *  1. 趋势折线图 (daily_trend)
 *  2. Top 10 概念排名
 *  3. 触发器健康度 (T1-T4 + dead_letter)
 *  4. 生命周期阶段分布柱状图
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend,
} from 'recharts';
import { Icon } from '../Icon';
import { STAGE_LABELS, STAGE_COLORS } from './LifecycleProgress';

/* ── Data types ──────────────────────────────────────────────── */

interface DailyTrendPoint {
  day: string;
  count: number;
  avg_score: number;
}

interface TopConcept {
  name: string;
  score: number;
}

interface TriggerHealth {
  t1_failed: number;
  t2_failed: number;
  t3_failed: number;
  t4_failed: number;
  dead_letter_count: number;
}

interface StageDistribution {
  [stage: string]: number;
}

interface CompoundingData {
  daily_trend: DailyTrendPoint[];
  weekly_trend: { week: string; count: number; avg_score: number }[];
  monthly_trend: { month: string; count: number; avg_score: number }[];
  top_concepts: TopConcept[];
  trigger_health: TriggerHealth;
  stage_distribution: StageDistribution;
}

/* ── Helpers ─────────────────────────────────────────────────── */

function healthColor(val: number): string {
  if (val === 0) return '#22c55e';
  if (val <= 5) return '#eab308';
  return '#ef4444';
}

function healthLabel(val: number): string {
  if (val === 0) return '健康';
  if (val <= 5) return '警告';
  return '严重';
}

/* ── Custom tooltip ──────────────────────────────────────────── */

const LineTooltip = ({ active, payload, label }: any) => {
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
        <p className="mb-1 font-mono" style={{ color: 'var(--text-secondary)' }}>
          {label}
        </p>
        {payload.map((entry: any) => (
          <div key={entry.name} className="flex items-center gap-2 mb-0.5">
            <span className="dot-indicator" style={{ backgroundColor: entry.color }} />
            <span style={{ color: 'var(--text-primary)' }}>{entry.name}: </span>
            <span className="font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
              {entry.value}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

/* ── Component ───────────────────────────────────────────────── */

export function KnowledgeCompoundingDashboard() {
  const [data, setData] = useState<CompoundingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/kl/compounding');
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const json: CompoundingData = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message || '获取复利数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Loading state ──────────────────────────────────────── */
  if (loading) {
    return (
      <div className="space-y-3" data-compounding-dashboard="loading">
        {[1, 2, 3, 4].map(i => (
          <div
            key={i}
            className="rounded-[var(--radius-md)] p-3.5 animate-shimmer"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
          >
            <div className="h-3 w-24 mb-3" style={{ backgroundColor: 'var(--border-color)', borderRadius: 'var(--radius-sm)' }} />
            <div className="h-28" style={{ backgroundColor: 'var(--border-subtle)', borderRadius: 'var(--radius-sm)' }} />
          </div>
        ))}
      </div>
    );
  }

  /* ── Error state ────────────────────────────────────────── */
  if (error) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-4 text-center"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        data-compounding-dashboard="error"
      >
        <div className="flex items-center justify-center gap-2 mb-2" style={{ color: '#ef4444' }}>
          <Icon size={16}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </Icon>
          <span className="text-sm font-semibold">加载失败</span>
        </div>
        <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>{error}</p>
        <button
          className="px-3 py-1.5 text-xs rounded-[var(--radius-sm)] font-medium"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 10%, transparent)',
            color: 'var(--area-accent, var(--color-success))',
            border: '1px solid color-mix(in srgb, var(--area-accent, var(--color-success)) 30%, transparent)',
          }}
          onClick={fetchData}
        >
          重试
        </button>
      </div>
    );
  }

  /* ── Empty state ────────────────────────────────────────── */
  if (!data || data.daily_trend.length === 0) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-6 text-center"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        data-compounding-dashboard="empty"
      >
        <div className="flex items-center justify-center gap-2 mb-2" style={{ color: 'var(--text-muted)' }}>
          <Icon size={20}>
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </Icon>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>暂无复利数据</span>
        </div>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          当天有知识条目被处理时，复利仪表盘将自动填充。
        </p>
      </div>
    );
  }

  const { daily_trend, top_concepts, trigger_health, stage_distribution } = data;
  const textMuted = 'var(--text-muted)';
  const textSec = 'var(--text-secondary)';
  const border = 'var(--border-color)';

  /* ── Stage distribution for bar chart ───────────────────── */
  const stageData = Object.entries(stage_distribution).map(([stage, count]) => ({
    stage: STAGE_LABELS[stage] || stage,
    count,
    fill: STAGE_COLORS[stage] || '#6b7280',
  }));

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className="space-y-3" data-compounding-dashboard="loaded">
      {/* Row 1: Trend Chart (2 cols) + Top Concepts (1 col) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* ── Trend Chart ── */}
        <section
          className="lg:col-span-2 rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
                color: 'var(--area-accent, var(--color-success))',
              }}
            >
              <Icon size={11}>
                <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                <polyline points="17 6 23 6 23 12" />
              </Icon>
            </span>
            每日摄入趋势
          </h3>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={daily_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke={border} vertical={false} />
                <XAxis
                  dataKey="day"
                  tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={{ stroke: border }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                  axisLine={false}
                  tickLine={false}
                  domain={[0, 1]}
                />
                <Tooltip content={<LineTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: '10px', color: textSec, paddingTop: '4px' }}
                  iconType="line"
                  iconSize={10}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="count"
                  name="条目数"
                  stroke="var(--area-accent, var(--color-success))"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="avg_score"
                  name="平均掌握度"
                  stroke="#8b5cf6"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                  activeDot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        {/* ── Top Concepts ── */}
        <section
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
                color: 'var(--area-accent, var(--color-success))',
              }}
            >
              <Icon size={11}>
                <circle cx="12" cy="12" r="10" />
                <polygon points="10 8 16 12 10 16 10 8" />
              </Icon>
            </span>
            Top 概念
          </h3>
          <div className="space-y-1.5">
            {top_concepts.length === 0 ? (
              <p className="text-xs" style={{ color: textMuted }}>暂无关联概念</p>
            ) : (
              top_concepts.map((c, i) => {
                const maxScore = top_concepts[0]?.score || 1;
                const barWidth = (c.score / maxScore) * 100;
                return (
                  <div key={c.name} className="flex items-center gap-2">
                    <span
                      className="text-[10px] font-mono w-4 text-right shrink-0"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-0.5">
                        <span
                          className="text-[11px] truncate"
                          style={{ color: 'var(--text-primary)' }}
                          title={c.name}
                        >
                          {c.name}
                        </span>
                        <span
                          className="text-[10px] font-mono tabular-nums ml-2 shrink-0"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {c.score}
                        </span>
                      </div>
                      <div
                        className="h-1 rounded-full"
                        style={{
                          backgroundColor: 'var(--border-color)',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${barWidth}%`,
                            backgroundColor: 'var(--area-accent, var(--color-success))',
                          }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>
      </div>

      {/* Row 2: Trigger Health (1 col) + Stage Distribution (1 col) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* ── Trigger Health ── */}
        <section
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
                color: 'var(--area-accent, var(--color-success))',
              }}
            >
              <Icon size={11}>
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </Icon>
            </span>
            触发器健康度
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {(['t1_failed', 't2_failed', 't3_failed', 't4_failed'] as const).map((key) => {
              const val = trigger_health[key];
              const color = healthColor(val);
              const label = key.replace('_failed', '').toUpperCase();
              return (
                <div
                  key={key}
                  className="rounded-[var(--radius-sm)] p-2.5 text-center"
                  style={{
                    backgroundColor: 'color-mix(in srgb, ' + color + ' 8%, transparent)',
                    border: '1px solid color-mix(in srgb, ' + color + ' 25%, transparent)',
                  }}
                >
                  <div className="text-lg font-bold font-mono tabular-nums" style={{ color }}>
                    {val}
                  </div>
                  <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                    {label}
                  </div>
                  <div
                    className="inline-block w-1.5 h-1.5 rounded-full mt-1"
                    style={{ backgroundColor: color }}
                    title={healthLabel(val)}
                  />
                </div>
              );
            })}
            <div
              className="rounded-[var(--radius-sm)] p-2.5 text-center"
              style={{
                backgroundColor: 'color-mix(in srgb, ' + healthColor(trigger_health.dead_letter_count) + ' 8%, transparent)',
                border: '1px solid color-mix(in srgb, ' + healthColor(trigger_health.dead_letter_count) + ' 25%, transparent)',
              }}
            >
              <div
                className="text-lg font-bold font-mono tabular-nums"
                style={{ color: healthColor(trigger_health.dead_letter_count) }}
              >
                {trigger_health.dead_letter_count}
              </div>
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                Dead
              </div>
              <div
                className="inline-block w-1.5 h-1.5 rounded-full mt-1"
                style={{ backgroundColor: healthColor(trigger_health.dead_letter_count) }}
                title={healthLabel(trigger_health.dead_letter_count)}
              />
            </div>
          </div>
        </section>

        {/* ── Stage Distribution ── */}
        <section
          className="rounded-[var(--radius-md)] p-3.5"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
                color: 'var(--area-accent, var(--color-success))',
              }}
            >
              <Icon size={11}>
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </Icon>
            </span>
            生命周期阶段分布
          </h3>
          {stageData.length === 0 ? (
            <p className="text-xs" style={{ color: textMuted }}>暂无阶段分布数据</p>
          ) : (
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={stageData}
                  layout="vertical"
                  margin={{ left: 0, right: 0, top: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={border} horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="stage"
                    tick={{ fill: textMuted, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                    axisLine={false}
                    tickLine={false}
                    width={60}
                  />
                  <Tooltip
                    content={({ active, payload, label }: any) => {
                      if (active && payload && payload.length) {
                        return (
                          <div
                            className="p-2 text-xs shadow-lg"
                            style={{
                              backgroundColor: 'var(--bg-elevated)',
                              border: '1px solid var(--border-color)',
                              borderRadius: 'var(--radius-sm)',
                            }}
                          >
                            <p style={{ color: 'var(--text-secondary)' }}>{label}</p>
                            <p className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                              {payload[0].value} 条
                            </p>
                          </div>
                        );
                      }
                      return null;
                    }}
                    cursor={{ fill: 'var(--border-subtle)' }}
                  />
                  <Bar
                    dataKey="count"
                    name="条目数"
                    radius={[0, 3, 3, 0]}
                    maxBarSize={20}
                    label={{
                      position: 'right',
                      fill: textMuted,
                      fontSize: 10,
                      fontFamily: 'JetBrains Mono, monospace',
                      formatter: (v: any) => (typeof v === 'number' && v > 0) ? v : '',
                    }}
                  >
                    {stageData.map((entry, idx) => (
                      <rect key={idx} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}