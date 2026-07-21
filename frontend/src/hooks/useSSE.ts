import { useState, useEffect, useRef, useCallback } from 'react';

interface SSEEvent {
  type: string;
  data: any;
  ts: string;
}

interface UseSSEOptions {
  onEvent?: (type: string, data: any) => void;
  autoReconnect?: boolean;
  reconnectDelay?: number;
}

interface UseSSEResult {
  connected: boolean;
  lastEvent: SSEEvent | null;
}

/**
 * SSE 事件流 Hook — 连接后端 /api/events SSE 端点。
 *
 * 用法:
 *   useSSE({ onEvent: (type, data) => { ... } })
 *
 * 自动重连（默认 3s 延时）。
 * 断开时返回 connected=false。
 */
export function useSSE(options: UseSSEOptions = {}): UseSSEResult {
  const {
    onEvent,
    autoReconnect = true,
    reconnectDelay = 3000,
  } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const onEventRef = useRef(onEvent);
  const reconnectTimerRef = useRef<number | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // 保持 onEvent 引用最新
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    // 清理旧连接
    if (esRef.current) {
      esRef.current.close();
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    let es: EventSource;
    try {
      es = new EventSource('/api/events');
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
        setLastEvent(event);
        onEventRef.current?.(event.type, event.data);
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
    };
  }, [connect]);

  return { connected, lastEvent };
}