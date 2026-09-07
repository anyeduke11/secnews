import { useState, useEffect, useRef, useCallback } from 'react';

interface SSEEvent {
  type: string;
  data: any;
  ts: string;
  // C11 R18: 来自后端 outbox 的 SQLite AUTOINCREMENT id.
  // 浏览器 EventSource 自动从 SSE `id:` 字段填充 lastEventId (字符串),
  // 我们统一转为 number 便于 ?last_id= 续传.
  id?: number;
}

interface UseSSEOptions {
  onEvent?: (type: string, data: any) => void;
  autoReconnect?: boolean;
  reconnectDelay?: number;
  // C11 R18: 从外部注入 last_id (例如与 V1Prototype 共享, 跨断线续传).
  initialLastId?: number;
  // C11 R18: 收到每条事件时回调 (暴露 id 给上层持久化到 localStorage).
  onLastId?: (id: number) => void;
}

interface UseSSEResult {
  connected: boolean;
  lastEvent: SSEEvent | null;
  // C11 R18: 当前已收到的最大 outbox id, 用于断线后 ?last_id= 续传.
  lastId: number;
}

/**
 * SSE 事件流 Hook — 连接后端 /api/events SSE 端点。
 *
 * 用法:
 *   useSSE({ onEvent: (type, data) => { ... } })
 *
 * 自动重连（默认 3s 延时）。
 * 断开时返回 connected=false。
 *
 * C11 R18 升级 (Last-Event-ID 续传):
 *   - 浏览器 EventSource 原生支持 SSE `id:` 字段, 自动填充 e.lastEventId
 *     (来自后端 publish_event 写 `id: {outbox_id}` 行)
 *   - 重连时把 lastId 拼到 URL: `EventSource("/api/events?last_id=N")`
 *     后端启动期回放 v1_outbox WHERE id > N 的所有未广播行 (含 dispatcher 跳过的)
 *   - onLastId 回调供上层持久化到 localStorage, 跨标签页/跨刷新续传
 *
 * P0.3: 节流 + 分帧
 * - onEvent 回调立即执行 (业务逻辑不延迟)
 * - lastEvent 状态更新用 requestAnimationFrame 批处理
 *   高频消息时只在下一帧 setState 最后一条, 避免渲染风暴
 */
export function useSSE(options: UseSSEOptions = {}): UseSSEResult {
  const {
    onEvent,
    autoReconnect = true,
    reconnectDelay = 3000,
    initialLastId = 0,
    onLastId,
  } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  // C11 R18: lastId 持久化, 重连时拼到 URL.
  // 使用 ref 而非 state, 避免每次更新都触发重渲染 (对断线重连延迟敏感).
  const lastIdRef = useRef<number>(initialLastId);
  const onEventRef = useRef(onEvent);
  const onLastIdRef = useRef(onLastId);
  const reconnectTimerRef = useRef<number | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // P0.3: raf 批处理 refs
  const pendingEventRef = useRef<SSEEvent | null>(null);
  const rafRef = useRef<number | null>(null);

  // 保持 callback 引用最新
  onEventRef.current = onEvent;
  onLastIdRef.current = onLastId;

  const connect = useCallback(() => {
    // 清理旧连接
    if (esRef.current) {
      esRef.current.close();
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    // C11 R18: 把 lastId 拼到 URL, 后端启动期回放未广播行.
    // 注意: 浏览器 EventSource 不支持自定义 header, 只能走 query string.
    const url = lastIdRef.current > 0
      ? `/api/events?last_id=${lastIdRef.current}`
      : '/api/events';

    let es: EventSource;
    try {
      es = new EventSource(url);
      esRef.current = es;
    } catch {
      setConnected(false);
      scheduleReconnect();
      return;
    }

    es.onopen = () => {
      setConnected(true);
    };

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        // C11 R18: 优先用事件 payload 里的 id (后端 publish_event 写入),
        // 回退用浏览器原生 lastEventId (SSE `id:` 字段).
        const eid = event.id
          ?? (e.lastEventId && /^\d+$/.test(e.lastEventId) ? Number(e.lastEventId) : 0);
        if (eid > 0) {
          lastIdRef.current = Math.max(lastIdRef.current, eid);
          onLastIdRef.current?.(eid);
        }
        // P0.3: onEvent 立即执行 (业务逻辑不延迟)
        onEventRef.current?.(event.type, event.data);
        // P0.3: lastEvent 更新分帧 — 缓存到 ref, 下一帧只 setState 最后一条
        pendingEventRef.current = event;
        if (rafRef.current === null) {
          rafRef.current = requestAnimationFrame(() => {
            rafRef.current = null;
            if (pendingEventRef.current) {
              setLastEvent(pendingEventRef.current);
              pendingEventRef.current = null;
            }
          });
        }
      } catch {
        // 忽略解析错误
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
      esRef.current = null;
      scheduleReconnect();
    };
  }, [autoReconnect, reconnectDelay]);

  const scheduleReconnect = useCallback(() => {
    if (!autoReconnect) return;
    if (reconnectTimerRef.current !== null) return;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, reconnectDelay);
  }, [autoReconnect, reconnectDelay, connect]);

  useEffect(() => {
    connect();
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      // P0.3: 清理 raf
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [connect]);

  return { connected, lastEvent, lastId: lastIdRef.current };
}