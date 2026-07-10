import { useState, useEffect, useCallback, useRef } from 'react';
import {
  TodoItem,
  TodoStatus,
  TodoListResponse,
  TodoCountResponse,
  TodoCreateRequest,
  TodoUpdateRequest,
  AvailableFavorite,
} from '../types';

export interface TodosFilter {
  status: TodoStatus | 'all';
  urgent: boolean | null;
  important: boolean | null;
  keyword: string;
}

export interface UseTodosReturn {
  // 数据
  items: TodoItem[];
  total: number;
  count: TodoCountResponse | null;
  availableFavorites: AvailableFavorite[];

  // 状态
  filter: TodosFilter;
  loading: boolean;
  error: string | null;

  // 操作
  setFilter: (patch: Partial<TodosFilter>) => void;
  refresh: () => Promise<void>;
  add: (req: TodoCreateRequest) => Promise<{ item: TodoItem; created: boolean }>;
  update: (id: number, req: TodoUpdateRequest) => Promise<TodoItem>;
  remove: (id: number) => Promise<void>;

  // 内部: 检查某 favorite 是否已在 todo
  isFavoriteInTodo: (sourceId: string) => boolean;
}

const DEFAULT_FILTER: TodosFilter = {
  status: 'all',
  urgent: null,
  important: null,
  keyword: '',
};

/**
 * Phase 36: Todo Hook
 *
 * 负责:
 *  - 列表拉取 (支持 status/urgent/important 过滤)
 *  - 计数拉取 (按 status / 优先级四象限)
 *  - 可选收藏拉取 (用于 add 对话框选择)
 *  - CRUD: add / update / remove
 *  - 客户端 keyword 过滤 (不重拉)
 */
export function useTodos(): UseTodosReturn {
  const [items, setItems] = useState<TodoItem[]>([]);
  const [total, setTotal] = useState(0);
  const [count, setCount] = useState<TodoCountResponse | null>(null);
  const [availableFavorites, setAvailableFavorites] = useState<AvailableFavorite[]>([]);
  const [filter, setFilterState] = useState<TodosFilter>(DEFAULT_FILTER);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 取消上一次 list 请求 (防止快速切换过滤条件导致旧数据覆盖新数据)
  const listAbortRef = useRef<AbortController | null>(null);

  // 将后端 0/1 规范化为 boolean
  const toBool = (v: unknown): boolean => v === 1 || v === true;

  const fetchList = useCallback(
    async (currentFilter: TodosFilter) => {
      // 取消上一次 list 请求
      if (listAbortRef.current) {
        listAbortRef.current.abort();
      }
      const controller = new AbortController();
      listAbortRef.current = controller;

      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams({ limit: '200' });
        if (currentFilter.status !== 'all') {
          params.set('status', currentFilter.status);
        }
        if (currentFilter.urgent !== null) {
          params.set('urgent', currentFilter.urgent ? '1' : '0');
        }
        if (currentFilter.important !== null) {
          params.set('important', currentFilter.important ? '1' : '0');
        }

        const r = await fetch(`/api/todos?${params}`, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        });
        if (!r.ok) throw new Error(`请求失败 (${r.status})`);

        const data: TodoListResponse = await r.json();
        // 归一化 urgent/important 为 boolean
        const normalized: TodoItem[] = (data.items || []).map(it => ({
          ...it,
          urgent: toBool(it.urgent),
          important: toBool(it.important),
        }));
        setItems(normalized);
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

  const fetchCount = useCallback(async () => {
    try {
      const r = await fetch('/api/todos/count', {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return;
      const data: TodoCountResponse = await r.json();
      setCount(data);
    } catch {
      // 静默: 计数拉取失败不影响列表
    }
  }, []);

  const fetchAvailableFavorites = useCallback(async () => {
    try {
      const r = await fetch('/api/todos/available_favorites?limit=200', {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return;
      const data = await r.json();
      setAvailableFavorites(data.items || []);
    } catch {
      // 静默: 可选收藏拉取失败不影响主流程
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([
      fetchList(filter),
      fetchCount(),
      fetchAvailableFavorites(),
    ]);
  }, [filter, fetchList, fetchCount, fetchAvailableFavorites]);

  // 初次 mount: 并行拉取 3 个端点
  useEffect(() => {
    refresh();
    return () => {
      if (listAbortRef.current) listAbortRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // filter.status / urgent / important 变化 → 重新拉 list (debounce 200ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchList(filter);
    }, 200);
    return () => clearTimeout(timer);
  }, [filter.status, filter.urgent, filter.important, fetchList]);

  const setFilter = useCallback((patch: Partial<TodosFilter>) => {
    setFilterState(prev => ({ ...prev, ...patch }));
  }, []);

  const add = useCallback(
    async (req: TodoCreateRequest): Promise<{ item: TodoItem; created: boolean }> => {
      const r = await fetch('/api/todos', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const errBody = await r.text().catch(() => '');
        throw new Error(`新建失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      const data = await r.json();
      const item: TodoItem = {
        ...data.item,
        urgent: toBool(data.item.urgent),
        important: toBool(data.item.important),
      };

      // 立即更新 items (用 filter 决定是否需要把新 item 插入)
      setItems(prev => {
        // 简化: 总是 prepend, 客户端 keyword 过滤会处理显示
        // 去重: 避免重复时覆盖
        const exists = prev.some(p => p.id === item.id);
        if (exists) {
          return prev.map(p => (p.id === item.id ? item : p));
        }
        return [item, ...prev];
      });
      setTotal(prev => prev + (data.created ? 1 : 0));

      // 重拉 count 和 available_favorites (可能新增 / 占用)
      await Promise.all([fetchCount(), fetchAvailableFavorites()]);

      return { item, created: !!data.created };
    },
    [fetchCount, fetchAvailableFavorites]
  );

  const update = useCallback(
    async (id: number, req: TodoUpdateRequest): Promise<TodoItem> => {
      const r = await fetch(`/api/todos/${id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const errBody = await r.text().catch(() => '');
        throw new Error(`更新失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      const data = await r.json();
      const item: TodoItem = {
        ...data.item,
        urgent: toBool(data.item.urgent),
        important: toBool(data.item.important),
      };

      // 更新对应 item
      setItems(prev => prev.map(p => (p.id === id ? item : p)));

      // 重拉 count (状态 / 优先级可能变化)
      await fetchCount();

      return item;
    },
    [fetchCount]
  );

  const remove = useCallback(
    async (id: number): Promise<void> => {
      const r = await fetch(`/api/todos/${id}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) {
        throw new Error(`删除失败 (${r.status})`);
      }
      // 从 items 移除
      setItems(prev => prev.filter(p => p.id !== id));
      setTotal(prev => Math.max(0, prev - 1));

      // 重拉 count 和 available_favorites
      await Promise.all([fetchCount(), fetchAvailableFavorites()]);
    },
    [fetchCount, fetchAvailableFavorites]
  );

  const isFavoriteInTodo = useCallback(
    (sourceId: string): boolean => {
      return items.some(
        it => it.source_type === 'favorite' && it.source_id === sourceId
      );
    },
    [items]
  );

  return {
    items,
    total,
    count,
    availableFavorites,
    filter,
    loading,
    error,
    setFilter,
    refresh,
    add,
    update,
    remove,
    isFavoriteInTodo,
  };
}
