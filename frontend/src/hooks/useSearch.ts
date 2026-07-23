import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * v1.7 Phase 3 — 统一搜索 Hook (防抖)
 *
 * 对接后端:
 *  - GET /api/search?q=&sources=&limit=  统一跨层搜索
 *
 * 行为:
 *  - 输入防抖 300ms (避免频繁请求)
 *  - 空查询返回空结果 (不发请求)
 *  - 支持 sources 过滤 (hotspot / knowledge)
 *  - 返回 items (扁平) + grouped (按 entity_type 分组)
 *
 * 验收 2: 500ms 内返回跨层结果 — 前端防抖 + 后端 LIKE 查询总延迟 < 500ms。
 */

export interface SearchResult {
  entity_type: string;
  entity_id: string;
  title: string;
  summary: string;
  category: string;
  ingested_at: string;
}

export interface UseSearchReturn {
  query: string;
  setQuery: (q: string) => void;
  results: SearchResult[];
  grouped: Record<string, SearchResult[]>;
  loading: boolean;
  error: string | null;
  search: (q?: string) => Promise<void>;
}

const DEBOUNCE_MS = 300;

export function useSearch(
  sources?: string[],
  limit: number = 20
): UseSearchReturn {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [grouped, setGrouped] = useState<Record<string, SearchResult[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const sourcesRef = useRef(sources);
  const limitRef = useRef(limit);
  sourcesRef.current = sources;
  limitRef.current = limit;

  const search = useCallback(async (q?: string) => {
    const searchTerm = q !== undefined ? q : query;
    if (!searchTerm.trim()) {
      setResults([]);
      setGrouped({});
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: searchTerm, limit: String(limitRef.current) });
      if (sourcesRef.current && sourcesRef.current.length > 0) {
        params.set('sources', sourcesRef.current.join(','));
      }
      const r = await fetch(`/api/search?${params}`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`搜索失败 (${r.status})`);
      const data = await r.json();
      setResults(data.result?.items || []);
      setGrouped(data.result?.grouped || {});
    } catch (e: any) {
      setError(e?.message || '搜索失败');
      setResults([]);
      setGrouped({});
    } finally {
      setLoading(false);
    }
  }, [query]);

  // 防抖: query 变化后 300ms 触发搜索
  useEffect(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    if (!query.trim()) {
      setResults([]);
      setGrouped({});
      return;
    }
    debounceRef.current = window.setTimeout(() => {
      search();
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [query, search]);

  return { query, setQuery, results, grouped, loading, error, search };
}
