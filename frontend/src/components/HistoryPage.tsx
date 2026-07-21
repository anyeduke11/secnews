// HistoryPage — 历史资讯 (按自然周边界 7 天分批)
// Phase 5A: 移除 onBack prop (用 useGoHome), 错误色走 --color-error, 收藏数用 --color-finance, 空态走 EmptyState
import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Batch,
  BatchListResponse,
  BatchItemsResponse,
  BatchSummaryResponse,
  HotspotItem,
  CATEGORIES,
} from '../types';
import { HotspotCard } from './HotspotCard';
import { useGoHome } from '../hooks/useGoHome';
import { Icon } from './Icon';
import { EmptyState } from './EmptyState';

interface HistoryPageProps {
  favoritedIds: Set<string>;
  onToggleFavorite: (item: HotspotItem) => void;
}

function formatBatchDate(isoString: string): string {
  // "2026-07-06T00:00:00+00:00" → "7/6"
  const d = new Date(isoString);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatBatchRange(start: string, end: string): string {
  return `${formatBatchDate(start)} - ${formatBatchDate(end)}`;
}

export function HistoryPage({ favoritedIds, onToggleFavorite }: HistoryPageProps) {
  const goHome = useGoHome();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [batchesLoading, setBatchesLoading] = useState(true);
  const [batchesError, setBatchesError] = useState<string | null>(null);
  const [selectedBatchNo, setSelectedBatchNo] = useState<number | null>(null);
  const [items, setItems] = useState<HotspotItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [summary, setSummary] = useState<BatchSummaryResponse | null>(null);
  const [category, setCategory] = useState('all');
  const [keyword, setKeyword] = useState('');
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef<string | null>(null);
  const hasMoreRef = useRef<boolean>(false);
  const loadingMoreRef = useRef<boolean>(false);
  const [archivedIds, setArchivedIds] = useState<Set<string>>(new Set());
  const [archivingIds, setArchivingIds] = useState<Set<string>>(new Set());

  const handleArchive = useCallback(async (item: HotspotItem) => {
    setArchivingIds(prev => { const n = new Set(prev); n.add(item.id); return n; });
    try {
      const r = await fetch('/api/knowledge/import-from-history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: [item.id] }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (data.errors?.length > 0) {
        alert(`归档失败: ${data.errors[0].error}`);
      } else {
        setArchivedIds(prev => { const n = new Set(prev); n.add(item.id); return n; });
      }
    } catch (e: any) {
      alert(`归档失败: ${e.message || '未知错误'}`);
    } finally {
      setArchivingIds(prev => { const n = new Set(prev); n.delete(item.id); return n; });
    }
  }, []);

  // 1) 加载批次列表
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/history/batches?limit=100');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data: BatchListResponse = await r.json();
        if (cancelled) return;
        setBatches(data.batches || []);
        if (data.batches.length > 0) {
          setSelectedBatchNo(data.batches[0].batch_no);
        }
      } catch (e: any) {
        if (!cancelled) setBatchesError(e.message || '加载批次失败');
      } finally {
        if (!cancelled) setBatchesLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // 2) 加载选中批次的 items + summary
  const loadBatchItems = useCallback(async (batchNo: number, reset: boolean) => {
    if (reset) {
      setItemsLoading(true);
      setItems([]);
      cursorRef.current = null;
      hasMoreRef.current = false;
    } else {
      if (!hasMoreRef.current || loadingMoreRef.current) return;
      loadingMoreRef.current = true;
    }
    setItemsError(null);
    try {
      const params = new URLSearchParams({
        category,
        limit: '50',
      });
      if (keyword.trim()) params.set('keyword', keyword.trim());
      if (cursorRef.current) params.set('cursor', cursorRef.current);
      const r = await fetch(`/api/history/batches/${batchNo}/items?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: BatchItemsResponse = await r.json();
      setItems(prev => reset ? data.items : [...prev, ...data.items]);
      cursorRef.current = data.cursor;
      hasMoreRef.current = data.has_more;
    } catch (e: any) {
      setItemsError(e.message || '加载失败');
    } finally {
      setItemsLoading(false);
      loadingMoreRef.current = false;
    }
  }, [category, keyword]);

  const loadBatchSummary = useCallback(async (batchNo: number) => {
    try {
      const r = await fetch(`/api/history/batches/${batchNo}/summary`);
      if (!r.ok) return;
      const data: BatchSummaryResponse = await r.json();
      setSummary(data);
    } catch {
      setSummary(null);
    }
  }, []);

  // 切换 batch / category / keyword 时重新加载
  useEffect(() => {
    if (selectedBatchNo == null) return;
    loadBatchItems(selectedBatchNo, true);
    loadBatchSummary(selectedBatchNo);
  }, [selectedBatchNo, category, keyword, loadBatchItems, loadBatchSummary]);

  // 滚动到底部自动加载更多
  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver(entries => {
      for (const e of entries) {
        if (e.isIntersecting && selectedBatchNo != null && hasMoreRef.current && !loadingMoreRef.current) {
          loadBatchItems(selectedBatchNo, false);
        }
      }
    });
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [selectedBatchNo, loadBatchItems]);

  return (
    <div className="history-page">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={goHome}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            📚 历史资讯
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            按自然周边界 7 天分批, 永久保留
          </span>
        </div>
      </div>

      <div className="flex gap-4">
        {/* 左侧批次列表 (sticky) */}
        <aside
          className="shrink-0"
          style={{
            width: 240,
            position: 'sticky',
            top: 16,
            alignSelf: 'flex-start',
            maxHeight: 'calc(100vh - 32px)',
            overflowY: 'auto',
          }}
        >
          <div
            className="rounded-[var(--radius-md)] p-3"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
          >
            <h3 className="text-xs font-bold mb-2" style={{ color: 'var(--text-muted)' }}>
              批次列表 (按时间倒序)
            </h3>
            {batchesLoading && (
              <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>加载中…</p>
            )}
            {batchesError && (
              <div
                className="text-xs py-2.5 px-2 rounded-[var(--radius-sm)]"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
                  border: '1px solid var(--color-error)',
                  color: 'var(--color-error)',
                }}
              >
                加载失败: {batchesError}
              </div>
            )}
            {!batchesLoading && !batchesError && batches.length === 0 && (
              <EmptyState
                compact
                title="暂无历史批次"
                description="项目刚启动, 第 1 批还未结束"
              />
            )}
            <ul className="space-y-1">
              {batches.map(b => {
                const active = b.batch_no === selectedBatchNo;
                return (
                  <li key={b.batch_no}>
                    <button
                      onClick={() => setSelectedBatchNo(b.batch_no)}
                      className={`w-full text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors ${active ? 'active' : ''}`}
                      style={{
                        backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
                        borderLeft: active ? '3px solid var(--color-ai)' : '3px solid transparent',
                        color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold">第 {b.batch_no} 批</span>
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {b.item_count} 条
                        </span>
                      </div>
                      <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {formatBatchRange(b.start, b.end)}
                      </div>
                      {b.favorite_count > 0 && (
                        <div className="text-[10px] mt-0.5" style={{ color: 'var(--color-finance)' }}>
                          ⭐ {b.favorite_count} 收藏
                        </div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>

        {/* 右侧 items 区域 */}
        <main className="flex-1 min-w-0">
          {/* 批次元数据 + 筛选 */}
          {selectedBatchNo != null && summary && (
            <div
              className="rounded-[var(--radius-md)] p-3 mb-3"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                  第 {selectedBatchNo} 批
                </span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {formatBatchRange(summary.start, summary.end)} · 共 {summary.total} 条 · {summary.source_count} 个信源
                </span>
              </div>
              {summary.top_sources.length > 0 && (
                <div className="text-xs mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                  Top 信源: {summary.top_sources.map(s => `${s.source}(${s.count})`).join(', ')}
                </div>
              )}
            </div>
          )}

          {/* 分类 + 搜索 */}
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <button
              onClick={() => setCategory('all')}
              className="btn-ghost px-2.5 py-1 text-xs"
              style={{
                color: category === 'all' ? 'var(--color-ai)' : undefined,
                borderBottom: category === 'all' ? '2px solid var(--color-ai)' : '2px solid transparent',
              }}
            >
              全部
            </button>
            {CATEGORIES.filter(c => c.id !== 'all').map(c => (
              <button
                key={c.id}
                onClick={() => setCategory(c.id)}
                className="btn-ghost px-2.5 py-1 text-xs"
                style={{
                  color: category === c.id ? c.color : undefined,
                  borderBottom: category === c.id ? `2px solid ${c.color}` : '2px solid transparent',
                }}
              >
                {c.label}
              </button>
            ))}
            <input
              type="text"
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              placeholder="搜索本批次内关键词 (FTS5)…"
              className="ml-auto px-2 py-1 text-xs rounded-[var(--radius-sm)]"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                width: 240,
              }}
            />
          </div>

          {/* items grid */}
          {itemsLoading && items.length === 0 && (
            <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>加载中…</p>
          )}
          {itemsError && (
            <div
              className="rounded-[var(--radius-md)] p-2.5 text-sm"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
                border: '1px solid var(--color-error)',
                color: 'var(--color-error)',
              }}
            >
              加载失败: {itemsError}
            </div>
          )}
          {!itemsLoading && !itemsError && items.length === 0 && selectedBatchNo != null && (
            <EmptyState
              title="本批次暂无数据"
              description="切换到其他批次或等待新批次"
            />
          )}
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
          >
            {items.map((item, i) => {
              const isArchived = archivedIds.has(item.id);
              const isArchiving = archivingIds.has(item.id);
              return (
                <div key={item.id} className="relative">
                  <HotspotCard
                    item={item}
                    index={i}
                    isFavorited={favoritedIds.has(item.id)}
                    onToggleFavorite={onToggleFavorite}
                  />
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleArchive(item); }}
                    disabled={isArchived || isArchiving}
                    className="btn-ghost absolute bottom-2 left-2 px-1.5 py-0.5 text-[10px] z-10"
                    style={{
                      backgroundColor: isArchived ? 'var(--bg-hover)' : 'var(--bg-elevated)',
                      color: isArchived ? 'var(--text-muted)' : 'var(--text-secondary)',
                      border: '1px solid var(--border-color)',
                      opacity: isArchiving ? 0.6 : 1,
                      cursor: (isArchived || isArchiving) ? 'default' : 'pointer',
                    }}
                    title={isArchived ? '已归档到知识库' : '归档到知识库'}
                  >
                    {isArchiving ? '📚 归档中…' : isArchived ? '✓ 已归档' : '📚 归档'}
                  </button>
                </div>
              );
            })}
          </div>

          {/* 加载更多 sentinel */}
          <div ref={sentinelRef} className="py-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
            {hasMoreRef.current ? '滚动加载更多…' : items.length > 0 ? '已加载全部' : ''}
          </div>
        </main>
      </div>
    </div>
  );
}
