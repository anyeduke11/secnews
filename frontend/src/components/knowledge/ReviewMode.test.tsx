/**
 * ReviewMode.test.tsx — Phase 17 间隔复习模式测试
 *
 * 覆盖:
 * - 空状态 (无到期复习)
 * - 卡片渲染
 * - 评分按钮点击
 * - 完成屏幕
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReviewMode } from './ReviewMode';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

function mockResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

function createMockReview(entityId: string, index: number) {
  return {
    id: index + 1,
    entity_type: 'concept',
    entity_id: entityId,
    easiness: 2.5,
    interval: 1,
    repetitions: 0,
    due_at: new Date().toISOString(),
    last_grade: null,
    last_reviewed_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function createMockDetail(entityId: string) {
  return {
    id: entityId,
    title: `Knowledge Item ${entityId}`,
    source: 'test',
    source_url: `https://example.com/${entityId}`,
    domain: 'security',
    tags: ['security', 'ai'],
    concepts: ['concept-a'],
    mastered: 0,
    content: 'This is the detailed content of the knowledge item for review.',
  };
}

describe('ReviewMode', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('shows empty state when no due reviews', async () => {
    mockFetch.mockImplementation(() =>
      mockResponse({ version: '1.0', count: 0, items: [] })
    );

    render(<ReviewMode />);

    await waitFor(() => {
      expect(screen.getByText('暂无到期复习')).toBeInTheDocument();
    });
  });

  it('renders review card with knowledge item', async () => {
    const review = createMockReview('k-review-1', 0);
    const detail = createMockDetail('k-review-1');

    // First call: due reviews, Second call: knowledge detail
    mockFetch
      .mockImplementationOnce(() =>
        mockResponse({ version: '1.0', count: 1, items: [review] })
      )
      .mockImplementationOnce(() => mockResponse(detail));

    render(<ReviewMode />);

    // Wait for the card title to appear (appears on front + back of card)
    await waitFor(() => {
      const elements = screen.getAllByText('Knowledge Item k-review-1');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    // The card should show tags (security appears as both tag and domain)
    expect(screen.getAllByText('security').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('ai')).toBeInTheDocument();

    // Progress indicator
    expect(screen.getByText('第 1 / 1 张')).toBeInTheDocument();
  });

  it('flips card and shows grade buttons', async () => {
    const review = createMockReview('k-review-2', 0);
    const detail = createMockDetail('k-review-2');

    mockFetch
      .mockImplementationOnce(() =>
        mockResponse({ version: '1.0', count: 1, items: [review] })
      )
      .mockImplementationOnce(() => mockResponse(detail));

    render(<ReviewMode />);

    // Wait for card to render
    await waitFor(() => {
      const elements = screen.getAllByText('Knowledge Item k-review-2');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    // Click to flip the card
    const flipButton = screen.getByRole('button', { name: /翻转卡片/ });
    fireEvent.click(flipButton);

    // After flipping, grade buttons should appear
    await waitFor(() => {
      expect(screen.getByLabelText('评分 0: 完全忘记')).toBeInTheDocument();
      expect(screen.getByLabelText('评分 5: 完全牢记')).toBeInTheDocument();
    });
  });

  it('submits grade and shows completion screen', async () => {
    const review = createMockReview('k-review-3', 0);
    const detail = createMockDetail('k-review-3');

    mockFetch
      .mockImplementationOnce(() =>
        mockResponse({ version: '1.0', count: 1, items: [review] })
      )
      .mockImplementationOnce(() => mockResponse(detail))
      .mockImplementationOnce(() =>
        mockResponse({
          version: '1.0',
          status: 'ok',
          item: { ...review, last_grade: 4, interval: 6, repetitions: 1 },
        })
      );

    render(<ReviewMode />);

    // Wait for card, flip it
    await waitFor(() => {
      const elements = screen.getAllByText('Knowledge Item k-review-3');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(screen.getByRole('button', { name: /翻转卡片/ }));

    // Click grade 4
    await waitFor(() => {
      expect(screen.getByLabelText('评分 4: 基本掌握')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('评分 4: 基本掌握'));

    // Should show completion screen
    await waitFor(() => {
      expect(screen.getByText('复习完成！')).toBeInTheDocument();
    });

    // Stats should be displayed
    expect(screen.getByText('本次共复习 1 张卡片')).toBeInTheDocument();
    expect(screen.getByText('通过')).toBeInTheDocument();
  });
});