import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import {
  __resetQueryCache,
  bindInvalidateOn,
  invalidate,
  useQuery,
  type QueryResult,
} from './useQuery';
import { registerInvalidate } from './realtime';

vi.mock('./realtime', () => ({
  registerInvalidate: vi.fn(() => () => {}),
  SSE_EVENTS: { COLLECT_DONE: 'collect_done' },
}));

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

afterEach(() => {
  __resetQueryCache();
  vi.clearAllMocks();
});

describe('useQuery', () => {
  it('首次挂载经历 loading, 取数成功后转为 ready 并携带数据', async () => {
    const fetcher = vi.fn(async () => ({ total: 3 }));
    const { result } = renderHook(() => useQuery('feed:test:ready', fetcher));

    expect(result.current.state).toBe('loading');
    expect(result.current.data).toBeUndefined();

    await waitFor(() => expect(result.current.state).toBe('ready'));
    expect(result.current.data).toEqual({ total: 3 });
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('空数组按 empty 处理 (契约: 空数据不显示为 ready)', async () => {
    const { result } = renderHook(() => useQuery('feed:test:empty', async () => [] as string[]));
    await waitFor(() => expect(result.current.state).toBe('empty'));
    expect(result.current.data).toEqual([]);
  });

  it('自定义 isEmpty 可覆盖默认空判定', async () => {
    const { result } = renderHook(() =>
      useQuery('feed:test:custom-empty', async () => ({ items: [] as string[] }), {
        isEmpty: (d) => d.items.length === 0,
      }),
    );
    await waitFor(() => expect(result.current.state).toBe('empty'));
  });

  it('取数失败转 error 并保留可读错误信息', async () => {
    const { result } = renderHook(() =>
      useQuery('feed:test:error', async () => {
        throw new Error('后端不可用');
      }),
    );
    await waitFor(() => expect(result.current.state).toBe('error'));
    expect(result.current.error).toBe('后端不可用');
  });

  it('同一 key 的并发消费者共享一次请求 (去重)', async () => {
    const d = deferred<string[]>();
    const fetcher = vi.fn(() => d.promise);
    const { result } = renderHook(() => ({
      a: useQuery('feed:test:dedupe', fetcher) as QueryResult<string[]>,
      b: useQuery('feed:test:dedupe', fetcher) as QueryResult<string[]>,
    }));

    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      d.resolve(['x']);
    });
    await waitFor(() => expect(result.current.a.state).toBe('ready'));
    expect(result.current.b.data).toEqual(['x']);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('缓存命中时重新挂载不重复请求', async () => {
    const fetcher = vi.fn(async () => ({ ok: true }));
    const first = renderHook(() => useQuery('feed:test:cache', fetcher));
    await waitFor(() => expect(first.result.current.state).toBe('ready'));
    first.unmount();

    const second = renderHook(() => useQuery('feed:test:cache', fetcher));
    expect(second.result.current.state).toBe('ready');
    expect(second.result.current.data).toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('invalidate 支持前缀匹配并重拉有订阅者的条目', async () => {
    let round = 1;
    const fetcher = vi.fn(async () => ({ round }));
    const { result } = renderHook(() => useQuery('feed:list:1', fetcher));
    await waitFor(() => expect(result.current.state).toBe('ready'));
    expect(result.current.data).toEqual({ round: 1 });

    round = 2;
    act(() => invalidate('feed:'));
    await waitFor(() => expect(result.current.data).toEqual({ round: 2 }));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('key=null 不发请求, 状态为 empty', () => {
    const fetcher = vi.fn(async () => 'never');
    const { result } = renderHook(() => useQuery(null, fetcher));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.state).toBe('empty');
  });

  it('refetch 强制重拉并更新数据', async () => {
    let round = 1;
    const fetcher = vi.fn(async () => `v${round}`);
    const { result } = renderHook(() => useQuery('feed:test:refetch', fetcher));
    await waitFor(() => expect(result.current.state).toBe('ready'));

    round = 2;
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.data).toBe('v2'));
  });

  it('bindInvalidateOn 复用 realtime 注册器并转发前缀失效', async () => {
    const dispose = vi.fn();
    vi.mocked(registerInvalidate).mockReturnValueOnce(dispose);

    const disposer = bindInvalidateOn(['collect_done'], 'feed:', { throttleMs: 3000 });
    expect(registerInvalidate).toHaveBeenCalledWith(['collect_done'], expect.any(Function), {
      throttleMs: 3000,
    });
    expect(disposer).toBe(dispose);

    // 注册器回调应触发对应前缀的失效
    const handler = vi.mocked(registerInvalidate).mock.calls[0][1] as () => void;
    const fetcher = vi.fn(async () => [1]);
    const { result } = renderHook(() => useQuery('feed:sse:1', fetcher));
    await waitFor(() => expect(result.current.state).toBe('ready'));
    act(() => handler());
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });
});