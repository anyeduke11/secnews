// frontend/src/hooks/useFavorites.test.ts
// P0 重构 — useFavorites 测试: 乐观更新 / 失败回滚 / 多实例状态一致
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useFavorites, resetFavoritesStore } from './useFavorites';
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

/** 默认: GET /api/favorites 返回空列表; 其余请求一律 reject (未配置) */
function mockDefaultList(items: Array<{ hotspot_id: string }> = [], total = 0) {
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method || 'GET';
    if (method === 'GET' && String(url).startsWith('/api/favorites')) {
      return Promise.resolve(jsonResponse({ total, items }));
    }
    return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
  });
}

beforeEach(() => {
  resetFavoritesStore();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
  mockDefaultList();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useFavorites', () => {
  it('挂载时拉取收藏列表, 多实例共享同一份状态 (多实例一致)', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (method === 'GET' && String(url).startsWith('/api/favorites')) {
        return Promise.resolve(jsonResponse({
          total: 2,
          items: [{ hotspot_id: 'a' }, { hotspot_id: 'b' }],
        }));
      }
      if (method === 'POST' && url === '/api/favorites') {
        return Promise.resolve(jsonResponse({ status: 'ok', created: true, item: { hotspot_id: 'c' } }));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
    });

    const first = renderHook(() => useFavorites());
    await waitFor(() => {
      expect(first.result.current.favorites.has('a')).toBe(true);
      expect(first.result.current.favorites.has('b')).toBe(true);
    });
    expect(first.result.current.count).toBe(2);
    expect(first.result.current.loading).toBe(false);

    // 第二个实例: 状态与第一个实例完全一致 (同一 store 快照)
    const second = renderHook(() => useFavorites());
    await waitFor(() => {
      expect(second.result.current.favorites.has('a')).toBe(true);
    });
    expect(second.result.current.favorites).toBe(first.result.current.favorites);
    expect(second.result.current.count).toBe(first.result.current.count);

    // 一个实例里翻转, 另一个实例立即看到 (乐观状态跨实例可见)
    let togglePromise!: Promise<void>;
    act(() => {
      togglePromise = first.result.current.toggleFavorite(makeItem('c'));
    });
    expect(second.result.current.favorites.has('c')).toBe(true);
    expect(second.result.current.count).toBe(3);

    // 等待请求完成, 避免 act 警告
    await act(async () => { await togglePromise; });
    expect(second.result.current.favorites.has('c')).toBe(true);

    first.unmount();
    second.unmount();
  });

  it('toggleFavorite 乐观更新: 请求未返回时本地已翻转, 成功后保持', async () => {
    mockDefaultList([{ hotspot_id: 'a' }], 1);

    let resolvePost!: (v: unknown) => void;
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (method === 'GET' && String(url).startsWith('/api/favorites')) {
        return Promise.resolve(jsonResponse({ total: 1, items: [{ hotspot_id: 'a' }] }));
      }
      if (method === 'POST' && url === '/api/favorites') {
        return new Promise(res => { resolvePost = res; });
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
    });

    const { result } = renderHook(() => useFavorites());
    await waitFor(() => expect(result.current.favorites.has('a')).toBe(true));
    expect(result.current.count).toBe(1);

    // 乐观更新: POST 未返回, 本地已添加
    let togglePromise!: Promise<void>;
    act(() => {
      togglePromise = result.current.toggleFavorite(makeItem('b'));
    });
    expect(result.current.favorites.has('b')).toBe(true);
    expect(result.current.count).toBe(2);

    // 请求成功后状态保持
    await act(async () => {
      resolvePost(jsonResponse({ status: 'ok', created: true, item: { hotspot_id: 'b' } }));
      await togglePromise;
    });
    expect(result.current.favorites.has('b')).toBe(true);
    expect(result.current.count).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it('toggleFavorite 失败自动回滚 (新增失败)', async () => {
    mockDefaultList([{ hotspot_id: 'a' }], 1);

    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (method === 'GET' && String(url).startsWith('/api/favorites')) {
        return Promise.resolve(jsonResponse({ total: 1, items: [{ hotspot_id: 'a' }] }));
      }
      if (method === 'POST' && url === '/api/favorites') {
        // 后端 500 + detail.message → apiFetch 抛友好 message
        return Promise.resolve(jsonResponse({ detail: { message: '服务端炸了' } }, 500));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
    });

    const { result } = renderHook(() => useFavorites());
    await waitFor(() => expect(result.current.favorites.has('a')).toBe(true));

    await act(async () => {
      await result.current.toggleFavorite(makeItem('b'));
    });

    // 回滚: b 被移除, 计数还原, error 带后端 message
    expect(result.current.favorites.has('b')).toBe(false);
    expect(result.current.favorites.has('a')).toBe(true);
    expect(result.current.count).toBe(1);
    expect(result.current.error).toBe('服务端炸了');
  });

  it('toggleFavorite 失败自动回滚 (取消收藏失败)', async () => {
    mockDefaultList([{ hotspot_id: 'a' }], 1);

    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (method === 'GET' && String(url).startsWith('/api/favorites')) {
        return Promise.resolve(jsonResponse({ total: 1, items: [{ hotspot_id: 'a' }] }));
      }
      if (method === 'DELETE' && url === '/api/favorites/a') {
        return Promise.reject(new Error('网络错误'));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
    });

    const { result } = renderHook(() => useFavorites());
    await waitFor(() => expect(result.current.favorites.has('a')).toBe(true));
    expect(result.current.count).toBe(1);

    // 乐观移除
    let togglePromise!: Promise<void>;
    act(() => {
      togglePromise = result.current.toggleFavorite(makeItem('a'));
    });
    expect(result.current.favorites.has('a')).toBe(false);
    expect(result.current.count).toBe(0);

    // 失败回滚
    await act(async () => {
      await togglePromise;
    });
    expect(result.current.favorites.has('a')).toBe(true);
    expect(result.current.count).toBe(1);
    expect(result.current.error).toBe('网络错误');
  });

  it('计数修正: POST created=false 不重复 +1; DELETE removed=0 不重复 -1', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (method === 'GET' && String(url).startsWith('/api/favorites')) {
        return Promise.resolve(jsonResponse({ total: 1, items: [{ hotspot_id: 'a' }] }));
      }
      if (method === 'POST' && url === '/api/favorites') {
        return Promise.resolve(jsonResponse({ status: 'ok', created: false, item: { hotspot_id: 'b' } }));
      }
      if (method === 'DELETE' && url === '/api/favorites/a') {
        return Promise.resolve(jsonResponse({ status: 'ok', hotspot_id: 'a', removed: 0 }));
      }
      return Promise.reject(new Error(`未预期的请求: ${method} ${url}`));
    });

    const { result } = renderHook(() => useFavorites());
    await waitFor(() => expect(result.current.favorites.has('a')).toBe(true));
    expect(result.current.count).toBe(1);

    // created=false: 本地已加 b, 但总数不 +1
    await act(async () => {
      await result.current.toggleFavorite(makeItem('b'));
    });
    expect(result.current.favorites.has('b')).toBe(true);
    expect(result.current.count).toBe(1);

    // removed=0: 本地已移除 a, 但总数不 -1
    await act(async () => {
      await result.current.toggleFavorite(makeItem('a'));
    });
    expect(result.current.favorites.has('a')).toBe(false);
    expect(result.current.count).toBe(1);
  });

  it('isFavorite 与 refresh 可用', async () => {
    mockDefaultList([{ hotspot_id: 'x' }], 1);
    const { result } = renderHook(() => useFavorites());
    await waitFor(() => expect(result.current.isFavorite('x')).toBe(true));
    expect(result.current.isFavorite('nope')).toBe(false);

    // refresh 重新拉取
    mockDefaultList([{ hotspot_id: 'x' }, { hotspot_id: 'y' }], 2);
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.isFavorite('y')).toBe(true);
    expect(result.current.count).toBe(2);
  });
});
