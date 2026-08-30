/**
 * AttentionHeatmap.test.tsx — Phase 17 注意力度热力图测试
 *
 * 覆盖:
 * - 空数据渲染
 * - 样本数据渲染
 * - tooltip 悬停
 * - 点击导航
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { AttentionHeatmap } from './AttentionHeatmap';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

function mockResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe('AttentionHeatmap', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockNavigate.mockReset();
    mockFetch.mockImplementation(() => mockResponse({ events: [] }));
  });

  it('renders title and date range', async () => {
    renderWithRouter(<AttentionHeatmap />);

    expect(screen.getByText('注意力度热力图')).toBeInTheDocument();

    // Date range should be displayed (format: YYYY-MM-DD ~ YYYY-MM-DD)
    await waitFor(() => {
      expect(screen.getByText(/^\d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2}$/)).toBeInTheDocument();
    });
  });

  it('shows empty state when no data', async () => {
    renderWithRouter(<AttentionHeatmap />);

    await waitFor(() => {
      expect(screen.getByText('暂无注意力数据')).toBeInTheDocument();
    });
  });

  it('renders grid with sample data', async () => {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

    mockFetch.mockImplementation(() =>
      mockResponse({
        events: [
          { date: dateStr, hour: 10, count: 5 },
          { date: dateStr, hour: 14, count: 3 },
        ],
      })
    );

    renderWithRouter(<AttentionHeatmap />);

    // Loading should resolve and grid should render
    await waitFor(() => {
      // The grid contains 30 rows of 24 cells each = 720 cells
      // With sample data, some cells should have color
      const cells = document.querySelectorAll('[data-cell]');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  it('shows tooltip on hover', async () => {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

    mockFetch.mockImplementation(() =>
      mockResponse({
        events: [
          { date: dateStr, hour: 10, count: 5 },
        ],
      })
    );

    renderWithRouter(<AttentionHeatmap />);

    // Wait for grid to render
    await waitFor(() => {
      // The grid cells are rendered, find one with a cursor pointer
      const cells = document.querySelectorAll('[data-cell]');
      expect(cells.length).toBeGreaterThan(0);
    });

    // Find all cells and hover over one
    const cells = document.querySelectorAll('[data-cell]');
    if (cells.length > 0) {
      fireEvent.mouseEnter(cells[0]);
      // Tooltip should appear with count info
      await waitFor(() => {
        const tooltip = document.querySelector('[style*="pointer-events: none"]');
        expect(tooltip).toBeInTheDocument();
      });
    }
  });

  it('does not navigate on cell click (briefing route removed, drill-down pending)', async () => {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

    mockFetch.mockImplementation(() =>
      mockResponse({
        events: [
          { date: dateStr, hour: 10, count: 5 },
        ],
      })
    );

    renderWithRouter(<AttentionHeatmap />);

    await waitFor(() => {
      const cells = document.querySelectorAll('[data-cell]');
      expect(cells.length).toBeGreaterThan(0);
    });

    const cells = document.querySelectorAll('[data-cell]');
    if (cells.length > 0) {
      fireEvent.click(cells[0]);
      // 原 /knowledge/briefing?date= 死链已移除; 下钻页未实现前点击不导航
      expect(mockNavigate).not.toHaveBeenCalled();
    }
  });
});