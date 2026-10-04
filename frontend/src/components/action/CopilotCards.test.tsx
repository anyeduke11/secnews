/**
 * CopilotCards colocated 测试 (v0.8.6 P1-3, M3 四卡)。
 *
 * WHY (Rule 9): 锁的是"四卡全部走提案通道"契约 — 判研卡走 draft-judgment
 * 专用端点、三副驾卡走 copilot-draft 且锚点参数正确; 起草成功必须广播
 * proposals:changed (审批收件箱自刷新的耦合点); 模型 failed 状态按显式
 * 失败呈现 (HTTP 200 陷阱), 不当成功。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CopilotCards, PROPOSALS_CHANGED_EVENT } from './CopilotCards';

vi.mock('../../api/proposals', () => ({
  draftJudgment: vi.fn(),
  copilotDraft: vi.fn(),
}));

import { copilotDraft, draftJudgment, type Proposal } from '../../api/proposals';

const mockJudgment = vi.mocked(draftJudgment);
const mockCopilot = vi.mocked(copilotDraft);

function draftProposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 'prop_X1', case_id: null, source: 'copilot',
    kind: 'knowledge_draft', payload: {}, evidence_ids: [],
    prompt_version: 'copilot-draft@v1', status: 'draft',
    error_msg: null, reject_reason: null, reviewed_by: null,
    reviewed_at: null, run_id: null, created_at: '2026-10-03T00:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CopilotCards', () => {
  it('渲染四卡 (研判/摘要/召回/复盘), 空输入时按钮禁用', () => {
    render(<CopilotCards />);
    for (const kind of ['judgment_draft', 'knowledge_draft', 'case_suggestion', 'report']) {
      expect(screen.getByTestId(`copilot-card-${kind}`)).toBeTruthy();
      expect((screen.getByTestId(`copilot-draft-btn-${kind}`) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it('研判卡 → draftJudgment(case_id); 成功广播 proposals:changed', async () => {
    mockJudgment.mockResolvedValue(draftProposal({ kind: 'judgment_draft', case_id: 'case_1' }));
    const dispatched = vi.spyOn(window, 'dispatchEvent');
    render(<CopilotCards />);

    fireEvent.change(screen.getByLabelText('研判建议锚点 ID'), { target: { value: 'case_1' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-judgment_draft'));

    await waitFor(() => expect(mockJudgment).toHaveBeenCalledWith('case_1'));
    expect(mockCopilot).not.toHaveBeenCalled();
    await waitFor(() => expect(dispatched.mock.calls.some(
      c => (c[0] as Event).type === PROPOSALS_CHANGED_EVENT,
    )).toBe(true));
    expect(screen.getByTestId('copilot-ok-judgment_draft')).toBeTruthy();
  });

  it('摘要卡 → copilotDraft(knowledge_draft, {knowledge_id})', async () => {
    mockCopilot.mockResolvedValue(draftProposal());
    render(<CopilotCards />);
    fireEvent.change(screen.getByLabelText('知识摘要锚点 ID'), { target: { value: 'kl-sum-1' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-knowledge_draft'));
    await waitFor(() => expect(mockCopilot).toHaveBeenCalledWith(
      'knowledge_draft', { knowledge_id: 'kl-sum-1' },
    ));
  });

  it('召回卡与复盘卡 → copilotDraft(kind, {case_id})', async () => {
    mockCopilot.mockResolvedValue(draftProposal());
    render(<CopilotCards />);
    fireEvent.change(screen.getByLabelText('证据召回 · 建案锚点 ID'), { target: { value: 'case_9' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-case_suggestion'));
    await waitFor(() => expect(mockCopilot).toHaveBeenCalledWith(
      'case_suggestion', { case_id: 'case_9' },
    ));
    fireEvent.change(screen.getByLabelText('复盘草案 (SK-04)锚点 ID'), { target: { value: 'case_9' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-report'));
    await waitFor(() => expect(mockCopilot).toHaveBeenCalledWith(
      'report', { case_id: 'case_9' },
    ));
  });

  it('HTTP 200 + status=failed → 显式失败呈现, 不广播成功事件', async () => {
    mockCopilot.mockResolvedValue(draftProposal({
      status: 'failed', error_msg: 'TimeoutError: read timed out',
    }));
    const dispatched = vi.spyOn(window, 'dispatchEvent');
    render(<CopilotCards />);
    fireEvent.change(screen.getByLabelText('知识摘要锚点 ID'), { target: { value: 'kl-1' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-knowledge_draft'));
    await waitFor(() => expect(
      screen.getByTestId('copilot-err-knowledge_draft').textContent,
    ).toContain('TimeoutError'));
    expect(dispatched.mock.calls.some(
      c => (c[0] as Event).type === PROPOSALS_CHANGED_EVENT,
    )).toBe(false);
  });

  it('请求异常 → 单卡错误隔离 (role=alert), 其他卡不受影响', async () => {
    mockCopilot.mockRejectedValue(new Error('backend down'));
    render(<CopilotCards />);
    fireEvent.change(screen.getByLabelText('知识摘要锚点 ID'), { target: { value: 'kl-1' } });
    fireEvent.click(screen.getByTestId('copilot-draft-btn-knowledge_draft'));
    await waitFor(() => expect(
      screen.getByTestId('copilot-err-knowledge_draft').textContent,
    ).toContain('backend down'));
    // 其他卡仍可交互
    expect((screen.getByTestId('copilot-draft-btn-report') as HTMLButtonElement).disabled).toBe(true);
  });
});
