import { useState, useEffect, useCallback, useRef } from 'react';
import { HotspotItem, HotspotResponse } from '../types';

// Phase 38: 页大小可调 (100/200/300/400), 居中显示在网格尾部
export const PAGE_SIZE_OPTIONS = [100, 200, 300, 400] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

interface PageData {
  items: HotspotItem[];
  nextCursor: string | null;
}

interface UseHotspotDataReturn {
  items: HotspotItem[];
  total: number;
  categoryCounts: Record<string, number>;
  loading: boolean;
  loadingPage: boolean;
  error: string | null;
  lastUpdated: string | null;
  hasMore: boolean;
  // Phase 38: 分页状态
  page: number;
  pageSize: number;
  totalPages: number;
  setPage: (p: number) => void;
  setPageSize: (s: number) => void;
  refresh: () => Promise<void>;
  // Phase 39: 最近一轮 run_once() 的产出 (供 Header "新增 X 条" 显示)
  latestIngestionCount: number;
  latestIngestionAt: string | null;
}

/**
 * Phase 38: cursor 缓存 + 页大小可调
 *
 * - 每页数据 (items + nextCursor) 缓存在 `pageData[page]`
 * - 翻页时优先用缓存, 没有再按 cursor 拉取
 * - 切换 pageSize / 分类 / 时间窗 / 关键词 → 重置到第 1 页, 缓存清空
 * - 翻页用 pageDataRef (ref) 拿最新缓存, 避免闭包陷阱
 */
export function useHotspotData(
  category: string,
  timeRange: string,
  keyword: string
): UseHotspotDataReturn {
  const [pageSize, _setPageSize] = useState<number>(100);
  const [page, _setPage] = useState<number>(1);
  const [pageData, setPageData] = useState<Record<number, PageData>>({});
  const [total, setTotal] = useState(0);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [loadingPage, setLoadingPage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  // Phase 39: 最新一轮 run_once() 的产出
  const [latestIngestionCount, setLatestIngestionCount] = useState(0);
  const [latestIngestionAt, setLatestIngestionAt] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 同步缓存到 ref, 让 fetchPage 闭包能拿到最新的 page-1 数据
  const pageDataRef = useRef<Record<number, PageData>>({});
  useEffect(() => {
    pageDataRef.current = pageData;
  }, [pageData]);

  const fetchPage = useCallback(
    async (targetPage: number) => {
      // 解析 cursor: page 1 → null, page N>1 → pageData[N-1].nextCursor
      let cursor: string | null = null;
      if (targetPage > 1) {
        const prev = pageDataRef.current[targetPage - 1];
        if (!prev) {
          // 缺少 page N-1 的 cursor, 无法直接跳到 page N, 自动回退到 page 1
          _setPage(1);
          return;
        }
        cursor = prev.nextCursor;
      }

      // page 1: 取消前一个 first-page 请求
      if (targetPage === 1 && abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      if (targetPage === 1) abortRef.current = controller;

      if (targetPage === 1) setLoading(true);
      else setLoadingPage(true);
      setError(null);

      try {
        const params = new URLSearchParams({
          category,
          time_range: timeRange,
          limit: String(pageSize),
        });
        if (keyword) params.set('keyword', keyword);
        if (cursor) params.set('cursor', cursor);

        const response = await fetch(`/api/hotspots?${params}`, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        });

        if (!response.ok) {
          throw new Error(`请求失败 (${response.status})`);
        }

        const data: HotspotResponse = await response.json();
        setPageData(prev => ({
          ...prev,
          [targetPage]: {
            items: data.items || [],
            nextCursor: data.next_cursor,
          },
        }));
        if (targetPage === 1) {
          setTotal(data.total || 0);
          setCategoryCounts(data.category_counts || {});
          setLastUpdated(data.fetched_at);
          // Phase 39: 最新一轮 run_once() 的产出
          setLatestIngestionCount(data.latest_ingestion_count ?? 0);
          setLatestIngestionAt(data.latest_ingestion_at ?? null);
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        setError(err.message || '数据加载失败');
      } finally {
        if (targetPage === 1) setLoading(false);
        else setLoadingPage(false);
      }
    },
    [category, timeRange, keyword, pageSize]
  );

  // 切换分类 / 时间窗 / 关键词 / 页大小 → 重置到第 1 页, 清空缓存
  useEffect(() => {
    setPageData({});
    _setPage(1);
  }, [category, timeRange, keyword, pageSize]);

  // 切换 page: 已缓存 → 立即生效; 未缓存 → fetch
  useEffect(() => {
    if (pageData[page]) return;
    fetchPage(page);
  }, [page, pageData, fetchPage]);

  const setPage = useCallback((p: number) => {
    if (!Number.isFinite(p) || p < 1) return;
    _setPage(Math.floor(p));
  }, []);

  const setPageSize = useCallback((s: number) => {
    if (!PAGE_SIZE_OPTIONS.includes(s as PageSize)) return;
    _setPageSize(s);
  }, []);

  const currentEntry = pageData[page];
  const items = currentEntry?.items || [];
  const hasMore = currentEntry?.nextCursor != null;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/refresh', { method: 'POST' });
      const data = await r.json();
      if (!data?.ok) {
        console.warn('refresh endpoint returned error:', data?.error);
      }
    } catch (e) {
      console.error('refresh network error:', e);
    }
    setPageData({});
    _setPage(1);
    // useEffect for [page, pageData, fetchPage] 会触发 fetchPage(1)
    // 但保险起见, 显式 await, 让 UI 立即反映 loading 状态
    await fetchPage(1);
  }, [fetchPage]);

  return {
    items,
    total,
    categoryCounts,
    loading,
    loadingPage,
    error,
    lastUpdated,
    hasMore,
    page,
    pageSize,
    totalPages,
    setPage,
    setPageSize,
    refresh,
    // Phase 39
    latestIngestionCount,
    latestIngestionAt,
  };
}
