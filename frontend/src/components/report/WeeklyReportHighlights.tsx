/**
 * report/WeeklyReportHighlights — 周报的「本期看点」区块
 * (快导航 + 主题折叠 + 文章行)。
 *
 * B5.6 拆分: 自 WeeklyReport.tsx 原样搬运, DOM/class/文案逐字不变;
 * 折叠态由容器持有 (expandedHighlight), 本文件只渲染。
 */
import { HighlightArticleCard } from './shared';
import { ReportHighlightHeader } from './sharedBlocks';
import type { WeeklyHighlight } from './types';

export function WeeklyHighlights({
  highlights,
  expandedHighlight,
  onToggle,
}: {
  highlights: WeeklyHighlight[];
  expandedHighlight: string | null;
  onToggle: (id: string) => void;
}) {
  return (
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
              onClick={() => onToggle(h.id)}
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
            <ReportHighlightHeader
              index={idx}
              title={h.title}
              count={h.count}
              expanded={expandedHighlight === h.id}
              onToggle={() => onToggle(h.id)}
            />

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
  );
}
