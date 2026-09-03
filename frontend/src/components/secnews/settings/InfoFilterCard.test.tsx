/**
 * InfoFilterCard 测试 — v0.8 P1 独立资讯筛选门禁 V2 哨兵化。
 *
 * 覆盖 (6 用例):
 *  A. /api/info-filter/gate 返回 404 → 渲染禁用提示卡 (disabled_hint + fallback_pass)
 *  B. /api/info-filter/gate 返回 is_enabled=false → 同上
 *  C. gate on → 拉规则列表 → 显示规则 chips + 总数/已启用
 *  D. 创建规则: 选 deny + source_name + match_value → POST /rules → 显示成功消息
 *  E. 实时预览: POST /preview → verdict 显示在 st-chip 上
 *  F. 删除规则: 确认对话框 → DELETE /rules/{id} → 显示 deleted toast
 *
 * I18n: useI18n 在无 provider 时回退到 key 字符串, 因此断言用 i18n key 名。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { InfoFilterCard } from './InfoFilterCard';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function mockGateResp(isEnabled: boolean, status = 200) {
  return {
    ok: status === 200,
    status,
    json: () => Promise.resolve({
      extension: 'info_filter',
      is_enabled: isEnabled,
    }),
  };
}

function mockRulesResp(rules: Array<Record<string, unknown>> = []) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ rules, count: rules.length }),
  };
}

function mockPreviewResp(verdict: 'allow' | 'deny' | 'neutral', matched: object | null = null) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ verdict, matched_rule: matched }),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  // 默认 mock confirm 永远 true
  vi.spyOn(window, 'confirm').mockImplementation(() => true);
});

// ===================================================================
// A. gate 404 → 禁用提示
// ===================================================================

describe('InfoFilterCard — gate off (404 / is_enabled=false)', () => {
  it('/api/info-filter/gate 返回 404 → 显示 disabled_hint + fallback_pass, 不拉规则', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/info-filter/gate') {
        return Promise.resolve(mockGateResp(false, 404));
      }
      return Promise.resolve({ ok: false, status: 404 });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      // i18n key 回退: 显示原 key 字符串
      expect(screen.getByText('info_filter.disabled_hint')).toBeInTheDocument();
      expect(screen.getByText('info_filter.fallback_pass')).toBeInTheDocument();
      expect(screen.getByText('info_filter.title')).toBeInTheDocument();
    });

    // 不应再发 /rules 请求
    const rulesCalls = mockFetch.mock.calls.filter((c) => c[0] === '/api/info-filter/rules');
    expect(rulesCalls.length).toBe(0);
  });

  it('/api/info-filter/gate 返回 is_enabled=false → 同样渲染禁用提示', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(false));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.disabled_hint')).toBeInTheDocument();
    });
    const rulesCalls = mockFetch.mock.calls.filter((c) => c[0] === '/api/info-filter/rules');
    expect(rulesCalls.length).toBe(0);
  });
});

// ===================================================================
// C. gate on → 规则列表
// ===================================================================

describe('InfoFilterCard — gate on, 规则列表', () => {
  it('加载 2 条规则 → 显示总数/已启用 + 每条 chip', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules') {
        return Promise.resolve(mockRulesResp([
          {
            id: 1, rule_type: 'deny', match_kind: 'source_name', match_value: '澎湃新闻',
            enabled: 1, note: '噪音太大', created_at: '', updated_at: '',
          },
          {
            id: 2, rule_type: 'allow', match_kind: 'category', match_value: 'tech',
            enabled: 0, note: '', created_at: '', updated_at: '',
          },
        ]));
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      // 总数 2, 已启用 1
      expect(screen.getByText('info_filter.rules_count')).toBeInTheDocument();
      expect(screen.getByText('info_filter.enabled_count')).toBeInTheDocument();
    });

    // 规则内容
    expect(screen.getByText('澎湃新闻')).toBeInTheDocument();
    expect(screen.getByText('tech')).toBeInTheDocument();
    // note "噪音太大" 被 "—" 分隔, 用 getAllByText (允许多元素)
    expect(screen.getAllByText(/噪音太大/).length).toBeGreaterThanOrEqual(1);
    // chip 文本 — 选第一个 (新建表单的 select option + 规则 chip)
    expect(screen.getAllByText('deny').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('allow').length).toBeGreaterThanOrEqual(1);
  });

  it('空规则 → 显示 info_filter.no_rules', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules') return Promise.resolve(mockRulesResp([]));
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.no_rules')).toBeInTheDocument();
    });
  });
});

// ===================================================================
// D. 创建规则
// ===================================================================

describe('InfoFilterCard — 创建规则', () => {
  it('填入 match_value → POST /rules → 显示 created toast', async () => {
    const postCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules' && (!init || init.method === 'GET' || init.method === undefined)) {
        return Promise.resolve(mockRulesResp([]));
      }
      if (url === '/api/info-filter/rules' && init?.method === 'POST') {
        postCalls.push(JSON.parse(init.body as string));
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ id: 99, rule_type: 'deny', match_kind: 'source_name', match_value: '测试源' }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.add_rule')).toBeInTheDocument();
    });

    // 找到 match_value input (placeholder 在无 provider 时回退为 i18n key)
    const valueInput = screen.getByPlaceholderText('info_filter.match_value_placeholder');
    fireEvent.change(valueInput, { target: { value: '测试源' } });

    const addBtn = screen.getByRole('button', { name: 'info_filter.add' });
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(postCalls.length).toBe(1);
      const body = postCalls[0] as Record<string, unknown>;
      expect(body.rule_type).toBe('deny');
      expect(body.match_kind).toBe('source_name');
      expect(body.match_value).toBe('测试源');
    });

    // 成功 toast
    await waitFor(() => {
      expect(screen.getByText('info_filter.created')).toBeInTheDocument();
    });
  });

  it('match_value 为空 → 按钮 disabled', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules') return Promise.resolve(mockRulesResp([]));
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.add_rule')).toBeInTheDocument();
    });

    const addBtn = screen.getByRole('button', { name: 'info_filter.add' });
    expect((addBtn as HTMLButtonElement).disabled).toBe(true);
  });
});

// ===================================================================
// E. 实时预览
// ===================================================================

describe('InfoFilterCard — 实时预览', () => {
  it('点预览 → POST /preview → verdict 显示', async () => {
    const previewCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules') return Promise.resolve(mockRulesResp([]));
      if (url === '/api/info-filter/preview' && init?.method === 'POST') {
        previewCalls.push(JSON.parse(init.body as string));
        return Promise.resolve(mockPreviewResp('deny', {
          id: 1, rule_type: 'deny', match_kind: 'source_name', match_value: '华尔街见闻',
        }));
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.preview')).toBeInTheDocument();
    });

    // preview form 默认 source_name="华尔街见闻"
    const previewBtn = screen.getByRole('button', { name: 'info_filter.preview_run' });
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(previewCalls.length).toBe(1);
      const body = previewCalls[0] as Record<string, unknown>;
      expect(body.category).toBeTruthy();
      expect(body.source_name).toBe('华尔街见闻');
    });

    // verdict chip 显示 — chip 文本是 "info_filter.verdict: deny" 拼接 (无元素分隔)
    await waitFor(() => {
      // 用 getAllByText + regex 兼容拼接文本
      const matches = screen.getAllByText(/info_filter\.verdict/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(matches.some(el => el.textContent?.includes('deny'))).toBe(true);
    });
  });

  it('verdict=neutral (无匹配规则) → 显示 neutral chip', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules') return Promise.resolve(mockRulesResp([]));
      if (url === '/api/info-filter/preview' && init?.method === 'POST') {
        return Promise.resolve(mockPreviewResp('neutral', null));
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('info_filter.preview')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'info_filter.preview_run' }));

    await waitFor(() => {
      const matches = screen.getAllByText(/info_filter\.verdict/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(matches.some(el => el.textContent?.includes('neutral'))).toBe(true);
    });
  });
});

// ===================================================================
// F. 删除规则
// ===================================================================

describe('InfoFilterCard — 删除规则', () => {
  it('点删除 → 确认 → DELETE /rules/{id}', async () => {
    const deleteCalls: string[] = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules' && (!init || init.method === undefined || init.method === 'GET')) {
        return Promise.resolve(mockRulesResp([
          {
            id: 42, rule_type: 'deny', match_kind: 'source_name', match_value: '噪音源',
            enabled: 1, note: '', created_at: '', updated_at: '',
          },
        ]));
      }
      if (url === '/api/info-filter/rules/42' && init?.method === 'DELETE') {
        deleteCalls.push(url);
        return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('噪音源')).toBeInTheDocument();
    });

    const delBtn = screen.getByRole('button', { name: 'info_filter.delete' });
    fireEvent.click(delBtn);

    await waitFor(() => {
      expect(deleteCalls.length).toBe(1);
      expect(deleteCalls[0]).toBe('/api/info-filter/rules/42');
    });

    await waitFor(() => {
      expect(screen.getByText('info_filter.deleted')).toBeInTheDocument();
    });
  });
});

// ===================================================================
// G. 启停规则 (toggle)
// ===================================================================

describe('InfoFilterCard — 启停规则 (toggle)', () => {
  it('点停用 → PATCH /rules/{id} 带 enabled=0', async () => {
    const patchCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/info-filter/gate') return Promise.resolve(mockGateResp(true));
      if (url === '/api/info-filter/rules' && (!init || init.method === undefined)) {
        return Promise.resolve(mockRulesResp([
          {
            id: 7, rule_type: 'allow', match_kind: 'category', match_value: 'finance',
            enabled: 1, note: '', created_at: '', updated_at: '',
          },
        ]));
      }
      if (url === '/api/info-filter/rules/7' && init?.method === 'PATCH') {
        patchCalls.push(JSON.parse(init.body as string));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 7, enabled: 0 }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<InfoFilterCard />);

    await waitFor(() => {
      expect(screen.getByText('finance')).toBeInTheDocument();
    });

    const disableBtn = screen.getByRole('button', { name: 'info_filter.disable' });
    fireEvent.click(disableBtn);

    await waitFor(() => {
      expect(patchCalls.length).toBe(1);
      const body = patchCalls[0] as Record<string, unknown>;
      expect(body.enabled).toBe(0);
    });
  });
});