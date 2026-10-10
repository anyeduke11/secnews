// frontend/src/hooks/useReactions.test.ts
// DEV-0311 — useReactions 测试: 回读 / 互斥切换 / 取消 / 失败回滚 / fail-safe 隐藏
//
// 测试意图 (Rule 9): reaction 是 "状态型信号" (区别于可叠加的 view/dwell),
// 契约核心 = 最态为准 — 同键取消 / 异键切换 / 失败回滚 / 端点不可用时不渲染死键。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useReactions, resetReactionsStore } from './useReactions';
import type { HotspotItem } from '../types';

const mockFetch = vi.fn();

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERROR',
    json: vi.fn().mockResolvedValue(data),
    blob: vi.fn(),
    text: vi.fn().mockResolvedValue(JSON.stringify(data)),
  } as unknown as Response;
}

function makeItem(id: string): HotspotItem {
  return {
    id,
    title: `标题-${id}`,
    source: 'test-source',
    url: `https://example.com/${id}`,
    category: 'ai',
    published_at: new Date().toISOString(),
  };
}

/** 默认 API 行为: GET 回读指定状态表; POST/DELETE 成功。未配置的请求 reject (兜底暴雷) */
function mockReactionsApi(items: Record<string, string> = {}) {
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method || 'GET';
    const u = String(url);
    if (method === 'GET' && u.startsWith('/api/interest/reactions')) {
      return Promise.resolve(jsonResponse({ items, count: Object.keys(items).length }));
    }
    if (method === 'POST' && u === '/api/interest/signals') {
      return Promise.resolve(jsonResponse({ status: 'ok' }));
    }
    if (method === 'DELETE' && u.startsWith('/api/interest/reactions/')) {
      return Promise.resolve(jsonResponse({ status: 'ok', deleted: 1 }));
    }
    return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
  });
}

beforeEach(() => {
  resetReactionsStore();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockReactionsApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useReactions', () => {
  it('挂载时回读状态表: 已有态度立即可见, available=true, 多实例共享同一份状态', async () => {
    mockReactionsApi({ a: 'like', b: 'dislike' });

    const first = renderHook(() => useReactions());
    await waitFor(() => {
      expect(first.result.current.reactionOf('a')).toBe('like');
      expect(first.result.current.reactionOf('b')).toBe('dislike');
    });
    expect(first.result.current.available).toBe(true);
    expect(first.result.current.loading).toBe(false);

    // 第二个实例: 读到同一 store 快照 (多实例一致)
    const second = renderHook(() => useReactions());
    await waitFor(() => expect(second.result.current.reactionOf('b')).toBe('dislike'));
    expect(second.result.current.reactionOf('a')).toBe('like');
    expect(second.result.current.available).toBe(true);

    first.unmount();
    second.unmount();
  });

  it('首次点赞 (无态度 → like): 乐观更新先于请求返回, 成功后保持', async () => {
    let resolvePost!: (v: unknown) => void;
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      const u = String(url);
      if (method === 'GET' && u.startsWith('/api/interest/reactions')) {
        return Promise.resolve(jsonResponse({ items: {}, count: 0 }));
      }
      if (method === 'POST' && u === '/api/interest/signals') {
        return new Promise(res => { resolvePost = res; }); // 挂起, 验证乐观态
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
    });

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.available).toBe(true));
    expect(result.current.reactionOf('x')).toBeUndefined();

    let flip!: Promise<boolean>;
    act(() => { flip = result.current.react(makeItem('x'), 'like'); });
    // 请求未返回, 本地已高亮 (乐观更新)
    expect(result.current.reactionOf('x')).toBe('like');

    await act(async () => {
      resolvePost(jsonResponse({ status: 'ok' }));
      await flip;
    });
    expect(result.current.reactionOf('x')).toBe('like');
    expect(result.current.error).toBeNull();
  });

  it('互斥切换 (like → dislike): 本地立即替换, 走 POST 由后端互斥销毁旧行', async () => {
    mockReactionsApi({ x: 'like' });

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.reactionOf('x')).toBe('like'));

    await act(async () => {
      await result.current.react(makeItem('x'), 'dislike');
    });

    expect(result.current.reactionOf('x')).toBe('dislike');
    const post = mockFetch.mock.calls.find(
      c => c[0] === '/api/interest/signals' && String(c[1]?.body ?? '').includes('"signal_type":"dislike"'),
    );
    expect(post).toBeTruthy();
    expect(JSON.parse(String(post![1]!.body))).toEqual({ item_id: 'x', signal_type: 'dislike' });
  });

  it('同键取消 (like → 再点 like): 本地立即还原无态度, 走 DELETE 删信号行', async () => {
    mockReactionsApi({ x: 'like' });

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.reactionOf('x')).toBe('like'));

    await act(async () => {
      await result.current.react(makeItem('x'), 'like');
    });

    expect(result.current.reactionOf('x')).toBeUndefined();
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/interest/reactions/x',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('失败自动回滚: 切换与取消均恢复原态度, error 带后端 message', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      const u = String(url);
      if (method === 'GET' && u.startsWith('/api/interest/reactions')) {
        return Promise.resolve(jsonResponse({ items: { x: 'like' }, count: 1 }));
      }
      if (method === 'POST' && u === '/api/interest/signals') {
        // 后端 500 + detail.message → apiFetch 抛友好 message
        return Promise.resolve(jsonResponse({ detail: { message: '服务端炸了' } }, 500));
      }
      if (method === 'DELETE' && u.startsWith('/api/interest/reactions/')) {
        return Promise.reject(new Error('网络错误'));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
    });

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.reactionOf('x')).toBe('like'));

    // 切换 like → dislike 失败: 回滚为 like
    await act(async () => { await result.current.react(makeItem('x'), 'dislike'); });
    expect(result.current.reactionOf('x')).toBe('like');
    expect(result.current.error).toBe('服务端炸了');

    // 取消 like 失败: 同样回滚为 like
    await act(async () => { await result.current.react(makeItem('x'), 'like'); });
    expect(result.current.reactionOf('x')).toBe('like');
    expect(result.current.error).toBe('网络错误');
  });

  it('回读失败 → available=false (fail-safe: 调用方隐藏按钮, 不渲染死键)', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: { message: 'Feature disabled' } }, 404)),
    );

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.available).toBe(false);
    expect(result.current.error).toBe('Feature disabled');
  });

  it('服务器丢弃 (accepted_no_domain) 如实回滚: 撤销高亮, 返回 true, 不污染 error (DEV-0314)', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      const u = String(url);
      if (method === 'GET' && u.startsWith('/api/interest/reactions')) {
        return Promise.resolve(jsonResponse({ items: { x: 'like' }, count: 1 }));
      }
      if (method === 'POST' && u === '/api/interest/signals') {
        return Promise.resolve(jsonResponse({ status: 'accepted_no_domain', domain: null }));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${u}`));
    });

    const { result } = renderHook(() => useReactions());
    await waitFor(() => expect(result.current.reactionOf('x')).toBe('like'));

    let discarded: boolean | undefined;
    await act(async () => { discarded = await result.current.react(makeItem('x'), 'dislike'); });

    expect(discarded).toBe(true);
    // 回滚到操作前态度 (like) — 不保留虚假 dislike 高亮
    expect(result.current.reactionOf('x')).toBe('like');
    // 语义性丢弃不是错误
    expect(result.current.error).toBeNull();
  });
});