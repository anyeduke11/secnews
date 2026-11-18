/**
 * report/MonthlyReportHighlights — 月报的「本期看点」区块
 * (快导航 + 主题折叠 + 文章行)。
 *
 * B5.6 拆分: 自 MonthlyReport.tsx 原样搬运, DOM/class/文案逐字不变;
 * 折叠态由容器持有 (expandedHighlight), 本文件只渲染。
 */
import { MonthlyArticleRow } from './shared';
import { ReportHighlightHeader } from './sharedBlocks';
import type { MonthlyHighlight } from './types';

export function MonthlyHighlights({
  highlights,
  expandedHighlight,
  onToggle,
}: {
  highlights: MonthlyHighlight[];
  expandedHighlight: string | null;
  onToggle: (id: string) => void;
}) {
  return (
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
              onClick={() => onToggle(h.id)}
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
            <ReportHighlightHeader
              index={idx}
              title={h.title}
              count={h.count}
              expanded={expandedHighlight === h.id}
              onToggle={() => onToggle(h.id)}
            />

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
  );
}
