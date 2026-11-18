/**
 * report/WeeklyReport — 周报 (AIHot 风格)。
 *
 * 拆自原 ReportPage.tsx (1401 行) 中 WeeklyReportContent (~501-941 行)。
 * 纯结构拆分: 状态/加载/渲染逻辑逐字迁移, 仅将 catColors/renderFormatted
 * 改为引用 utils, 文章行改为共享 HighlightArticleCard。
 *
 * B5.6 拆分: 本文件只留状态与取数编排 (容器); 纯展示区块见
 * WeeklyReportBlocks.tsx / WeeklyReportHighlights.tsx / sharedBlocks.tsx。
 */
import { useState, useEffect } from 'react';
import { ApiError } from '../../lib/api';
import { getWeeklyAvailable, getWeeklyOverview } from '../../api/report';
import { ReportMainTheme } from './sharedBlocks';
import {
  WeeklyArchivePanel,
  WeeklyReportHeader,
  WeeklyStatsRow,
  type WeekOption,
} from './WeeklyReportBlocks';
import { WeeklyHighlights } from './WeeklyReportHighlights';
import type { WeeklyOverview } from './types';

export function WeeklyReportContent() {
  const [overview, setOverview] = useState<WeeklyOverview | null>(null);
  const [weeks, setWeeks] = useState<WeekOption[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedHighlight, setExpandedHighlight] = useState<string | null>(null);

  // Load available weeks
  useEffect(() => {
    let cancelled = false;
    // 非 2xx 由 apiFetch 抛错 → 与原 `r.ok ? json : {weeks: []}` 同为空列表降级
    getWeeklyAvailable<{ weeks?: WeekOption[] }>()
      .then(data => {
        if (!cancelled) {
          const w = data.weeks || [];
          setWeeks(w);
          if (w.length > 0 && !selectedWeek) {
            setSelectedWeek(w[0].value);
          }
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Load overview for selected week
  useEffect(() => {
    if (!selectedWeek) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getWeeklyOverview<WeeklyOverview>(selectedWeek);
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
  }, [selectedWeek]);

  const handlePrevWeek = () => {
    const idx = weeks.findIndex(w => w.value === selectedWeek);
    if (idx < weeks.length - 1) setSelectedWeek(weeks[idx + 1].value);
  };
  const handleNextWeek = () => {
    const idx = weeks.findIndex(w => w.value === selectedWeek);
    if (idx > 0) setSelectedWeek(weeks[idx - 1].value);
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
  if (!overview) {
    return (
      <div className="text-center py-12 text-xs" style={{ color: 'var(--text-muted)' }}>
        暂无周报数据
      </div>
    );
  }

  const { period, total, main_theme, highlights, stats } = overview;

  return (
    <div className="space-y-6">

      {/* ── VOL Header (AIHot 风格) ── */}
      <WeeklyReportHeader
        period={period}
        total={total}
        weeks={weeks}
        selectedWeek={selectedWeek}
        onSelectWeek={setSelectedWeek}
        onPrevWeek={handlePrevWeek}
        onNextWeek={handleNextWeek}
      />

      {/* ── 本期主线 (AIHot 风格) ── */}
      <ReportMainTheme mainTheme={main_theme} />

      {/* ── Stats Row (AIHot #95 风格) ── */}
      {stats && (
        <WeeklyStatsRow stats={stats} total={total} />
      )}

      {/* ── 本期看点 (AIHot 风格) ── */}
      <WeeklyHighlights
        highlights={highlights}
        expandedHighlight={expandedHighlight}
        onToggle={toggleHighlight}
      />

      {/* ── 往期周报 (AIHot 风格) ── */}
      {weeks.length > 0 && (
        <WeeklyArchivePanel
          weeks={weeks}
          selectedWeek={selectedWeek}
          onSelectWeek={setSelectedWeek}
          onPrevWeek={handlePrevWeek}
          onNextWeek={handleNextWeek}
        />
      )}
    </div>
  );
}
