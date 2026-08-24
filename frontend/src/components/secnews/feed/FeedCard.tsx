/**
 * FeedCard — 单条资讯卡片
 *
 * 报纸风格的单条安全资讯展示。
 */
interface FeedCardProps {
  item: {
    id: string;
    title: string;
    url: string;
    source: string;
    category: string;
    summary?: string;
    published_at?: string;
  };
}

export function FeedCard({ item }: FeedCardProps) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block p-3 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
      style={{ border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium leading-snug line-clamp-2" style={{ color: 'var(--text-primary)' }}>
            {item.title}
          </h3>
          {item.summary && (
            <p className="text-xs mt-1 line-clamp-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {item.summary}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
              {item.source}
            </span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
              {item.category}
            </span>
          </div>
        </div>
      </div>
    </a>
  );
}
