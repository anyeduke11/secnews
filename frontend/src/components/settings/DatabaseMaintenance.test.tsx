/**
 * DatabaseMaintenance — 危险区二次确认守门测试 (R-15 / v0.8.8)
 *
 * 断言意图 (Rule 9): 危险动作是"不可逆写", 首次点击必须只登记待确认动作,
 * 在用户显式确认前不得发出任何写请求; 取消后同样不得发出请求。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DatabaseMaintenance } from './DatabaseMaintenance';

function makeFetch() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'POST' && url.includes('/api/maintenance/vacuum')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok', total_seconds: 1 }) } as Response);
    }
    if (url.includes('/api/maintenance/health')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ size_mb: 12.5, fragmentation_pct: 3.1, journal_mode: 'wal' }),
      } as Response);
    }
    if (url.includes('/api/maintenance/table-stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ tables: [] }) } as Response);
    }
    if (url.includes('/api/maintenance/dirty-report')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }
    if (url.includes('/api/maintenance/duplicates')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ hotspots: [], knowledge_items: [] }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

const vacuumCalls = (m: ReturnType<typeof makeFetch>) =>
  m.mock.calls.filter(c => String(c[0]).includes('/api/maintenance/vacuum'));

describe('DatabaseMaintenance — 危险区二次确认', () => {
  let fetchMock: ReturnType<typeof makeFetch>;

  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('首次点击只弹确认条, 不发出 VACUUM 请求; 确认后才放行', async () => {
    render(<DatabaseMaintenance />);
    await waitFor(() => expect(screen.getByText('12.5 MB')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('danger-arm-vacuum'));

    // 确认前: 有确认条, 无写请求 (核心断言: 二次确认真的挡住了请求)
    expect(screen.getByTestId('danger-confirm-text')).toHaveTextContent('VACUUM 压缩');
    expect(vacuumCalls(fetchMock)).toHaveLength(0);

    fireEvent.click(screen.getByTestId('danger-confirm-yes'));

    await waitFor(() => expect(vacuumCalls(fetchMock).length).toBeGreaterThan(0));
    // 请求方法是 POST, 不是 GET
    expect((vacuumCalls(fetchMock)[0][1]?.method ?? 'GET').toUpperCase()).toBe('POST');
  });

  it('取消确认后仍不发出请求', async () => {
    render(<DatabaseMaintenance />);
    await waitFor(() => expect(screen.getByText('12.5 MB')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('danger-arm-vacuum'));
    expect(screen.getByTestId('danger-confirm-text')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('danger-confirm-cancel'));

    expect(screen.queryByTestId('danger-confirm-text')).toBeNull();
    expect(vacuumCalls(fetchMock)).toHaveLength(0);
  });
});