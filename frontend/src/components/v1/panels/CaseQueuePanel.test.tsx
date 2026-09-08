/**
 * CaseQueuePanel colocated 测试 (v0.8.5 C3, spec §6.2)
 * 断言: blocked + open/in_progress 两次重复键查询 / blocked 置顶 / unavailable 降级。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CaseQueuePanel } from './CaseQueuePanel';

vi.mock('../../../api/v1', async () => {
  const actual = await vi.importActual<typeof import('../../../api/v1')>('../../../api/v1');
  return { ...actual, listCases: vi.fn() };
});

import { listCases } from '../../../api/v1';
const mockListCases = vi.mocked(listCases);

function ui(node: React.ReactElement) {
  return <MemoryRouter>{node}</MemoryRouter>;
}

beforeEach(() => vi.clearAllMocks());

describe('CaseQueuePanel', () => {
  it('两次查询 (blocked + open/in_progress 重复键), blocked 置顶', async () => {
    const mk = (id: string, status: string) => ({
      id, title: `T-${id}`, question: 'q', status, priority: 'p2', revision: 1,
    } as any);
    mockListCases.mockImplementation((q: any) => {
      if (q?.status?.[0] === 'blocked') {
        return Promise.resolve({ version: 'v1', total: 1, items: [mk('B', 'blocked')] } as any);
      }
      return Promise.resolve({ version: 'v1', total: 2, items: [mk('O', 'open'), mk('I', 'in_progress')] } as any);
    });
    render(ui(<CaseQueuePanel />));
    await waitFor(() => expect(screen.getAllByTestId('case-queue-item').length).toBe(3));
    const first = screen.getAllByTestId('case-queue-item')[0];
    expect(first.textContent).toContain('T-B');
    // 重复键语义: status 数组逐键 append, 无逗号写法 (FactCheck #2)
    const calls = mockListCases.mock.calls;
    expect(calls.some(c => JSON.stringify(c[0]?.status) === JSON.stringify(['blocked']))).toBe(true);
    expect(calls.some(c => JSON.stringify(c[0]?.status) === JSON.stringify(['open', 'in_progress']))).toBe(true);
  });

  it('接口失败 → unavailable 降级', async () => {
    mockListCases.mockRejectedValue(new Error('backend down'));
    render(ui(<CaseQueuePanel />));
    expect(await screen.findByText(/队列不可用 \(unavailable\)/)).toBeTruthy();
  });

  it('空数组合法 → empty 态', async () => {
    mockListCases.mockResolvedValue({ version: 'v1', total: 0, items: [] } as any);
    render(ui(<CaseQueuePanel />));
    expect(await screen.findByText(/无活跃事项/)).toBeTruthy();
  });
});
