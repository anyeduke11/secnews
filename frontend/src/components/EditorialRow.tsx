/**
 * EditorialRow — v1.9 Editorial 信息流条目行（agihunt 报纸风）。
 * 无卡片无阴影，1px 下边线分隔；serif 标题 hover 变 accent；操作按钮 hover 浮现。
 * v1.9.1: 分类/来源可点击筛选 (与 LeadStory 一致)。
 */
import React from 'react';
import {
  HotspotItem, getCategoryLabel, getCategoryColorVar, getBidStatusColor,
  formatRelativeTime,
} from '../types';

interface EditorialRowProps {
  item: HotspotItem;
  isFavorited?: boolean;
  onToggleFavorite?: (item: HotspotItem) => void;
  onCategoryClick?: (category: string) => void;
  onSourceClick?: (source: string) => void;
}

export function EditorialRow({
  item, isFavorited = false, onToggleFavorite, onCategoryClick, onSourceClick,
}: EditorialRowProps) {
  const color = getCategoryColorVar(item.category);
  const hasQualityNote = item.quality_flags?.includes('title_replaced');
  const isVerified = item.url_check_status === 'verified' && !hasQualityNote;

  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(item);
  };

  return (
    <article className="feed-row">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* meta 行: 分类 · 来源 · 时间 · 状态 */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
            <button
              type="button"
              onClick={() => onCategoryClick?.(item.category)}
              className="font-semibold tracking-wide uppercase focus-ring transition-opacity hover:opacity-70"
              style={{ color, background: 'none', border: 'none', padding: '4px 4px', margin: '-4px -4px', cursor: 'pointer', fontSize: 'inherit', fontFamily: 'inherit' }}
              title={`查看分类: ${getCategoryLabel(item.category)}`}
            >
              {getCategoryLabel(item.category)}
            </button>
            {item.category === 'bid' && item.bid_status && item.bid_status !== '其他' && (
              <span className="editorial-badge" style={{ color: getBidStatusColor(item.bid_status), borderColor: 'currentColor' }}>
                {item.bid_status}
              </span>
            )}
            {item.source && (
              <>
                <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
                <button
                  type="button"
                  onClick={() => onSourceClick?.(item.source!)}
                  className="truncate max-w-[140px] focus-ring transition-colors hover:text-[var(--accent)]"
                  style={{ background: 'none', border: 'none', padding: '4px 4px', margin: '-4px -4px', cursor: 'pointer', fontSize: 'inherit', fontFamily: 'inherit', color: 'inherit' }}
                  title={`只看来源: ${item.source}`}
                >
                  {item.source}
                </button>
              </>
            )}
            <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
            <span className="font-mono tabular-nums">{formatRelativeTime(item.published_at)}</span>
            {hasQualityNote && (
              <span className="status-icon warning" title="同 URL 存在多条记录, 详情页 <title> 验证后以另一条标题为准">!</span>
            )}
            {isVerified && (
              <span className="status-icon success" title="URL 已验证">
                <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </span>
            )}
          </div>

          <h3 className="feed-title">
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="focus-ring">
              {item.title}
            </a>
          </h3>

          {item.summary && (
            <p className="text-[13px] leading-relaxed mt-1.5 line-clamp-2 max-w-[70ch]" style={{ color: 'var(--text-secondary)' }}>
              {item.summary}
            </p>
          )}
        </div>

        <div className="feed-actions shrink-0 pt-0.5">
          <button
            onClick={handleStarClick}
            className="p-2 -m-1 rounded-sm transition-colors focus-ring"
            style={{ color: isFavorited ? 'var(--accent)' : 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
            title={isFavorited ? '取消收藏' : '收藏'}
            aria-label={isFavorited ? '取消收藏' : '收藏'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </button>
        </div>
      </div>
    </article>
  );
}
