/**
 * OutboxMode.test.tsx — Phase 17 整理模式测试
 *
 * 覆盖:
 * - 渲染条目列表
 * - 空状态
 * - 筛选交互
 * - 批量选择
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OutboxMode } from './OutboxMode';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

function mockResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

function mockErrorResponse(status: number) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({}),
  } as Response);
}

describe('OutboxMode', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    // Default: return items with data
    mockFetch.mockImplementation(() =>
      mockResponse({
        items: [
          {
            id: 'k-1',
            title: 'Knowledge Item 1',
            source: 'cubox',
            source_url: 'https://example.com/1',
            domain: 'security',
            topic: null,
            type: 'article',
            difficulty: 'beginner',
            tags: ['security'],
            concepts: [],
            mastered: 0,
            compiled: false,
            ingested_at: '2026-07-28T00:00:00Z',
            updated_at: '2026-07-28T00:00:00Z',
            attention_score: 85,
            lifecycle: 'kl:raw',
          },
          {
            id: 'k-2',
            title: 'Knowledge Item 2',
            source: 'secnews',
            source_url: 'https://example.com/2',
            domain: 'ai',
            topic: null,
            type: 'article',
            difficulty: 'intermediate',
            tags: ['ai'],
            concepts: [],
            mastered: 0,
            compiled: false,
            ingested_at: '2026-07-27T00:00:00Z',
            updated_at: '2026-07-27T00:00:00Z',
            attention_score: 42,
            lifecycle: 'kl:refine',
          },
        ],
        total: 2,
      })
    );
  });

  it('renders title and item count', async () => {
    render(<OutboxMode />);

    // 页面标题是 h3; 嵌套的 OnboardingHint 也有同文案 h4, 用 heading level 消歧
    expect(screen.getByRole('heading', { level: 3, name: '整理模式' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('2 条待处理')).toBeInTheDocument();
    });
  });

  it('renders item cards with data', async () => {
    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Item 1')).toBeInTheDocument();
      expect(screen.getByText('Knowledge Item 2')).toBeInTheDocument();
    });
  });

  it('shows empty state when no items', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({ items: [], total: 0 })
    );

    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText('暂无待处理项目')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockFetch.mockImplementation(() => mockErrorResponse(500));

    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText(/请求失败/)).toBeInTheDocument();
    });
  });

  it('filters by lifecycle', async () => {
    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Item 1')).toBeInTheDocument();
    });

    const select = screen.getByLabelText('按生命周期筛选');
    fireEvent.change(select, { target: { value: 'kl:raw' } });

    // Should re-fetch with lifecycle filter
    await waitFor(() => {
      const calls = mockFetch.mock.calls.filter(
        (args: unknown[]) => typeof args[0] === 'string' && (args[0] as string).includes('/api/knowledge/items')
      );
      const lastCall = calls[calls.length - 1] as [string];
      expect(lastCall[0]).toContain('lifecycle=kl%3Araw');
    });
  });

  it('supports batch selection', async () => {
    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Item 1')).toBeInTheDocument();
    });

    // Select all
    const selectAllCheckbox = screen.getByLabelText('全选');
    fireEvent.click(selectAllCheckbox);

    // Batch action bar should appear (text appears in two places: header + sticky bar)
    await waitFor(() => {
      const elements = screen.getAllByText('已选 2 项');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    // Batch action buttons should be visible
    expect(screen.getByText('标记已读')).toBeInTheDocument();
    expect(screen.getByText('归档')).toBeInTheDocument();
    expect(screen.getByText('生成摘要')).toBeInTheDocument();
  });

  it('supports individual item selection', async () => {
    render(<OutboxMode />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge Item 1')).toBeInTheDocument();
    });

    // Select first item
    const checkbox1 = screen.getByLabelText('选择 Knowledge Item 1');
    fireEvent.click(checkbox1);

    await waitFor(() => {
      const elements = screen.getAllByText('已选 1 项');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });
  });
});