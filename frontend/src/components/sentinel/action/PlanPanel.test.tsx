/**
 * 执行计划面板 colocated 测试 (v0.8.9 P3 C3-4)
 *
 * 断言意图 (不只是行为):
 *  - L1 默认拒绝: 只有显式批准才产生 approved; 驳回必须留原因 (审计可回溯);
 *  - approved 冻结: 冻结后不再提供任何改动入口, 只暴露 boundary_hash;
 *  - 404 是「无草稿」合法空态, 不得伪装成错误; 其他失败必须显式呈现 (fail-loud);
 *  - AI 起草 503 时给出人工手写兜底, 而不是静默失败。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiError } from '../../../lib/api';

vi.mock('../../../api/v1', () => ({
  getRunPlan: vi.fn(),
  submitRunPlan: vi.fn(),
  generateRunPlan: vi.fn(),
  approveRunPlan: vi.fn(),
  rejectRunPlan: vi.fn(),
}));

import {
  getRunPlan,
  approveRunPlan,
  rejectRunPlan,
  submitRunPlan,
  generateRunPlan,
  type ApiVersioned,
  type ExecutionPlanEnvelope,
} from '../../../api/v1';
import { PlanPanel } from './PlanPanel';

const mkEnv = (status: 'draft' | 'approved' | 'rejected'): ApiVersioned<ExecutionPlanEnvelope> => ({
  version: 'v1',
  item: {
    status,
    submitted_by: 'user',
    submitted_at: '2026-11-16T00:00:00',
    source: status === 'draft' ? 'ai_draft' : 'manual',
    boundary_hash: status === 'approved' ? 'f'.repeat(64) : null,
    approved_by: status === 'approved' ? 'user' : null,
    reject_reason: status === 'rejected' ? '证据不足' : null,
    plan: {
      commands: [['ls', '-la']],
      writable_paths: ['/tmp/out'],
      readable_paths: [],
      network: [],
      command_timeout_sec: 60,
      total_timeout_sec: 300,
      output_artifact: { kind: 'report', title: '报告' },
    },
  },
});

const notFound = () => new ApiError(404, 'run plan not found');

describe('PlanPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('404 → 无草稿空态 (不是错误), 提供 AI 起草与手写入口', async () => {
    vi.mocked(getRunPlan).mockRejectedValueOnce(notFound());
    render(<PlanPanel runId="r1" actionId="a1" />);

    expect(await screen.findByText(/尚无执行计划/)).toBeTruthy();
    expect(screen.queryByTestId('plan-error')).toBeNull();
    expect(screen.getByTestId('plan-generate')).toBeTruthy();
    expect(screen.getByTestId('plan-manual-open')).toBeTruthy();
  });

  it('draft → 呈现命令与边界; 批准后回调 approve 并刷新父层', async () => {
    vi.mocked(getRunPlan).mockResolvedValueOnce(mkEnv('draft'));
    vi.mocked(approveRunPlan).mockResolvedValueOnce(mkEnv('approved'));
    const onRefresh = vi.fn();
    render(<PlanPanel runId="r1" actionId="a1" onRefresh={onRefresh} />);

    expect(await screen.findByText(/ls -la/)).toBeTruthy();
    expect(screen.getByTestId('plan-boundary').textContent).toContain('/tmp/out');

    fireEvent.click(screen.getByTestId('plan-approve'));
    await waitFor(() => expect(approveRunPlan).toHaveBeenCalledWith('r1'));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('驳回必须留原因: 原因为空不发请求, 填写后带上 reason', async () => {
    vi.mocked(getRunPlan).mockResolvedValueOnce(mkEnv('draft'));
    vi.mocked(rejectRunPlan).mockResolvedValueOnce(mkEnv('rejected'));
    render(<PlanPanel runId="r1" actionId="a1" />);

    fireEvent.click(await screen.findByTestId('plan-reject-open'));
    const submit = screen.getByTestId('plan-reject-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    fireEvent.change(screen.getByTestId('plan-reject-reason'), {
      target: { value: '缺少回滚步骤' },
    });
    fireEvent.click(submit);
    await waitFor(() =>
      expect(rejectRunPlan).toHaveBeenCalledWith('r1', { reason: '缺少回滚步骤' })
    );
  });

  it('approved 冻结: 只暴露 boundary_hash, 无批准/驳回/起草入口', async () => {
    vi.mocked(getRunPlan).mockResolvedValueOnce(mkEnv('approved'));
    render(<PlanPanel runId="r1" actionId="a1" />);

    expect(await screen.findByTestId('plan-frozen')).toBeTruthy();
    expect(screen.queryByTestId('plan-approve')).toBeNull();
    expect(screen.queryByTestId('plan-reject-open')).toBeNull();
    expect(screen.queryByTestId('plan-generate')).toBeNull();
    expect(screen.queryByTestId('plan-manual-open')).toBeNull();
  });

  it('AI 起草 503 → 错误显式呈现并提示手写 JSON 兜底', async () => {
    vi.mocked(getRunPlan).mockRejectedValueOnce(notFound());
    vi.mocked(generateRunPlan).mockRejectedValueOnce(new ApiError(503, 'ai_hub down'));
    render(<PlanPanel runId="r1" actionId="a1" />);

    fireEvent.click(await screen.findByTestId('plan-generate'));
    const err = await screen.findByTestId('plan-error');
    expect(err.textContent).toContain('手写 JSON');
  });

  it('手写 JSON 非法 → 不发请求并报错', async () => {
    vi.mocked(getRunPlan).mockRejectedValueOnce(notFound());
    render(<PlanPanel runId="r1" actionId="a1" />);

    fireEvent.click(await screen.findByTestId('plan-manual-open'));
    fireEvent.change(screen.getByTestId('plan-manual-json'), { target: { value: '{oops' } });
    fireEvent.click(screen.getByTestId('plan-manual-submit'));

    expect(await screen.findByTestId('plan-error')).toBeTruthy();
    expect(submitRunPlan).not.toHaveBeenCalled();
  });
});