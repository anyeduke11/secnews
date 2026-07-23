import { useState, useEffect, useCallback } from 'react';

/**
 * v1.7 Phase 1 — 标签数据 Hook
 *
 * 负责拉取 /api/tags 列表 (支持 type 筛选), 暴露:
 *  - tags: 当前标签列表
 *  - loading / error: 加载状态
 *  - refresh: 手动重新拉取
 *  - suggest: 按前缀搜索 (/api/tags/suggest)
 */

export interface Tag {
  id: string;
  label: string;
  type: string;
  parent_id: string | null;
  weight: number;
  created_at: string;
}

export interface UseTagsReturn {
  tags: Tag[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  suggest: (q: string) => Promise<Tag[]>;
}

export function useTags(type?: string): UseTagsReturn {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '500' });
      if (type) params.set('type', type);
      const r = await fetch(`/api/tags?${params}`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setTags(data.items || []);
    } catch (e: any) {
      setError(e?.message || '标签加载失败');
    } finally {
      setLoading(false);
    }
  }, [type]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const suggest = useCallback(async (q: string): Promise<Tag[]> => {
    if (!q.trim()) return [];
    try {
      const r = await fetch(
        `/api/tags/suggest?q=${encodeURIComponent(q.trim())}&limit=20`,
        { headers: { Accept: 'application/json' } }
      );
      if (!r.ok) return [];
      const data = await r.json();
      return data.items || [];
    } catch {
      return [];
    }
  }, []);

  return { tags, loading, error, refresh: fetchList, suggest };
}
