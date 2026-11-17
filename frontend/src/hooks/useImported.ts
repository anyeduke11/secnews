import { useState, useCallback } from 'react';
import { listImportedKnowledge } from '../api/knowledge';
import { ImportedItem } from '../types';

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
      const result = await listImportedKnowledge(params ?? {});
      setData(result);
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetchItems };
}