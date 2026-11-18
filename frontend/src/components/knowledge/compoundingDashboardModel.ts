/**
 * compoundingDashboardModel — 复利仪表盘纯类型 / 纯函数 (B5 续拆自 KnowledgeCompoundingDashboard)
 *
 * 只放无 React 依赖的内容: 数据类型、健康度阈值、图表 option 构建。
 * option 构建公式逐字搬运自原容器, 未改写。
 */
import { STAGE_LABELS, STAGE_COLORS } from './LifecycleProgress';

/* ── Data types ──────────────────────────────────────────────── */

export interface DailyTrendPoint {
  day: string;
  count: number;
  avg_score: number;
}

export interface TopConcept {
  name: string;
  score: number;
}

export interface TriggerHealth {
  t1_failed: number;
  t2_failed: number;
  t3_failed: number;
  t4_failed: number;
  dead_letter_count: number;
}

export interface StageDistribution {
  [stage: string]: number;
}

export interface CompoundingData {
  daily_trend: DailyTrendPoint[];
  weekly_trend: { week: string; count: number; avg_score: number }[];
  monthly_trend: { month: string; count: number; avg_score: number }[];
  top_concepts: TopConcept[];
  trigger_health: TriggerHealth;
  stage_distribution: StageDistribution;
}

/* ── Helpers ─────────────────────────────────────────────────── */

export function healthColor(val: number): string {
  if (val === 0) return '#22c55e';
  if (val <= 5) return '#eab308';
  return '#ef4444';
}

export function healthLabel(val: number): string {
  if (val === 0) return '健康';
  if (val <= 5) return '警告';
  return '严重';
}

/** 图表 option 所需主题色值 (容器由 useThemeColors / 计算样式取得后传入) */
export interface DashboardPalette {
  textMuted: string;
  textSec: string;
  border: string;
  textPrimary: string;
  accentColor: string;
}

/* ── Stage distribution ──────────────────────────────────────── */

export interface StageDatum {
  stage: string;
  count: number;
  fill: string;
}

export function buildStageData(stage_distribution: StageDistribution): StageDatum[] {
  return Object.entries(stage_distribution).map(([stage, count]) => ({
    stage: STAGE_LABELS[stage] || stage,
    count,
    fill: STAGE_COLORS[stage] || '#6b7280',
  }));
}

/* ── ECharts option 构建 ─────────────────────────────────────── */

function tooltipHTML(border: string, bg: string, label: string, rows: string): string {
  return `<div class="p-3 text-xs shadow-lg" style="background-color:${bg};border:1px solid ${border};border-radius:var(--radius-sm)">` +
    `${label}${rows}</div>`;
}

export function buildTrendOption(daily_trend: DailyTrendPoint[], palette: DashboardPalette) {
  const { textMuted, textSec, textPrimary, border, accentColor } = palette;

  const tickStyle = {
    color: textMuted,
    fontSize: 10,
    fontFamily: 'JetBrains Mono, monospace',
  };

  return {
    grid: { top: 12, left: 32, right: 36, bottom: 30 },
    xAxis: {
      type: 'category' as const,
      data: daily_trend.map(d => d.day),
      axisLabel: tickStyle,
      axisLine: { lineStyle: { stroke: border } },
      splitLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value' as const,
        axisLabel: tickStyle,
        axisLine: { show: false },
        axisTick: { show: false },
        minInterval: 1,
        splitLine: { lineStyle: { type: 'dashed' as const, color: border }, show: true },
      },
      {
        type: 'value' as const,
        min: 0,
        max: 1,
        axisLabel: tickStyle,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params];
        if (!list.length) return '';
        const label = `<p class="mb-1 font-mono" style="color:${textSec}">${list[0].axisValue}</p>`;
        let rows = '';
        for (const p of list) {
          rows += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">';
          rows += `<span class="dot-indicator" style="background-color:${p.color}"></span>`;
          rows += `<span style="color:${textPrimary}">${p.seriesName}: </span>`;
          rows += `<span class="font-semibold font-mono" style="color:${textPrimary}">${p.value}</span>`;
          rows += '</div>';
        }
        return tooltipHTML(border, 'var(--bg-elevated)', label, rows);
      },
    },
    legend: {
      bottom: 0,
      icon: 'roundRect',
      textStyle: { fontSize: 10, color: textSec },
    },
    series: [
      {
        type: 'line' as const,
        name: '条目数',
        yAxisIndex: 0,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: accentColor },
        emphasis: { focus: 'series' as const },
        data: daily_trend.map(d => d.count),
      },
      {
        type: 'line' as const,
        name: '平均掌握度',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, type: 'dashed' as const, color: '#8b5cf6' },
        emphasis: { focus: 'series' as const },
        data: daily_trend.map(d => d.avg_score),
      },
    ],
  };
}

export type TrendChartOption = ReturnType<typeof buildTrendOption>;

export function buildStageOption(stageData: StageDatum[], palette: DashboardPalette) {
  const { textMuted, textSec, textPrimary, border } = palette;

  const tickStyle = {
    color: textMuted,
    fontSize: 10,
    fontFamily: 'JetBrains Mono, monospace',
  };

  return {
    grid: { top: 4, left: 70, right: 16, bottom: 24 },
    xAxis: {
      type: 'value' as const,
      axisLabel: tickStyle,
      axisLine: { show: false },
      axisTick: { show: false },
      minInterval: 1,
      splitLine: { lineStyle: { type: 'dashed' as const, color: border }, show: false },
    },
    yAxis: {
      type: 'category' as const,
      data: stageData.map(d => d.stage),
      axisLabel: tickStyle,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const, shadowStyle: { color: 'var(--border-subtle)' } },
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params;
        if (!p) return '';
        const label = `<p style="color:${textSec}">${p.name}</p>`;
        const rows = `<p class="font-mono font-semibold" style="color:${textPrimary}">${p.value} 条</p>`;
        return tooltipHTML(border, 'var(--bg-elevated)', label, rows);
      },
    },
    series: [
      {
        type: 'bar' as const,
        name: '条目数',
        barMaxWidth: 20,
        label: {
          show: true,
          position: 'right' as const,
          color: textMuted,
          fontSize: 10,
          fontFamily: 'JetBrains Mono, monospace',
          formatter: (v: any) => (typeof v.value === 'number' && v.value > 0 ? v.value : ''),
        },
        itemStyle: { borderRadius: [0, 3, 3, 0] },
        data: stageData.map(d => ({ value: d.count, itemStyle: { color: d.fill } })),
      },
    ],
  };
}

export type StageChartOption = ReturnType<typeof buildStageOption>;
