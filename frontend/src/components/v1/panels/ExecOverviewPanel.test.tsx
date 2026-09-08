/**
 * ExecOverviewPanel colocated 测试 (v0.8.5 C3, spec §6.4)
 * 断言: limit=8 / 并行聚合单 case 失败隔离为 unavailable (不显示 0) / 列表失败降级。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExecOverviewPanel } from './ExecOverviewPanel';

vi.mock('../../../api/v1', async () => {
  const actual = await vi.importActual<typeof import('../../../api/v1')>('../../../api/v1');
  return { ...actual, listCases: vi.fn(), getCaseAggregate: vi.fn() };
});

import { listCases, getCaseAggregate } from '../../../api/v1';
const mockListCases = vi.mocked(listCases);
const mockGetCaseAggregate = vi.mocked(getCaseAggregate);

function ui(node: React.ReactElement) {
  return <MemoryRouter>{node}</MemoryRouter>;
}

beforeEach(() => vi.clearAllMocks());

describe('ExecOverviewPanel', () => {
  it('并行聚合 + 单 case 失败隔离为 unavailable (不显示 0)', async () => {
    mockListCases.mockResolvedValue({
      version: 'v1', total: 2,
      items: [
        { id: 'case01HBWXAZ2P3XQV5M8B7CDERF', title: '事项A', question: 'q', status: 'in_progress', priority: 'p2', revision: 1 },
        { id: 'case02HBWXAZ2P3XQV5M8B7CDERF', title: '事项B', question: 'q', status: 'open', priority: 'p1', revision: 1 },
      ],
    } as any);
    mockGetCaseAggregate.mockImplementation((id: string) => {
      if (id.startsWith('case01')) {
        return Promise.resolve({
          version: 'v1', case: {} as any, judgments: [],
          actions: [{ id: 'a1', status: 'planned' }, { id: 'a2', status: 'running' }] as any[],
          runs: [], artifacts: [{ id: 'f1', status: 'verified' }] as any[],
        } as any);
      }
      return Promise.reject(new Error('aggregate boom'));
    });
    render(ui(<ExecOverviewPanel />));
    await waitFor(() => expect(screen.getAllByTestId('exec-overview-item').length).toBe(1));
    const card = screen.getByTestId('exec-overview-item');
    expect(card.textContent).toContain('待批准');
    expect(screen.getByText(/unavailable: aggregate boom/)).toBeTruthy();
    expect(mockListCases).toHaveBeenCalledWith({ status: ['open', 'in_progress'], limit: 8 });
  });

  it('列表失败 → unavailable 降级', async () => {
    mockListCases.mockRejectedValue(new Error('backend down'));
    render(ui(<ExecOverviewPanel />));
    expect(await screen.findByText(/总览不可用 \(unavailable\)/)).toBeTruthy();
  });
});
