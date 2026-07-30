import React from 'react';
import {
  HotspotItem,
  getCategoryColor,
  getCategoryLabel,
  getQualityColor,
  getBidStatusColor,
  formatRelativeTime,
} from '../types';

interface HotspotCardProps {
  item: HotspotItem;
  index: number;
  isFavorited?: boolean;
  onToggleFavorite?: (item: HotspotItem) => void;
}

export function HotspotCard({ item, index, isFavorited = false, onToggleFavorite }: HotspotCardProps) {
  const color = getCategoryColor(item.category);
  const delayClass = `delay-${Math.min(index + 1, 10)}`;

  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(item);
  };

  const hasQualityNote = item.quality_flags?.includes('title_replaced');
  const isVerified = item.url_check_status === 'verified' && !hasQualityNote;

  return (
    <article
      className={`editorial-card animate-fade-in-up ${delayClass} flex flex-col h-full`}
    >
      <div className="flex items-start justify-between gap-2 px-3.5 pt-3 pb-2">
        <span
          className="editorial-badge"
          style={{ backgroundColor: `${color}15`, color }}
        >
          {getCategoryLabel(item.category)}
        </span>
        <span className="text-[11px] shrink-0 font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
          {formatRelativeTime(item.published_at)}
        </span>
      </div>

      <div className="px-3.5 pb-2 flex-1">
        <h3 className="text-sm font-semibold leading-snug" style={{ color: 'var(--text-primary)' }}>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline decoration-from-font"
            style={{ textDecorationColor: `${color}50`, textUnderlineOffset: '2px' }}
          >
            {item.title}
          </a>
        </h3>
        {item.summary && (
          <p className="text-xs leading-relaxed mt-1.5 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
            {item.summary}
          </p>
        )}
      </div>

      <div className="px-3.5 pb-3 flex items-center justify-between gap-2" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 8 }}>
        <div className="flex flex-wrap items-center gap-1.5">
          {item.category === 'bid' && item.bid_status && item.bid_status !== '其他' && (
            <span
              className="editorial-badge"
              style={{
                backgroundColor: `${getBidStatusColor(item.bid_status)}15`,
                color: getBidStatusColor(item.bid_status),
              }}
            >
              {item.bid_status}
            </span>
          )}

          {hasQualityNote && (
            <span className="status-icon warning" title="同 URL 存在多条记录, 详情页 <title> 验证后以另一条标题为准">
              !
            </span>
          )}

          {isVerified && (
            <span className="status-icon success" title="URL 已验证">
              <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
          )}

          {item.source && (
            <span className="text-[10px] font-mono truncate max-w-[100px]" style={{ color: 'var(--text-muted)' }}>
              {item.source}
            </span>
          )}
        </div>

        <button
          onClick={handleStarClick}
          className="shrink-0 p-0.5 rounded-sm transition-colors focus-ring"
          style={{ color: isFavorited ? 'var(--color-finance)' : 'var(--text-disabled)' }}
          title={isFavorited ? '取消收藏' : '收藏'}
          aria-label={isFavorited ? '取消收藏' : '收藏'}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </button>
      </div>
    </article>
  );
}