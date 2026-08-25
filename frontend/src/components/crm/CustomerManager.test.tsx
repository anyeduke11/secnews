// CustomerManager.test.tsx — 客户管理组件测试 (v0.6 方案 C)
// 覆盖: 列表渲染、过滤参数透传、新建 POST、令牌头注入、删除确认
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CustomerManager } from './CustomerManager';

const MOCK_META = {
  stages: ['需求沟通', '方案提交', '商务谈判', '合同签订', '赢单', '输单'],
  levels: ['S', 'A', 'B', 'C'],
  statuses: ['活跃', '续约中', '停滞', '流失'],
  industries: ['网络安全服务'],
};

const MOCK_CUSTOMERS = [
  {
    id: 1, name: '盾山科技', industry: '网络安全服务', level: 'B', status: '活跃',
    region: '华东', owner: '', contact_name: '李四', contact_phone: '', email: '',
    contract_start_date: null, contract_end_date: null, contract_amount: 120000,
    nps_score: 9, notes: '', created_at: '2026-08-25T00:00:00Z', updated_at: '2026-08-25T00:00:00Z',
  },
];

function mockFetchRouter(postCalls: { url: string; opts: RequestInit }[] = []) {
  return vi.fn(async (url: any, opts?: any) => {
    const u = typeof url === 'string' ? url : url.url;
    const method = opts?.method || 'GET';
    if (method === 'GET' && u.startsWith('/api/crm/customers')) {
      return new Response(
        JSON.stringify({ items: MOCK_CUSTOMERS, total: MOCK_CUSTOMERS.length, limit: 200 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    postCalls.push({ url: u, opts });
    return new Response(JSON.stringify({ id: 2 }), { status: method === 'POST' ? 201 : 200, headers: { 'Content-Type': 'application/json' } });
  });
}

describe('CustomerManager', () => {
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
    window.confirm = vi.fn(() => true);
    store.clear();
  });

  it('renders customer rows with formatted amounts', async () => {
    global.fetch = mockFetchRouter();
    render(<CustomerManager meta={MOCK_META} />);
    expect(await screen.findByText('盾山科技')).toBeTruthy();
    expect(screen.getByText('¥120,000')).toBeTruthy();
  });

  it('passes filter params to list API', async () => {
    global.fetch = mockFetchRouter();
    render(<CustomerManager meta={MOCK_META} />);
    await screen.findByText('盾山科技');
    fireEvent.change(screen.getByLabelText('按状态过滤'), { target: { value: '流失' } });
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('status=%E6%B5%81%E5%A4%B1'),
        expect.anything(),
      );
    });
  });

  it('submits new customer via POST and injects X-CRM-Token from localStorage', async () => {
    localStorage.setItem('hotspot-crm-token', 'tok-123');
    const calls: { url: string; opts: RequestInit }[] = [];
    global.fetch = mockFetchRouter(calls);
    render(<CustomerManager meta={MOCK_META} />);
    await screen.findByText('盾山科技');

    fireEvent.click(screen.getByText('+ 新建客户'));
    fireEvent.change(screen.getByLabelText('客户名'), { target: { value: '新客户甲' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      const post = calls.find(c => c.opts.method === 'POST');
      expect(post).toBeTruthy();
      expect(post!.url).toBe('/api/crm/customers');
      expect(JSON.parse(post!.opts.body as string)).toEqual(expect.objectContaining({ name: '新客户甲' }));
      expect((post!.opts.headers as Record<string, string>)['X-CRM-Token']).toBe('tok-123');
    });
  });

  it('deletes after confirmation', async () => {
    const calls: { url: string; opts: RequestInit }[] = [];
    global.fetch = mockFetchRouter(calls);
    render(<CustomerManager meta={MOCK_META} />);
    await screen.findByText('盾山科技');

    fireEvent.click(screen.getByText('删除'));
    await waitFor(() => {
      const del = calls.find(c => c.opts.method === 'DELETE');
      expect(del?.url).toBe('/api/crm/customers/1');
    });
    expect(window.confirm).toHaveBeenCalled();
  });
});
