/**
 * KnowledgeCompoundingDashboard — 复利仪表盘 (Phase 13)
 *
 * 4 个卡片网格:
 *  1. 趋势折线图 (daily_trend)
 *  2. Top 10 概念排名
 *  3. 触发器健康度 (T1-T4 + dead_letter)
 *  4. 生命周期阶段分布柱状图
 *
 * B5 续拆: 容器只保留状态 / 取数编排与组合;
 * 纯类型与图表 option 构建 → compoundingDashboardModel.ts,
 * 三态展示 → CompoundingStates.tsx, 四个卡片 → CompoundingCards.tsx。
 */
import { useState, useEffect, useCallback } from 'react';
import { getKlCompounding } from '../../api/secnews';
import { useThemeColors } from '../../hooks/useThemeColors';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import {
  buildStageData,
  buildStageOption,
  buildTrendOption,
  type CompoundingData,
} from './compoundingDashboardModel';
import { CompoundingEmpty, CompoundingError, CompoundingSkeleton } from './CompoundingStates';
import { StageDistributionCard, TopConceptsCard, TrendCard, TriggerHealthCard } from './CompoundingCards';

/* ── Component ───────────────────────────────────────────────── */

export function KnowledgeCompoundingDashboard() {
  const [data, setData] = useState<CompoundingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const themeColors = useThemeColors([
    'text-muted',
    'text-secondary',
    'border-color',
    'color-success',
  ]);
  const accentColor =
    getComputedStyle(document.documentElement).getPropertyValue('--area-accent').trim()
    || themeColors['color-success']
    || '#22c55e';

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 非 2xx 由 apiFetch 抛错 (message 经 getApiErrorMessage 兜底)
      const json = await getKlCompounding<CompoundingData>();
      if (dead.current) return;
      setData(json);
    } catch (e: any) {
      if (dead.current) return;
      setError(e.message || '获取复利数据失败');
    } finally {
      if (!dead.current) setLoading(false);
    }
  }, [dead]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Loading state ──────────────────────────────────────── */
  if (loading) {
    return <CompoundingSkeleton />;
  }

  /* ── Error state ────────────────────────────────────────── */
  if (error) {
    return <CompoundingError error={error} onRetry={fetchData} />;
  }

  /* ── Empty state ────────────────────────────────────────── */
  if (!data || data.daily_trend.length === 0) {
    return <CompoundingEmpty />;
  }

  const { daily_trend, top_concepts, trigger_health, stage_distribution } = data;
  const textMuted = themeColors['text-muted'] || 'var(--text-muted)';
  const textSec = themeColors['text-secondary'] || 'var(--text-secondary)';
  const border = themeColors['border-color'] || 'var(--border-color)';
  const textPrimary = 'var(--text-primary)';

  const palette = { textMuted, textSec, border, textPrimary, accentColor };

  /* ── Stage distribution for bar chart ───────────────────── */
  const stageData = buildStageData(stage_distribution);
  const trendOption = buildTrendOption(daily_trend, palette);
  const stageOption = buildStageOption(stageData, palette);

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className="space-y-3" data-compounding-dashboard="loaded">
      {/* Row 1: Trend Chart (2 cols) + Top Concepts (1 col) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <TrendCard option={trendOption} />
        <TopConceptsCard top_concepts={top_concepts} textMuted={textMuted} />
      </div>

      {/* Row 2: Trigger Health (1 col) + Stage Distribution (1 col) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <TriggerHealthCard trigger_health={trigger_health} />
        <StageDistributionCard stageData={stageData} option={stageOption} textMuted={textMuted} />
      </div>
    </div>
  );
}
