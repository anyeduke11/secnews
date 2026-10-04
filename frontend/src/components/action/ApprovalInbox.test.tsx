/**
 * ApprovalInbox colocated 测试 (v0.8.6 P1-1 切片3, M1 用例 A)。
 *
 * WHY (Rule 9): 锁的是人主律交互契约 — 批准必须二次确认 (防误触产生真实写入)、
 * 驳回原因必填且 ≤200、写操作类型挂橙标、失败提案凭 case 锚点重试。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { ApprovalInbox } from './ApprovalInbox';

vi.mock('../../api/proposals', () => ({
  listProposals: vi.fn(),
  draftJudgment: vi.fn(),
  copilotDraft: vi.fn(),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));

import {
  listProposals,
  draftJudgment,
  copilotDraft,
  approveProposal,
  rejectProposal,
  type Proposal,
} from '../../api/proposals';

const mockList = vi.mocked(listProposals);
const mockDraft = vi.mocked(draftJudgment);
const mockCopilot = vi.mocked(copilotDraft);
const mockApprove = vi.mocked(approveProposal);
const mockReject = vi.mocked(rejectProposal);

function draftProposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 'prop_D1',
    case_id: 'case_1',
    source: 'agent',
    kind: 'judgment_draft',
    payload: { claim: '存在公开 PoC 且补丁缺失', confidence: 'high' },
    evidence_ids: ['mat_1', 'mat_2'],
    prompt_version: 'judgment-draft@v1',
    status: 'draft',
    error_msg: null,
    reject_reason: null,
    reviewed_by: null,
    reviewed_at: null,
    run_id: null,
    created_at: '2026-10-03T10:00:00Z',
    ...over,
  };
}

function failedProposal(over: Partial<Proposal> = {}): Proposal {
  return draftProposal({
    id: 'prop_F1',
    status: 'failed',
    payload: {},
    evidence_ids: [],
    prompt_version: 'judgment-draft@v1',
    error_msg: 'TimeoutError: read timed out',
    ...over,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockImplementation((params) => {
    if (params?.status === 'failed') {
      return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
    }
    return Promise.resolve({ items: [], total: 0, filter: { status: 'draft', kind: null } });
  });
});

function card(testid: string) {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return document.querySelector(`[data-testid="${testid}"]`)! as HTMLElement;
}

describe('ApprovalInbox', () => {
  it('渲染待审卡: 类型/发起方/证据数/case/正文 + 写操作橙标', async () => {
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
      }
      return Promise.resolve({
        items: [draftProposal(), draftProposal({
          id: 'prop_D2', kind: 'case_suggestion',
          payload: { title: '建案' }, evidence_ids: ['m1'],
        })],
        total: 2,
        filter: { status: 'draft', kind: null },
      });
    });
    render(<ApprovalInbox />);

    await waitFor(() => expect(screen.getAllByTestId('approval-draft-card').length).toBe(2));
    const cards = screen.getAllByTestId('approval-draft-card');
    expect(cards[0].textContent).toContain('研判草案');
    expect(cards[0].textContent).toContain('AI 代理');
    expect(cards[0].textContent).toContain('证据 2 条');
    expect(cards[0].textContent).toContain('case_1');
    expect(cards[0].textContent).toContain('存在公开 PoC 且补丁缺失');
    expect(cards[0].textContent).toContain('judgment-draft@v1');
    expect(within(cards[0]).getByTestId('write-op-badge')).toBeTruthy();
    // 非写操作类型不挂橙标
    expect(within(cards[1]).queryByTestId('write-op-badge')).toBeNull();
  });

  it('批准二次确认: 首击不调 API, 确认后才 approve 并重拉', async () => {
    mockApprove.mockResolvedValue(draftProposal({ status: 'approved' }));
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
      }
      return Promise.resolve({
        items: [draftProposal()], total: 1,
        filter: { status: 'draft', kind: null },
      });
    });
    render(<ApprovalInbox />);
    await waitFor(() => expect(screen.getByTestId('approve-arm-btn')).toBeTruthy());

    fireEvent.click(screen.getByTestId('approve-arm-btn'));
    expect(mockApprove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('approve-confirm-btn'));

    await waitFor(() => expect(mockApprove).toHaveBeenCalledTimes(1));
    expect(mockApprove).toHaveBeenCalledWith('prop_D1', 'owner', undefined);
    // 批准成功后重拉 (初始 2 次 + 重拉 2 次)
    expect(mockList).toHaveBeenCalledTimes(4);
  });

  it('修订 JSON 后批准: 非法 JSON 拦截, 合法则带修订 payload 提交', async () => {
    mockApprove.mockResolvedValue(draftProposal({ status: 'approved' }));
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
      }
      return Promise.resolve({
        items: [draftProposal()], total: 1,
        filter: { status: 'draft', kind: null },
      });
    });
    render(<ApprovalInbox />);
    await waitFor(() => expect(screen.getByTestId('approve-arm-btn')).toBeTruthy());

    const d = card('approval-draft-card');
    fireEvent.click(within(d).getByText('修订后批准（展开编辑 JSON）'));
    const textarea = within(d).getByLabelText('修订提案 payload JSON') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '{ 非法 json' } });
    fireEvent.click(within(d).getByTestId('approve-arm-btn'));
    fireEvent.click(within(d).getByTestId('approve-confirm-btn'));
    expect(mockApprove).not.toHaveBeenCalled();
    expect(within(d).getByTestId('draft-card-error')).toBeTruthy();

    fireEvent.change(textarea, { target: { value: JSON.stringify({ claim: '人工修订结论' }) } });
    fireEvent.click(within(d).getByTestId('approve-confirm-btn'));
    await waitFor(() => expect(mockApprove).toHaveBeenCalledTimes(1));
    expect(mockApprove).toHaveBeenCalledWith('prop_D1', 'owner', { claim: '人工修订结论' });
  });

  it('驳回: 原因必填且 ≤200, 合规才调 reject', async () => {
    mockReject.mockResolvedValue(draftProposal({ status: 'rejected' }));
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
      }
      return Promise.resolve({
        items: [draftProposal()], total: 1,
        filter: { status: 'draft', kind: null },
      });
    });
    render(<ApprovalInbox />);
    await waitFor(() => expect(screen.getByTestId('reject-arm-btn')).toBeTruthy());
    const d = card('approval-draft-card');

    fireEvent.click(within(d).getByTestId('reject-arm-btn'));
    const confirmBtn = within(d).getByTestId('reject-confirm-btn') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
    const input = within(d).getByLabelText('驳回原因') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'x'.repeat(201) } });
    expect(confirmBtn.disabled).toBe(true);
    fireEvent.change(input, { target: { value: '证据不足, 需补充公告链接' } });
    expect(confirmBtn.disabled).toBe(false);
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(mockReject).toHaveBeenCalledWith(
      'prop_D1', 'owner', '证据不足, 需补充公告链接',
    ));
  });

  it('失败提案: 有 case 锚点可重试 (重新起草), 无锚点按钮禁用', async () => {
    mockDraft.mockResolvedValue(draftProposal({ id: 'prop_D2' }));
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({
          items: [
            failedProposal(),
            failedProposal({ id: 'prop_F2', case_id: null }),
          ],
          total: 2,
          filter: { status: 'failed', kind: null },
        });
      }
      return Promise.resolve({ items: [], total: 0, filter: { status: 'draft', kind: null } });
    });
    render(<ApprovalInbox />);

    await waitFor(() => expect(screen.getAllByTestId('approval-failed-card').length).toBe(2));
    const failedCards = screen.getAllByTestId('approval-failed-card');
    expect(failedCards[0].textContent).toContain('TimeoutError: read timed out');

    const buttons = screen.getAllByTestId('retry-btn') as HTMLButtonElement[];
    expect(buttons[0].disabled).toBe(false);
    expect(buttons[1].disabled).toBe(true);
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(mockDraft).toHaveBeenCalledWith('case_1'));
  });

  it('P1-3 kind 感知重试: 副驾 kind 失败提案 → copilotDraft 同 kind + case 锚', async () => {
    mockCopilot.mockResolvedValue(draftProposal({ id: 'prop_D3', kind: 'report' }));
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({
          items: [failedProposal({ kind: 'report' })],
          total: 1,
          filter: { status: 'failed', kind: null },
        });
      }
      return Promise.resolve({ items: [], total: 0, filter: { status: 'draft', kind: null } });
    });
    render(<ApprovalInbox />);
    await waitFor(() => expect(screen.getByTestId('retry-btn')).toBeTruthy());
    fireEvent.click(screen.getByTestId('retry-btn'));
    await waitFor(() => expect(mockCopilot).toHaveBeenCalledWith(
      'report', { case_id: 'case_1' },
    ));
    expect(mockDraft).not.toHaveBeenCalled();
  });

  it('P1-3 起草事件 (proposals:changed) → 收件箱自刷新', async () => {
    // 首轮拉取 2 次 (draft+failed), 事件后再拉 2 次
    mockList.mockImplementation((params) => {
      if (params?.status === 'failed') {
        return Promise.resolve({ items: [], total: 0, filter: { status: 'failed', kind: null } });
      }
      return Promise.resolve({ items: [], total: 0, filter: { status: 'draft', kind: null } });
    });
    render(<ApprovalInbox />);
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
    window.dispatchEvent(new Event('proposals:changed'));
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(4));
  });

  it('收件箱拉取失败 → 显 unavailable, 不伪装空态', async () => {
    mockList.mockRejectedValue(new Error('backend down'));
    render(<ApprovalInbox />);
    expect(await screen.findByText(/收件箱不可用 \(unavailable\)/)).toBeTruthy();
    expect(screen.queryByTestId('approval-draft-card')).toBeNull();
  });
});
