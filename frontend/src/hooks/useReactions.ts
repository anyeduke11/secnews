/**
 * useReactions — 资讯赞/踩统一 Hook (DEV-0311)。
 *
 * 对标 useFavorites 的模块级单例模式 (useSyncExternalStore):
 *   - 初始化 GET /api/interest/reactions 回读 (90d 窗口);
 *   - react(): 同键=取消 (DELETE) / 异键=切换 (POST, 后端互斥);
 *   - 乐观更新 + 失败自动回滚。
 *
 * 边界:
 *   - available=false (初始化失败, 如 interest_engine gate 关闭 404) →
 *     调用方隐藏按钮, 不渲染死键;
 *   - DEV-0326: 所有条目均可赞/踩并持久化 (含非安全领域/未归类) —
 *     后端以哨兵域 + weight 0 记录 (点了就记住), 不再回滚乐观态。
 *
 * 后端契约 (backend/api/interest_api.py, DEV-0311):
 *   GET    /api/interest/reactions?days=90   → { items: {id: 'like'|'dislike'}, count }
 *   POST   /api/interest/signals             → { status, domain? } (互斥切换)
 *   DELETE /api/interest/reactions/{id}      → { status: 'ok', deleted }
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import {
  deleteReaction,
  fetchReactions,
  postReaction,
  type ReactionType,
} from '../lib/interest';

export type { ReactionType };

/**
 * reaction 最小目标 — 仅需 id (开关态键) 与 title (a11y 文案)。
 * 放宽后首页精选 / 告警 / feed / 历史 / 今日重点等异构资讯均可复用 (DEV-0326)。
 */
export interface ReactionTarget {
  id: string;
  title: string;
}

interface ReactionsStoreState {
  map: Map<string, ReactionType>;
  loading: boolean;
  error: string | null;
  available: boolean;
}

// ── 模块级单例 store ──────────────────────────────────────────
let state: ReactionsStoreState = {
  map: new Map(),
  loading: false,
  error: null,
  available: false, // 回读成功才开放按钮 (gate 关闭/端点挂 → 隐藏)
};

const listeners = new Set<() => void>();
let refreshPromise: Promise<void> | null = null;

function updateState(updater: (prev: ReactionsStoreState) => ReactionsStoreState) {
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

function getSnapshot(): ReactionsStoreState {
  return state;
}

/** 回读 reaction 状态表 (并发去重, 不抛错 — 错误写入 error 状态) */
export function refreshReactions(): Promise<void> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    updateState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const items = await fetchReactions();
      updateState(() => ({
        map: new Map(Object.entries(items)),
        loading: false,
        error: null,
        available: true,
      }));
    } catch (e) {
      updateState(prev => ({
        ...prev,
        loading: false,
        error: (e as Error).message || '加载赞踩状态失败',
        available: false, // 端点不可用 → 上层隐藏按钮 (fail-safe, 不做假的可用承诺)
      }));
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/**
 * 赞/踩操作: 同键 = 取消 (删信号), 异键 = 切换/首设 (POST, 后端互斥)。
 * 乐观更新立即翻转本地状态; 请求失败自动回滚并写入 error (不向调用方抛错)。
 */
export function reactToItem(item: ReactionTarget, type: ReactionType): Promise<void> {
  const current = state.map.get(item.id);
  const isCancel = current === type;

  // 乐观更新
  updateState(prev => {
    const map = new Map(prev.map);
    if (isCancel) map.delete(item.id);
    else map.set(item.id, type);
    return { ...prev, map, error: null };
  });

  return (async () => {
    try {
      if (isCancel) {
        await deleteReaction(item.id);
        return;
      }
      await postReaction(item.id, type);
    } catch (e) {
      // 失败回滚 (恢复操作前状态: 无态度 / like / dislike)
      updateState(prev => {
        const map = new Map(prev.map);
        if (current === undefined) map.delete(item.id);
        else map.set(item.id, current);
        return { ...prev, map, error: (e as Error).message || '赞踩操作失败' };
      });
    }
  })();
}

/** 仅测试使用: 重置模块级单例状态 */
export function resetReactionsStore(): void {
  state = { map: new Map(), loading: false, error: null, available: false };
  refreshPromise = null;
  listeners.forEach(l => l());
}

export interface UseReactionsReturn {
  reactionOf: (id: string) => ReactionType | undefined;
  /** 赞/踩 (同键取消/异键切换); 失败自动回滚 + error, 不向调用方抛错 */
  react: (item: ReactionTarget, type: ReactionType) => Promise<void>;
  available: boolean;
  loading: boolean;
  error: string | null;
}

export function useReactions(): UseReactionsReturn {
  const { map, loading, error, available } = useSyncExternalStore(subscribe, getSnapshot);

  const reactionOf = useCallback((id: string) => map.get(id), [map]);

  // 挂载时拉一次 (内部并发去重, 多个实例只发一次请求)
  useEffect(() => {
    refreshReactions();
  }, []);

  return { reactionOf, react: reactToItem, available, loading, error };
}