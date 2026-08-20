/**
 * AgihuntCard — agihunt 风格资讯卡片。
 * 3 列网格布局用，含分类徽标、标题、摘要、来源、原文链接按钮。
 */
import React from 'react';
import {
  HotspotItem, getCategoryLabel, getCategoryColorVar,
  getBidStatusColor, formatRelativeTime,
} from '../types';

/** 剥离 HTML 标签，保留纯文本 */
function stripHtml(text: string): string {
  return text.replace(/<[^>]+>/g, '').trim();
}

interface AgihuntCardProps {
  item: HotspotItem;
  index: number;
  isFavorited?: boolean;
  onToggleFavorite?: (item: HotspotItem) => void;
  onCategoryClick?: (category: string) => void;
  onSourceClick?: (source: string) => void;
}

function AgihuntCardComponent({
  item, index, isFavorited = false,
  onToggleFavorite, onCategoryClick, onSourceClick,
}: AgihuntCardProps) {
  const color = getCategoryColorVar(item.category);
  const delayClass = `delay-${Math.min(index + 1, 10)}`;

  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(item);
  };

  return (
    <article className={`agihunt-card animate-fade-in-up ${delayClass}`}>
      {/* 顶部: 分类徽标 + 时间 */}
      <div className="agihunt-card-header">
        <button
          type="button"
          onClick={() => onCategoryClick?.(item.category)}
          className="agihunt-card-badge focus-ring"
          style={{ color, borderColor: `color-mix(in srgb, ${color} 40%, transparent)` }}
          title={`查看分类: ${getCategoryLabel(item.category)}`}
        >
          {getCategoryLabel(item.category)}
        </button>
        <span className="agihunt-card-time">
          {formatRelativeTime(item.published_at)}
        </span>
      </div>

      {/* 标题 */}
      <h3 className="agihunt-card-title">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="focus-ring"
        >
          {item.title}
        </a>
      </h3>

      {/* 摘要 */}
      {item.summary && (
        <p className="agihunt-card-summary">
          {stripHtml(item.summary)}
        </p>
      )}

      {/* 底部: 来源 + 操作按钮 */}
      <div className="agihunt-card-footer">
        <div className="agihunt-card-meta">
          {item.source && (
            <button
              type="button"
              onClick={() => onSourceClick?.(item.source!)}
              className="agihunt-card-source focus-ring"
              title={`只看来源: ${item.source}`}
            >
              {item.source}
            </button>
          )}
          {item.category === 'bid' && item.bid_status && item.bid_status !== '其他' && (
            <span className="editorial-badge" style={{ color: getBidStatusColor(item.bid_status), borderColor: 'currentColor' }}>
              {item.bid_status}
            </span>
          )}
        </div>

        <div className="agihunt-card-actions">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="agihunt-card-link focus-ring"
          >
            阅读原文
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
          <button
            onClick={handleStarClick}
            className="agihunt-card-star focus-ring"
            style={{ color: isFavorited ? 'var(--accent)' : 'var(--text-muted)' }}
            title={isFavorited ? '取消收藏' : '收藏'}
            aria-label={isFavorited ? '取消收藏' : '收藏'}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </button>
        </div>
      </div>
    </article>
  );
}

// P2.1: React.memo 包裹 — 大数据列表 (pageSize 达 400) 时防止无谓重渲染。
// 浅比较 item/isFavorited 引用; item 引用不变 (翻页/收藏状态变换) 时跳过重渲染。
export const AgihuntCard = React.memo(AgihuntCardComponent);