/**
 * report/WeeklyReportBlocks — 周报的纯展示区块 (VOL 头部 / 统计行 / 往期周报)。
 *
 * B5.6 拆分: 自 WeeklyReport.tsx 原样搬运, DOM/class/aria 文案逐字不变;
 * 取数与状态编排全部留在 WeeklyReport 容器。
 */
import type { WeeklyPeriod, WeeklyStats } from './types';

/** 可选周条目 (GET /api/reports/weekly/available 的 weeks 元素) */
export interface WeekOption {
  value: string;
  label: string;
  vol: string;
}

/** 上一期 / 下一期的可用态 (头部与往期面板共用同一判定) */
export function weekNavState(weeks: WeekOption[], selectedWeek: string | null) {
  const idx = weeks.findIndex(w => w.value === selectedWeek);
  return {
    prevDisabled: !selectedWeek || idx >= weeks.length - 1,
    nextDisabled: !selectedWeek || idx <= 0,
  };
}

/** VOL 头部 (期号 / 标题 / 周期切换器) */
export function WeeklyReportHeader({
  period,
  total,
  weeks,
  selectedWeek,
  onSelectWeek,
  onPrevWeek,
  onNextWeek,
}: {
  period: WeeklyPeriod;
  total: number;
  weeks: WeekOption[];
  selectedWeek: string | null;
  onSelectWeek: (value: string) => void;
  onPrevWeek: () => void;
  onNextWeek: () => void;
}) {
  const { prevDisabled, nextDisabled } = weekNavState(weeks, selectedWeek);
  return (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <div>
        <div className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--text-muted)' }}>
          VOL.{period.vol} · {total} STORIES · HOTSPOT 周报
        </div>
        <h3 className="text-xl font-bold tracking-tight mt-1" style={{ color: 'var(--text-primary)' }}>
          {period.label}周报
        </h3>
        <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {period.start.slice(0, 10).replace(/-/g, '-')} ~ {period.end.slice(0, 10).replace(/-/g, '-')}
          {' · '}WEEKLY · 编辑系统自动综合
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onPrevWeek}
          disabled={prevDisabled}
          className="ink-chip focus-ring transition-colors"
          style={{
            padding: '3px 9px', fontSize: '12px',
            opacity: prevDisabled ? 0.4 : 1,
          }}
          aria-label="上一周"
        >
          ← 上一期
        </button>
        <select
          value={selectedWeek || ''}
          onChange={e => onSelectWeek(e.target.value)}
          className="text-xs px-2 py-1 rounded focus-ring"
          style={{
            backgroundColor: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
          }}
        >
          {weeks.map(w => (
            <option key={w.value} value={w.value} style={{ backgroundColor: 'var(--bg-secondary)' }}>{w.label}</option>
          ))}
        </select>
        <button
          onClick={onNextWeek}
          disabled={nextDisabled}
          className="ink-chip focus-ring transition-colors"
          style={{
            padding: '3px 9px', fontSize: '12px',
            opacity: nextDisabled ? 0.4 : 1,
          }}
          aria-label="下一周"
        >
          下一期 →
        </button>
      </div>
    </div>
  );
}

/** 统计行 (AIHot #95 风格) */
export function WeeklyStatsRow({ stats, total }: { stats: WeeklyStats; total: number }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          #{stats.events ?? total}
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>独立事件</div>
      </div>
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          #{stats.selected ?? total}
        </div>
        <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>条精选</div>
      </div>
      <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
          #{stats.daily_reports ?? 0}
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

/** 往期周报 (期数 + 期次按钮 + 上一期/下一期) */
export function WeeklyArchivePanel({
  weeks,
  selectedWeek,
  onSelectWeek,
  onPrevWeek,
  onNextWeek,
}: {
  weeks: WeekOption[];
  selectedWeek: string | null;
  onSelectWeek: (value: string) => void;
  onPrevWeek: () => void;
  onNextWeek: () => void;
}) {
  const { prevDisabled, nextDisabled } = weekNavState(weeks, selectedWeek);
  return (
    <div
      className="p-5 rounded-lg"
      style={{ backgroundColor: 'var(--bg-hover)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
          往期周报
        </h4>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {weeks.length} 期
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {weeks.map(w => {
          const isActive = w.value === selectedWeek;
          return (
            <button
              key={w.value}
              onClick={() => !isActive && onSelectWeek(w.value)}
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
              {w.label}
            </button>
          );
        })}
      </div>
      {weeks.length > 0 && (
        <div className="flex items-center gap-2 mt-4">
          <button
            onClick={onPrevWeek}
            disabled={prevDisabled}
            className="text-[11px] px-3 py-1.5 rounded hover:bg-[var(--bg-secondary)] transition-colors focus-ring"
            style={{
              color: prevDisabled ? 'var(--border-color)' : 'var(--text-muted)',
              border: '1px solid var(--border-color)',
            }}
          >
            ← 上一期
          </button>
          <button
            onClick={onNextWeek}
            disabled={nextDisabled}
            className="text-[11px] px-3 py-1.5 rounded hover:bg-[var(--bg-secondary)] transition-colors focus-ring"
            style={{
              color: nextDisabled ? 'var(--border-color)' : 'var(--text-muted)',
              border: '1px solid var(--border-color)',
            }}
          >
            下一期 →
          </button>
        </div>
      )}
    </div>
  );
}
