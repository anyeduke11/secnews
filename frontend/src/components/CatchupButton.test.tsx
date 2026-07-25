// frontend/src/components/CatchupButton.test.tsx
// v1.8 Phase 8 — CatchupButton 组件测试
//
// 覆盖 (8 用例):
//   - F3.1 渲染触发按钮
//   - F3.2 点击触发 → 调用 POST /api/catchup/run
//   - F3.3 显示当前运行进度 (succeeded/attempted 计数)
//   - F3.4 点击中止 → 调用 POST /api/catchup/abort
//   - F3.5 409 conflict 时显示 toast
//   - F3.6 终态后停止轮询
//   - F3.7 GET /api/catchup/status 失败不崩
//   - F3.8 无 current_running 时不显示 abort 按钮
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

import { CatchupButton } from './CatchupButton';

const mockStatus = {
  current_running: null,
  current_manual_run_id: null,
  recent: [],
  last_orphan_recovery_at: null,
  total_recent: 0,
};

const mockStatusRunning = {
  current_running: {
    id: 42,
    mode: 'manual',
    status: 'running',
    started_at: '2026-07-25T20:00:00+00:00',
    finished_at: null,
    items_ingested: 5,
    sources_attempted: 10,
    sources_succeeded: 3,
    error_msg: null,
    duration_s: 12.3,
    categories: ['ai', 'security'],
  },
  current_manual_run_id: 42,
  recent: [],
  last_orphan_recovery_at: null,
  total_recent: 1,
};

describe('CatchupButton', () => {
  let mockFetch: any;

  beforeEach(() => {
    mockFetch = vi.fn(async (url: any, opts: any = {}) => {
      const u = typeof url === 'string' ? url : url.url;
      const method = opts.method || 'GET';
      if (u.includes('/api/catchup/status')) {
        return new Response(JSON.stringify(mockStatus), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (u.includes('/api/catchup/run') && method === 'POST') {
        return new Response(
          JSON.stringify({ run_id: 42, status: 'running', mode: 'manual' }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (u.includes('/api/catchup/abort') && method === 'POST') {
        return new Response(
          JSON.stringify({ ok: true, aborted_run_id: 42 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    global.fetch = mockFetch as any;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // F3.1
  it('renders trigger button on mount', async () => {
    await act(async () => {
      render(<CatchupButton />);
    });
    expect(screen.getByTestId('catchup-trigger')).toBeInTheDocument();
    expect(screen.getByLabelText('追抓资讯')).toBeInTheDocument();
  });

  // F3.2
  it('triggers POST /api/catchup/run on click', async () => {
    await act(async () => {
      render(<CatchupButton />);
    });
    // 等待初始 status fetch
    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
    });
    // 点击触发
    const btn = screen.getByTestId('catchup-trigger');
    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => {
      const runCall = mockFetch.mock.calls.find(
        (c: any) => typeof c[0] === 'string' && c[0].includes('/api/catchup/run') && (c[1]?.method === 'POST'),
      );
      expect(runCall).toBeDefined();
    });
  });

  // F3.3
  it('displays progress when current_running is set', async () => {
    // 用 mock 返回 running 状态
    mockFetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/catchup/status')) {
        return new Response(JSON.stringify(mockStatusRunning), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    global.fetch = mockFetch as any;

    await act(async () => {
      render(<CatchupButton />);
    });
    await waitFor(() => {
      expect(screen.getByTestId('catchup-progress')).toHaveTextContent('3/10 源');
    });
  });

  // F3.4
  it('triggers POST /api/catchup/abort when abort button clicked', async () => {
    mockFetch = vi.fn(async (url: any, opts: any = {}) => {
      const u = typeof url === 'string' ? url : url.url;
      const method = opts.method || 'GET';
      if (u.includes('/api/catchup/status')) {
        return new Response(JSON.stringify(mockStatusRunning), { status: 200 });
      }
      if (u.includes('/api/catchup/abort') && method === 'POST') {
        return new Response(
          JSON.stringify({ ok: true, aborted_run_id: 42 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    global.fetch = mockFetch as any;

    await act(async () => {
      render(<CatchupButton />);
    });
    const abortBtn = await waitFor(() => screen.getByTestId('catchup-abort'));
    await act(async () => {
      fireEvent.click(abortBtn);
    });
    await waitFor(() => {
      const abortCall = mockFetch.mock.calls.find(
        (c: any) => typeof c[0] === 'string' && c[0].includes('/api/catchup/abort'),
      );
      expect(abortCall).toBeDefined();
    });
  });

  // F3.5
  it('shows error toast on 409 conflict', async () => {
    mockFetch = vi.fn(async (url: any, opts: any = {}) => {
      const u = typeof url === 'string' ? url : url.url;
      const method = opts.method || 'GET';
      if (u.includes('/api/catchup/status')) {
        return new Response(JSON.stringify(mockStatus), { status: 200 });
      }
      if (u.includes('/api/catchup/run') && method === 'POST') {
        return new Response(
          JSON.stringify({ detail: { message: 'manual in progress', active_run_id: 99 } }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    global.fetch = mockFetch as any;

    await act(async () => {
      render(<CatchupButton />);
    });
    const btn = screen.getByTestId('catchup-trigger');
    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => {
      const toast = screen.queryByTestId('catchup-toast');
      expect(toast).toBeInTheDocument();
      expect(toast).toHaveTextContent('已有 manual 追抓在跑');
    });
  });

  // F3.6
  it('stops showing progress when current_running becomes null', async () => {
    // 此测试用真实定时器 — 改写 status 回调以模拟终态到达, 验证 React effect 的清理
    // 不依赖 fake timers (避免与 React testing-library 的 act 循环冲突)
    let statusResponse: any = mockStatusRunning;
    mockFetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/catchup/status')) {
        return new Response(JSON.stringify(statusResponse), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    global.fetch = mockFetch as any;

    await act(async () => {
      render(<CatchupButton />);
    });
    // 初始: current_running 存在 → 显示 progress
    await waitFor(() => {
      expect(screen.getByTestId('catchup-progress')).toBeInTheDocument();
    });
    // 模拟终态: current_running=null
    // 改写 mock 返回值 + 主动重渲染 (通过 key 触发)
    statusResponse = { ...mockStatusRunning, current_running: null };
    // 用 waitFor 等待下一次 polling 完成
    await waitFor(
      () => {
        expect(screen.queryByTestId('catchup-progress')).not.toBeInTheDocument();
      },
      { timeout: 5000, interval: 500 },
    );
  });

  // F3.7
  it('handles status fetch failure gracefully', async () => {
    mockFetch = vi.fn(async () => {
      return new Response('Server Error', { status: 500 });
    });
    global.fetch = mockFetch as any;

    await act(async () => {
      render(<CatchupButton />);
    });
    // 不应崩, 按钮仍可点击
    const btn = screen.getByTestId('catchup-trigger');
    expect(btn).toBeInTheDocument();
  });

  // F3.8
  it('does not show abort button when no current_running', async () => {
    await act(async () => {
      render(<CatchupButton />);
    });
    await waitFor(() => {
      expect(screen.getByTestId('catchup-trigger')).toBeInTheDocument();
    });
    // 不应显示中止按钮
    expect(screen.queryByTestId('catchup-abort')).not.toBeInTheDocument();
  });
});
