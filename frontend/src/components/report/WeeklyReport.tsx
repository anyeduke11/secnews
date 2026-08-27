/**
 * report/WeeklyReport — 周报 (AIHot 风格)。
 *
 * 拆自原 ReportPage.tsx (1401 行) 中 WeeklyReportContent (~501-941 行)。
 * 纯结构拆分: 状态/加载/渲染逻辑逐字迁移, 仅将 catColors/renderFormatted
 * 改为引用 utils, 文章行改为共享 HighlightArticleCard。
 */
import { useState, useEffect } from 'react';
import { catColors, renderFormatted } from './utils';
import { HighlightArticleCard } from './shared';
import type { WeeklyOverview } from './types';

export function WeeklyReportContent() {
  const [overview, setOverview] = useState<WeeklyOverview | null>(null);
  const [weeks, setWeeks] = useState<Array<{ value: string; label: string; vol: string }>>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedHighlight, setExpandedHighlight] = useState<string | null>(null);

  // Load available weeks
  useEffect(() => {
    let cancelled = false;
    fetch('/api/reports/weekly/available')
      .then(r => r.ok ? r.json() : { weeks: [] })
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
        const r = await fetch(`/api/reports/weekly/overview?week_start=${selectedWeek}`);
        if (!cancelled && r.ok) {
          const data = await r.json();
          setOverview(data);
        } else if (!cancelled) {
          setError(`加载失败 (${r.status})`);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载失败');
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

  const { period, total, category_counts, main_theme, highlights, stats } = overview;

  return (
    <div className="space-y-6">

      {/* ── VOL Header (AIHot 风格) ── */}
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
            onClick={handlePrevWeek}
            disabled={!selectedWeek || weeks.findIndex(w => w.value === selectedWeek) >= weeks.length - 1}
            className="ink-chip focus-ring transition-colors"
            style={{
              padding: '3px 9px', fontSize: '12px',
              opacity: !selectedWeek || weeks.findIndex(w => w.value === selectedWeek) >= weeks.length - 1 ? 0.4 : 1,
            }}
            aria-label="上一周"
          >
            ← 上一期
          </button>
          <select
            value={selectedWeek || ''}
            onChange={e => setSelectedWeek(e.target.value)}
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
            onClick={handleNextWeek}
            disabled={!selectedWeek || weeks.findIndex(w => w.value === selectedWeek) <= 0}
            className="ink-chip focus-ring transition-colors"
            style={{
              padding: '3px 9px', fontSize: '12px',
              opacity: !selectedWeek || weeks.findIndex(w => w.value === selectedWeek) <= 0 ? 0.4 : 1,
            }}
            aria-label="下一周"
          >
            下一期 →
          </button>
        </div>
      </div>

      {/* ── 本期主线 (AIHot 风格) ── */}
      <div
        className="p-5 rounded-lg"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--accent) 6%, transparent)',
          borderLeft: '4px solid var(--accent)',
        }}
      >
        <h4 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color: 'var(--accent)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 17 10 11 13 14 19 8" />
            <polyline points="14 8 19 8 19 13" />
          </svg>
          本期主线
        </h4>
        <div className="text-xs leading-relaxed whitespace-pre-line" style={{ color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          {renderFormatted(main_theme)}
        </div>
      </div>

      {/* ── Stats Row (AIHot #95 风格) ── */}
      {stats && (
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
      )}

      {/* ── 本期看点 (AIHot 风格) ── */}
      <div>
        <h4 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          本期看点
          <span className="text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>
            {highlights.length} 个主题 · {highlights.reduce((s, h) => s + h.articles.length, 0)} 篇报道
          </span>
        </h4>

        {/* Quick nav — AIHot style numbered links */}
        {highlights.length > 0 && (
          <div className="flex flex-wrap gap-x-5 gap-y-1 mb-4 text-xs">
            {highlights.map((h, idx) => (
              <button
                key={h.id}
                onClick={() => setExpandedHighlight(expandedHighlight === h.id ? null : h.id)}
                className="hover:underline focus-ring"
                style={{ color: 'var(--text-secondary)' }}
              >
                {String(idx + 1).padStart(2, '0')}{h.title}
                <span className="font-mono ml-0.5" style={{ color: 'var(--text-muted)' }}>{h.count}</span>
              </button>
            ))}
          </div>
        )}

        {/* Highlight sections — AIHot style */}
        <div className="space-y-5">
          {highlights.map((h, idx) => (
            <section
              key={h.id}
              className="rounded-lg overflow-hidden"
              style={{ border: '1px solid var(--border-color)' }}
            >
              {/* Section header */}
              <button
                onClick={() => setExpandedHighlight(expandedHighlight === h.id ? null : h.id)}
                className="w-full flex items-center justify-between px-4 py-3 text-left focus-ring transition-colors hover:bg-[var(--bg-hover)]"
                style={{ borderBottom: expandedHighlight === h.id ? '1px solid var(--border-color)' : 'none' }}
              >
                <div className="flex items-center gap-3">
                  <span
                    className="w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
                    style={{
                      backgroundColor: `color-mix(in srgb, ${catColors[idx % catColors.length]} 13%, transparent)`,
                      color: catColors[idx % catColors.length],
                    }}
                  >
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {h.title}
                    </span>
                    <span className="text-[10px] ml-2 font-mono" style={{ color: 'var(--text-muted)' }}>
                      {h.count} 篇
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {expandedHighlight === h.id ? '收起' : '展开'}
                  </span>
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    style={{
                      transform: expandedHighlight === h.id ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s',
                      color: 'var(--text-muted)',
                    }}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </button>

              {/* Expanded content — AIHot style article cards */}
              {expandedHighlight === h.id && (
                <div className="px-4 py-3 space-y-3">
                  {/* Summary */}
                  <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    {h.summary || `本周${h.title}领域共收录${h.count}篇资讯，精选${h.articles.length}篇代表性文章。`}
                  </p>

                  {/* Article cards — AIHot style */}
                  {h.articles.length > 0 && (
                    <div className="space-y-0">
                      {h.articles.map((article, ai) => (
                        <HighlightArticleCard
                          key={article.id}
                          article={article}
                          last={ai === h.articles.length - 1}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      </div>

      {/* ── 往期周报 (AIHot 风格) ── */}
      {weeks.length > 0 && (
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
                  onClick={() => !isActive && setSelectedWeek(w.value)}
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
                onClick={handlePrevWeek}
                disabled={!selectedWeek || weeks.findIndex(w => w.value === selectedWeek) >= weeks.length - 1}
                className="text-[11px] px-3 py-1.5 rounded hover:bg-[var(--bg-secondary)] transition-colors focus-ring"
                style={{
                  color: !selectedWeek || weeks.findIndex(w => w.value === selectedWeek) >= weeks.length - 1 ? 'var(--border-color)' : 'var(--text-muted)',
                  border: '1px solid var(--border-color)',
                }}
              >
                ← 上一期
              </button>
              <button
                onClick={handleNextWeek}
                disabled={!selectedWeek || weeks.findIndex(w => w.value === selectedWeek) <= 0}
                className="text-[11px] px-3 py-1.5 rounded hover:bg-[var(--bg-secondary)] transition-colors focus-ring"
                style={{
                  color: !selectedWeek || weeks.findIndex(w => w.value === selectedWeek) <= 0 ? 'var(--border-color)' : 'var(--text-muted)',
                  border: '1px solid var(--border-color)',
                }}
              >
                下一期 →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
