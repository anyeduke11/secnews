import { useState, useEffect, useCallback, useRef } from 'react';
import { getJSON } from '../lib/api';

/**
 * 安全知识图谱 Hook — 端点为单一 hook 专用 → 常量化于此。
 */

const SECURITY_GRAPH_URL = '/api/security/graph';

export interface SecurityEntity {
  id: string;
  entity_type: 'tactic' | 'technique' | 'cve' | 'cwe' | 'compliance' | 'product' | 'cpe';
  name: string;
  description?: string;
  external_ref?: string;
  metadata?: Record<string, any>;
}

export interface SecurityGraphResponse {
  ok: boolean;
  nodes: (SecurityEntity & { entity_type: string })[];
  edges: { source_id: string; target_id: string; edge_type: string; weight: number }[];
  stats: {
    tactics: number;
    techniques: number;
    cves: number;
    compliance_items: number;
    knowledge_items: number;
  };
}

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
      const json = await getJSON<SecurityGraphResponse>(`${SECURITY_GRAPH_URL}?view=${view}`, {
        signal: controller.signal,
      });
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
