/**
 * realtime.ts — 统一的 "SSE 事件 → 失效动作" 注册器 (Batch 5 任务 C)
 *
 * 背景: 前端此前并存两套 SSE 失效实现 —
 *   1. sentinel 域 "事件 → 节流重拉" (原 useSSE 直接调用, 2026-09-13 已全部迁移至本模块)
 *   2. v1 域 "事件 → 精确失效" (useSSEAggregateInvalidate / useSSEWithRefetch, Batch 5 已迁移)
 * 本模块是第三套的"防波堤": 今后任何新的 SSE 失效消费方都从这里注册,
 * 不得再直接 new useSSE 自建连接 (useSSE 底座本身保持不动)。
 *
 * API 面:
 *   - SSE_EVENTS / V1_AGGREGATE_EVENT_TYPES  事件类型常量 (避免魔法字符串扩散)
 *   - registerInvalidate(types, handler, opts) 模块级注册, 返回 disposer。
 *     事件由"主 hub" (当前第一个挂载的 useRealtimeInvalidation 连接) 分发,
 *     避免多连接并发分发导致同一 handler 被重复触发。
 *     注意: 没有任何 hub 挂载时注册的 handler 处于休眠状态 (不建连接) —
 *     本应用三层壳常驻, hub 实际上始终在线。
 *   - useRealtimeInvalidation(entries, opts)  组合式: 内部基于 useSSE
 *     (复用其自动重连 / lastId 断线续传 / rAF 分帧), 对 entries 做类型路由,
 *     每个 entry 可选 throttleMs / debounceMs, unmount 时清理定时器与连接。
 *
 * 与 useSSE 的 types 过滤的关系: hub 不向 useSSE 传 types (接收全量事件),
 * 类型过滤统一下沉到 dispatcher 匹配。语义等价 (useSSE 的 types 过滤也只作用于
 * onEvent), 且支持 registry 动态注册 — 连接期固定的 types 数组无法覆盖后注册的
 * handler。
 *
 * 迁移状态 (2026-09-13): 全部消费方已收尾, 全仓 useSSE 唯一调用点 = 本文件内部底座。
 * 已完成的 sentinel 域迁移 (节流窗口 / 事件过滤 / 只读重拉语义逐字等价):
 *   - src/components/sentinel/SentinelHomePage.tsx  (collect_done → 心跳条 + 右栏 10s 节流 + 主列 3s 合并)
 *   - src/components/sentinel/SentinelJudgePage.tsx (collect_done → 心跳条 + 30s 节流 load; 已删 DEV-0258, 历史迁移记录)
 *   - src/components/sentinel/SentinelGraphPage.tsx (全量事件 → 心跳条 + 30s 节流 load)
 *   - src/components/sentinel/SentinelGardenPage.tsx (全量事件 → 15s 节流 reloadPipe + load)
 *   - src/components/sentinel/SentinelShell.tsx usePipeReloadOnSse: 非 SSE 消费方 (不带连接),
 *     10s 节流 + 模块级 mountedReload 优先 (DEV-0167) 原样保留, 由各页 realtime handler 调用。
 */
import { useCallback, useEffect, useRef } from 'react';
import { useSSE } from './useSSE';

// ---------------------------------------------------------------------------
// 事件类型常量 (与 backend core/events.py publish_event 及 v1 repo 写入对齐)
// ---------------------------------------------------------------------------

export const SSE_EVENTS = {
  /** 一轮采集完成 (sentinel 资料层/心跳条只关心这个) */
  COLLECT_DONE: 'collect_done',
  /** 单篇提取完成 */
  EXTRACT_DONE: 'extract_done',
  /** 后台 job 结束 */
  JOB_DONE: 'job_done',
  /** 管线告警 */
  ALERT: 'alert',
  /** 资讯告警落库 (2026-09-27 四模式 P1, payload {count}; 首页「告警」未读徽标刷新) */
  NEWS_ALERT: 'news_alert',
  /** CodeGarden 任务完成 */
  TASK_DONE: 'task_done',
  /** v1 判断发布 (judgment_id / case_id / revision) */
  V1_JUDGMENT: 'v1_judgment',
  /** v1 行动变更 (action_id / case_id / revision) */
  V1_ACTION: 'v1_action',
  /** v1 产物 verify/accept (artifact_id / run_id / case_id / revision) */
  V1_ARTIFACT: 'v1_artifact',
  /** v1 知识更新 (knowledge_id / case_id / revision) */
  V1_KNOWLEDGE: 'v1_knowledge',
  /** v1 信号录入 (signal_id / case_id / revision) */
  V1_SIGNAL: 'v1_signal',
} as const;

/** 5 个携带 case_id + revision payload 的 v1 aggregate 事件类型 */
export const V1_AGGREGATE_EVENT_TYPES: string[] = [
  SSE_EVENTS.V1_JUDGMENT,
  SSE_EVENTS.V1_ACTION,
  SSE_EVENTS.V1_ARTIFACT,
  SSE_EVENTS.V1_KNOWLEDGE,
  SSE_EVENTS.V1_SIGNAL,
];

/** SSE 失效 handler: (event_type, payload) */
export type RealtimeHandler = (type: string, data: unknown) => void;

export interface RealtimeTimingOptions {
  /** 节流窗口 (ms): 窗口内首条触发, 其余丢弃。与 debounceMs 同设时 debounce 先合并、throttle 再限速 */
  throttleMs?: number;
  /** 防抖窗口 (ms): 窗口内最后一条触发 (适合"连续事件合并为一次重拉") */
  debounceMs?: number;
}

export interface RealtimeEntry extends RealtimeTimingOptions {
  /** 只匹配这些事件类型; 省略 = 匹配所有事件 */
  types?: string | string[];
  handler: RealtimeHandler;
}

// ---------------------------------------------------------------------------
// throttle / debounce 包装 (零依赖; 暴露 cancel 供 unmount/注销清理)
// ---------------------------------------------------------------------------

interface TimedHandler {
  invoke: RealtimeHandler;
  cancel: () => void;
}

function makeTimedHandler(handler: RealtimeHandler, opts: RealtimeTimingOptions): TimedHandler {
  const { throttleMs, debounceMs } = opts;
  const hasThrottle = typeof throttleMs === 'number' && throttleMs > 0;
  const hasDebounce = typeof debounceMs === 'number' && debounceMs > 0;

  if (hasDebounce && hasThrottle) {
    // debounce 合并 → 外层再 throttle 限速
    let timer: number | null = null;
    let lastFire = 0;
    return {
      invoke: (type, data) => {
        if (timer !== null) window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          timer = null;
          const now = Date.now();
          if (now - lastFire < (throttleMs as number)) return;
          lastFire = now;
          handler(type, data);
        }, debounceMs as number);
      },
      cancel: () => {
        if (timer !== null) {
          window.clearTimeout(timer);
          timer = null;
        }
      },
    };
  }

  if (hasDebounce) {
    let timer: number | null = null;
    return {
      invoke: (type, data) => {
        if (timer !== null) window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          timer = null;
          handler(type, data);
        }, debounceMs as number);
      },
      cancel: () => {
        if (timer !== null) {
          window.clearTimeout(timer);
          timer = null;
        }
      },
    };
  }

  if (hasThrottle) {
    let lastFire = 0;
    return {
      invoke: (type, data) => {
        const now = Date.now();
        if (now - lastFire < (throttleMs as number)) return;
        lastFire = now;
        handler(type, data);
      },
      cancel: () => {
        lastFire = 0;
      },
    };
  }

  return { invoke: handler, cancel: () => {} };
}

function toTypeSet(types?: string | string[]): Set<string> | null {
  if (!types) return null;
  return new Set(Array.isArray(types) ? types : [types]);
}

// ---------------------------------------------------------------------------
// 模块级注册表 (registerInvalidate)
// ---------------------------------------------------------------------------

const registry = new Map<number, { types: Set<string> | null; timed: TimedHandler }>();
let registrySeq = 0;

/**
 * 模块级注册一个 "SSE 事件 → 失效动作"。
 * 事件由当前挂载的主 hub (第一个 useRealtimeInvalidation 连接) 分发;
 * 返回 disposer, 组件 unmount / effect cleanup 时必须调用。
 */
export function registerInvalidate(
  types: string | string[] | undefined,
  handler: RealtimeHandler,
  opts: RealtimeTimingOptions = {},
): () => void {
  const key = ++registrySeq;
  registry.set(key, { types: toTypeSet(types), timed: makeTimedHandler(handler, opts) });
  return () => {
    const reg = registry.get(key);
    if (reg) {
      reg.timed.cancel();
      registry.delete(key);
    }
  };
}

// 主 hub 裁决: 只有第一个挂载的 hub 分发 registry 事件, 防多连接重复触发
const hubStack: symbol[] = [];

// ---------------------------------------------------------------------------
// 组合式 hook
// ---------------------------------------------------------------------------

export interface UseRealtimeInvalidationOptions {
  /** 透传 useSSE: 从外部注入 last_id (跨刷新续传) */
  initialLastId?: number;
  /** 透传 useSSE: 收到每条事件时回调 (id 持久化到 localStorage) */
  onLastId?: (id: number) => void;
  autoReconnect?: boolean;
  reconnectDelay?: number;
}

export interface UseRealtimeInvalidationResult {
  connected: boolean;
  lastId: number;
}

/**
 * 统一的 SSE 失效入口。挂载一条 useSSE 连接, 把事件按 entries 路由
 * (types 匹配 + throttle/debounce), 同时分发给 registerInvalidate 注册的
 * 模块级 handler (仅主 hub)。unmount 关闭连接并清理 pending 定时器。
 */
export function useRealtimeInvalidation(
  entries: RealtimeEntry[] = [],
  opts: UseRealtimeInvalidationOptions = {},
): UseRealtimeInvalidationResult {
  const tokenRef = useRef<symbol>(Symbol('realtime-hub'));

  // handler / types 每次渲染同步到 ref (entry 可能是内联字面量, 引用每次变化)
  const handlersRef = useRef<(RealtimeHandler | undefined)[]>([]);
  handlersRef.current = entries.map((e) => e.handler);
  const typesRef = useRef<(Set<string> | null)[]>([]);
  typesRef.current = entries.map((e) => toTypeSet(e.types));
  const entriesRef = useRef(entries);
  entriesRef.current = entries;

  // 定时器状态 (throttle lastFire / debounce timer) 必须跨渲染存活,
  // 只在 entry 数量或 timing 配置变化时重建 (重建即重置计时窗口)。
  const slotsRef = useRef<TimedHandler[] | null>(null);
  const timingSigRef = useRef<string | null>(null);
  const timingSig = entries.map((e) => `${e.throttleMs ?? 0}:${e.debounceMs ?? 0}`).join('|');
  if (slotsRef.current === null || slotsRef.current.length !== entries.length || timingSigRef.current !== timingSig) {
    timingSigRef.current = timingSig;
    // 重建前取消旧 slots 的 pending 定时器, 否则旧 debounce 在 unmount 后仍会触发
    if (slotsRef.current) {
      for (const old of slotsRef.current) old.cancel();
    }
    slotsRef.current = entries.map((_, i) => {
      const entry: RealtimeEntry | undefined = entries[i];
      // 稳定的 "调用当前 handler" 内核: handler 引用变化不重置计时状态
      const invokeCurrent: RealtimeHandler = (type, data) => {
        handlersRef.current[i]?.(type, data);
      };
      return makeTimedHandler(invokeCurrent, {
        throttleMs: entry?.throttleMs,
        debounceMs: entry?.debounceMs,
      });
    });
  }

  // unmount 清理 pending 定时器 (经 ref 读最新 slots, 避免闭包捕获过期数组)
  useEffect(() => {
    return () => {
      const slots = slotsRef.current;
      if (slots) {
        for (const slot of slots) slot.cancel();
      }
    };
  }, []);

  // 主 hub 登记 / 注销
  useEffect(() => {
    const token = tokenRef.current;
    hubStack.push(token);
    return () => {
      const i = hubStack.indexOf(token);
      if (i >= 0) hubStack.splice(i, 1);
    };
  }, []);

  // 事件分发: entries 类型匹配 + 主 hub 期间分发模块级 registry
  const dispatchRef = useRef<(type: string, data: unknown) => void>(() => {});
  dispatchRef.current = (type, data) => {
    const slots = slotsRef.current ?? [];
    for (let i = 0; i < slots.length; i++) {
      const wanted = typesRef.current[i];
      if (wanted && !wanted.has(type)) continue;
      slots[i]?.invoke(type, data);
    }
    if (hubStack[0] === tokenRef.current) {
      for (const reg of registry.values()) {
        if (reg.types && !reg.types.has(type)) continue;
        reg.timed.invoke(type, data);
      }
    }
  };

  const onEvent = useCallback((type: string, data: unknown) => {
    dispatchRef.current(type, data);
  }, []);

  // 不向 useSSE 传 types: 全量事件进入 dispatcher, 由 dispatcher 统一做
  // 类型匹配 (语义等价 useSSE 的 types 过滤, 且支持 registry 动态注册)。
  return useSSE({
    onEvent,
    autoReconnect: opts.autoReconnect ?? true,
    reconnectDelay: opts.reconnectDelay ?? 3000,
    initialLastId: opts.initialLastId ?? 0,
    onLastId: opts.onLastId,
  });
}
