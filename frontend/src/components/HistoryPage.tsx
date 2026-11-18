// HistoryPage — 历史资讯 (按自然周边界 7 天分批)
// Phase 5A: 移除 onBack prop (用 useGoBack), 错误色走 --color-error, 收藏数用 --color-finance, 空态走 EmptyState
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Batch,
  BatchListResponse,
  BatchItemsResponse,
  BatchSummaryResponse,
  HotspotItem,
} from '../types';
import { useGoBack } from '../hooks/useGoBack';
import { importFromHistory } from '../api/knowledge';
import {
  getHistoryBatchSummary,
  listHistoryBatchItems,
  listHistoryBatches,
} from '../api/settings';
import { Icon } from './Icon';
import { EmptyState } from './EmptyState';
import { useReactions } from '../hooks/useReactions';
import { useReactionAction } from './sentinel/ReactionButtons';
import { BatchSummaryBar } from './HistoryPageParts';
import { HistoryPageBatchList } from './HistoryPageBatchList';
import { HistoryPageFilters } from './HistoryPageFilters';
import { HistoryPageItem } from './HistoryPageItem';

interface HistoryPageProps {
  favoritedIds: Set<string>;
  onToggleFavorite: (item: HotspotItem) => void;
}

export function HistoryPage({ favoritedIds, onToggleFavorite }: HistoryPageProps) {
  const goBack = useGoBack();
  // DEV-0326: 历史资讯接入赞/踩 (统一 4 资讯面)
  const { reactionOf, available: reactionsAvailable } = useReactions();
  const doReact = useReactionAction();
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
      const data = await importFromHistory<{ errors?: { error: string }[] }>([item.id]);
      const errors = data.errors;
      if (errors && errors.length > 0) {
        alert(`归档失败: ${errors[0].error}`);
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
        const data: BatchListResponse = await listHistoryBatches<BatchListResponse>(100);
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
      const data: BatchItemsResponse = await listHistoryBatchItems<BatchItemsResponse>(
        batchNo,
        params.toString(),
      );
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
      const data: BatchSummaryResponse = await getHistoryBatchSummary<BatchSummaryResponse>(batchNo);
      setSummary(data);
    } catch {
      // 与原实现语义一致: 失败时回退空 summary (apiFetch 将非 ok 也归一为 throw)
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={goBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回"
            aria-label="返回"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回
          </button>
          <h2 className="text-base font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </Icon>
            历史资讯
          </h2>
          <span className="hidden sm:inline text-xs" style={{ color: 'var(--text-muted)' }}>
            按自然周边界 7 天分批, 永久保留
          </span>
        </div>
      </div>

      <div className="flex gap-4 flex-col md:flex-row">
        {/* 左侧批次列表 (sticky) */}
        <HistoryPageBatchList
          batches={batches}
          batchesLoading={batchesLoading}
          batchesError={batchesError}
          selectedBatchNo={selectedBatchNo}
          onSelectBatch={setSelectedBatchNo}
        />

        {/* 右侧 items 区域 */}
        <main className="flex-1 min-w-0">
          {/* 批次元数据 + 筛选 */}
          {selectedBatchNo != null && summary && (
            <BatchSummaryBar batchNo={selectedBatchNo} summary={summary} />
          )}

          {/* 分类 + 搜索 */}
          <HistoryPageFilters
            category={category}
            keyword={keyword}
            onCategoryChange={setCategory}
            onKeywordChange={setKeyword}
          />

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
            {items.map((item, i) => (
              <HistoryPageItem
                key={item.id}
                item={item}
                index={i}
                isFavorited={favoritedIds.has(item.id)}
                onToggleFavorite={onToggleFavorite}
                isArchived={archivedIds.has(item.id)}
                isArchiving={archivingIds.has(item.id)}
                onArchive={handleArchive}
                reactionsAvailable={reactionsAvailable}
                currentReaction={reactionOf(item.id)}
                onReact={doReact}
              />
            ))}
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