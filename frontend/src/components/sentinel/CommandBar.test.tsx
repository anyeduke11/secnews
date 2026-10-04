/**
 * CommandBar colocated 测试 (v0.8.6 P1-4, M4)。
 *
 * WHY (Rule 9): 锁命令栏人主律契约 — 建案/出报告命令广播 proposals:changed
 * (审批收件箱刷新耦合点)、查询结果外链 rel 安全、unknown 不猜显式列动作、
 * Esc 关结果面板。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CommandBar } from './CommandBar';
import type { CommandResult } from '../../api/commands';

vi.mock('../../api/commands', () => ({
  runCommand: vi.fn(),
  listCommands: vi.fn(),
}));

import { runCommand } from '../../api/commands';

const mockRun = vi.mocked(runCommand);

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  vi.restoreAllMocks();
});

function queryResult(over: Partial<CommandResult> = {}): CommandResult {
  return {
    command_id: 'cmd_X',
    intent: 'query', outcome: 'done',
    message: '近 14 天「勒索」命中 1 条信号',
    results: [{
      signal_id: 'sig_1', summary: '勒索软件新增变种', url: 'https://src.example.com/r1',
      title: '勒索周报', occurred_at: '2026-10-01T00:00:00+00:00',
      confidence: 'unverified',
    }],
    result_count: 1, window_days: 14,
    ...over,
  };
}

describe('CommandBar', () => {
  it('空输入按钮禁用; 输入后 Enter 提交 runCommand', async () => {
    mockRun.mockResolvedValue(queryResult());
    render(<CommandBar />);
    const btn = screen.getByRole('button', { name: '执行命令' }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    const input = screen.getByLabelText('命令栏');
    fireEvent.change(input, { target: { value: '查勒索信号' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(mockRun).toHaveBeenCalledWith('查勒索信号'));
  });

  it('查询结果卡: Source 链接带 noopener (安全), Esc 关闭', async () => {
    mockRun.mockResolvedValue(queryResult());
    render(<CommandBar />);
    fireEvent.change(screen.getByLabelText('命令栏'), { target: { value: '查勒索信号' } });
    fireEvent.click(screen.getByRole('button', { name: '执行命令' }));
    const link = await screen.findByRole('link', { name: '勒索周报' });
    expect(link).toHaveAttribute('href', 'https://src.example.com/r1');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByTestId('command-result')).toBeNull());
  });

  it('建案命令: 显示 proposal_id 引导收件箱 + 广播 proposals:changed', async () => {
    mockRun.mockResolvedValue({
      command_id: 'cmd_C', intent: 'create_case', outcome: 'done',
      message: '已生成建案提案，进审批收件箱（人审后生效）',
      proposal_id: 'prop_ABC',
    });
    const dispatched = vi.spyOn(window, 'dispatchEvent');
    render(<CommandBar />);
    fireEvent.change(screen.getByLabelText('命令栏'), { target: { value: '为X建案' } });
    fireEvent.click(screen.getByRole('button', { name: '执行命令' }));
    await waitFor(() => expect(screen.getByTestId('command-result').textContent)
      .toContain('prop_ABC'));
    expect(dispatched.mock.calls.some(
      c => (c[0] as Event).type === 'proposals:changed',
    )).toBe(true);
  });

  it('unknown 意图: 显式可选动作清单, 不猜', async () => {
    mockRun.mockResolvedValue({
      command_id: 'cmd_U', intent: 'unknown', outcome: 'unrecognized',
      message: '未理解，可选动作：',
      options: ['查 <关键词> 过去N天的信号 — 检索信号池 (带原文链接)',
        '为 <主题> 建案 — 生成建案提案进审批收件箱',
        '出 <主题> 报告 — 生成报告提案进审批收件箱'],
    });
    render(<CommandBar />);
    fireEvent.change(screen.getByLabelText('命令栏'), { target: { value: '天气' } });
    fireEvent.click(screen.getByRole('button', { name: '执行命令' }));
    await waitFor(() => expect(screen.getByTestId('command-result').textContent)
      .toContain('未理解，可选动作'));
    expect(screen.getByTestId('command-result').textContent).toContain('建案');
  });

  it('请求异常 → role=alert 显式错误', async () => {
    mockRun.mockRejectedValue(new Error('backend down'));
    render(<CommandBar />);
    fireEvent.change(screen.getByLabelText('命令栏'), { target: { value: '查x信号' } });
    fireEvent.click(screen.getByRole('button', { name: '执行命令' }));
    await waitFor(() => expect(screen.getByTestId('command-error').textContent)
      .toContain('backend down'));
  });
});
