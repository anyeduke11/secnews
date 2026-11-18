/**
 * useQuery — 统一查询工厂 (FRONTEND_REWRITE_V1_PLAN §5)
 *
 * 目标: 消除 "组件内 useEffect + 三个 useState + 手写三态" 的重复,
 * 让同一 key 的并发消费者共享一次请求与一份缓存。
 *
 * 设计:
 *   - 模块级缓存 Map<key, entry>, entry 持有不可变快照 (useSyncExternalStore 要求)
 *   - entry 自带取数函数 / 空判定 / 订阅者, invalidate 不依赖旁路注册表
 *   - 同一 key 有在途请求时, 后来者复用同一 Promise (去抖 + 去重)
 *   - 命中缓存立即返回数据 (无 loading 闪烁); refetch / invalidate 才重新拉取
 *   - state 取值与 primitives/AsyncState 的 AsyncStatus 对齐:
 *       loading | ready | empty | error   (契约 §5 的 success ≡ 本实现的 ready)
 *   - invalidate(keyOrPrefix) 支持前缀 (例 'feed:' 命中 'feed:list:1'),
 *     无订阅者的条目直接淘汰, 下次挂载重新拉取
 *   - bindInvalidateOn(events, prefix) 复用 hooks/realtime.ts 的 SSE 事件名,
 *     由域层在 B4/B5 挂载时绑定 collect_done 等事件 (本文件不含域策略)
 */
import { useCallback, useSyncExternalStore } from 'react';
import { registerInvalidate, type RealtimeTimingOptions } from './realtime';

export type QueryState = 'loading' | 'ready' | 'empty' | 'error';

export interface QuerySnapshot<T> {
  data: T | undefined;
  state: QueryState;
  error: string | null;
}

export interface QueryResult<T> extends QuerySnapshot<T> {
  /** 强制重新拉取 (同一 key 的所有消费者共享结果) */
  refetch: () => void;
}

export interface UseQueryOptions<T> {
  /** 空值判定, 默认 undefined/null/空数组/空字符串 视为 empty */
  isEmpty?: (data: T) => boolean;
  /** false 时不发请求 (与 key=null 等价) */
  enabled?: boolean;
}

interface QueryEntry<T> {
  key: string;
  snapshot: QuerySnapshot<T>;
  listeners: Set<() => void>;
  promise: Promise<void> | null;
  fetcher: (() => Promise<T>) | null;
  isEmpty: (data: T) => boolean;
  lastUsed: number;
}

/** 缓存条目上限: 超过后淘汰无订阅者的最久未用条目 */
const MAX_ENTRIES = 200;

const entries = new Map<string, QueryEntry<unknown>>();

const DISABLED_SNAPSHOT: QuerySnapshot<never> = Object.freeze({
  data: undefined,
  state: 'empty',
  error: null,
});

function defaultIsEmpty(data: unknown): boolean {
  if (data === undefined || data === null) return true;
  if (Array.isArray(data)) return data.length === 0;
  if (typeof data === 'string') return data.length === 0;
  return false;
}

function ensureEntry<T>(key: string): QueryEntry<T> {
  let entry = entries.get(key) as QueryEntry<T> | undefined;
  if (!entry) {
    entry = {
      key,
      snapshot: { data: undefined, state: 'loading', error: null },
      listeners: new Set(),
      promise: null,
      fetcher: null,
      isEmpty: defaultIsEmpty as (data: T) => boolean,
      lastUsed: Date.now(),
    };
    entries.set(key, entry as QueryEntry<unknown>);
    evictIfNeeded();
  }
  return entry;
}

function evictIfNeeded(): void {
  if (entries.size <= MAX_ENTRIES) return;
  const idle = [...entries]
    .filter(([, e]) => e.listeners.size === 0)
    .sort((a, b) => a[1].lastUsed - b[1].lastUsed);
  for (const [key] of idle) {
    if (entries.size <= MAX_ENTRIES) break;
    entries.delete(key);
  }
}

function publish<T>(key: string, snapshot: QuerySnapshot<T>): void {
  const entry = entries.get(key) as QueryEntry<T> | undefined;
  if (!entry) return;
  entry.snapshot = snapshot;
  entry.lastUsed = Date.now();
  for (const listener of entry.listeners) listener();
}

async function load<T>(entry: QueryEntry<T>): Promise<void> {
  if (entry.promise) return entry.promise;
  const fetcher = entry.fetcher;
  if (!fetcher) return;
  const isEmpty = entry.isEmpty;

  // 已有数据时保持当前状态 (避免重拉导致闪白); 首次加载才置 loading
  if (entry.snapshot.data === undefined && entry.snapshot.state !== 'error') {
    publish(entry.key, { data: undefined, state: 'loading', error: null });
  }

  entry.promise = (async () => {
    try {
      const data = await fetcher();
      publish<T>(entry.key, { data, state: isEmpty(data) ? 'empty' : 'ready', error: null });
    } catch (e: unknown) {
      const message = e instanceof Error && e.message ? e.message : '请求失败';
      publish<T>(entry.key, { data: entry.snapshot.data, state: 'error', error: message });
    } finally {
      entry.promise = null;
    }
  })();
  return entry.promise;
}

/**
 * 按 key 精确失效, 或按前缀批量失效 (例 'feed:' / 'knowledge:case:42')。
 * 有订阅者的条目立即重拉; 无订阅者的条目被淘汰, 下次挂载重新请求。
 */
export function invalidate(keyOrPrefix: string): void {
  for (const [key, entry] of entries) {
    if (key !== keyOrPrefix && !key.startsWith(keyOrPrefix)) continue;
    if (entry.listeners.size === 0) {
      entries.delete(key);
      continue;
    }
    if (entry.promise) continue;
    void load(entry as QueryEntry<unknown>);
  }
}

/**
 * 绑定 SSE 事件 → 查询缓存前缀失效。
 * 事件名沿用 hooks/realtime.ts 的 SSE_EVENTS; 返回 disposer。
 * 例: bindInvalidateOn(SSE_EVENTS.COLLECT_DONE, 'feed:', { throttleMs: 3000 })
 */
export function bindInvalidateOn(
  eventTypes: string | string[],
  prefix: string,
  timing?: RealtimeTimingOptions,
): () => void {
  return registerInvalidate(eventTypes, () => invalidate(prefix), timing);
}

/**
 * 查询 hook。
 *
 * @param key     缓存键 (同 key 共享请求); null 表示不查询
 * @param fetcher 取数函数 (通常来自 api/<domain>.ts)
 */
export function useQuery<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  options: UseQueryOptions<T> = {},
): QueryResult<T> {
  const enabled = key !== null && (options.enabled ?? true);
  const isEmpty = options.isEmpty ?? (defaultIsEmpty as (data: T) => boolean);

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!enabled || !key) return () => {};
      const entry = ensureEntry<T>(key);
      entry.listeners.add(onStoreChange);
      entry.lastUsed = Date.now();
      if (entry.snapshot.data === undefined && entry.snapshot.state !== 'error' && !entry.promise) {
        void load(entry);
      }
      return () => {
        entries.get(key)?.listeners.delete(onStoreChange);
      };
    },
    [key, enabled],
  );

  const getSnapshot = useCallback((): QuerySnapshot<T> => {
    if (!enabled || !key) return DISABLED_SNAPSHOT as QuerySnapshot<T>;
    return ensureEntry<T>(key).snapshot;
  }, [key, enabled]);

  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  // 取数函数随渲染写入 entry —— invalidate 需要它才能重拉
  if (enabled && key) {
    const entry = ensureEntry<T>(key);
    entry.fetcher = fetcher;
    entry.isEmpty = isEmpty;
  }

  const refetch = useCallback(() => {
    if (!enabled || !key) return;
    const entry = ensureEntry<T>(key);
    entry.fetcher = fetcher;
    entry.isEmpty = isEmpty;
    void load(entry);
  }, [key, enabled, fetcher, isEmpty]);

  return { ...snapshot, refetch };
}

/** 仅供测试: 清空模块级缓存 */
export function __resetQueryCache(): void {
  entries.clear();
}
