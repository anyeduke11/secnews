/**
 * P0.2: useHotspotData hook 测试
 *
 * 测试意图 (Rule 9):
 * - 翻页时如果 pageData 已有缓存, 不应重复发起网络请求
 * - fetchPage 完成后 (setPageData) 不应触发额外的 effect 重新评估
 * - 切换筛选条件 (category/timeRange/keyword) 时应清空缓存并回到第 1 页
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// Mock fetch — 每个 test 重新 mock
const mockFetch = vi.fn();

describe('useHotspotData — P0.2 useEffect 依赖修复', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockResponse(items: any[], opts: { total?: number; next_cursor?: string | null; category_counts?: any } = {}) {
    return {
      ok: true,
      json: async () => ({
        items,
        next_cursor: opts.next_cursor ?? null,
        total: opts.total ?? items.length,
        category_counts: opts.category_counts ?? {},
        fetched_at: '2026-01-01T00:00:00Z',
      }),
    };
  }

  it('首次挂载应请求第 1 页', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse([{ id: '1', title: 'test' }], { total: 100 })
    );

    const { useHotspotData } = await import('./useHotspotData');
    const { result } = renderHook(() =>
      useHotspotData('ai', 'd7', '')
    );

    await waitFor(() => {
      expect(result.current.items.length).toBe(1);
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toContain('/api/hotspots');
  });

  it('P0.2 核心意图: fetchPage 完成后不应触发额外 effect 重新评估', async () => {
    /**
     * 修复前: useEffect 依赖 [page, pageData, fetchPage]
     *   → setPageData 更新 pageData → useEffect 重新评估
     * 修复后: useEffect 依赖 [page] (用 ref 读 pageData)
     *   → setPageData 不触发 effect
     */
    mockFetch.mockResolvedValueOnce(
      mockResponse([{ id: '1', title: 'test' }], {
        total: 100,
        next_cursor: 'cursor_2',
        category_counts: { ai: 100 },
      })
    );

    const { useHotspotData } = await import('./useHotspotData');
    const { result } = renderHook(() =>
      useHotspotData('ai', 'd7', '')
    );

    await waitFor(() => {
      expect(result.current.items.length).toBe(1);
    });

    // 等待额外的 effect tick (如果有 bug, 这里会多一次 fetch)
    await new Promise(r => setTimeout(r, 200));

    // 核心断言: fetch 应只被调用 1 次 (修复前可能被多次调用)
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('翻到第 2 页缓存未命中应发起请求', async () => {
    // 第 1 页
    mockFetch.mockResolvedValueOnce(
      mockResponse([{ id: '1', title: 'p1' }], {
        total: 200,
        next_cursor: 'cursor_2',
      })
    );
    // 第 2 页
    mockFetch.mockResolvedValueOnce(
      mockResponse([{ id: '2', title: 'p2' }], {
        total: 200,
        next_cursor: null,
      })
    );

    const { useHotspotData } = await import('./useHotspotData');
    const { result } = renderHook(() =>
      useHotspotData('ai', 'd7', '')
    );

    await waitFor(() => {
      expect(result.current.items.length).toBe(1);
    });

    // 翻到第 2 页
    act(() => {
      result.current.setPage(2);
    });

    await waitFor(() => {
      expect(result.current.items[0]?.id).toBe('2');
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('切换 category 应清空缓存并回到第 1 页', async () => {
    // 使用 mockImplementation 而非 mockResolvedValueOnce, 应对所有 fetch 调用
    let callCount = 0;
    mockFetch.mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        return mockResponse([{ id: '1', title: 'ai_item' }], { total: 10 });
      }
      return mockResponse([{ id: '2', title: 'sec_item' }], { total: 5 });
    });

    const { useHotspotData } = await import('./useHotspotData');
    const { result, rerender } = renderHook(
      ({ category }) => useHotspotData(category, 'd7', ''),
      { initialProps: { category: 'ai' } }
    );

    await waitFor(() => {
      expect(result.current.items[0]?.id).toBe('1');
    });

    rerender({ category: 'security' });

    await waitFor(() => {
      expect(result.current.items[0]?.id).toBe('2');
    }, { timeout: 3000 });

    expect(result.current.page).toBe(1);
  });
});

/**
 * cadence 修正批 (2026-09-10): refetch / refresh 语义分离
 *
 * 意图: SSE collect_done 到达时首页只该"拿新数据", 绝不能再回触后端采集 —
 * 否则 "采集 → collect_done → POST /api/refresh → 再采集" 自激, 30 分钟节奏
 * 被打成连续抓取。refresh() 保留给用户显式点击「立即采集」。
 */
describe('useHotspotData — refetch(只读) vs refresh(触发采集)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const page = (title: string) => ({
    ok: true,
    json: async () => ({
      items: [{ id: title, title }],
      next_cursor: null,
      total: 1,
      category_counts: {},
      fetched_at: '2026-01-01T00:00:00Z',
    }),
  });

  const urls = () => mockFetch.mock.calls.map((c: any[]) => String(c[0]));
  const methods = () => mockFetch.mock.calls.map((c: any[]) => ((c[1]?.method ?? 'GET') as string).toUpperCase());

  it('refetch(): 清缓存重拉第 1 页, 全程不出现 POST /api/refresh', async () => {
    mockFetch.mockImplementation(async (input: any) => {
      const url = String(input);
      if (url.startsWith('/api/hotspots')) return page(urls().length === 1 ? 'first' : 'second');
      throw new Error(`unexpected fetch ${url}`);
    });

    const { useHotspotData } = await import('./useHotspotData');
    const { result } = renderHook(() => useHotspotData('all', '24h', ''));

    await waitFor(() => expect(result.current.items[0]?.id).toBe('first'));

    await act(async () => { await result.current.refetch(); });

    await waitFor(() => expect(result.current.items[0]?.id).toBe('second'));
    expect(urls().filter(u => u === '/api/refresh')).toHaveLength(0);
    expect(urls().filter(u => u.startsWith('/api/hotspots'))).toHaveLength(2);
    expect(methods().every(m => m === 'GET')).toBe(true);
  });

  it('refresh(): 先 POST /api/refresh 同步采集, 再重拉第 1 页', async () => {
    mockFetch.mockImplementation(async (input: any, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/refresh' && (init?.method ?? 'GET').toUpperCase() === 'POST') {
        return { ok: true, json: async () => ({ ok: true, total: 3 }) };
      }
      if (url.startsWith('/api/hotspots')) return page('after-collect');
      throw new Error(`unexpected fetch ${url}`);
    });

    const { useHotspotData } = await import('./useHotspotData');
    const { result } = renderHook(() => useHotspotData('all', '24h', ''));
    await waitFor(() => expect(result.current.items.length).toBe(1));

    await act(async () => { await result.current.refresh(); });

    const seq = urls();
    const refreshIdx = seq.indexOf('/api/refresh');
    expect(refreshIdx).toBeGreaterThan(0);
    // 采集之后紧跟一次只读重拉
    expect(seq[refreshIdx + 1]).toMatch(/^\/api\/hotspots/);
    expect(seq.filter(u => u === '/api/refresh')).toHaveLength(1);
  });
});
