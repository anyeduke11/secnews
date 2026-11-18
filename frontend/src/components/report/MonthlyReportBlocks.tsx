/**
 * report/MonthlyReportBlocks — 月报的纯展示区块
 * (VOL 头部 / 统计行 / 领域分布 / 往期月报)。
 *
 * B5.6 拆分: 自 MonthlyReport.tsx 原样搬运, DOM/class/aria 文案逐字不变;
 * 取数与状态编排全部留在 MonthlyReport 容器。
 */
import type { ChangeEvent } from 'react';
import { catColors } from './utils';
import type { MonthlyPeriod, MonthlyStats } from './types';

/** 可选月份条目 (GET /api/reports/monthly/available 的 months 元素) */
export interface MonthOption {
  value: string;
  label: string;
}

/** VOL 头部 (期号 / 标题 / 月份切换器) */
export function MonthlyReportHeader({
  period,
  total,
  volLabel,
  months,
  selectedOffset,
  onPrevMonth,
  onNextMonth,
  onSelectMonth,
}: {
  period: MonthlyPeriod;
  total: number;
  volLabel: string;
  months: MonthOption[];
  selectedOffset: number;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onSelectMonth: (ev: ChangeEvent<HTMLSelectElement>) => void;
}) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <div>
        <div className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--text-muted)' }}>
          VOL.{volLabel} · {total} STORIES · HOTSPOT 月报
        </div>
        <h3 className="text-xl font-bold tracking-tight mt-1" style={{ color: 'var(--text-primary)' }}>
          {period.label}月报
        </h3>
        <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {period.start.slice(0, 10).replace(/-/g, '-')} ~ {period.end.slice(0, 10).replace(/-/g, '-')}
          {' · '}MONTHLY · 编辑系统自动综合
        </p>
      </div>
      {/* Month switcher */}
      <div className="flex items-center gap-2">
        <button
          onClick={onPrevMonth}
          className="ink-chip focus-ring transition-colors"
          style={{ padding: '3px 9px', fontSize: '12px' }}
          aria-label="上一月"
        >
          ← 上一期
        </button>
        <select
          value={selectedOffset}
          onChange={onSelectMonth}
          className="text-xs px-2 py-1 rounded focus-ring"
          style={{
            backgroundColor: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
          }}
        >
          <option value={0} style={{ backgroundColor: 'var(--bg-secondary)' }}>{period.label}</option>
          {months.filter(m => m.label !== period.label).map(m => (
            <option key={m.value} value={-months.findIndex(mm => mm.value === m.value)} style={{ backgroundColor: 'var(--bg-secondary)' }}>{m.label}</option>
          ))}
        </select>
        <button
          onClick={onNextMonth}
          disabled={selectedOffset >= 0}
          className="ink-chip focus-ring transition-colors"
          style={{
            padding: '3px 9px', fontSize: '12px',
            opacity: selectedOffset >= 0 ? 0.4 : 1,
          }}
          aria-label="下一月"
        >
          下一期 →
        </button>
      </div>
    </div>
  );
}

/** 统计行 (AIHot style) */
export function MonthlyStatsRow({ stats, total }: { stats: MonthlyStats; total: number }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          {stats.events ?? total}
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>独立事件</div>
      </div>
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          {stats.selected ?? total}
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>条精选</div>
      </div>
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          {stats.daily_reports ?? 0}
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>期日报浓缩</div>
      </div>
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          ≈{stats.reading_time ?? 1} min
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>读完本页</div>
      </div>
    </div>
  );
}

/** 数字盘点 — 领域分布 */
export function MonthlyCategoryPanel({ categoryCounts }: { categoryCounts: Record<string, number> }) {
  return (
    <div>
      <h4 className="text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>领域分布</h4>
      <div className="flex flex-wrap gap-2">
        {Object.entries(categoryCounts).map(([label, count], i) => (
          <span
            key={label}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded"
            style={{
              backgroundColor: `color-mix(in srgb, ${catColors[i % catColors.length]} 10%, transparent)`,
              color: catColors[i % catColors.length],
            }}
          >
            {label}
            <span className="font-mono font-bold">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** 往期月报 (期数 + 月份按钮 + 上一期/下一期) */
export function MonthlyArchivePanel({
  months,
  period,
  selectedOffset,
  onPrevMonth,
  onNextMonth,
  onSwitchToMonth,
}: {
  months: MonthOption[];
  period: MonthlyPeriod;
  selectedOffset: number;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onSwitchToMonth: (value: string) => void;
}) {
  return (
    <div
      className="p-5 rounded-lg"
      style={{ backgroundColor: 'var(--bg-hover)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
          往期月报
        </h4>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {months.length} 期
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {months.map((m) => {
          const isActive = m.label === period.label;
          return (
            <button
              key={m.value}
              onClick={() => !isActive && onSwitchToMonth(m.value)}
              disabled={isActive}
              className="text-xs px-3 py-1.5 rounded transition-colors"
              style={{
                backgroundColor: isActive ? 'color-mix(in srgb, var(--accent) 13%, transparent)' : 'transparent',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border-color)'}`,
                cursor: isActive ? 'default' : 'pointer',
                fontWeight: isActive ? 600 : 400,
              }}
            >
              {m.label}
            </button>
          );
        })}
        {months.length > 0 && (
          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={onPrevMonth}
              className="text-[11px] px-2 py-1 rounded hover:bg-[var(--bg-secondary)] transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              ← 上一期
            </button>
            <button
              onClick={onNextMonth}
              disabled={selectedOffset >= 0}
              className="text-[11px] px-2 py-1 rounded hover:bg-[var(--bg-secondary)] transition-colors"
              style={{ color: selectedOffset >= 0 ? 'var(--border-color)' : 'var(--text-muted)' }}
            >
              下一期 →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
