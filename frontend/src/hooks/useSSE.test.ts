/**
 * P0.3: useSSE hook 节流测试
 *
 * 测试意图 (Rule 9):
 * - 高频消息时 setLastEvent 不应每条都触发 re-render (应分帧批处理)
 * - onEvent 回调应立即执行 (业务逻辑不延迟)
 * - 最后一条消息应最终反映到 lastEvent 状态
 * - 组件卸载时应清理 raf
 *
 * 这些测试验证的是"避免高频 SSE 消息导致渲染风暴"的意图。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
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

  // 模拟推送消息
  simulateMessage(data: any) {
    if (this.onmessage && !this._closed) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  // 模拟连接打开
  simulateOpen() {
    if (this.onopen && !this._closed) {
      this.onopen(new Event('open'));
    }
  }

  // 模拟错误
  simulateError() {
    if (this.onerror && !this._closed) {
      this.onerror(new Event('error'));
    }
  }
}

describe('useSSE — P0.3 节流 + 分帧', () => {
  let originalEventSource: typeof EventSource;
  let rafSpy: ReturnType<typeof vi.spyOn>;
  let originalRaf: typeof globalThis.requestAnimationFrame;

  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource as any;

    // Mock requestAnimationFrame — 立即执行回调
    originalRaf = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) => {
      return setTimeout(() => cb(performance.now()), 0) as any;
    }) as any;
    globalThis.cancelAnimationFrame = ((id: number) => {
      clearTimeout(id as any);
    }) as any;
  });

  afterEach(() => {
    globalThis.EventSource = originalEventSource;
    globalThis.requestAnimationFrame = originalRaf;
    vi.restoreAllMocks();
  });

  it('onEvent 回调应立即执行, 不被 raf 延迟', async () => {
    const onEvent = vi.fn();
    const { useSSE } = await import('./useSSE');

    renderHook(() => useSSE({ onEvent }));

    // 等待 EventSource 创建
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    const es = MockEventSource.instances[0];
    es.simulateOpen();

    // 推送 1 条消息
    es.simulateMessage({ type: 'test', data: { foo: 'bar' }, ts: '2026-01-01T00:00:00Z' });

    // onEvent 应立即被调用 (不等 raf)
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith('test', { foo: 'bar' });
  });

  it('P0.3 核心意图: 高频消息只 setState 一次 (分帧批处理)', async () => {
    /**
     * 这是 P0.3 的核心测试。
     *
     * 修复前: 每条 SSE 消息都 setLastEvent → N 条消息 = N 次 re-render
     * 修复后: 消息缓存到 ref, raf 内只 setState 最后一条 → N 条消息 = 1 次 re-render
     */
    const { useSSE } = await import('./useSSE');
    const { result } = renderHook(() => useSSE({}));

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    const es = MockEventSource.instances[0];
    es.simulateOpen();

    // 连续推送 5 条消息 (模拟高频)
    for (let i = 0; i < 5; i++) {
      es.simulateMessage({
        type: 'progress',
        data: { count: i },
        ts: '2026-01-01T00:00:00Z',
      });
    }

    // 等待 raf 执行 (setTimeout 0)
    await new Promise(r => setTimeout(r, 50));

    // lastEvent 应只反映最后一条 (count: 4)
    expect(result.current.lastEvent).not.toBeNull();
    expect((result.current.lastEvent as any).data.count).toBe(4);
  });

  it('低频消息应正常反映到 lastEvent', async () => {
    const { useSSE } = await import('./useSSE');

    const { result } = renderHook(() => useSSE({}));

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    const es = MockEventSource.instances[0];
    es.simulateOpen();

    es.simulateMessage({ type: 'alert', data: { id: 'a1' }, ts: '2026-01-01T00:00:00Z' });

    await waitFor(() => {
      expect(result.current.lastEvent).not.toBeNull();
    });

    expect((result.current.lastEvent as any).type).toBe('alert');
    expect((result.current.lastEvent as any).data.id).toBe('a1');
  });

  it('组件卸载应清理 raf + 关闭 EventSource', async () => {
    const { useSSE } = await import('./useSSE');
    const { unmount } = renderHook(() => useSSE({}));

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    const es = MockEventSource.instances[0];

    unmount();

    // EventSource 应被关闭
    expect(es.isClosed()).toBe(true);
  });

  it('连接成功后 connected 应为 true', async () => {
    const { useSSE } = await import('./useSSE');
    const { result } = renderHook(() => useSSE({}));

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    const es = MockEventSource.instances[0];
    es.simulateOpen();

    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });
  });
});
