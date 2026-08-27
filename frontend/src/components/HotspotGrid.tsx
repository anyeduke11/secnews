/**
 * HotspotGrid — 热点信息流 + 分页 + 三态（Loading/Empty/Error）。
 * v1.10+: 头条 (LeadStory) + 3 列卡片网格 (AgihuntCard)，参照 agihunt.info 风格。
 */
import { HotspotItem } from '../types';
import { LeadStory } from './LeadStory';
import { AgihuntCard } from './AgihuntCard';
import { EmptyState } from './EmptyState';
import { PAGE_SIZE_OPTIONS } from '../hooks/useHotspotData';
import { Icon } from './Icon';

interface HotspotGridProps {
  items: HotspotItem[];
  loading: boolean;
  error: string | null;
  favoritedIds?: Set<string>;
  onToggleFavorite?: (item: HotspotItem) => void;
  page: number;
  pageSize: number;
  totalPages: number;
  total: number;
  hasMore: boolean;
  loadingPage: boolean;
  onSetPage: (page: number) => void;
  onSetPageSize: (size: number) => void;
  onCategoryClick?: (category: string) => void;
  onSourceClick?: (source: string) => void;
}

export function HotspotGrid({
  items,
  loading,
  error,
  favoritedIds,
  onToggleFavorite,
  page,
  pageSize,
  totalPages,
  total,
  hasMore,
  loadingPage,
  onSetPage,
  onSetPageSize,
  onCategoryClick,
  onSourceClick,
}: HotspotGridProps) {
  if (error) {
    return (
      <EmptyState
        title="数据加载失败"
        description={error}
        icon={
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        }
      />
    );
  }

  if (!loading && items.length === 0) {
    return (
      <EmptyState
        title="暂无热点数据"
        description="当前筛选条件下没有匹配的热点，试试调整分类或时间范围"
        icon={
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        }
      />
    );
  }

  return (
    <>
      {/* 第一页首条升格 LeadStory */}
      {page === 1 && items.length > 0 && (
        <LeadStory
          key={items[0].id}
          item={items[0]}
          isFavorited={favoritedIds?.has(items[0].id) ?? false}
          onToggleFavorite={onToggleFavorite}
          onCategoryClick={onCategoryClick}
          onSourceClick={onSourceClick}
        />
      )}

      {/* 其余条目: 3 列卡片网格 */}
      {items.length > (page === 1 ? 1 : 0) && (
        <div className="agihunt-card-grid">
          {items.slice(page === 1 ? 1 : 0).map((item, index) => (
            <AgihuntCard
              key={item.id}
              item={item}
              index={index}
              isFavorited={favoritedIds?.has(item.id) ?? false}
              onToggleFavorite={onToggleFavorite}
              onCategoryClick={onCategoryClick}
              onSourceClick={onSourceClick}
            />
          ))}
        </div>
      )}

      {/* 分页控件 */}
      {!loading && total > 0 && (
        <div className="mt-10 mb-2 flex flex-col sm:flex-row items-center justify-center gap-4">
          <div className="flex items-center gap-1.5 order-2 sm:order-1">
            {PAGE_SIZE_OPTIONS.map(size => {
              const active = size === pageSize;
              return (
                <button
                  key={size}
                  type="button"
                  onClick={() => onSetPageSize(size)}
                  aria-label={`每页 ${size} 条`}
                  aria-pressed={active}
                  className={`ink-chip focus-ring text-xs ${active ? 'active' : ''}`}
                  style={{ padding: '4px 10px', fontSize: '10.5px' }}
                >
                  {size}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 order-1 sm:order-2">
            <button
              type="button"
              onClick={() => onSetPage(page - 1)}
              disabled={page <= 1 || loadingPage}
              className="pagination-btn focus-ring"
              aria-label="上一页"
              style={{ padding: '7px 16px' }}
            >
              <Icon size={12}>
                <polyline points="15 18 9 12 15 6" />
              </Icon>
              <span>上一页</span>
            </button>

            <span className="page-indicator" aria-live="polite">
              第 <strong>{page}</strong> / {totalPages} 页
            </span>

            <button
              type="button"
              onClick={() => onSetPage(page + 1)}
              disabled={!hasMore || loadingPage}
              className="pagination-btn focus-ring"
              aria-label="下一页"
              style={{ padding: '7px 16px' }}
            >
              <span>下一页</span>
              <Icon size={12}>
                <polyline points="9 18 15 12 9 6" />
              </Icon>
            </button>
          </div>

          <div className="text-[11px] order-3 font-mono" style={{ color: 'var(--text-muted)' }}>
            {loadingPage ? (
              <span className="flex items-center gap-1.5">
                <Icon size={10}>
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </Icon>
                加载中…
              </span>
            ) : (
              <>
                已显示 <b style={{ color: 'var(--text-secondary)' }}>{items.length}</b> / {total} 条
                {hasMore ? '' : ' · 已是最后一页'}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}