/**
 * useFavorites — 收藏统一 Hook (P0 重构)。
 *
 * 收敛原先散布在 App.tsx / DataLayerPage.tsx / favorites/index.tsx /
 * DataFavoritesPage.tsx 的 4 份「拉取 + 乐观更新 + 失败回滚」重复实现。
 *
 * 设计:
 *   - 模块级单例 store + useSyncExternalStore: 所有 useFavorites 实例
 *     共享同一份收藏状态, 跨页/跨组件不再各持一份导致不同步。
 *   - 乐观更新: toggleFavorite 立即翻转本地 ids/count, 请求失败自动回滚。
 *   - refresh 内部去重: 多个实例同时挂载只发一次 GET /api/favorites。
 *
 * 对外 API:
 *   favorites      Set<string>   已收藏 hotspot_id 集合
 *   count          number        收藏总数 (后端 total)
 *   isFavorite(id) boolean       是否已收藏
 *   toggleFavorite(item) Promise 乐观翻转收藏 (POST/DELETE), 失败回滚
 *   refresh()      Promise       重新拉取收藏列表
 *   loading        boolean       拉取中
 *   error          string|null   最近一次错误
 *
 * 后端契约 (backend/api/favorites.py):
 *   GET    /api/favorites?limit=1000  → { total, items: [{ hotspot_id, ... }] }
 *   POST   /api/favorites             → { status, created, item }
 *   DELETE /api/favorites/{hotspot_id} → { status, hotspot_id, removed }
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { apiFetch } from '../lib/api';
import type {
  AddFavoriteResponse,
  FavoritesListResponse,
  HotspotItem,
  RemoveFavoriteResponse,
} from '../types';

interface FavoritesStoreState {
  ids: Set<string>;
  total: number;
  loading: boolean;
  error: string | null;
}

// ── 模块级单例 store ──────────────────────────────────────────
let state: FavoritesStoreState = {
  ids: new Set(),
  total: 0,
  loading: false,
  error: null,
};

const listeners = new Set<() => void>();
let refreshPromise: Promise<void> | null = null;

function updateState(updater: (prev: FavoritesStoreState) => FavoritesStoreState) {
  const next = updater(state);
  if (next === state) return;
  state = next;
  listeners.forEach(l => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): FavoritesStoreState {
  return state;
}

/** 拉取收藏列表 (并发去重, 不抛错 — 错误写入 error 状态) */
export function refreshFavorites(): Promise<void> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    updateState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const data = await apiFetch<FavoritesListResponse>('/api/favorites?limit=1000');
      updateState(() => ({
        ids: new Set((data.items || []).map(it => it.hotspot_id)),
        total: data.total || 0,
        loading: false,
        error: null,
      }));
    } catch (e) {
      updateState(prev => ({
        ...prev,
        loading: false,
        error: (e as Error).message || '加载收藏失败',
      }));
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/** 乐观翻转收藏状态; 失败自动回滚并写入 error (不向调用方抛错) */
export function toggleFavorite(item: HotspotItem): Promise<void> {
  const wasFavorited = state.ids.has(item.id);

  // 乐观更新: 立即翻转 ids + count
  updateState(prev => {
    const ids = new Set(prev.ids);
    if (wasFavorited) ids.delete(item.id);
    else ids.add(item.id);
    return {
      ...prev,
      ids,
      total: Math.max(0, prev.total + (wasFavorited ? -1 : 1)),
      error: null,
    };
  });

  return (async () => {
    try {
      if (wasFavorited) {
        const r = await apiFetch<RemoveFavoriteResponse>(
          `/api/favorites/${encodeURIComponent(item.id)}`,
          { method: 'DELETE' },
        );
        // 服务端本来就没有该收藏 → 总数不应 -1
        if (!r.removed) {
          updateState(prev => ({ ...prev, total: prev.total + 1 }));
        }
      } else {
        const r = await apiFetch<AddFavoriteResponse>('/api/favorites', {
          method: 'POST',
          body: JSON.stringify({
            hotspot_id: item.id,
            category: item.category,
            title: item.title,
            source: item.source,
            url: item.url,
          }),
        });
        // 后端 created=false → 本来已收藏, 总数不应 +1
        if (!r.created) {
          updateState(prev => ({ ...prev, total: Math.max(0, prev.total - 1) }));
        }
      }
    } catch (e) {
      // 失败回滚
      updateState(prev => {
        const ids = new Set(prev.ids);
        if (wasFavorited) ids.add(item.id);
        else ids.delete(item.id);
        return {
          ...prev,
          ids,
          total: Math.max(0, prev.total + (wasFavorited ? 1 : -1)),
          error: (e as Error).message || '收藏操作失败',
        };
      });
    }
  })();
}

/**
 * 外部同步入口 (供 FavoritesPanel 的 onFavoritesChange / onCountChange 桥接)。
 * 传 ids 则整体替换收藏集合; 传 count 则只更新总数。
 */
export function syncFavorites(ids?: Set<string>, count?: number): void {
  updateState(prev => {
    const next: FavoritesStoreState = { ...prev, error: null };
    if (ids) next.ids = new Set(ids);
    if (count !== undefined) next.total = count;
    return next;
  });
}

/** 仅测试使用: 重置模块级单例状态 */
export function resetFavoritesStore(): void {
  state = { ids: new Set(), total: 0, loading: false, error: null };
  refreshPromise = null;
  listeners.forEach(l => l());
}

export interface UseFavoritesReturn {
  favorites: Set<string>;
  count: number;
  isFavorite: (id: string) => boolean;
  toggleFavorite: (item: HotspotItem) => Promise<void>;
  refresh: () => Promise<void>;
  loading: boolean;
  error: string | null;
}

export function useFavorites(): UseFavoritesReturn {
  const { ids, total, loading, error } = useSyncExternalStore(subscribe, getSnapshot);

  const isFavorite = useCallback((id: string) => ids.has(id), [ids]);

  const refresh = useCallback(() => refreshFavorites(), []);

  // 挂载时拉一次 (内部并发去重, 多个实例只发一次请求)
  useEffect(() => {
    refreshFavorites();
  }, []);

  return {
    favorites: ids,
    count: total,
    isFavorite,
    toggleFavorite,
    refresh,
    loading,
    error,
  };
}
