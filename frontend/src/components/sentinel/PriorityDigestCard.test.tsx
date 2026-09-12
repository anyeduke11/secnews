/**
 * PriorityDigestCard 组件测试 (Workbench Focus T0.5 收敛, DEV-0177)。
 *
 * 覆盖: 有画像按域分组 (interest 顺序在前 + other) / 无画像单组 /
 * fallback 空态 / 刷新按钮 force 请求。
 * i18n: 无 Provider 时 t() 回退 key 字符串 (仓库已知行为)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PriorityDigestCard } from './PriorityDigestCard';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function mockResponse(data: unknown) {
  mockFetch.mockImplementation(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(data) }),
  );
}

const BASE = {
  watchlist_changes: [],
  suggested_actions: [],
  generated_at: '2026-09-12T00:00:00Z',
  mode: 'dsh',
};

describe('PriorityDigestCard', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('有画像: 按兴趣域顺序分组 + other 兜底', async () => {
    mockResponse({
      ...BASE,
      top_items: [
        { title: 'CVE 漏洞复现', practice_domain: 'vuln_research' },
        { title: '等保测评要点', practice_domain: 'compliance' },
        { title: '某基金走势', practice_domain: null },
      ],
      interest_domains: ['vuln_research', 'compliance'],
      practice_partitions: {
        vuln_research: [{ title: 'CVE 漏洞复现', practice_domain: 'vuln_research' }],
        compliance: [{ title: '等保测评要点', practice_domain: 'compliance' }],
        other: [{ title: '某基金走势', practice_domain: null }],
      },
    });
    render(<PriorityDigestCard />);

    await waitFor(() => {
      expect(screen.getByText(/CVE 漏洞复现/)).toBeInTheDocument();
    });
    expect(screen.getByText('漏洞研究')).toBeInTheDocument();
    expect(screen.getByText('合规监管')).toBeInTheDocument();
    expect(screen.getByText('feed.priority.other')).toBeInTheDocument();
    expect(screen.getByText(/某基金走势/)).toBeInTheDocument();
  });

  it('无画像: 单组渲染 (practice_partitions null)', async () => {
    mockResponse({
      ...BASE,
      top_items: [{ title: '某条资讯', practice_domain: null }],
      interest_domains: [],
      practice_partitions: null,
    });
    render(<PriorityDigestCard />);

    await waitFor(() => {
      expect(screen.getByText('· 某条资讯')).toBeInTheDocument();
    });
    expect(screen.queryByText('feed.priority.other')).not.toBeInTheDocument();
  });

  it('空数据: 显示空态文案', async () => {
    mockResponse({ ...BASE, top_items: [], interest_domains: [], practice_partitions: null });
    render(<PriorityDigestCard />);

    await waitFor(() => {
      expect(screen.getByText('feed.priority.empty')).toBeInTheDocument();
    });
  });

  it('刷新按钮发 force 请求', async () => {
    mockResponse({ ...BASE, top_items: [], interest_domains: [], practice_partitions: null });
    render(<PriorityDigestCard />);
    await waitFor(() => {
      expect(screen.getByText('feed.priority.empty')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'feed.priority.refresh' }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenLastCalledWith('/api/digests/priority?force=true', expect.anything());
    });
  });
});
