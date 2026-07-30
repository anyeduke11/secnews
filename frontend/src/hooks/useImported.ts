import { useState, useCallback } from 'react';
import { ImportedItem, ImportedResponse } from '../types';

interface FetchParams {
  type?: string;
  keyword?: string;
  since?: string;
  until?: string;
  page?: number;
  pageSize?: number;
}

interface UseImportedReturn {
  data: { items: ImportedItem[]; total: number; page: number; page_size: number } | null;
  loading: boolean;
  error: string | null;
  fetchItems: (params?: FetchParams) => Promise<void>;
}

export function useImported(): UseImportedReturn {
  const [data, setData] = useState<UseImportedReturn['data']>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(async (params?: FetchParams) => {
    setLoading(true);
    setError(null);
    try {
      const searchParams = new URLSearchParams();
      if (params?.type) searchParams.set('type', params.type);
      if (params?.keyword) searchParams.set('keyword', params.keyword);
      if (params?.since) searchParams.set('since', params.since);
      if (params?.until) searchParams.set('until', params.until);
      searchParams.set('page', String(params?.page ?? 1));
      searchParams.set('page_size', String(params?.pageSize ?? 20));

      const qs = searchParams.toString();
      const response = await fetch(`/api/knowledge/imported${qs ? `?${qs}` : ''}`);
      if (!response.ok) {
        throw new Error(`请求失败 (${response.status})`);
      }
      const result: ImportedResponse = await response.json();
      setData(result);
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetchItems };
}