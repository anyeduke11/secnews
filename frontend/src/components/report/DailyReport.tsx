/**
 * report/DailyReport — 日报 (AIHot 风格)。
 *
 * 拆自原 ReportPage.tsx (1401 行) 中 DailyReport (~141-453 行)。
 * 纯结构拆分: 状态/加载/渲染逻辑逐字迁移, 仅将 catColors/renderFormatted
 * 改为引用 utils, 文章行改为共享 HighlightArticleCard。
 */
import { useState, useEffect } from 'react';
import { catColors, renderFormatted } from './utils';
import { HighlightArticleCard } from './shared';
import type { DailyOverview } from './types';

export function DailyReport() {
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
