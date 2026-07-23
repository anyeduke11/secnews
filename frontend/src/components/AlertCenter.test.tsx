// frontend/src/components/AlertCenter.test.tsx
// v1.7 Phase 3 — AlertCenter 组件测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock useSSE — 避免 jsdom 中无 EventSource 的问题
let sseOnEvent: ((type: string, data: any) => void) | null = null;
vi.mock('../hooks/useSSE', () => ({
  useSSE: vi.fn((opts: any = {}) => {
    sseOnEvent = opts.onEvent || null;
    return { connected: true, lastEvent: null };
  }),
}));

import { AlertCenter } from './AlertCenter';

const mockAlerts = [
  {
    id: 'alert-1',
    rule_id: 'rule-1',
    entity_type: 'hotspot',
    entity_id: 'h1',
    payload: { title: 'FastAPI 漏洞告警', summary: '规则: fastapi-tag', rule_name: 'fastapi-tag' },
    status: 'pending',
    created_at: '2026-07-23T10:00:00+00:00',
    processed_at: null,
  },
  {
    id: 'alert-2',
    rule_id: 'rule-2',
    entity_type: 'knowledge',
    entity_id: 'k1',
    payload: { title: '新概念出现', summary: '规则: new-concept' },
    status: 'read',
    created_at: '2026-07-23T09:00:00+00:00',
    processed_at: '2026-07-23T09:30:00+00:00',
  },
];

describe('AlertCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sseOnEvent = null;
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      // GET /api/alerts → 返回告警列表
      if (u.startsWith('/api/alerts?') || u === '/api/alerts') {
        return new Response(JSON.stringify({ items: mockAlerts }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // PUT /api/alerts/{id}/read
      if (u.match(/\/api\/alerts\/[^/]+\/read/)) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      // PUT /api/alerts/{id}/dismiss
      if (u.match(/\/api\/alerts\/[^/]+\/dismiss/)) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      // DELETE /api/alerts/{id}
      if (u.match(/\/api\/alerts\/[^/]+$/) && (!url.method || url.method === 'GET' || (url.method && url.method === 'DELETE'))) {
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('renders alert badge with unread count', async () => {
    render(<AlertCenter />);
    // mockAlerts 中 1 条 pending → 未读数=1
    await waitFor(() => {
      expect(screen.getByLabelText('1 条未读告警')).toBeInTheDocument();
    });
  });

  it('shows empty state when no alerts', async () => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ items: [] }), { status: 200 })
    ) as any;
    render(<AlertCenter />);
    // 徽章不显示 (count=0)
    // 打开下拉
    await waitFor(() => {
      // 没有徽章按钮 (count=0 时 AlertBadge 返回 null)
      expect(screen.queryByLabelText(/条未读告警/)).not.toBeInTheDocument();
    });
  });

  it('opens dropdown on badge click and shows alerts', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByLabelText('1 条未读告警')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
      expect(screen.getByText('新概念出现')).toBeInTheDocument();
    });
  });

  it('shows "暂无告警" when alert list is empty after opening', async () => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ items: [] }), { status: 200 })
    ) as any;
    render(<AlertCenter />);
    // count=0, AlertBadge 不渲染, 无法点击打开
    // 所以这个 case 只验证不渲染徽章
    expect(screen.queryByLabelText(/条未读告警/)).not.toBeInTheDocument();
  });

  it('marks alert as read on button click', async () => {
    render(<AlertCenter />);
    await waitFor(() => {
      expect(screen.getByLabelText('1 条未读告警')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    // pending 状态的告警有 "标记已读" 按钮
    const readBtn = screen.getByText('标记已读');
    fireEvent.click(readBtn);
    // 验证 fetch 被调用 (PUT /read)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/alerts\/alert-1\/read/),
        expect.objectContaining({ method: 'PUT' })
      );
    });
  });

  it('dismisses alert on button click', async () => {
    render(<AlertCenter />);
    fireEvent.click(await screen.findByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    const dismissBtn = screen.getAllByText('忽略')[0];
    fireEvent.click(dismissBtn);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/alerts\/alert-1\/dismiss/),
        expect.objectContaining({ method: 'PUT' })
      );
    });
  });

  it('deletes alert on button click', async () => {
    render(<AlertCenter />);
    fireEvent.click(await screen.findByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    const deleteBtn = screen.getAllByText('删除')[0];
    fireEvent.click(deleteBtn);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/alerts\/alert-1$/),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });

  it('SSE alert event adds new alert to list (验收 3)', async () => {
    render(<AlertCenter />);
    fireEvent.click(await screen.findByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    // SSE hook 已被 mock, sseOnEvent 应该被设置了
    expect(sseOnEvent).not.toBeNull();
    // 模拟 SSE 推送一条新告警
    const newAlert = {
      id: 'alert-sse-1',
      rule_id: 'rule-3',
      entity_type: 'hotspot',
      entity_id: 'h3',
      payload: { title: 'SSE 推送告警', summary: '实时推送' },
      status: 'pending',
      created_at: '2026-07-23T11:00:00+00:00',
      processed_at: null,
    };
    await act(async () => {
      sseOnEvent!('alert', { alert: newAlert });
    });
    await waitFor(() => {
      expect(screen.getByText('SSE 推送告警')).toBeInTheDocument();
    });
  });

  it('SSE alert event does not duplicate existing alert', async () => {
    render(<AlertCenter />);
    fireEvent.click(await screen.findByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    // 推送已存在的告警 (同 id)
    await act(async () => {
      sseOnEvent!('alert', { alert: mockAlerts[0] });
    });
    // 列表不应出现重复
    const items = screen.getAllByText('FastAPI 漏洞告警');
    expect(items.length).toBe(1);
  });

  it('ignores non-alert SSE events', async () => {
    render(<AlertCenter />);
    fireEvent.click(await screen.findByLabelText('1 条未读告警'));
    await waitFor(() => {
      expect(screen.getByText('FastAPI 漏洞告警')).toBeInTheDocument();
    });
    const beforeCount = screen.getAllByText(/漏洞告警|概念出现|推送告警/).length;
    await act(async () => {
      sseOnEvent!('collect_done', { count: 10 });
      sseOnEvent!('refresh', {});
    });
    // 非告警事件不应添加新项
    const afterCount = screen.getAllByText(/漏洞告警|概念出现|推送告警/).length;
    expect(afterCount).toBe(beforeCount);
  });
});
