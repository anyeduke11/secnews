/**
 * SignalPanel colocated 测试 (v0.8.5 C3, spec §6.1)
 * 断言: 真实 API 参数 / confidence 徽标 / unavailable 降级 / empty 合法 / 立项携带 signal 引用。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../Toast';
import { SignalPanel } from './SignalPanel';

vi.mock('../../../api/v1', async () => {
  const actual = await vi.importActual<typeof import('../../../api/v1')>('../../../api/v1');
  return { ...actual, listSignals: vi.fn(), createCase: vi.fn() };
});

import { listSignals, createCase } from '../../../api/v1';
const mockListSignals = vi.mocked(listSignals);
const mockCreateCase = vi.mocked(createCase);

function ui(node: React.ReactElement) {
  return (
    <MemoryRouter>
      <ToastProvider>{node}</ToastProvider>
    </MemoryRouter>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('SignalPanel', () => {
  it('渲染信号 + confidence 徽标 + 立项按钮; 查询 days=7&limit=50', async () => {
    mockListSignals.mockResolvedValue({
      version: 'v1', total: 1,
      items: [{
        id: 'sig01HBWXAZ2P3XQV5M8B7CDERF', subject_id: 'subj01HBWXAZ2P3XQV5M8B7CDERF',
        material_id: 'mat01HBWXAZ2P3XQV5M8B7CDERF', summary: 'OpenSSH 新漏洞利用出现在野',
        occurred_at: '2026-09-08T08:00:00+00:00', confidence: 'verified', status: 'verified',
        subject_name: 'OpenSSH',
      }],
    } as any);
    render(ui(<SignalPanel />));
    expect(await screen.findByText('OpenSSH 新漏洞利用出现在野')).toBeTruthy();
    expect(screen.getByText('verified')).toBeTruthy();
    expect(screen.getByTestId('signal-open-case-btn')).toBeTruthy();
    expect(mockListSignals).toHaveBeenCalledWith({ days: 7, limit: 50 });
  });

  it('接口失败 → unavailable 降级, 不伪造数据', async () => {
    mockListSignals.mockRejectedValue(new Error('backend down'));
    render(ui(<SignalPanel />));
    expect(await screen.findByText(/信号不可用 \(unavailable\)/)).toBeTruthy();
    expect(screen.getByText(/backend down/)).toBeTruthy();
  });

  it('空数组合法 (B1 未贯通) → empty 态而非报错', async () => {
    mockListSignals.mockResolvedValue({ version: 'v1', total: 0, items: [] } as any);
    render(ui(<SignalPanel />));
    expect(await screen.findByText(/近 7 天无受管信号/)).toBeTruthy();
  });

  it('立项: createCase 携带 related_signal_ids, title ≤120', async () => {
    mockListSignals.mockResolvedValue({
      version: 'v1', total: 1,
      items: [{
        id: 'sig01HBWXAZ2P3XQV5M8B7CDERF', subject_id: 'subj01HBWXAZ2P3XQV5M8B7CDERF',
        material_id: 'mat01HBWXAZ2P3XQV5M8B7CDERF', summary: '测试信号摘要',
        occurred_at: '2026-09-08T08:00:00+00:00', confidence: 'likely', status: 'likely',
      }],
    } as any);
    mockCreateCase.mockResolvedValue({
      version: 'v1',
      item: { id: 'case01HBWXAZ2P3XQV5M8B7CDERF', title: 'x', question: 'y', status: 'open', revision: 1 } as any,
    });
    render(ui(<SignalPanel />));
    (await screen.findByTestId('signal-open-case-btn') as HTMLButtonElement).click();
    await waitFor(() => {
      expect(mockCreateCase).toHaveBeenCalledTimes(1);
      const body = mockCreateCase.mock.calls[0][0];
      expect(body.related_signal_ids).toEqual(['sig01HBWXAZ2P3XQV5M8B7CDERF']);
      expect(body.title.length).toBeLessThanOrEqual(120);
    });
  });
});
