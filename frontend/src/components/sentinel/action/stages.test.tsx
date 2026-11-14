/**
 * 行动四段区块 colocated 测试 (R-15)
 *
 * 断言意图 (不只是行为):
 *  - 四段是各自独立可视区块, 未选案件时各段渲染引导空态, 不合并成一张大表;
 *  - 段内标签只映射真实字段 (run.status / artifact.accepted_at / verified_result),
 *    不存在「部分成功」这类无数据来源的虚构状态;
 *  - 「发起运行」只在已批准且无运行记录时出现, 避免重复触发真实执行。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CaseStage } from './CaseStage';
import { ClaimStage } from './ClaimStage';
import { RunStage } from './RunStage';
import { ArtifactStage } from './ArtifactStage';
import type { Action, Case, Judgment, Run } from '../../../domain/v1_0';
// ArtifactStage 的 props 类型来自 API 层 (CaseAggregate.artifacts), 夹具同源
import type { Artifact } from '../../../api/v1';

const mkCase = (id: string, status = 'open'): Case =>
  ({ id, title: `案件-${id}`, question: 'q', status, priority: 'p1', created_at: '', updated_at: '' } as Case);

const mkJudgment = (id: string): Judgment =>
  ({ id, case_id: 'c1', claim_type: 'finding', claim: `主张-${id}`, evidence_refs: [{ material_id: 'm1', hash: 'h' }], created_at: '', updated_at: '' } as Judgment);

const mkAction = (id: string, status = 'approved', revision = 1): Action =>
  ({ id, case_id: 'c1', judgment_id: 'j1', title: `动作-${id}`, plan: 'p', plan_hash: 'h', status, revision, created_at: '', updated_at: '' } as Action);

const mkRun = (id: string, actionId: string, status: string): Run =>
  ({ id, action_id: actionId, protocol: 'dsh', trigger_source: 'user', idempotency_key: 'k', status, created_at: '', updated_at: '' } as Run);

const mkArtifact = (id: string, extra: Partial<Artifact> = {}): Artifact =>
  ({ id, run_id: 'r1', kind: 'report', title: `产物-${id}`, content_hash: 'h', format: 'md', size_bytes: 2048, created_at: '', updated_at: '', ...extra } as Artifact);

// ---------------------------------------------------------------- ① Case
describe('CaseStage', () => {
  it('列出案件并提供选中回调; 仅选中项 aria-pressed', () => {
    const onSelect = vi.fn();
    render(
      <CaseStage
        cases={[mkCase('a'), mkCase('b', 'blocked')]}
        selectedCaseId="a"
        onSelect={onSelect}
        loading={false}
        error={null}
      />,
    );
    const items = screen.getAllByTestId('case-stage-item');
    expect(items.length).toBe(2);
    expect(items[0].getAttribute('aria-pressed')).toBe('true');
    expect(items[1].getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(items[1]);
    expect(onSelect).toHaveBeenCalledWith('b');
  });

  it('接口失败 → 「案件不可用」而不是空态', () => {
    render(<CaseStage cases={[]} selectedCaseId={null} onSelect={vi.fn()} loading={false} error="backend down" />);
    expect(screen.getByText(/案件不可用/).textContent).toContain('backend down');
  });
});

// --------------------------------------------------------------- ② Claim
describe('ClaimStage', () => {
  it('未选案件 → 引导空态, 不渲染任何 claim 条目', () => {
    render(<ClaimStage caseId={null} items={[]} loading={false} error={null} />);
    expect(screen.getByText(/先在上方选择案件/)).toBeTruthy();
    expect(screen.queryAllByTestId('claim-stage-item').length).toBe(0);
  });

  it('选中案件 → 渲染该案件的 claim', () => {
    render(<ClaimStage caseId="c1" items={[mkJudgment('j1')]} loading={false} error={null} />);
    expect(screen.getAllByTestId('claim-stage-item').length).toBe(1);
    expect(screen.getByText(/主张-j1/)).toBeTruthy();
  });
});

// ----------------------------------------------------------------- ③ Run
describe('RunStage', () => {
  const base = { caseId: 'c1', loading: false, error: null, starting: null };

  it('已批准且无运行记录 → 出现「发起运行」, 点击回调 action', () => {
    const onStart = vi.fn();
    render(<RunStage {...base} actions={[mkAction('a1', 'approved', 7)]} runs={[]} onStart={onStart} />);
    const btn = screen.getByTestId('run-stage-start');
    fireEvent.click(btn);
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onStart.mock.calls[0][0].id).toBe('a1');
  });

  it('已有运行记录 → 不再出现「发起运行」', () => {
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'running')]}
        runs={[mkRun('r1', 'a1', 'running')]}
        onStart={vi.fn()}
      />,
    );
    expect(screen.queryAllByTestId('run-stage-start').length).toBe(0);
    expect(screen.getAllByTestId('run-stage-run').length).toBe(1);
  });

  it('v0.8.9 R-1: queued run → 认领/取消按钮; claimed → 开工; 点击回调 run', () => {
    const onClaim = vi.fn();
    const onStartRun = vi.fn();
    const onCancel = vi.fn();
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'running'), mkAction('a2', 'running')]}
        runs={[mkRun('r1', 'a1', 'queued'), mkRun('r2', 'a2', 'claimed')]}
        onStart={vi.fn()}
        onClaimRun={onClaim}
        onStartRun={onStartRun}
        onCancelRun={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId('run-claim'));
    expect(onClaim.mock.calls[0][0].id).toBe('r1');
    fireEvent.click(screen.getAllByTestId('run-start')[0]);
    expect(onStartRun).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByTestId('run-cancel')[0]);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('v0.8.9 R-1: running run → 登记结果表单 (outcome 选择 + failed 须 error 才可提交)', () => {
    const onFinish = vi.fn();
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'running')]}
        runs={[mkRun('r1', 'a1', 'running')]}
        onStart={vi.fn()}
        onFinishRun={onFinish}
      />,
    );
    fireEvent.click(screen.getByTestId('run-finish-open'));
    // 默认 outcome=done 无需 error → 直接提交
    fireEvent.click(screen.getByTestId('run-finish-submit'));
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(onFinish.mock.calls[0][1].outcome).toBe('done');
    // 失败真实性: failed 无 error → 提交按钮 disabled
    render(
      <RunStage
        {...base}
        actions={[mkAction('a2', 'running')]}
        runs={[mkRun('r2', 'a2', 'running')]}
        onStart={vi.fn()}
        onFinishRun={onFinish}
      />,
    );
    fireEvent.click(screen.getAllByTestId('run-finish-open')[0]);
    fireEvent.change(screen.getByTestId('run-finish-outcome'), { target: { value: 'failed' } });
    expect((screen.getByTestId('run-finish-submit') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId('run-finish-error'), { target: { value: '原因' } });
    expect((screen.getByTestId('run-finish-submit') as HTMLButtonElement).disabled).toBe(false);
  });

  it('v0.8.9 C1-2: run 全终态且 action running → 收口按钮; 回调 action', () => {
    const onFinishAction = vi.fn();
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'running')]}
        runs={[mkRun('r1', 'a1', 'succeeded')]}
        onStart={vi.fn()}
        onFinishAction={onFinishAction}
      />,
    );
    const btn = screen.getByTestId('action-finish');
    fireEvent.click(btn);
    expect(onFinishAction).toHaveBeenCalledTimes(1);
    expect(onFinishAction.mock.calls[0][0].id).toBe('a1');
  });

  it('v0.8.9: 未传回执回调时 (旧调用方) 不渲染回执按钮 — 向后兼容', () => {
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'running')]}
        runs={[mkRun('r1', 'a1', 'queued'), mkRun('r2', 'a1', 'running')]}
        onStart={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('run-claim')).toBeNull();
    expect(screen.queryByTestId('run-finish-open')).toBeNull();
  });

  it('outcome 只映射真实 run.status: timed_out → 超时失败, succeeded → 成功', () => {
    render(
      <RunStage
        {...base}
        actions={[mkAction('a1', 'failed'), mkAction('a2', 'succeeded')]}
        runs={[mkRun('r1', 'a1', 'timed_out'), mkRun('r2', 'a2', 'succeeded')]}
        onStart={vi.fn()}
      />,
    );
    expect(screen.getByText(/超时失败/)).toBeTruthy();
    // 精确匹配 run 段 outcome, 避免命中 Action 状态「已成功」
    expect(screen.getByText('成功')).toBeTruthy();
  });

  it('无 Action → 引导文案指向 Claim 前置条件', () => {
    render(<RunStage {...base} actions={[]} runs={[]} onStart={vi.fn()} />);
    expect(screen.getByText(/该案件暂无 Action/)).toBeTruthy();
  });
});

// ------------------------------------------------------------- ④ Artifact
describe('ArtifactStage', () => {
  it('未选案件 → 引导空态', () => {
    render(<ArtifactStage caseId={null} items={[]} loading={false} error={null} />);
    expect(screen.getByText(/先在上方选择案件/)).toBeTruthy();
  });

  it('回执标签由真实字段决定: accepted_at 优先于 verified_result', () => {
    render(
      <ArtifactStage
        caseId="c1"
        items={[
          mkArtifact('a1', { accepted_at: '2026-11-10T00:00:00Z', verified_result: 'pass' }),
          mkArtifact('a2', { verified_result: 'fail' }),
        ]}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText(/已验收 · 回执已签署/)).toBeTruthy();
    expect(screen.getByText(/验证失败/)).toBeTruthy();
    expect(screen.getAllByTestId('artifact-stage-item').length).toBe(2);
  });

  it('两者皆无 → 待验证 (不谎报已验收)', () => {
    render(<ArtifactStage caseId="c1" items={[mkArtifact('a3')]} loading={false} error={null} />);
    expect(screen.getByText(/待验证/)).toBeTruthy();
  });
});