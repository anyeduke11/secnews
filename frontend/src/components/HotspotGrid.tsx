import React from 'react';
import { HotspotItem } from '../types';
import { HotspotCard } from './HotspotCard';
import { PAGE_SIZE_OPTIONS } from '../hooks/useHotspotData';

interface HotspotGridProps {
  items: HotspotItem[];
  loading: boolean;
  error: string | null;
  favoritedIds?: Set<string>;
  onToggleFavorite?: (item: HotspotItem) => void;
  // Phase 38: 分页
  page: number;
  pageSize: number;
  totalPages: number;
  total: number;
  hasMore: boolean;
  loadingPage: boolean;
  onSetPage: (page: number) => void;
  onSetPageSize: (size: number) => void;
}

// 复用项目 14×14 stroke=2 strokeLinecap=round 风格
function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
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
}: HotspotGridProps) {
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center mb-3"
          style={{
            backgroundColor: 'rgba(232, 93, 93, 0.1)',
            border: '1px solid rgba(232, 93, 93, 0.2)',
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#e85d5d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <p className="text-sm font-medium mb-1" style={{ color: '#e85d5d' }}>数据加载失败</p>
        <p className="text-xs max-w-md" style={{ color: 'var(--text-muted)' }}>{error}</p>
      </div>
    );
  }

  if (!loading && items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center mb-3"
          style={{
            backgroundColor: 'var(--bg-hover)',
            border: '1px solid var(--border-color)',
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </div>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>暂无热点数据</p>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          当前筛选条件下没有匹配的热点，试试调整分类或时间范围
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3.5">
        {items.map((item, index) => (
          <HotspotCard
            key={item.id}
            item={item}
            index={index}
            isFavorited={favoritedIds?.has(item.id) ?? false}
            onToggleFavorite={onToggleFavorite}
          />
        ))}
      </div>

      {/* Phase 38: 分页控件 - 居中显示在网格尾部
          - 页大小选择: 100/200/300/400 (切换后回到第 1 页)
          - 上下页 + 页码指示
          - 已显示 / 总数 计数 */}
      {!loading && total > 0 && (
        <div className="mt-8 flex flex-col items-center gap-3.5">
          {/* 页大小选择器 (4 选项, 居中) */}
          <div className="flex items-center gap-2">
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>每页</span>
            {PAGE_SIZE_OPTIONS.map(size => {
              const active = size === pageSize;
              return (
                <button
                  key={size}
                  type="button"
                  onClick={() => onSetPageSize(size)}
                  aria-label={`每页 ${size} 条`}
                  aria-pressed={active}
                  className="focus-ring transition-colors"
                  style={{
                    minWidth: 38,
                    height: 26,
                    padding: '0 10px',
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: active ? 600 : 500,
                    background: active ? 'var(--color-ai)' : 'var(--bg-card)',
                    color: active ? '#0a0a0f' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--color-ai)' : 'var(--border-color)'}`,
                    cursor: 'pointer',
                  }}
                >
                  {size}
                </button>
              );
            })}
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>条</span>
          </div>

          {/* 翻页 + 页码指示 */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => onSetPage(page - 1)}
              disabled={page <= 1 || loadingPage}
              className="btn-ghost flex items-center gap-1 transition-colors"
              style={{
                padding: '5px 12px',
                fontSize: 12,
                opacity: page <= 1 || loadingPage ? 0.5 : 1,
                cursor: page <= 1 || loadingPage ? 'not-allowed' : 'pointer',
              }}
              aria-label="上一页"
            >
              <Icon size={12}>
                <polyline points="15 18 9 12 15 6" />
              </Icon>
              <span>上一页</span>
            </button>

            <span
              className="text-[12px] px-3 tabular-nums"
              style={{ color: 'var(--text-secondary)', minWidth: 80, textAlign: 'center' }}
              aria-live="polite"
            >
              第 <b style={{ color: 'var(--text-primary)' }}>{page}</b> / {totalPages} 页
            </span>

            <button
              type="button"
              onClick={() => onSetPage(page + 1)}
              disabled={!hasMore || loadingPage}
              className="btn-ghost flex items-center gap-1 transition-colors"
              style={{
                padding: '5px 12px',
                fontSize: 12,
                opacity: !hasMore || loadingPage ? 0.5 : 1,
                cursor: !hasMore || loadingPage ? 'not-allowed' : 'pointer',
              }}
              aria-label="下一页"
            >
              <span>下一页</span>
              <Icon size={12}>
                <polyline points="9 18 15 12 9 6" />
              </Icon>
            </button>
          </div>

          {/* 计数 (显示已加载/总数) */}
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
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
