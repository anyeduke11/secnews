/**
 * OpsRunsPanel — 任务失败面板 (v0.8.6 P0-5 / M5 最小版)。
 * 意图: 任一 job 失败 24h 内可在 UI 查到原因 — failed/missed 优先 + 原因列。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { OpsRunsPanel } from './OpsRunsPanel';

const RESP = {
  runs: [
    { id: 2, job_id: 'sm2_daily_push-2', job_type: 'sm2_daily_push',
      status: 'missed', started_at: '2026-10-02T07:00:00+00:00',
      finished_at: null, duration_ms: null,
      error: 'misfire: 超过 misfire_grace_time 被调度器丢弃 (E4)', trace_id: null },
    { id: 1, job_id: 'collect_all-1', job_type: 'collect_all',
      status: 'failed', started_at: '2026-10-02T09:10:00+00:00',
      finished_at: '2026-10-02T09:10:32+00:00', duration_ms: 32100,
      error: 'RuntimeError: proxy timeout', trace_id: 'job:collect_all:1' },
  ],
  summary: { ok: 128, failed: 1, missed: 1, running: 0, stale_running: 2 },
  window_hours: 24,
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    if (String(input).startsWith('/api/ops/runs')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(RESP) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('OpsRunsPanel — 任务失败面板', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染标题 + summary 四态计数 + 僵尸 running 提示', async () => {
    render(<MemoryRouter><OpsRunsPanel /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('任务失败面板')).toBeInTheDocument());
    expect(screen.getByText('失败 1')).toBeInTheDocument();
    expect(screen.getByText('错过 1')).toBeInTheDocument();
    expect(screen.getByText('成功 128')).toBeInTheDocument();
    expect(screen.getByText('僵尸 2')).toBeInTheDocument();
  });

  it('失败/错过行显示任务名与原因 (可查到原因 = P0-5 验收)', async () => {
    render(<MemoryRouter><OpsRunsPanel /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('collect_all')).toBeInTheDocument());
    expect(screen.getByText('sm2_daily_push')).toBeInTheDocument();
    expect(screen.getByText('RuntimeError: proxy timeout')).toBeInTheDocument();
    expect(screen.getByText(/misfire: 超过/)).toBeInTheDocument();
  });

  it('默认请求失败优先过滤; 切「全部」重拉 status=all', async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><OpsRunsPanel /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('collect_all')).toBeInTheDocument());
    const defaultCall = String(fetchMock.mock.calls[0][0]);
    expect(defaultCall).toContain('status=failed%2Cmissed');

    await userEvent.click(screen.getByRole('button', { name: '全部' }));
    await waitFor(() => {
      const allCall = fetchMock.mock.calls
        .map(c => String(c[0]))
        .find(u => u.includes('status=all'));
      expect(allCall).toBeDefined();
    });
  });

  it('空数据走 LayerTable 空态', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({
        runs: [], summary: { ok: 0, failed: 0, missed: 0, running: 0, stale_running: 0 },
        window_hours: 24,
      }) } as Response)));
    render(<MemoryRouter><OpsRunsPanel /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/24h 内无失败/)).toBeInTheDocument());
  });

  it('P1-7 竞态: 卸载后慢响应返回 → 无脏状态写入 (不抛/无更新告警)', async () => {
    // WHY (PRD 验收 "快速切换路由/组件卸载无脏状态写入"):
    // fetch 在组件卸载后才 resolve — 守卫 (useAbortGuard) 必须拦住
    // setData/setLoading, 不得触发 React 状态更新告警或异常。
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    let resolveFetch!: (v: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(res => {
      resolveFetch = res;
    }) as unknown as Promise<Response>));

    const { unmount } = render(<MemoryRouter><OpsRunsPanel /></MemoryRouter>);
    // fetch 已发出但未返回 → 模拟路由快速切换卸载
    unmount();
    // 慢响应此刻才到达
    resolveFetch({
      ok: true,
      json: () => Promise.resolve(RESP),
    } as Response);
    await new Promise(r => setTimeout(r, 0)); // 冲刷微任务

    // 守卫生效: 无 "state update on an unmounted component" 类告警/异常
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
