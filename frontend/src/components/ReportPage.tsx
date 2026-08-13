import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { CATEGORIES, getCategoryColorVar, getCategoryLabel, HotspotItem } from '../types';
import { Icon } from './Icon';

interface ReportPageProps {
  onBack: () => void;
}

type Tab = 'daily' | 'weekly' | 'monthly';

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'daily', label: '日报' },
  { id: 'weekly', label: '周报' },
  { id: 'monthly', label: '月报' },
];

// ── helpers ──

function fmtDate(iso: string): string {
  try { const d = new Date(iso); return `${d.getMonth() + 1}/${d.getDate()}`; }
  catch { return iso.slice(5, 10); }
}

/** Render markdown-like formatting (**bold**) in text. */
function renderFormatted(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>;
    }
    if (part.trim().startsWith('-') || part.trim().startsWith('  -')) {
      return <span key={i} className="block">{part}</span>;
    }
    return <span key={i}>{part}</span>;
  });
}

function todayStr(): string {
  const d = new Date();
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${weekdays[d.getDay()]}`;
}

function monthStr(offset = 0): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
}

// ── shared sub-components ──

function CategoryBar({ summary }: { summary: Record<string, number> }) {
  const total = Object.values(summary).filter(v => typeof v === 'number').reduce((a, b) => a + b, 0) || 1;
  const segments = CATEGORIES.filter(c => c.id !== 'all' && (summary[c.id] || 0) > 0).map(c => ({
    id: c.id, count: summary[c.id] || 0, color: c.color,
    pct: ((summary[c.id] || 0) / total) * 100,
  }));
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-4 rounded-full overflow-hidden flex" style={{ backgroundColor: 'var(--bg-hover)' }}>
        {segments.map(s => (
          <div key={s.id} style={{ width: `${s.pct}%`, backgroundColor: s.color, minWidth: s.pct > 0 ? 2 : 0 }} title={`${getCategoryLabel(s.id)}: ${s.count}`} />
        ))}
      </div>
      <span className="text-xs font-mono tabular-nums shrink-0" style={{ color: 'var(--text-secondary)' }}>{total}</span>
    </div>
  );
}

function ItemList({ items, max = 10 }: { items: HotspotItem[]; max?: number }) {
  const slice = items.slice(0, max);
  if (slice.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {slice.map((item, i) => (
        <div key={item.id || i} className="flex items-start gap-2 text-xs">
          <span className="font-mono shrink-0" style={{ color: 'var(--text-muted)', width: 20 }}>{i + 1}.</span>
          <a
            href={item.url} target="_blank" rel="noreferrer"
            className="truncate hover:underline flex-1 min-w-0"
            style={{ color: 'var(--text-primary)' }}
            title={item.title}
          >
            {item.title}
          </a>
          <span className="shrink-0 px-1.5 rounded text-[10px] whitespace-nowrap" style={{
            backgroundColor: `color-mix(in srgb, ${getCategoryColorVar(item.category)} 13%, transparent)`,
            color: getCategoryColorVar(item.category),
          }}>
            {getCategoryLabel(item.category)}
          </span>
        </div>
      ))}
      {items.length > max && (
        <div className="text-[10px] pl-7" style={{ color: 'var(--text-muted)' }}>还有 {items.length - max} 条…</div>
      )}
    </div>
  );
}

// ── Daily Report Types ──

interface DailyHighlightArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  url: string;
  score: number;
}

interface DailyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: DailyHighlightArticle[];
}

interface DailyStats {
  events: number;
  selected: number;
  sources: number;
  reading_time: number;
}

interface DailyOverview {
  date: string;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  hot_analysis: string;
  highlights: DailyHighlight[];
  other_news: Array<{ id: string; title: string; url: string; source: string; category: string; category_label: string }>;
  stats: DailyStats;
  generated_at: string;
}

// ── Daily Report (AIHot 风格) ──

function DailyReport() {
  const [overview, setOverview] = useState<DailyOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedHighlight, setExpandedHighlight] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch('/api/reports/daily/overview');
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
  }, []);

  const catColors = [
    '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B',
    '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6',
  ];

  if (loading) {
    return <div className="text-center py-12 text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>;
  }
  if (error) {
    return <div className="px-3 py-2 rounded text-xs" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 13%, transparent)', color: 'var(--color-error)' }}>{error}</div>;
  }
  if (!overview) {
    return (
      <div className="text-center py-12 text-xs" style={{ color: 'var(--text-muted)' }}>
        暂无日报数据
      </div>
    );
  }

  const { date, total, main_theme, hot_analysis, highlights, other_news, stats } = overview;

  return (
    <div className="space-y-6">

      {/* ── Header (AIHot style) ── */}
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div>
          <div className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--text-muted)' }}>
            HOTSPOT DAILY · {total} STORIES · 每日八时
          </div>
          <h3 className="text-lg font-bold tracking-tight mt-1" style={{ color: 'var(--text-primary)' }}>
            {date}
          </h3>
          <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            今日看点 {total} 篇报道 · 约 {stats.reading_time ?? 1} 分钟
          </p>
        </div>
      </div>

      {/* ── 本期主线 (500字, 含加粗标记) ── */}
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

      {/* ── 热点分析 ── */}
      <div
        className="p-5 rounded-lg"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--color-warning) 6%, transparent)',
          borderLeft: '4px solid var(--color-warning)',
        }}
      >
        <h4 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color: 'var(--color-warning)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          热点分析
        </h4>
        <div className="text-xs leading-relaxed whitespace-pre-line font-mono" style={{ color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          {renderFormatted(hot_analysis)}
        </div>
      </div>

      {/* ── Stats Row ── */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
            <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
              #{stats.events ?? total}
            </div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>今日事件</div>
          </div>
          <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
            <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
              #{stats.selected ?? total}
            </div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>一手报道</div>
          </div>
          <div className="text-center p-4 rounded-lg" style={{ backgroundColor: 'var(--bg-hover)' }}>
            <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--accent)' }}>
              #{stats.sources ?? 0}
            </div>
            <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>信源</div>
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
        <div className="space-y-4">
          {highlights.map((h, idx) => (
            <section
              key={h.id}
              className="rounded-lg overflow-hidden"
              style={{ border: '1px solid var(--border-color)' }}
            >
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

              {expandedHighlight === h.id && (
                <div className="px-4 py-3 space-y-3">
                  <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                    {h.summary || `今日${h.title}领域共收录${h.count}篇资讯，精选${h.articles.length}篇代表性文章。`}
                  </p>

                  {h.articles.length > 0 && (
                    <div className="space-y-0">
                      {h.articles.map((article, ai) => (
                        <div
                          key={article.id}
                          className="py-2.5 px-3 -mx-3 rounded transition-colors hover:bg-[var(--bg-hover)]"
                          style={{ borderBottom: ai < h.articles.length - 1 ? '1px solid var(--border-light)' : 'none' }}
                        >
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noreferrer"
                            className="block"
                          >
                            <div className="flex items-start gap-2">
                              <span className="text-[11px] font-medium leading-snug flex-1 min-w-0 hover:underline" style={{ color: 'var(--text-primary)' }}>
                                {article.title}
                              </span>
                              <span className="shrink-0 text-[10px] px-2 py-0.5 rounded whitespace-nowrap" style={{ color: 'var(--accent)', border: '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' }}>
                                阅读 →
                              </span>
                            </div>
                          </a>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                              {article.source}
                            </span>
                            {article.score > 0 && (
                              <span className="text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
                                {article.score}分
                              </span>
                            )}
                          </div>
                          {article.summary && (
                            <p className="text-[10px] mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                              {article.summary.slice(0, 120)}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      </div>

      {/* ── 其他关键资讯 (AIHot style — 仅标题，支持跳转) ── */}
      {other_news.length > 0 && (
        <div
          className="p-5 rounded-lg"
          style={{ backgroundColor: 'var(--bg-hover)' }}
        >
          <h4 className="text-xs font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
            其他关键资讯
            <span className="text-[10px] font-normal font-mono" style={{ color: 'var(--text-muted)' }}>
              {other_news.length} 条
            </span>
          </h4>
          <div className="space-y-0">
            {other_news.map((item, i) => (
              <div
                key={item.id}
                className="flex items-center gap-2 py-2 px-2 -mx-2 rounded transition-colors hover:bg-[var(--bg-secondary)]"
                style={{ borderBottom: i < other_news.length - 1 ? '1px solid var(--border-light)' : 'none' }}
              >
                <span className="text-[10px] font-mono shrink-0" style={{ color: 'var(--text-muted)', width: 20 }}>{i + 1}.</span>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[11px] flex-1 min-w-0 truncate hover:underline"
                  style={{ color: 'var(--text-primary)' }}
                  title={item.title}
                >
                  {item.title}
                </a>
                <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded" style={{
                  backgroundColor: `color-mix(in srgb, ${catColors[Math.abs(item.category.charCodeAt(0) || 0) % catColors.length]} 10%, transparent)`,
                  color: catColors[Math.abs(item.category.charCodeAt(0) || 0) % catColors.length],
                }}>
                  {item.category_label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Weekly Report Types ──

interface WeeklyPeriod {
  label: string;
  vol: string;
  start: string;
  end: string;
  week_start: string;
}

interface WeeklyStats {
  events: number;
  selected: number;
  daily_reports: number;
  reading_time: number;
}

interface WeeklyHighlightArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  url: string;
  score: number;
}

interface WeeklyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: WeeklyHighlightArticle[];
}

interface WeeklyOverview {
  period: WeeklyPeriod;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  highlights: WeeklyHighlight[];
  stats: WeeklyStats;
  generated_at: string;
}

// ── Weekly Report ──

function WeeklyReportContent() {
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

  const catColors = [
    '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B',
    '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6',
  ];

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
                        <div
                          key={article.id}
                          className="py-2.5 px-3 -mx-3 rounded transition-colors hover:bg-[var(--bg-hover)]"
                          style={{ borderBottom: ai < h.articles.length - 1 ? '1px solid var(--border-light)' : 'none' }}
                        >
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noreferrer"
                            className="block"
                          >
                            <div className="flex items-start gap-2">
                              <span className="text-[11px] font-medium leading-snug flex-1 min-w-0 hover:underline" style={{ color: 'var(--text-primary)' }}>
                                {article.title}
                              </span>
                              <span className="shrink-0 text-[10px] px-2 py-0.5 rounded whitespace-nowrap" style={{ color: 'var(--accent)', border: '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' }}>
                                阅读 →
                              </span>
                            </div>
                          </a>
                          {/* Source + score */}
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                              {article.source}
                            </span>
                            {article.score > 0 && (
                              <span className="text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
                                {article.score}分
                              </span>
                            )}
                          </div>
                          {article.summary && (
                            <p className="text-[10px] mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                              {article.summary.slice(0, 120)}
                            </p>
                          )}
                        </div>
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

// ── Monthly Report Types ──

interface MonthlyPeriod {
  label: string;
  start: string;
  end: string;
  offset: number;
}

interface HighlightArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  url: string;
  score: number;
}

interface MonthlyHighlight {
  id: string;
  title: string;
  count: number;
  summary: string;
  articles: HighlightArticle[];
}

interface MonthlyStats {
  events: number;
  selected: number;
  daily_reports: number;
  reading_time: number;
}

interface MonthlyOverview {
  period: MonthlyPeriod;
  total: number;
  category_counts: Record<string, number>;
  main_theme: string;
  highlights: MonthlyHighlight[];
  stats: MonthlyStats;
  generated_at: string;
}

// ── Monthly Report ──

function MonthlyReport() {
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

  // Derive unique category color for number badge
  const catColors = [
    '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B',
    '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6',
  ];

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
                        <div
                          key={article.id}
                          className="flex items-start gap-3 py-2.5 px-3 -mx-3 rounded transition-colors hover:bg-[var(--bg-hover)]"
                          style={{ borderBottom: ai < h.articles.length - 1 ? '1px solid var(--border-light)' : 'none' }}
                        >
                          <span className="text-[10px] font-mono shrink-0 mt-0.5" style={{ color: 'var(--text-muted)', width: 16, textAlign: 'right' }}>
                            {ai + 1}.
                          </span>
                          <div className="flex-1 min-w-0">
                            <a
                              href={article.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-xs font-medium hover:underline truncate block"
                              style={{ color: 'var(--text-primary)' }}
                              title={article.title}
                            >
                              {article.title}
                            </a>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                                {article.source}
                              </span>
                              {article.score > 0 && (
                                <span className="text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
                                  {article.score}分
                                </span>
                              )}
                            </div>
                            {article.summary && (
                              <p className="text-[10px] mt-0.5 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                                {article.summary.slice(0, 120)}
                              </p>
                            )}
                          </div>
                          <a
                            href={article.url}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 text-[10px] px-2 py-0.5 rounded transition-colors hover:bg-[var(--bg-secondary)]"
                            style={{ color: 'var(--accent)', border: '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' }}
                          >
                            阅读 →
                          </a>
                        </div>
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

// ── Main ReportPage ──

export function ReportPage({ onBack }: ReportPageProps) {
  const [activeTab, setActiveTab] = useState<Tab>('daily');

  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab);
  }, []);

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="btn-ghost px-2 py-1.5 text-xs" aria-label="返回首页">
          <Icon><polyline points="15 18 9 12 15 6" /></Icon>
        </button>
        <div>
          <h2 className="text-base font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </Icon>
            报告
          </h2>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>本系统资讯与标讯 · 自动聚合报告</p>
        </div>
      </div>

      {/* Tab 导航 */}
      <div className="flex items-center gap-1 pb-2" style={{ borderBottom: '1px solid var(--border-color)' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className="ink-chip focus-ring transition-colors"
            style={{
              padding: '4px 14px',
              fontSize: '13px',
              fontWeight: activeTab === tab.id ? 600 : 400,
              backgroundColor: activeTab === tab.id ? 'var(--accent)' : 'transparent',
              color: activeTab === tab.id ? 'var(--text-on-light)' : 'var(--text-secondary)',
            }}
            aria-current={activeTab === tab.id ? 'page' : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 内容 */}
      {activeTab === 'daily' && <DailyReport />}
      {activeTab === 'weekly' && <WeeklyReportContent />}
      {activeTab === 'monthly' && <MonthlyReport />}
    </div>
  );
}