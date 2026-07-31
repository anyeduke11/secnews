/**
 * LeadStory — v1.9 Editorial 头版头条（agihunt 报纸风）。
 * serif 大标题 + dropcap 首字下沉摘要；仅首页第一页第一条使用。
 */
import React from 'react';
import {
  HotspotItem, getCategoryLabel, getCategoryColorVar, formatRelativeTime,
} from '../types';

interface LeadStoryProps {
  item: HotspotItem;
  isFavorited?: boolean;
  onToggleFavorite?: (item: HotspotItem) => void;
}

export function LeadStory({ item, isFavorited = false, onToggleFavorite }: LeadStoryProps) {
  const color = getCategoryColorVar(item.category);

  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(item);
  };

  return (
    <article className="pb-5 mb-1" style={{ borderBottom: '1px solid var(--border-color)' }}>
      <div className="flex items-center gap-2 mb-2 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
        <span className="font-bold tracking-[0.12em] uppercase" style={{ color: 'var(--accent)' }}>
          头条
        </span>
        <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
        <span className="font-semibold tracking-wide uppercase" style={{ color }}>
          {getCategoryLabel(item.category)}
        </span>
        {item.source && (
          <>
            <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
            <span className="truncate max-w-[160px]">{item.source}</span>
          </>
        )}
        <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
        <span className="font-mono tabular-nums">{formatRelativeTime(item.published_at)}</span>
        <button
          onClick={handleStarClick}
          className="ml-auto p-1 rounded-sm transition-colors focus-ring shrink-0"
          style={{ color: isFavorited ? 'var(--accent)' : 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
          title={isFavorited ? '取消收藏' : '收藏'}
          aria-label={isFavorited ? '取消收藏' : '收藏'}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </button>
      </div>

      <h2
        className="font-serif font-bold"
        style={{ fontSize: 'clamp(22px, 3vw, 30px)', lineHeight: 1.25, color: 'var(--text-primary)' }}
      >
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="focus-ring transition-colors hover:text-[var(--accent)]"
        >
          {item.title}
        </a>
      </h2>

      {item.summary && (
        <p className="dropcap font-serif text-[15px] leading-[1.7] mt-2.5" style={{ color: 'var(--text-secondary)' }}>
          {item.summary}
        </p>
      )}
    </article>
  );
}
