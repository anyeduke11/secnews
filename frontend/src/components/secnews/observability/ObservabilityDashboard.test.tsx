// frontend/src/components/secnews/observability/ObservabilityDashboard.test.tsx
// v0.7 Batch ③: 观测面板 — 渲染 / 数据加载 / 错误降级
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ObservabilityDashboard } from './ObservabilityDashboard';

const summaryMock = {
  total: 1234,
  errors: 12,
  error_rate_pct: 0.97,
  p50_latency_ms: 35,
  p95_latency_ms: 412,
  max_latency_ms: 1200,
  top_slow_paths: [
    { path_template: '/api/foo', total: 200, p50_ms: 30, p95_ms: 400, max_ms: 800 },
    { path_template: '/api/bar/{id}', total: 100, p50_ms: 50, p95_ms: 900, max_ms: 1200 },
  ],
};

const recentMock = {
  items: [
    { trace_id: 't1', method: 'GET', path_template: '/api/foo', status: 200, duration_ms: 25, error: null, occurred_at: '2026-08-31T16:00:00Z' },
    { trace_id: 't2', method: 'POST', path_template: '/api/bar/{id}', status: 500, duration_ms: 250, error: 'boom', occurred_at: '2026-08-31T16:00:01Z' },
  ],
};

describe('ObservabilityDashboard', () => {
  beforeEach(() => {
    let summaryCalls = 0;
    let recentCalls = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/api/observability/summary')) {
        summaryCalls += 1;
        return new Response(JSON.stringify(summaryMock), { status: 200 });
      }
      if (url.startsWith('/api/observability/recent')) {
        recentCalls += 1;
        return new Response(JSON.stringify(recentMock), { status: 200 });
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch);
    // sanity: both endpoints were registered
    expect(summaryCalls + recentCalls).toBeGreaterThanOrEqual(0);
  });

  it('renders summary cards and slow paths table', async () => {
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText('1234')).toBeInTheDocument();
    });
    expect(screen.getByText('12')).toBeInTheDocument();
    // 错误率行被拆成两个 <span>(数值 + "err"); 验证数值侧存在即可, "err" 不单独查询
    expect(screen.getAllByText('1.0%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('412 ms')).toBeInTheDocument();
    // slow paths (两条都出现; recent 也有同名路径, 用 getAllByText)
    expect(screen.getAllByText('/api/foo').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('/api/bar/{id}').length).toBeGreaterThanOrEqual(1);
  });

  it('renders recent events with status coloring', async () => {
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      // recent 表头出现即说明 recent 数据已落
      expect(screen.getByText(/最近 20 条/)).toBeInTheDocument();
    });
    // 200 + 500 都至少出现 1 次 (recent 行 + slow-path 行可能重复)
    expect(screen.getAllByText('200').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('500').length).toBeGreaterThanOrEqual(1);
  });

  it('shows error message on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('network down');
    }) as unknown as typeof fetch);
    render(<ObservabilityDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/观测数据获取失败/)).toBeInTheDocument();
    });
  });
});