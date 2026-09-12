import { useState, useEffect, useCallback, useRef } from 'react';
import { getJSON, postJSON, apiFetch } from '../lib/api';
import {
  SkillItem,
  SkillListResponse,
  SkillCountBySourceResponse,
  SkillSource,
  SkillCreateRequest,
  SkillUpdateRequest,
} from '../types';

/**
 * Phase 41: Skill 管理 Hook
 *
 * 负责:
 *  - 列表 (source / tag / keyword 过滤)
 *  - count_by_source 统计
 *  - CRUD: add / update / remove
 *
 * 端点为单一 hook 专用 → 常量化于此, 走 lib/api 统一封装。
 */

const SKILLS_URL = '/api/skills';

export interface UseSkillsReturn {
  items: SkillItem[];
  total: number;
  countsBySource: Record<string, number>;
  loading: boolean;
  error: string | null;

  // 过滤条件
  source: SkillSource | 'all';
  tag: string | null;
  keyword: string;

  // 操作
  setSource: (s: SkillSource | 'all') => void;
  setTag: (t: string | null) => void;
  setKeyword: (k: string) => void;
  refresh: () => Promise<void>;
  add: (req: SkillCreateRequest) => Promise<SkillItem>;
  update: (id: number, req: SkillUpdateRequest) => Promise<SkillItem>;
  remove: (id: number) => Promise<void>;
}

export function useSkills(): UseSkillsReturn {
  const [items, setItems] = useState<SkillItem[]>([]);
  const [total, setTotal] = useState(0);
  const [countsBySource, setCountsBySource] = useState<Record<string, number>>({});
  const [source, setSourceState] = useState<SkillSource | 'all'>('all');
  const [tag, setTag] = useState<string | null>(null);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listAbortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(
    async (currentSource: string, currentTag: string | null, currentKeyword: string) => {
      if (listAbortRef.current) {
        listAbortRef.current.abort();
      }
      const controller = new AbortController();
      listAbortRef.current = controller;

      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams({ limit: '200' });
        if (currentSource !== 'all') params.set('source', currentSource);
        if (currentTag) params.set('tag', currentTag);
        if (currentKeyword.trim()) params.set('keyword', currentKeyword.trim());

        const data: SkillListResponse = await getJSON<SkillListResponse>(`${SKILLS_URL}?${params}`, {
          signal: controller.signal,
        });
        setItems(data.items || []);
        setTotal(data.total || 0);
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        setError(e?.message || '数据加载失败');
      } finally {
        if (listAbortRef.current === controller) {
          setLoading(false);
        }
      }
    },
    []
  );

  const fetchCounts = useCallback(async () => {
    try {
      const data = await getJSON<SkillCountBySourceResponse>(`${SKILLS_URL}/count_by_source`);
      setCountsBySource(data.counts || {});
    } catch {
      // 静默
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([fetchList(source, tag, keyword), fetchCounts()]);
  }, [source, tag, keyword, fetchList, fetchCounts]);

  // 初次 mount
  useEffect(() => {
    refresh();
    return () => {
      if (listAbortRef.current) listAbortRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 过滤条件变化 → 重新拉 list (debounce 250ms 应对 keyword 输入)
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchList(source, tag, keyword);
    }, 250);
    return () => clearTimeout(timer);
  }, [source, tag, keyword, fetchList]);

  const setSource = useCallback((s: SkillSource | 'all') => setSourceState(s), []);

  const add = useCallback(
    async (req: SkillCreateRequest): Promise<SkillItem> => {
      const data = await postJSON<{ item: SkillItem }>(SKILLS_URL, req);
      const item = data.item;
      setItems(prev => [item, ...prev]);
      setTotal(prev => prev + 1);
      await fetchCounts();
      return item;
    },
    [fetchCounts]
  );

  const update = useCallback(
    async (id: number, req: SkillUpdateRequest): Promise<SkillItem> => {
      const data = await apiFetch<{ item: SkillItem }>(`${SKILLS_URL}/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(req),
      });
      const item = data.item;
      setItems(prev => prev.map(p => (p.id === id ? item : p)));
      await fetchCounts();
      return item;
    },
    [fetchCounts]
  );

  const remove = useCallback(
    async (id: number): Promise<void> => {
      await apiFetch<void>(`${SKILLS_URL}/${id}`, { method: 'DELETE' });
      setItems(prev => prev.filter(p => p.id !== id));
      setTotal(prev => Math.max(0, prev - 1));
      await fetchCounts();
    },
    [fetchCounts]
  );

  return {
    items,
    total,
    countsBySource,
    loading,
    error,
    source,
    tag,
    keyword,
    setSource,
    setTag,
    setKeyword,
    refresh,
    add,
    update,
    remove,
  };
}
