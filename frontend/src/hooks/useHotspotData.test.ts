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
