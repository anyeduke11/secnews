/**
 * KnowledgeFavoritesView — 5 源数据聚合列表视图
 *
 * Phase 8: 资讯收藏聚合视图
 * 聚合 favorites / cubox / bookmark / secnews_archive / secnews 五源数据，
 * 提供类型筛选、关键词搜索、时间范围、分页等功能。
 */
import React, { useState, useEffect } from 'react';
import { useImported } from '../../hooks/useImported';

const SOURCE_TYPE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'favorites', label: '收藏' },
  { value: 'cubox', label: 'Cubox' },
  { value: 'bookmark', label: '书签' },
  { value: 'secnews_archive', label: '归档' },
  { value: 'secnews', label: '实时资讯' },
];

const PAGE_SIZE_OPTIONS = [20, 50, 100];

// v1.9 Editorial: 油墨色变量随主题切换, 去高饱和 material 色
const SOURCE_TYPE_COLORS: Record<string, string> = {
  favorites: 'var(--color-success)',
  cubox: 'var(--color-info)',
  bookmark: 'var(--color-warning)',
  secnews_archive: 'var(--text-muted)',
  secnews: 'var(--color-error)',
};

export default function KnowledgeFavoritesView() {
  // Type filter
  const [typeFilter, setTypeFilter] = useState('');
  // Keyword search
  const [keyword, setKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  // Time range
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data, loading, error, fetchItems } = useImported();

  // Debounce keyword
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedKeyword(keyword), 300);
    return () => clearTimeout(timer);
  }, [keyword]);

  // Fetch on params change
  useEffect(() => {
    fetchItems({
      type: typeFilter || undefined,
      keyword: debouncedKeyword || undefined,
      since: since || undefined,
      until: until || undefined,
      page,
      pageSize,
    });
  }, [typeFilter, debouncedKeyword, since, until, page, pageSize, fetchItems]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="knowledge-favorites-view">
      {/* v1.9 Editorial: 栏目头 — 上边粗线 + uppercase 小标 */}
      <div className="flex items-center justify-between pb-2 mb-4" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-[0.12em] uppercase" style={{ color: 'var(--text-primary)' }}>资讯收藏</h1>
        {data && (
          <span className="text-xs font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>共 {data.total} 条</span>
        )}
      </div>

      {/* Filters */}
      <div className="filters mb-4">
        <div className="filter-row flex flex-wrap items-center gap-x-2 gap-y-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <label>类型：</label>
          <select
            className="text-xs px-2 py-1 focus-ring"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
            value={typeFilter}
            onChange={e => { setTypeFilter(e.target.value); setPage(1); }}
          >
            {SOURCE_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          <label>搜索：</label>
          <input
            type="text"
            className="text-xs px-2 py-1 focus-ring"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
            placeholder="搜索标题..."
            value={keyword}
            onChange={e => { setKeyword(e.target.value); setPage(1); }}
          />

          <label>起止：</label>
          <input
            type="date" value={since}
            className="text-xs px-2 py-1 focus-ring"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
            onChange={e => { setSince(e.target.value); setPage(1); }}
          />
          <input
            type="date" value={until}
            className="text-xs px-2 py-1 focus-ring"
            style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
            onChange={e => { setUntil(e.target.value); setPage(1); }}
          />
        </div>
      </div>

      {/* Loading */}
      {loading && <div className="loading text-xs py-4" style={{ color: 'var(--text-muted)' }}>加载中...</div>}

      {/* Error */}
      {error && <div className="error text-xs py-4" style={{ color: 'var(--color-error)' }}>错误: {error}</div>}

      {/* Items */}
      {data && data.items.length === 0 && !loading && (
        <div className="empty text-xs py-8 text-center" style={{ color: 'var(--text-muted)' }}>暂无数据</div>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="item-list flex flex-col">
            {data.items.map((item) => (
              <article key={item.id} className="feed-row">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                  <span
                    className="editorial-badge source-type-tag"
                    style={{ color: SOURCE_TYPE_COLORS[item.source_type] || 'var(--text-muted)', borderColor: 'currentColor' }}
                  >
                    {item.source_name}
                  </span>
                  <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
                  <span className="item-origin">{item.origin}</span>
                  <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>·</span>
                  <span className="item-time font-mono tabular-nums">{item.ingested_at}</span>
                </div>
                <h3 className="feed-title" style={{ fontSize: 16 }}>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="item-title focus-ring"
                  >
                    {item.title}
                  </a>
                </h3>
              </article>
            ))}
          </div>

          {/* Pagination */}
          <div className="pagination mt-5 flex flex-wrap items-center justify-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span>共 {data.total} 条</span>
            <button className="pagination-btn focus-ring" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span className="page-indicator">第 {page}/{totalPages} 页</span>
            <button className="pagination-btn focus-ring" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
            <select
              className="text-xs px-2 py-1 focus-ring"
              style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
              value={pageSize}
              onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
            >
              {PAGE_SIZE_OPTIONS.map(opt => (
                <option key={opt} value={opt}>{opt}条/页</option>
              ))}
            </select>
          </div>
        </>
      )}
    </div>
  );
}