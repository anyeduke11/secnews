/**
 * 行动四段指挥台容器 colocated 测试 (R-15)
 *
 * 断言意图:
 *  - 验收①「[data-stage] 恰为四个节点」: 不论是否选案件, 四段节点恒在 (不因加载态塌缩);
 *  - 「共享 selectedCaseId」: 选中案件后一次 aggregate 请求同时喂满后三段, 不各拉各的;
 *  - 「发起运行」走既有 startAction 并携带 revision 幂等键, 成功后重拉账本;
 *  - 端点不可用如实降级, 不静默吞错。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ActionCommandConsole } from './ActionCommandConsole';

vi.mock('../../../api/v1', async () => {
  const actual = await vi.importActual<typeof import('../../../api/v1')>('../../../api/v1');
  return { ...actual, listCases: vi.fn(), getCaseAggregate: vi.fn(), startAction: vi.fn() };
});

import { getCaseAggregate, listCases, startAction } from '../../../api/v1';
const mockListCases = vi.mocked(listCases);
const mockAggregate = vi.mocked(getCaseAggregate);
const mockStart = vi.mocked(startAction);

const CASES = [
  { id: 'c1', title: '案件一', question: 'q', status: 'open', priority: 'p1', revision: 1, created_at: '', updated_at: '' },
  { id: 'c2', title: '案件二', question: 'q', status: 'blocked', priority: 'p0', revision: 1, created_at: '', updated_at: '' },
] as any;

const AGGREGATE = {
  version: 'v1',
  case: CASES[0],
  judgments: [{ id: 'j1', case_id: 'c1', claim_type: 'finding', claim: '主张一', evidence_refs: [], created_at: '', updated_at: '' }],
  actions: [{ id: 'a1', case_id: 'c1', judgment_id: 'j1', title: '动作一', plan: 'p', plan_hash: 'h', status: 'approved', revision: 7, created_at: '', updated_at: '' }],
  runs: [{ id: 'r1', action_id: 'a1', protocol: 'dsh', trigger_source: 'user', idempotency_key: 'k', status: 'succeeded', created_at: '', updated_at: '' }],
  artifacts: [{ id: 'f1', run_id: 'r1', kind: 'report', title: '产物一', content_hash: 'h', format: 'md', size_bytes: 10, created_at: '', updated_at: '' }],
} as any;

beforeEach(() => {
  vi.clearAllMocks();
  mockListCases.mockResolvedValue({ version: 'v1', total: 2, items: CASES } as any);
  mockAggregate.mockResolvedValue(AGGREGATE);
  mockStart.mockResolvedValue({ version: 'v1', item: {}, run: {}, replayed: false } as any);
});

describe('ActionCommandConsole', () => {
  it('初始即渲染恰好 4 个 [data-stage], 未选案件时后三段为引导空态', async () => {
    const { container } = render(<ActionCommandConsole />);
    await waitFor(() => expect(screen.getAllByTestId('case-stage-item').length).toBe(2));
    expect(container.querySelectorAll('[data-stage]').length).toBe(4);
    expect(screen.getByText(/选择下方任一案件/)).toBeTruthy();
    expect(mockAggregate).not.toHaveBeenCalled();
  });

  it('选中案件 → 一次 aggregate 喂满 Claim/Run/Artifact 三段', async () => {
    const { container } = render(<ActionCommandConsole />);
    await waitFor(() => expect(screen.getAllByTestId('case-stage-item').length).toBe(2));
    fireEvent.click(screen.getAllByTestId('case-stage-item')[0]);

    await waitFor(() => expect(screen.getAllByTestId('claim-stage-item').length).toBe(1));
    expect(mockAggregate).toHaveBeenCalledTimes(1);
    expect(mockAggregate.mock.calls[0][0]).toBe('c1');
    expect(screen.getAllByTestId('run-stage-action').length).toBe(1);
    expect(screen.getAllByTestId('artifact-stage-item').length).toBe(1);
    expect(container.querySelectorAll('[data-stage]').length).toBe(4);
  });

  it('已批准且无运行 → 发起运行携带 revision + 幂等键, 并重拉账本', async () => {
    mockAggregate.mockResolvedValue({ ...AGGREGATE, runs: [] } as any);
    render(<ActionCommandConsole />);
    await waitFor(() => expect(screen.getAllByTestId('case-stage-item').length).toBe(2));
    fireEvent.click(screen.getAllByTestId('case-stage-item')[0]);

    const btn = await screen.findByTestId('run-stage-start');
    fireEvent.click(btn);

    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(1));
    const [actionId, body] = mockStart.mock.calls[0];
    expect(actionId).toBe('a1');
    expect(body.expected_revision).toBe(7);
    expect(String(body.idempotency_key).startsWith('ui-a1-')).toBe(true);
    expect(body.protocol).toBe('dsh');
    expect(body.trigger_source).toBe('user');
    await waitFor(() => expect(mockAggregate).toHaveBeenCalledTimes(2));
  });

  it('listCases 失败 → Case 段如实报不可用', async () => {
    mockListCases.mockRejectedValue(new Error('backend down'));
    render(<ActionCommandConsole />);
    expect(await screen.findByText(/案件不可用/)).toBeTruthy();
  });
});