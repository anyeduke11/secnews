import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch, getJSON } from '../lib/api';
import { DeepReadResponse, DeepReadSections } from '../types';

export interface UseDeepReadReturn {
  /** 当前深读内容 (无则 null) */
  data: DeepReadResponse | null;
  /** 4 节结构 (从 data.sections 展开, 缺省空串) */
  sections: DeepReadSections;
  /** 加载中 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 读取已有分析 (不触发 LLM) */
  fetch: (entityType: string, entityId: string) => Promise<void>;
  /** 触发/刷新 4 节 LLM 分析 */
  regenerate: (entityType: string, entityId: string, force?: boolean) => Promise<void>;
  /** 清空当前状态 */
  clear: () => void;
}

const EMPTY_SECTIONS: DeepReadSections = {
  summary: '',
  impact: '',
  relations: '',
  risks: '',
};

export function useDeepRead(): UseDeepReadReturn {
  const [data, setData] = useState<DeepReadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAbortRef = useRef<AbortController | null>(null);

  const sections: DeepReadSections = data?.sections
    ? {
        summary: data.sections.summary || '',
        impact: data.sections.impact || '',
        relations: data.sections.relations || '',
        risks: data.sections.risks || '',
      }
    : EMPTY_SECTIONS;

  const clear = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  const fetch = useCallback(async (entityType: string, entityId: string) => {
    if (fetchAbortRef.current) fetchAbortRef.current.abort();
    const controller = new AbortController();
    fetchAbortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const item = await getJSON<DeepReadResponse>(
        `/api/deep-read/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
        { signal: controller.signal },
      );
      setData(item);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载深读失败');
      setData(null);
    } finally {
      if (fetchAbortRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  const regenerate = useCallback(
    async (entityType: string, entityId: string, force = true) => {
      if (fetchAbortRef.current) fetchAbortRef.current.abort();
      const controller = new AbortController();
      fetchAbortRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const item = await apiFetch<DeepReadResponse>(
          `/api/deep-read/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?force=${force ? '1' : '0'}`,
          {
            method: 'POST',
            signal: controller.signal,
          },
        );
        setData(item);
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        setError(e?.message || '深读生成失败');
      } finally {
        if (fetchAbortRef.current === controller) {
          setLoading(false);
        }
      }
    },
    [],
  );

  // 清理
  useEffect(() => {
    return () => {
      fetchAbortRef.current?.abort();
    };
  }, []);

  return { data, sections, loading, error, fetch, regenerate, clear };
}
