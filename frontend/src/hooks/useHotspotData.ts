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
  keyword: string,
  region?: string,
  source?: string,  // v1.9.1: 来源精确筛选 (点击条目来源触发)
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
  // P0.2: 同步更新 ref, 不再用 useEffect (避免额外渲染)
  // 每次 pageData 变化时立即同步到 ref, 供 fetchPage 读取最新缓存
  pageDataRef.current = pageData;

  // P0.2: fetchPage ref — 让 useEffect 依赖只读 page, 不依赖 fetchPage 引用
  // 这样 fetchPage 重建 (因筛选变化) 不会触发 page effect 重新执行
  const fetchPageRef = useRef<(p: number) => Promise<void>>(async () => {});

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
        if (region) params.set('region', region);
        if (source) params.set('source', source);

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
    [category, timeRange, keyword, region, source, pageSize]
  );

  // P0.2: 同步 fetchPage 到 ref (每次渲染都更新, 无需 effect)
  fetchPageRef.current = fetchPage;

  // P0.2: 首次挂载标志 — 避免筛选 effect 和 page effect 在首次都触发 fetch
  const isFirstMountRef = useRef(true);

  // 切换分类 / 时间窗 / 关键词 / 来源 / 页大小 → 重置到第 1 页, 清空缓存, 显式 fetch
  // P0.2: 不再依赖 useEffect [pageData] 触发, 而是显式调用 fetchPageRef
  useEffect(() => {
    // 首次挂载跳过: page effect 会处理首次 fetchPage(1)
    if (isFirstMountRef.current) {
      isFirstMountRef.current = false;
      return;
    }
    setPageData({});
    _setPage(1);
    // P0.2: 显式触发第 1 页请求 (因为 page 可能没变, useEffect [page] 不会触发)
    fetchPageRef.current(1);
  }, [category, timeRange, keyword, region, source, pageSize]);

  // P0.2 修复: useEffect 依赖只保留 [page]
  // - 用 pageDataRef.current 读缓存 (不触发 effect)
  // - 用 fetchPageRef.current 调用 (fetchPage 重建不触发 effect)
  // 修复前: [page, pageData, fetchPage] → 每次 setPageData/fetchPage 重建都触发
  // 注意: 首次挂载时 page=1, pageDataRef.current[1] 为空, 会触发 fetchPage(1)
  useEffect(() => {
    if (pageDataRef.current[page]) return;
    fetchPageRef.current(page);
  }, [page]);

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
    // P0.2: useEffect for [page] 会触发 fetchPageRef.current(1)
    // 但保险起见, 显式 await, 让 UI 立即反映 loading 状态
    await fetchPageRef.current(1);
  }, []);

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
