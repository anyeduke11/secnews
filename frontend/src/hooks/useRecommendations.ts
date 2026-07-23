import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * v1.7 Phase 4 — 上下文推荐 Hook
 *
 * 对接后端:
 *  - GET /api/recommend/{entity_type}/{entity_id}?limit=N
 *
 * 暴露:
 *  - items:  推荐结果列表, 每条 { item, score, shared_tags }
 *  - loading / error
 *  - refresh: 重新拉取
 *
 * 验收 2: 知识推荐侧栏显示相关条目 — 给定 entity 后, items 非空.
 */
export interface RecommendationItem {
  item: {
    id: string;
    title: string;
    summary?: string;
    source?: string;
    url?: string;
    category?: string;
    ingested_at?: string;
    score?: number;
    [k: string]: unknown;
  };
  score: number;
  shared_tags: string[];
}

export interface UseRecommendationsReturn {
  items: RecommendationItem[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useRecommendations(
  entityType: string | null,
  entityId: string | null,
  limit: number = 5
): UseRecommendationsReturn {
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (!entityType || !entityId) {
      setItems([]);
      return;
    }
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const url = `/api/recommend/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?limit=${limit}`;
      const r = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setItems(data.items || []);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '推荐加载失败');
      setItems([]);
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, [entityType, entityId, limit]);

  useEffect(() => {
    refresh();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [refresh]);

  return { items, loading, error, refresh };
}
