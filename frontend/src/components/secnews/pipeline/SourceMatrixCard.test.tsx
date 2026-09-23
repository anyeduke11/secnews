// SourceMatrixCard — B2 (DEV-0192) 源矩阵测试: 排序/截断/空态
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SourceMatrixCard } from './SourceMatrixCard';

function sourcesFixture(n: number) {
  const statuses = ['active', 'stale', 'dead'] as const;
  return Array.from({ length: n }, (_, i) => ({
    category: 'security',
    source_name: `源-${String(i).padStart(3, '0')}`,
    status: statuses[i % 3],
    total_items: n - i,
    last_seen_at: '2026-09-16T08:00:00+00:00',
  }));
}

describe('SourceMatrixCard — 印厂源健康矩阵 (B2)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/sources/health')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ sources: sourcesFixture(6) }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('表格渲染: 状态着色列 + 排序 dead 置顶', async () => {
    render(<SourceMatrixCard />);
    await waitFor(() => expect(screen.getAllByText('离线').length).toBe(2));
    const firstRow = document.querySelector('.ed-table tbody tr')!;
    expect(firstRow.textContent).toContain('离线');
    expect(screen.getByText(/6 源 · 故障置顶/)).toBeInTheDocument();
  });

  it('超 100 源截断 + 计数提示', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/sources/health')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ sources: sourcesFixture(120) }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<SourceMatrixCard />);
    await waitFor(() => expect(screen.getByText(/仅显示前 100 源 · 共 120 源/)).toBeInTheDocument());
    expect(document.querySelectorAll('.ed-table tbody tr').length).toBe(100);
  });

  it('空源 / 接口失败 → 显式空态', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/sources/health')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ sources: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<SourceMatrixCard />);
    await waitFor(() => expect(screen.getByText('暂无注册源')).toBeInTheDocument());
  });

  it('bid (招投标) 类目与 *(搜狗) 镜像源不进矩阵', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/sources/health')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            sources: [
              ...sourcesFixture(2),
              { category: 'bid', source_name: '采联网', status: 'active', total_items: 9, last_seen_at: '2026-09-16T08:00:00+00:00' },
              { category: 'security', source_name: '安全内参(搜狗)', status: 'dead', total_items: 1377, last_seen_at: '2026-08-03T09:53:00+00:00' },
            ],
          }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<SourceMatrixCard />);
    await waitFor(() => expect(screen.getByText(/2 源 · 故障置顶/)).toBeInTheDocument());
    expect(screen.queryByText('采联网')).not.toBeInTheDocument();
    expect(screen.queryByText('安全内参(搜狗)')).not.toBeInTheDocument();
  });
});
