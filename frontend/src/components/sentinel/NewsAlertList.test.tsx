/**
 * NewsAlertList — 资讯告警列表 (2026-09-27 四模式 P1)
 * 意图: 4 分类 tab + severity 色条 + reason 展示 + 已读/解决; 空态诚实。
 * 「漏洞/合规时限」同时在 tab 与条目标签出现 → 用 getAllByText 断言 ≥1 处。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NewsAlertList } from './NewsAlertList';

const ALERTS = {
  count: 2,
  items: [
    { id: 1, rule_type: 'critical_vuln', title: 'Chrome 0day 在野利用',
      description: '需排查 | 详见原文', severity: 'critical', source: 'FreeBuf',
      source_url: 'https://f.com/1', item_id: 'h1', status: 'unread',
      created_at: '2026-09-27T10:00:00' },
    { id: 2, rule_type: 'must_know_regulatory', title: '等保报送时限',
      description: '限时报送', severity: 'medium', source: '监管',
      source_url: null, item_id: null, status: 'unread',
      created_at: '2026-09-27T09:00:00' },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/alerts/v2/unread-count')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 2 }) } as Response);
    }
    if (url.startsWith('/api/alerts/v2')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(ALERTS) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('NewsAlertList — 资讯告警列表', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染告警条目与 severity 标识', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/Chrome 0day/)).toBeInTheDocument());
    expect(screen.getByText(/等保报送/)).toBeInTheDocument();
    expect(screen.getAllByText('漏洞').length).toBeGreaterThanOrEqual(1);   // tab + rule_type 标签
    expect(screen.getAllByText('合规时限').length).toBeGreaterThanOrEqual(1);
  });

  it('分类 tab 过滤: 点「漏洞」只看 critical_vuln', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => screen.getByText(/Chrome 0day/));
    fireEvent.click(screen.getByRole('tab', { name: /漏洞/ }));
    await waitFor(() => {
      const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .filter((c: unknown[]) => String(c[0]).includes('rule_type=critical_vuln'));
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('全部已读按钮触发 PUT', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => screen.getByText(/Chrome 0day/));
    fireEvent.click(screen.getByRole('button', { name: /全部已读/ }));
    await waitFor(() => {
      const puts = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .filter((c: unknown[]) => String((c[1] as RequestInit | undefined)?.method ?? '').toUpperCase() === 'PUT'
          && String(c[0]).includes('read-all'));
      expect(puts.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('空态诚实: 无告警时提示自动扫描', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/alerts/v2/unread-count')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 0 }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 0, items: [] }) } as Response);
    }));
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/当前无可执行告警/)).toBeInTheDocument());
  });
});
