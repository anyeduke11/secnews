import { useState, useEffect, useCallback, useRef } from 'react';
import { TrendResponse, TrendPoint } from '../types';

interface UseTrendDataReturn {
  trends: TrendPoint[];
  hours: number;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
  byCategoryData: Record<string, TrendPoint[]> | null;
  refresh: () => void;
}

/**
 * Phase 5: 调用 /api/trends 拉 24h 趋势数据。
 *
 * 用法
 * ----
 * const { trends, byCategoryData } = useTrendData(24, false);
 */
export function useTrendData(
  hours: number = 24,
  byCategory: boolean = false
): UseTrendDataReturn {
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [byCategoryData, setByCategoryData] = useState<
    Record<string, TrendPoint[]> | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [currentHours, setCurrentHours] = useState(hours);
  const abortRef = useRef<AbortController | null>(null);

  const fetchTrends = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ hours: String(currentHours) });
      if (byCategory) params.set('by_category', 'true');

      const response = await fetch(`/api/trends?${params}`, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });

      if (!response.ok) {
        throw new Error(`请求失败 (${response.status})`);
      }

      const data: TrendResponse = await response.json();
      setTrends(data.trends || []);
      setByCategoryData(byCategory ? data.data || null : null);
      setLastUpdated(data.fetched_at);
      setCurrentHours(data.hours);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setError(err.message || '趋势加载失败');
    } finally {
      setLoading(false);
    }
  }, [currentHours, byCategory]);

  useEffect(() => {
    fetchTrends();
    const interval = setInterval(fetchTrends, 600000); // 10 min refresh
    return () => {
      clearInterval(interval);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [fetchTrends]);

  return {
    trends,
    hours: currentHours,
    loading,
    error,
    lastUpdated,
    byCategoryData,
    refresh: fetchTrends,
  };
}
