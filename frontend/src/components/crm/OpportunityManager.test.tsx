// OpportunityManager.test.tsx — 商机推进组件测试 (v0.6 方案 C)
// 覆盖: 列表 + 客户名联表、阶段推进按钮 (STAGE_FLOW 镜像)、输单原因必填、终态无按钮
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OpportunityManager } from './OpportunityManager';

const MOCK_META = {
  stages: ['需求沟通', '方案提交', '商务谈判', '合同签订', '赢单', '输单'],
  levels: ['S', 'A', 'B', 'C'],
  statuses: ['活跃', '续约中', '停滞', '流失'],
  industries: [],
};

const CUSTOMERS = [
  { id: 1, name: '盾山科技' } as any,
];

function opp(over: Partial<any> = {}) {
  return {
    id: 10, customer_id: 1, name: '等保测评', service_type: '安全评估',
    stage: '需求沟通', amount: 100000, cost: 30000, owner: '',
    expected_close_date: null, description: '', won_at: null, lost_reason: '',
    created_at: '', updated_at: '', ...over,
  };
}

const OPPS = [
  opp(),
  opp({ id: 11, name: '已赢单', stage: '赢单', won_at: '2026-08-01T00:00:00Z' }),
  opp({ id: 12, name: '已输单', stage: '输单', lost_reason: '预算砍掉' }),
];

function mockFetchRouter(calls: { url: string; opts: RequestInit }[] = []) {
  return vi.fn(async (url: any, opts?: any) => {
    const u = typeof url === 'string' ? url : url.url;
    const method = opts?.method || 'GET';
    if (method === 'GET' && u.startsWith('/api/crm/opportunities')) {
      return new Response(JSON.stringify({ items: OPPS, total: OPPS.length, limit: 200 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (method === 'GET' && u.startsWith('/api/crm/customers')) {
      return new Response(JSON.stringify({ items: CUSTOMERS, total: 1, limit: 500 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    calls.push({ url: u, opts });
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
}

describe('OpportunityManager', () => {
  // 环境无原生 localStorage (同 App.test.tsx 处理), 用内存 stub
  const store = new Map<string, string>();
  beforeAll(() => {
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => void store.clear(),
    });
  });
  beforeEach(() => {
    vi.clearAllMocks();
    window.prompt = vi.fn(() => '价格过高');
    store.clear();
  });

  it('renders opportunities with joined customer names and stage badges', async () => {
    global.fetch = mockFetchRouter();
    render(<OpportunityManager meta={MOCK_META} />);
    expect(await screen.findByText('等保测评')).toBeTruthy();
    // 三条商机同属客户 #1, 客户名联表渲染 3 处
    expect(screen.getAllByText('盾山科技').length).toBe(3);
    expect(screen.getByText('预算砍掉')).toBeTruthy(); // 输单原因截断展示
  });

  it('advances stage via /transition endpoint only', async () => {
    const calls: { url: string; opts: RequestInit }[] = [];
    global.fetch = mockFetchRouter(calls);
    render(<OpportunityManager meta={MOCK_META} />);
    await screen.findByText('等保测评');

    fireEvent.click(screen.getByText('→ 方案提交'));
    await waitFor(() => {
      const post = calls.find(c => c.opts.method === 'POST');
      expect(post?.url).toBe('/api/crm/opportunities/10/transition');
      expect(JSON.parse(post!.opts.body as string)).toEqual(
        expect.objectContaining({ to_stage: '方案提交' }),
      );
    });
  });

  it('requires lost reason before marking 输单', async () => {
    const calls: { url: string; opts: RequestInit }[] = [];
    global.fetch = mockFetchRouter(calls);
    render(<OpportunityManager meta={MOCK_META} />);
    await screen.findByText('等保测评');

    // prompt 返回空 → 不发起推进
    (window.prompt as any).mockReturnValueOnce('');
    fireEvent.click(screen.getByText('标记输单'));
    expect(calls.find(c => c.opts.method === 'POST')).toBeUndefined();

    // prompt 有原因 → 推进携带 lost_reason
    fireEvent.click(screen.getByText('标记输单'));
    await waitFor(() => {
      const post = calls.find(c => c.opts.method === 'POST');
      expect(JSON.parse(post!.opts.body as string)).toEqual(
        expect.objectContaining({ to_stage: '输单', lost_reason: '价格过高' }),
      );
    });
  });

  it('offers no transition buttons for terminal stages', async () => {
    global.fetch = mockFetchRouter();
    render(<OpportunityManager meta={MOCK_META} />);
    await screen.findByText('已赢单');
    expect(screen.getAllByText('已终态').length).toBe(2); // 赢单 + 输单
    // 全表仅「需求沟通」行有推进按钮 (→ 方案提交 / 标记输单 各一个)
    expect(screen.getAllByText('标记输单').length).toBe(1);
    expect(screen.getByText('→ 方案提交')).toBeTruthy();
  });

  it('creates opportunity via POST with numeric customer_id', async () => {
    const calls: { url: string; opts: RequestInit }[] = [];
    global.fetch = mockFetchRouter(calls);
    render(<OpportunityManager meta={MOCK_META} />);
    await screen.findByText('等保测评');

    fireEvent.click(screen.getByText('+ 新建商机'));
    fireEvent.change(screen.getByLabelText('所属客户'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('商机名'), { target: { value: '新商机' } });
    fireEvent.change(screen.getByLabelText('金额'), { target: { value: '50000' } });
    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => {
      const post = calls.find(c => c.opts.method === 'POST');
      expect(post?.url).toBe('/api/crm/opportunities');
      expect(JSON.parse(post!.opts.body as string)).toEqual(
        expect.objectContaining({ customer_id: 1, name: '新商机', amount: 50000 }),
      );
    });
  });
});
