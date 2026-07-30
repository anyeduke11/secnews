/**
 * KnowledgeFavoritesView.test.tsx — 5 源数据聚合列表视图测试
 *
 * Phase 8: 资讯收藏聚合视图
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import KnowledgeFavoritesView from './KnowledgeFavoritesView';

// Mock fetch globally (same pattern as useHooks.test.ts)
const mockFetch = vi.fn();
global.fetch = mockFetch;

function mockResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

/** Extract URL from fetch mock calls matching the imported API */
function getLastApiUrl(): string | null {
  const calls = mockFetch.mock.calls.filter(
    (args: unknown[]) => typeof args[0] === 'string' && (args[0] as string).includes('/api/knowledge/imported')
  );
  if (calls.length === 0) return null;
  return calls[calls.length - 1][0] as string;
}

describe('KnowledgeFavoritesView', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    // Default: return empty data
    mockFetch.mockImplementation(() =>
      mockResponse({ items: [], total: 0, page: 1, page_size: 20 })
    );
  });

  it('renders title and filter controls', async () => {
    render(<KnowledgeFavoritesView />);

    // 标题
    expect(screen.getByText('资讯收藏')).toBeInTheDocument();

    // 筛选控件：类型下拉、搜索输入框、日期输入
    expect(screen.getByText('类型：')).toBeInTheDocument();
    expect(screen.getByText('搜索：')).toBeInTheDocument();
    expect(screen.getByText('起止：')).toBeInTheDocument();

    // 下拉选项
    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();
    expect(screen.getByText('全部')).toBeInTheDocument();
    expect(screen.getByText('收藏')).toBeInTheDocument();
    expect(screen.getByText('Cubox')).toBeInTheDocument();
  });

  it('calls API with type filter when select changes', async () => {
    render(<KnowledgeFavoritesView />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'cubox' } });

    await waitFor(() => {
      const url = getLastApiUrl();
      expect(url).not.toBeNull();
      expect(url).toContain('type=cubox');
    });
  });

  it('debounces keyword input before calling API', async () => {
    render(<KnowledgeFavoritesView />);

    const input = screen.getByPlaceholderText('搜索标题...');
    mockFetch.mockClear();

    fireEvent.change(input, { target: { value: 'test' } });

    // 立即检查：debounce 未触发，不应有包含 keyword=test 的 API 调用
    expect(getLastApiUrl()).toBeNull();

    // 等待 debounce (300ms) 完成
    await waitFor(
      () => {
        const url = getLastApiUrl();
        expect(url).not.toBeNull();
        expect(url).toContain('keyword=test');
      },
      { timeout: 500 }
    );
  });

  it('calls API with page=2 when next page is clicked', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({
        items: [
          { id: '1', title: 'Item 1', url: 'https://example.com/1', source_type: 'cubox', source_name: 'Cubox', ingested_at: '2026-07-28T00:00:00Z', origin: 'Cubox 同步' },
          { id: '2', title: 'Item 2', url: 'https://example.com/2', source_type: 'secnews', source_name: '实时', ingested_at: '2026-07-27T00:00:00Z', origin: 'SecNews 实时' },
        ],
        total: 30,
        page: 1,
        page_size: 20,
      })
    );

    render(<KnowledgeFavoritesView />);

    // 等待数据加载完成，下一页按钮出现
    await waitFor(() => {
      expect(screen.getByText('下一页')).toBeInTheDocument();
    });

    mockFetch.mockClear();

    // 点击下一页
    const nextButton = screen.getByText('下一页');
    fireEvent.click(nextButton);

    await waitFor(() => {
      const url = getLastApiUrl();
      expect(url).not.toBeNull();
      expect(url).toContain('page=2');
    });
  });

  it('shows empty state when no data', async () => {
    render(<KnowledgeFavoritesView />);

    await waitFor(() => {
      expect(screen.getByText('暂无数据')).toBeInTheDocument();
    });
  });
});