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

const SOURCE_TYPE_COLORS: Record<string, string> = {
  favorites: '#4CAF50',
  cubox: '#2196F3',
  bookmark: '#FF9800',
  secnews_archive: '#9E9E9E',
  secnews: '#E91E63',
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
      <h1>资讯收藏</h1>

      {/* Filters */}
      <div className="filters">
        <div className="filter-row">
          <label>类型：</label>
          <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1); }}>
            {SOURCE_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          <label>搜索：</label>
          <input
            type="text"
            placeholder="搜索标题..."
            value={keyword}
            onChange={e => { setKeyword(e.target.value); setPage(1); }}
          />

          <label>起止：</label>
          <input type="date" value={since} onChange={e => { setSince(e.target.value); setPage(1); }} />
          <input type="date" value={until} onChange={e => { setUntil(e.target.value); setPage(1); }} />
        </div>
      </div>

      {/* Loading */}
      {loading && <div className="loading">加载中...</div>}

      {/* Error */}
      {error && <div className="error">错误: {error}</div>}

      {/* Items */}
      {data && data.items.length === 0 && !loading && (
        <div className="empty">暂无数据</div>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="item-list">
            {data.items.map((item) => (
              <div key={item.id} className="item-card">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="item-title"
                >
                  {item.title}
                </a>
                <div className="item-meta">
                  <span
                    className="source-type-tag"
                    style={{ backgroundColor: SOURCE_TYPE_COLORS[item.source_type] || '#999' }}
                  >
                    {item.source_name}
                  </span>
                  <span className="item-origin">{item.origin}</span>
                  <span className="item-time">{item.ingested_at}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="pagination">
            <span>共 {data.total} 条</span>
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span>第 {page}/{totalPages} 页</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>
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