/**
 * CustomRulesPanel 组件测试 — v0.8.6 P2 两层质量规则
 *
 * 意图锚点:
 * - open 门控: 面板家族契约 — 隐藏时不拉状态 (与 QualitySettings 顶层一致)
 * - 语义规则 UI 契约: match_kind 强制 nl + action 强制 flag (语义层只软扣分)
 * - gate 开关走 PUT /api/quality/rules 的 quality.gate.<name>.enabled 通道
 * - dry-run: with_semantic 决定是否花 LLM 预算; 命中数要可见
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CustomRulesPanel } from './CustomRulesPanel';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function jsonResp(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) };
}

function mockRules(rules: unknown[] = []) {
  return jsonResp({ rules });
}

function mockGates() {
  return jsonResp({
    gates: [
      { name: 'schema', tier: 'hard', enabled: true },
      { name: 'semantic_rules', tier: 'soft', enabled: true },
    ],
  });
}

const ONE_RULE = [{
  id: 7, name: '黑名单词', rule_kind: 'expert', match_kind: 'title_contains',
  match_value: '免费领取', action: 'reject', deduction: 50,
  scope_category: '', enabled: true,
}];

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/quality/custom-rules/gates') return Promise.resolve(mockGates());
    if (url === '/api/quality/custom-rules' && init?.method === 'POST') {
      return Promise.resolve(jsonResp({ id: 8, ...JSON.parse(init.body as string) }));
    }
    if (url === '/api/quality/custom-rules/dry-run') {
      return Promise.resolve(jsonResp({
        sampled: 20,
        expert: { reject_hits: [{ item_id: 'x1', title: 'T', deduction: 50, reason: 'r' }], flag_hits: [] },
        semantic: { ran: 0, cap: 0, skipped: 20, hits: [], notes: [] },
      }));
    }
    if (url === '/api/quality/custom-rules') return Promise.resolve(mockRules(ONE_RULE));
    return Promise.resolve({ ok: false });
  });
});

describe('CustomRulesPanel — open 门控', () => {
  it('open=false 不拉取规则与 gates', async () => {
    render(<CustomRulesPanel open={false} />);
    await new Promise(r => setTimeout(r, 30));
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('CustomRulesPanel — 渲染与 CRUD', () => {
  it('加载后渲染专家/语义标签与匹配摘要', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/custom-rules/gates') return Promise.resolve(mockGates());
      if (url === '/api/quality/custom-rules') {
        return Promise.resolve(mockRules([
          ...ONE_RULE,
          { id: 9, name: '语义一条', rule_kind: 'semantic', match_kind: 'nl',
            match_value: '标题党', action: 'flag', deduction: 10,
            scope_category: 'ai', enabled: false },
        ]));
      }
      return Promise.resolve({ ok: false });
    });
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByText('黑名单词')).toBeInTheDocument());
    expect(screen.getByText(/AI语义/)).toBeInTheDocument();
    expect(screen.getByText(/语义: 标题党/)).toBeInTheDocument();
    expect(screen.getByText(/拒收\s*-50/)).toBeInTheDocument();
    expect(screen.getByText(/限 ai/)).toBeInTheDocument();
  });

  it('创建专家规则 → POST 透传 match_kind 与 action', async () => {
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByTestId('custom-rule-form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('规则名称'), { target: { value: '来源黑名单' } });
    fireEvent.change(screen.getByLabelText('匹配值'), { target: { value: 'spam_src' } });
    fireEvent.click(screen.getByRole('button', { name: '创建规则' }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const post = mockFetch.mock.calls.find(c => c[1]?.method === 'POST');
    expect(post).toBeTruthy();
    const body = JSON.parse(post![1].body);
    expect(body).toMatchObject({
      rule_kind: 'expert', match_kind: 'title_contains',
      match_value: 'spam_src', action: 'flag', deduction: 10,
    });
  });

  it('创建语义规则 → 强制 match_kind=nl + action=flag (语义层只软扣分)', async () => {
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByTestId('custom-rule-form')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('规则类型'), { target: { value: 'semantic' } });
    fireEvent.change(screen.getByLabelText('规则名称'), { target: { value: '夸张表述' } });
    fireEvent.change(screen.getByLabelText('匹配值'), { target: { value: '惊天秘密' } });
    fireEvent.click(screen.getByRole('button', { name: '创建规则' }));
    await waitFor(() => {
      const post = mockFetch.mock.calls.find(c => c[1]?.method === 'POST');
      expect(post).toBeTruthy();
      const body = JSON.parse(post![1].body);
      expect(body.match_kind).toBe('nl');
      expect(body.action).toBe('flag');
    });
  });

  it('空名称/匹配值 → 不发请求, 提示必填', async () => {
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByTestId('custom-rule-form')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '创建规则' }));
    expect(screen.getByText('名称与匹配值不能为空')).toBeInTheDocument();
    expect(mockFetch.mock.calls.filter(c => c[1]?.method === 'POST')).toHaveLength(0);
  });
});

describe('CustomRulesPanel — gate 开关与 dry-run', () => {
  it('gate 勾选切换 → PUT quality.gate.<name>.enabled', async () => {
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByLabelText('gate schema')).toBeChecked());
    fireEvent.click(screen.getByLabelText('gate schema'));
    await waitFor(() => {
      const put = mockFetch.mock.calls.find(
        c => c[0] === '/api/quality/rules' && c[1]?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(JSON.parse(put![1].body)).toEqual({
        rules: { 'quality.gate.schema.enabled': false },
      });
    });
  });

  it('dry-run 不勾语义 → with_semantic=false, 渲染命中数与原因', async () => {
    render(<CustomRulesPanel open />);
    await waitFor(() => expect(screen.getByRole('button', { name: '运行 dry-run' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '运行 dry-run' }));
    await waitFor(() => expect(screen.getByTestId('dry-run-result')).toBeInTheDocument());
    const post = mockFetch.mock.calls.find(c => c[0] === '/api/quality/custom-rules/dry-run');
    expect(JSON.parse(post![1].body)).toEqual({ limit: 20, with_semantic: false });
    expect(screen.getByTestId('dry-run-result')).toHaveTextContent('拒收命中 1');
  });
});
