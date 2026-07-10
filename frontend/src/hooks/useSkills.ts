import { useState, useEffect, useCallback, useRef } from 'react';
import {
  SkillItem,
  SkillListResponse,
  SkillCountBySourceResponse,
  SkillSource,
  SkillCreateRequest,
  SkillUpdateRequest,
} from '../types';

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

/**
 * Phase 41: Skill 管理 Hook
 *
 * 负责:
 *  - 列表 (source / tag / keyword 过滤)
 *  - count_by_source 统计
 *  - CRUD: add / update / remove
 */
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

        const r = await fetch(`/api/skills?${params}`, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        });
        if (!r.ok) throw new Error(`请求失败 (${r.status})`);

        const data: SkillListResponse = await r.json();
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
      const r = await fetch('/api/skills/count_by_source', {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return;
      const data: SkillCountBySourceResponse = await r.json();
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
      const r = await fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const errBody = await r.text().catch(() => '');
        throw new Error(`新建失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      const data = await r.json();
      const item: SkillItem = data.item;
      setItems(prev => [item, ...prev]);
      setTotal(prev => prev + 1);
      await fetchCounts();
      return item;
    },
    [fetchCounts]
  );

  const update = useCallback(
    async (id: number, req: SkillUpdateRequest): Promise<SkillItem> => {
      const r = await fetch(`/api/skills/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const errBody = await r.text().catch(() => '');
        throw new Error(`更新失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      const data = await r.json();
      const item: SkillItem = data.item;
      setItems(prev => prev.map(p => (p.id === id ? item : p)));
      await fetchCounts();
      return item;
    },
    [fetchCounts]
  );

  const remove = useCallback(
    async (id: number): Promise<void> => {
      const r = await fetch(`/api/skills/${id}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) {
        throw new Error(`删除失败 (${r.status})`);
      }
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
