// AlertCenter.test.tsx — Phase 12 告警中心组件测试
// 覆盖 v2 AlertCenter 组件：列表渲染、未读计数、标记已读/解决、手动评估
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import AlertCenter from './AlertCenter';

const API_BASE = '/api/alerts/v2';

const mockAlerts = [
  {
    id: 1,
    rule_type: 'tech_stack_cve',
    title: 'FastAPI CVE-2024-1234 漏洞',
    description: 'CVE-2024-1234 命中项目 tech_stack',
    severity: 'high',
    source: 'CVE-2024-1234',
    source_url: 'https://example.com/cve-1234',
    status: 'unread',
    created_at: '2026-07-31T10:00:00+00:00',
  },
  {
    id: 2,
    rule_type: 'critical_cve',
    title: 'CVE-2024-9999 严重漏洞',
    description: 'CVSS 9.5 关键 CVE',
    severity: 'critical',
    source: 'CVE-2024-9999',
    source_url: 'https://example.com/cve-9999',
    status: 'read',
    created_at: '2026-07-31T09:00:00+00:00',
  },
  {
    id: 3,
    rule_type: 'bid_match',
    title: 'FastAPI 框架招标公告',
    description: '标讯命中项目 tech_stack',
    severity: 'medium',
    source: 'bid-source',
    source_url: null,
    status: 'unread',
    created_at: '2026-07-31T08:00:00+00:00',
  },
];

describe('AlertCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any, _opts?: any) => {
      const u = typeof url === 'string' ? url : url.url;

      // GET /api/alerts/v2 — 告警列表
      if (u.startsWith(`${API_BASE}?`) || u === API_BASE) {
        return new Response(
          JSON.stringify({ count: mockAlerts.length, items: mockAlerts }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      // GET /api/alerts/v2/unread-count
      if (u.startsWith(`${API_BASE}/unread-count`)) {
        const unread = mockAlerts.filter(a => a.status === 'unread').length;
        return new Response(
          JSON.stringify({ count: unread }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      // PUT /api/alerts/v2/{id}/read
      if (u.match(new RegExp(`${API_BASE}/\\d+/read`))) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      // PUT /api/alerts/v2/{id}/resolve
      if (u.match(new RegExp(`${API_BASE}/\\d+/resolve`))) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      // PUT /api/alerts/v2/read-all
      if (u === `${API_BASE}/read-all`) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      // POST /api/alerts/v2/evaluate
      if (u === `${API_BASE}/evaluate`) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('renders alert center title', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('告警中心')).toBeInTheDocument();
    });
  });

  it('shows unread count badge', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('2 条未读告警')).toBeInTheDocument();
    });
  });

  it('renders alert list items', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('FastAPI CVE-2024-1234 漏洞')).toBeInTheDocument();
      expect(screen.getByText('CVE-2024-9999 严重漏洞')).toBeInTheDocument();
    });
  });

  it('shows empty state when no alerts', async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ count: 0, items: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as any;
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('暂无告警')).toBeInTheDocument();
    });
  });

  it('marks alert as read on button click', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('FastAPI CVE-2024-1234 漏洞')).toBeInTheDocument();
    });
    const readBtn = screen.getAllByTitle('标记已读')[0];
    fireEvent.click(readBtn);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE}/1/read`,
        expect.objectContaining({ method: 'PUT' }),
      );
    });
  });

  it('resolves alert on button click', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('FastAPI CVE-2024-1234 漏洞')).toBeInTheDocument();
    });
    const resolveBtn = screen.getAllByText('解决')[0];
    fireEvent.click(resolveBtn);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE}/1/resolve`,
        expect.objectContaining({ method: 'PUT' }),
      );
    });
  });

  it('marks all alerts as read', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('全部已读')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('全部已读'));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE}/read-all`,
        expect.objectContaining({ method: 'PUT' }),
      );
    });
  });

  it('triggers rule evaluation on button click', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('评估规则')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('评估规则'));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE}/evaluate`,
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('filters alerts by status', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByText('未读')).toBeInTheDocument();
    });
    // 点击筛选栏中的"未读"按钮
    const filterButtons = screen.getAllByRole('button').filter(b => b.textContent === '未读');
    fireEvent.click(filterButtons[0]);
    // 筛选后组件应重新加载数据
    await waitFor(() => {
      // 验证 fetch 至少被调用过（含带 status 参数的 URL）
      const calls = (global.fetch as any).mock.calls.filter((c: any[]) =>
        typeof c[0] === 'string' && c[0].includes('status=unread')
      );
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows severity colors', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      const criticalBadge = screen.getByText('严重');
      expect(criticalBadge).toBeInTheDocument();
      const highBadge = screen.getByText('高');
      expect(highBadge).toBeInTheDocument();
    });
  });
});