// SourceMatrixCard — B2 (DEV-0192) 源矩阵测试: 排序/截断/空态
// 治理 T3 追加: 介质分组筛选 (全部/网页/微信/多媒体) + dead 行灰显
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

  it('dead 行灰显 (opacity 半显), 非 dead 行不灰显', async () => {
    render(<SourceMatrixCard />);
    await waitFor(() => expect(screen.getAllByText('离线').length).toBe(2));
    const rows = document.querySelectorAll('.ed-table tbody tr');
    const deadRows = Array.from(rows).filter(r => r.textContent!.includes('离线'));
    const liveRows = Array.from(rows).filter(r => !r.textContent!.includes('离线'));
    expect(deadRows.length).toBeGreaterThan(0);
    for (const r of deadRows) expect(r.className).toContain('opacity-50');
    for (const r of liveRows) expect(r.className).not.toContain('opacity-50');
  });

  it('介质筛选: 全部视图排除 wechat 行, 微信 tab 专属展示 (治理 T3)', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/sources/health')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            sources: [
              { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 500, last_seen_at: '2026-09-16T08:00:00+00:00', media_kind: 'web' },
              { category: 'security', source_name: '微步在线(搜狗)', status: 'dead', total_items: 1526, last_seen_at: '2026-08-03T09:53:00+00:00', media_kind: 'wechat' },
              { category: 'security', source_name: 'LiveOverflow (YouTube)', status: 'stale', total_items: 0, last_seen_at: null, media_kind: 'multimedia' },
            ],
          }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<SourceMatrixCard />);

    // 全部视图: wechat 行被排除 (原裁决升级为按介质), 计数只含 web + multimedia
    await waitFor(() => expect(screen.getByText(/2 源 · 故障置顶/)).toBeInTheDocument());
    expect(screen.queryByText('微步在线(搜狗)')).not.toBeInTheDocument();

    // 微信 tab: 只展示 wechat 行
    await user.click(screen.getByRole('button', { name: '微信' }));
    expect(screen.getByText(/1 源 · 故障置顶/)).toBeInTheDocument();
    expect(screen.getByText('微步在线(搜狗)')).toBeInTheDocument();
    expect(screen.queryByText('FreeBuf')).not.toBeInTheDocument();

    // 网页 tab: 只展示 web 行
    await user.click(screen.getByRole('button', { name: '网页' }));
    expect(screen.getByText('FreeBuf')).toBeInTheDocument();
    expect(screen.queryByText('微步在线(搜狗)')).not.toBeInTheDocument();

    // 多媒体 tab: 只展示 multimedia 行
    await user.click(screen.getByRole('button', { name: '多媒体' }));
    expect(screen.getByText('LiveOverflow (YouTube)')).toBeInTheDocument();
    expect(screen.getByText('multimedia')).toBeInTheDocument();
  });

  it('缺 media_kind 的旧数据回落 web 口径, 进网页 tab', async () => {
    const user = userEvent.setup();
    render(<SourceMatrixCard />);  // fixture 6 行均无 media_kind
    await waitFor(() => expect(screen.getByText(/6 源 · 故障置顶/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '网页' }));
    expect(screen.getByText(/6 源 · 故障置顶/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '微信' }));
    expect(screen.getByText('暂无注册源')).toBeInTheDocument();
  });
});
