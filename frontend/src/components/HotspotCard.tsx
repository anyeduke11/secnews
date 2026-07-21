/**
 * HotspotCard — 单条热点卡片。
 *
 * Phase 2: 全部走 token 系统, 状态色用 --color-* 而非硬编码 #xxx。
 */
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
  const qColor = getQualityColor(item.quality_score);

  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(item);
  };

  return (
    <article
      className={`
        block p-4 card-base animate-fade-in opacity-0 relative
        delay-${Math.min(index + 1, 10)}
        corner-brackets
      `}
      style={{
        animationFillMode: 'forwards',
        borderTop: `2px solid ${color}80`,
        ['--brackets-color' as any]: color,
      }}
      title={
        item.quality_score != null
          ? `quality_score: ${item.quality_score}` +
            (item.quality_flags?.length
              ? `, flags: ${item.quality_flags.join(', ')}`
              : '')
          : undefined
      }
    >
      {/* 收藏按钮 — 卡片右上角,absolute 定位避免占布局空间 */}
      <button
        type="button"
        onClick={handleStarClick}
        className="absolute top-2 right-2 p-1 rounded transition-all duration-150 hover:scale-110 z-10"
        style={{
          backgroundColor: isFavorited ? 'var(--color-finance)' : 'transparent',
          color: isFavorited ? 'var(--bg-primary)' : 'var(--text-muted)',
          border: `1px solid ${isFavorited ? 'var(--color-finance)' : 'var(--border-color)'}`,
        }}
        title={isFavorited ? '取消收藏' : '收藏'}
        aria-label={isFavorited ? '取消收藏' : '收藏'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      </button>

      {/* Top: badge + quality dot + bid_status + time */}
      <div className="flex items-center justify-between gap-2 mb-2.5 pr-8">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className="badge"
            style={{
              backgroundColor: `${color}14`,
              color: color,
            }}
          >
            {getCategoryLabel(item.category)}
          </span>
          {/* 标讯状态标签 (仅 category=bid 显示) */}
          {item.category === 'bid' && item.bid_status && item.bid_status !== '其他' && (
            <span
              className="badge"
              style={{
                backgroundColor: `${getBidStatusColor(item.bid_status)}1A`,
                color: getBidStatusColor(item.bid_status),
                border: `1px solid ${getBidStatusColor(item.bid_status)}40`,
              }}
            >
              {item.bid_status}
            </span>
          )}
          {item.quality_score != null && (
            <span
              className="inline-block w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: qColor }}
              aria-label={`quality ${item.quality_score}`}
            />
          )}
          {/* 标题被替换 (title_replaced) 角标 */}
          {item.quality_flags?.includes('title_replaced') && (
            <span
              className="badge"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-warning) 10%, transparent)',
                color: 'var(--color-warning)',
                border: '1px solid color-mix(in srgb, var(--color-warning) 25%, transparent)',
              }}
              title="同 URL 存在多条记录, 详情页 <title> 验证后以另一条标题为准; 本条 title 为旧/抓取摘要"
            >
              ⚠ 标题已替换
            </span>
          )}
          {/* 详情页 <title> 验证 (url_check_status=verified) */}
          {item.url_check_status === 'verified' && !item.quality_flags?.includes('title_replaced') && (
            <span
              className="badge"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-success) 10%, transparent)',
                color: 'var(--color-success)',
                border: '1px solid color-mix(in srgb, var(--color-success) 25%, transparent)',
              }}
              title="已与详情页 <title> 验证一致"
            >
              ✓ 标题已验证
            </span>
          )}
        </div>

        <span className="text-[10px] shrink-0" style={{ color: 'var(--text-muted)' }}>
          {formatRelativeTime(item.published_at)}
        </span>
      </div>

      {/* Title — 用 a 包裹标题,点击跳转原文 */}
      <h3
        className="text-sm font-semibold leading-snug mb-2 line-clamp-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
          onClick={e => e.stopPropagation()}
        >
          {item.title}
        </a>
      </h3>

      {/* Summary */}
      {item.summary && (
        <p className="text-xs leading-normal line-clamp-2 mb-2.5" style={{ color: 'var(--text-secondary)' }}>
          {item.summary}
        </p>
      )}

      {/* Bottom: source + action — 整行也是 a 包裹 */}
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-between text-xs pt-2 no-underline"
        style={{ borderTop: '1px solid var(--border-subtle)', color: 'inherit' }}
        onClick={e => e.stopPropagation()}
      >
        <span className="truncate max-w-[60%] text-xs" style={{ color: 'var(--text-muted)' }}>
          {item.source}
        </span>
        <span
          className="shrink-0 ml-2 text-xs font-semibold transition-colors duration-150"
          style={{ color: color }}
        >
          查看原文
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline-block ml-0.5" style={{ verticalAlign: '-2px' }}>
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </span>
      </a>
    </article>
  );
}
