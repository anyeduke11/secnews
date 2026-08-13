/**
 * report/shared — ReportPage 共享子组件。
 *
 * 拆自原 ReportPage.tsx (1401 行):
 *   - CategoryBar / ItemList: 共享子组件 (原文件保留但未在页面中挂载, 此处原样迁移)
 *   - HighlightArticleCard: 日报/周报共用的"看点文章行" (原内联 JSX 提取, 渲染等价)
 *   - MonthlyArticleRow: 月报专用的"看点文章行" (原内联 JSX 提取, 渲染等价)
 */
import { CATEGORIES, getCategoryColorVar, getCategoryLabel, HotspotItem } from '../../types';
import type { ReportHighlightArticle } from './types';

export function CategoryBar({ summary }: { summary: Record<string, number> }) {
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

export function ItemList({ items, max = 10 }: { items: HotspotItem[]; max?: number }) {
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

/**
 * 日报/周报共用的看点文章行 (原 DailyReport / WeeklyReportContent 内联 JSX, 渲染等价)。
 * `last` 控制底部分隔线。
 */
export function HighlightArticleCard({ article, last }: { article: ReportHighlightArticle; last: boolean }) {
  return (
    <div
      className="py-2.5 px-3 -mx-3 rounded transition-colors hover:bg-[var(--bg-hover)]"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border-light)' }}
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
  );
}

/**
 * 月报专用的看点文章行 (带序号 + 右侧"阅读 →"链接, 原 MonthlyReport 内联 JSX, 渲染等价)。
 * `index` 为 0-based 序号, `last` 控制底部分隔线。
 */
export function MonthlyArticleRow({ article, index, last }: { article: ReportHighlightArticle; index: number; last: boolean }) {
  return (
    <div
      className="flex items-start gap-3 py-2.5 px-3 -mx-3 rounded transition-colors hover:bg-[var(--bg-hover)]"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border-light)' }}
    >
      <span className="text-[10px] font-mono shrink-0 mt-0.5" style={{ color: 'var(--text-muted)', width: 16, textAlign: 'right' }}>
        {index + 1}.
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
  );
}
