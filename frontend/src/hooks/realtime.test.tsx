/**
 * Batch 5 任务 C: realtime.ts 统一 SSE 失效注册器单测
 *
 * 测试意图 (Rule 9):
 * - useRealtimeInvalidation: entries 类型路由 / throttle / debounce / unmount 清理 /
 *   lastId 透传 (onLastId 回调 + 重连 URL ?last_id= 续传)
 * - registerInvalidate: 模块级注册 → 主 hub 分发 / disposer 注销 / 无 hub 时休眠 /
 *   多 hub 不重复分发
 * - 事件常量与 useSSE 底座复用 (不新建连接语义)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useRealtimeInvalidation,
  registerInvalidate,
  SSE_EVENTS,
  V1_AGGREGATE_EVENT_TYPES,
} from './realtime';

// Mock EventSource (jsdom 不内置; 同 useSSE.test.ts / c11 测试写法)
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent & { lastEventId?: string }) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private _closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this._closed = true;
  }

  isClosed() {
    return this._closed;
  }

  simulateMessage(data: unknown, lastEventId?: string) {
    if (this.onmessage && !this._closed) {
      this.onmessage({ data: JSON.stringify(data), lastEventId } as unknown as MessageEvent);
    }
  }

  simulateError() {
    if (this.onerror && !this._closed) this.onerror(new Event('error'));
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  vi.clearAllMocks();
  MockEventSource.instances = [];
  (globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;
});

afterEach(() => {
  delete (globalThis as { EventSource?: unknown }).EventSource;
});

function getES(index = 0): MockEventSource {
  const es = MockEventSource.instances[index];
  if (!es) throw new Error(`MockEventSource[${index}] 不存在`);
  return es;
}

describe('useRealtimeInvalidation — entries 路由', () => {
  it('types 匹配的 entry 才收到事件, 不匹配的被过滤', () => {
    const onCollect = vi.fn();
    const onV1 = vi.fn();
    renderHook(() =>
      useRealtimeInvalidation([
        { types: [SSE_EVENTS.COLLECT_DONE], handler: onCollect },
        { types: V1_AGGREGATE_EVENT_TYPES, handler: onV1 },
      ]),
    );
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'collect_done', data: { total: 5 } });
      es.simulateMessage({ type: 'view', data: {} });
      es.simulateMessage({ type: 'v1_judgment', data: { case_id: 'C1', revision: 2 } });
    });
    expect(onCollect).toHaveBeenCalledTimes(1);
    expect(onCollect).toHaveBeenCalledWith('collect_done', { total: 5 });
    expect(onV1).toHaveBeenCalledTimes(1);
    expect(onV1).toHaveBeenCalledWith('v1_judgment', { case_id: 'C1', revision: 2 });
  });

  it('省略 types 的 entry 匹配所有事件', () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeInvalidation([{ handler }]));
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'alert', data: { a: 1 } });
      es.simulateMessage({ type: 'collect_done', data: { b: 2 } });
    });
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('重渲染重建 entries 字面量不重置 throttle 计时窗口', async () => {
    // 真实场景: entries 是内联字面量, 每轮渲染新数组 — 计时状态必须跨渲染存活
    // 窗口取 800ms (sleep 900): 全量并发下调度抖动可 >80ms, 窄窗会被负载击穿致 msg2 未被节流
    const handler = vi.fn();
    const { rerender } = renderHook(
      ({ h }) => useRealtimeInvalidation([{ types: ['e'], handler: h, throttleMs: 800 }]),
      { initialProps: { h: handler } },
    );
    const es = getES();
    act(() => { es.simulateMessage({ type: 'e', data: 1 }); });
    rerender({ h: handler }); // 重渲染 → 新 entries 数组 / 新 wrapper 链
    act(() => { es.simulateMessage({ type: 'e', data: 2 }); });
    expect(handler).toHaveBeenCalledTimes(1); // 窗口内第二条被节流掉
    await sleep(900);
    act(() => { es.simulateMessage({ type: 'e', data: 3 }); });
    expect(handler).toHaveBeenCalledTimes(2);
  });
});

describe('useRealtimeInvalidation — throttle / debounce', () => {
  it('throttleMs: 窗口内多次事件只触发首条', async () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeInvalidation([{ types: ['e'], handler, throttleMs: 60 }]));
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'e', data: 'first' });
      es.simulateMessage({ type: 'e', data: 'second' });
      es.simulateMessage({ type: 'e', data: 'third' });
    });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith('e', 'first');
    await sleep(80);
    act(() => { es.simulateMessage({ type: 'e', data: 'next-window' }); });
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('debounceMs: 窗口内多次事件合并为最后一次', async () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeInvalidation([{ types: ['e'], handler, debounceMs: 60 }]));
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'e', data: 'a' });
    });
    await sleep(30);
    act(() => {
      es.simulateMessage({ type: 'e', data: 'b' });
      es.simulateMessage({ type: 'e', data: 'c' });
    });
    expect(handler).not.toHaveBeenCalled(); // 窗口内不断重置
    await sleep(90);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith('e', 'c');
  });

  it('无 timing 选项时 handler 同步立即执行', () => {
    const handler = vi.fn();
    renderHook(() => useRealtimeInvalidation([{ types: ['e'], handler }]));
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'e', data: 'x' });
      es.simulateMessage({ type: 'e', data: 'y' });
    });
    expect(handler).toHaveBeenCalledTimes(2);
  });
});

describe('useRealtimeInvalidation — unmount 清理', () => {
  it('unmount 关闭 EventSource', () => {
    const { unmount } = renderHook(() => useRealtimeInvalidation([]));
    const es = getES();
    unmount();
    expect(es.isClosed()).toBe(true);
  });

  it('unmount 取消 pending debounce 定时器 (handler 不再被调)', async () => {
    const handler = vi.fn();
    const { unmount } = renderHook(() =>
      useRealtimeInvalidation([{ types: ['e'], handler, debounceMs: 50 }]),
    );
    const es = getES();
    act(() => { es.simulateMessage({ type: 'e', data: 'late' }); });
    unmount();
    await sleep(100);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe('useRealtimeInvalidation — lastId 透传 (C11 R18 续传语义)', () => {
  it('onLastId 对每条事件回调 id', () => {
    const onLastId = vi.fn();
    renderHook(() => useRealtimeInvalidation([{ types: ['e'], handler: vi.fn() }], { onLastId }));
    const es = getES();
    act(() => {
      es.simulateMessage({ id: 11, type: 'noise', data: {} });
      es.simulateMessage({ id: 12, type: 'e', data: {} });
    });
    expect(onLastId).toHaveBeenCalledTimes(2);
    expect(onLastId).toHaveBeenLastCalledWith(12);
  });

  it('断线重连 URL 携带 ?last_id= 续传', async () => {
    renderHook(() => useRealtimeInvalidation([], { reconnectDelay: 50 }));
    expect(getES().url).toBe('/api/events');
    const es = getES();
    act(() => {
      es.simulateMessage({ id: 42, type: 'e', data: {} });
      es.simulateError();
    });
    await sleep(200);
    const reconnect = MockEventSource.instances[MockEventSource.instances.length - 1]!;
    expect(reconnect.url).toBe('/api/events?last_id=42');
  });
});

describe('registerInvalidate — 模块级注册', () => {
  it('主 hub 挂载时分发 registry 事件; disposer 注销后不再分发', () => {
    const handler = vi.fn();
    const dispose = registerInvalidate(['collect_done'], handler);
    renderHook(() => useRealtimeInvalidation([])); // hub
    const es = getES();
    act(() => { es.simulateMessage({ type: 'collect_done', data: { n: 1 } }); });
    act(() => { es.simulateMessage({ type: 'v1_judgment', data: {} }); }); // 类型不匹配
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith('collect_done', { n: 1 });

    dispose();
    act(() => { es.simulateMessage({ type: 'collect_done', data: { n: 2 } }); });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('无 hub 挂载时注册处于休眠 (不建连接, handler 不触发)', () => {
    const handler = vi.fn();
    const dispose = registerInvalidate(['e'], handler);
    // 没有任何 useRealtimeInvalidation / useSSE 挂载
    expect(MockEventSource.instances).toHaveLength(0);
    dispose();
    expect(handler).not.toHaveBeenCalled();
  });

  it('registry handler 支持 throttle 选项', async () => {
    const handler = vi.fn();
    const dispose = registerInvalidate(['e'], handler, { throttleMs: 60 });
    renderHook(() => useRealtimeInvalidation([]));
    const es = getES();
    act(() => {
      es.simulateMessage({ type: 'e', data: 1 });
      es.simulateMessage({ type: 'e', data: 2 });
    });
    expect(handler).toHaveBeenCalledTimes(1);
    await sleep(80);
    act(() => { es.simulateMessage({ type: 'e', data: 3 }); });
    expect(handler).toHaveBeenCalledTimes(2);
    dispose();
  });

  it('多 hub 并存时 registry 事件只由主 hub 分发一次', () => {
    const handler = vi.fn();
    const dispose = registerInvalidate(['e'], handler);
    renderHook(() => useRealtimeInvalidation([])); // 主 hub
    renderHook(() => useRealtimeInvalidation([])); // 次级 hub
    expect(MockEventSource.instances).toHaveLength(2);
    // 两条连接各收到同一事件 (后端广播语义) → registry handler 仍只触发 1 次
    act(() => {
      MockEventSource.instances[0]!.simulateMessage({ type: 'e', data: 'x' });
      MockEventSource.instances[1]!.simulateMessage({ type: 'e', data: 'x' });
    });
    expect(handler).toHaveBeenCalledTimes(1);
    dispose();
  });
});

describe('事件类型常量', () => {
  it('V1_AGGREGATE_EVENT_TYPES 覆盖 5 个 v1_* aggregate 事件', () => {
    expect(V1_AGGREGATE_EVENT_TYPES).toEqual([
      'v1_judgment', 'v1_action', 'v1_artifact', 'v1_knowledge', 'v1_signal',
    ]);
    expect(SSE_EVENTS.COLLECT_DONE).toBe('collect_done');
    expect(SSE_EVENTS.JOB_DONE).toBe('job_done');
    expect(SSE_EVENTS.EXTRACT_DONE).toBe('extract_done');
    expect(SSE_EVENTS.ALERT).toBe('alert');
  });
});
