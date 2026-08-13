/**
 * report/MonthlyReport — 月报。
 *
 * 拆自原 ReportPage.tsx (1401 行) 中 MonthlyReport (~942-1343 行)。
 * 纯结构拆分: 状态/加载/渲染逻辑逐字迁移, 仅将 catColors/renderFormatted
 * 改为引用 utils, 文章行改为共享 MonthlyArticleRow。
 */
import React, { useState, useEffect } from 'react';
import { catColors, renderFormatted } from './utils';
import { MonthlyArticleRow } from './shared';
import type { MonthlyOverview } from './types';

export function MonthlyReport() {
  const [overview, setOverview] = useState<MonthlyOverview | null>(null);
  const [months, setMonths] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedOffset, setSelectedOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedHighlight, setExpandedHighlight] = useState<string | null>(null);

  // Load available months
  useEffect(() => {
    let cancelled = false;
    fetch('/api/reports/monthly/available')
      .then(r => r.ok ? r.json() : { months: [] })
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
        const r = await fetch(`/api/reports/monthly/overview?offset=${selectedOffset}`);
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
            onClick={handlePrevMonth}
            className="ink-chip focus-ring transition-colors"
            style={{ padding: '3px 9px', fontSize: '12px' }}
            aria-label="上一月"
          >
            ← 上一期
          </button>
          <select
            value={selectedOffset}
            onChange={handleMonthSelect}
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
            onClick={handleNextMonth}
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

      {/* ── 本期主线 ── */}
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

      {/* ── Stats Row (AIHot style) ── */}
      {stats && (
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
      )}

      {/* ── 数字盘点 ── */}
      <div>
        <h4 className="text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>领域分布</h4>
        <div className="flex flex-wrap gap-2">
          {Object.entries(category_counts).map(([label, count], i) => (
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

      {/* ── 本期看点 ── */}
      <div>
        <h4 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          本期看点
          <span className="text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>
            {highlights.length} 个主题 · {highlights.reduce((s, h) => s + h.articles.length, 0)} 篇报道
          </span>
        </h4>

        {/* Quick nav */}
        {highlights.length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 mb-4 text-xs" style={{ color: 'var(--text-muted)' }}>
            {highlights.map((h, idx) => (
              <button
                key={h.id}
                onClick={() => setExpandedHighlight(expandedHighlight === h.id ? null : h.id)}
                className="hover:underline focus-ring"
                style={{ color: 'var(--text-secondary)' }}
              >
                {String(idx + 1).padStart(2, '0')} {h.title}
                <span className="font-mono ml-0.5" style={{ color: 'var(--text-muted)' }}>{h.count}</span>
              </button>
            ))}
          </div>
        )}

        <div className="space-y-4">
          {highlights.map((h, idx) => (
            <section
              key={h.id}
              className="rounded-lg overflow-hidden"
              style={{ border: '1px solid var(--border-color)' }}
            >
              {/* ── 看点头部 ── */}
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

              {/* ── 看点详情 ── */}
              {expandedHighlight === h.id && (
                <div className="px-4 py-3 space-y-3">
                  <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    {h.summary || `本月${h.title}领域共收录${h.count}篇资讯，精选${h.articles.length}篇代表性文章。`}
                  </p>
                  {h.articles.length > 0 && (
                    <div className="space-y-0">
                      {h.articles.map((article, ai) => (
                        <MonthlyArticleRow
                          key={article.id}
                          article={article}
                          index={ai}
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

      {/* ── 往期月报 ── */}
      {months.length > 0 && (
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
            {months.map((m, mi) => {
              const isActive = m.label === period.label;
              return (
                <button
                  key={m.value}
                  onClick={() => !isActive && switchToMonth(m.value)}
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
                  onClick={handlePrevMonth}
                  className="text-[11px] px-2 py-1 rounded hover:bg-[var(--bg-secondary)] transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                >
                  ← 上一期
                </button>
                <button
                  onClick={handleNextMonth}
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
      )}
    </div>
  );
}
