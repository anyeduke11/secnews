import { useState, useEffect, useCallback, useRef } from 'react';
import { getSecurityGraph } from '../api/security';
import type { SecurityEntity, SecurityGraphResponse } from '../api/security';

/**
 * 安全知识图谱 Hook — 端点函数见 api/security.ts。
 */

// 类型对外兼容: 既有消费方 (components/security/*) 仍从本模块 import
export type { SecurityEntity, SecurityGraphResponse };

export function useSecurityGraph(view: 'full' | 'attack' | 'cve' | 'compliance' = 'full') {
  const [data, setData] = useState<SecurityGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchGraph = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const json = await getSecurityGraph(view, { signal: controller.signal });
      setData(json);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    fetchGraph();
    return () => { if (abortRef.current) abortRef.current.abort(); };
  }, [fetchGraph]);

  return { data, loading, error, refresh: fetchGraph };
}