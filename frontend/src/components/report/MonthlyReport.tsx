/**
 * report/MonthlyReport — 月报。
 *
 * 拆自原 ReportPage.tsx (1401 行) 中 MonthlyReport (~942-1343 行)。
 * 纯结构拆分: 状态/加载/渲染逻辑逐字迁移, 仅将 catColors/renderFormatted
 * 改为引用 utils, 文章行改为共享 MonthlyArticleRow。
 *
 * B5.6 拆分: 本文件只留状态与取数编排 (容器); 纯展示区块见
 * MonthlyReportBlocks.tsx / MonthlyReportHighlights.tsx / sharedBlocks.tsx。
 */
import React, { useState, useEffect } from 'react';
import { ApiError } from '../../lib/api';
import { getMonthlyAvailable, getMonthlyOverview } from '../../api/report';
import { ReportMainTheme } from './sharedBlocks';
import {
  MonthlyArchivePanel,
  MonthlyCategoryPanel,
  MonthlyReportHeader,
  MonthlyStatsRow,
  type MonthOption,
} from './MonthlyReportBlocks';
import { MonthlyHighlights } from './MonthlyReportHighlights';
import type { MonthlyOverview } from './types';

export function MonthlyReport() {
  const [overview, setOverview] = useState<MonthlyOverview | null>(null);
  const [months, setMonths] = useState<MonthOption[]>([]);
  const [selectedOffset, setSelectedOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedHighlight, setExpandedHighlight] = useState<string | null>(null);

  // Load available months
  useEffect(() => {
    let cancelled = false;
    // 非 2xx 由 apiFetch 抛错 → 与原 `r.ok ? json : {months: []}` 同为空列表降级
    getMonthlyAvailable<{ months?: MonthOption[] }>()
      .then(data => { if (!cancelled) setMonths(data.months || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Load overview for selected offset
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getMonthlyOverview<MonthlyOverview>(selectedOffset);
        if (!cancelled) setOverview(data);
      } catch (e: any) {
        if (!cancelled) {
          setError(e instanceof ApiError ? `加载失败 (${e.status})` : (e?.message || '加载失败'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [selectedOffset]);

  const handlePrevMonth = () => setSelectedOffset(prev => prev - 1);
  const handleNextMonth = () => setSelectedOffset(prev => Math.min(prev + 1, 0));
  const handleMonthSelect = (ev: React.ChangeEvent<HTMLSelectElement>) => {
    const val = parseInt(ev.target.value, 10);
    setSelectedOffset(isNaN(val) ? 0 : val);
  };

  const switchToMonth = (value: string) => {
    const idx = months.findIndex(m => m.value === value);
    if (idx >= 0) setSelectedOffset(-idx);
  };

  /** 折叠态切换 (与拆分前内联表达式等价) */
  function toggleHighlight(id: string) {
    setExpandedHighlight(expandedHighlight === id ? null : id);
  }

  if (loading) {
    return <div className="text-center py-12 text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>;
  }
  if (error) {
    return <div className="px-3 py-2 rounded text-xs" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 13%, transparent)', color: 'var(--color-error)' }}>{error}</div>;
  }
  if (!overview) return null;

  const { period, total, category_counts, main_theme, highlights, stats } = overview;
  const volLabel = period.label.replace('年', '.').replace('月', '');

  return (
    <div className="space-y-6">

      {/* ── VOL Header ── */}
      <MonthlyReportHeader
        period={period}
        total={total}
        volLabel={volLabel}
        months={months}
        selectedOffset={selectedOffset}
        onPrevMonth={handlePrevMonth}
        onNextMonth={handleNextMonth}
        onSelectMonth={handleMonthSelect}
      />

      {/* ── 本期主线 ── */}
      <ReportMainTheme mainTheme={main_theme} />

      {/* ── Stats Row (AIHot style) ── */}
      {stats && (
        <MonthlyStatsRow stats={stats} total={total} />
      )}

      {/* ── 数字盘点 ── */}
      <MonthlyCategoryPanel categoryCounts={category_counts} />

      {/* ── 本期看点 ── */}
      <MonthlyHighlights
        highlights={highlights}
        expandedHighlight={expandedHighlight}
        onToggle={toggleHighlight}
      />

      {/* ── 往期月报 ── */}
      {months.length > 0 && (
        <MonthlyArchivePanel
          months={months}
          period={period}
          selectedOffset={selectedOffset}
          onPrevMonth={handlePrevMonth}
          onNextMonth={handleNextMonth}
          onSwitchToMonth={switchToMonth}
        />
      )}
    </div>
  );
}
