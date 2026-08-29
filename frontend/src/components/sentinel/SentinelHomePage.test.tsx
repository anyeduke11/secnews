/**
 * SentinelHomePage — 哨兵终端首页测试
 *
 * 测试意图 (Rule 9):
 * - 首页骨架契约: 品牌/管道心跳/四态阅读模式/频道 chips 必须常驻 (设计稿结构)
 * - 真实数据驱动: 头条与快讯来自 /api/hotspots; 管道统计来自 /api/sources/health
 *   (避免首页退化为静态示意稿)
 * - 频道切换 → 重新以对应 category 拉取
 * - 空数据 → 空态面板 (含手动采集入口), 不白屏
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock EventSource (useSSE 依赖)
class MockEventSource {
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  close() {}
}

const HOTSPOT_FIXTURE = {
  version: 'test',
  total: 5,
  time_range: '1d',
  category: 'all',
  keyword: '',
  items: [
    { id: 'h1', title: '企业自建大模型网关曝出未授权访问风险', summary: 'RAG 应用直接挂在内网索引上。', source: 'The Hacker News', url: 'https://example.com/1', category: 'ai_security', published_at: new Date().toISOString(), score: 88 },
    { id: 'h2', title: '次级重点条目一', summary: '', source: 'FreeBuf', url: 'https://example.com/2', category: 'security', published_at: new Date().toISOString(), score: 70 },
    { id: 'h3', title: '次级重点条目二', summary: '', source: '奇安信威胁情报', url: 'https://example.com/2b', category: 'security', published_at: new Date().toISOString(), score: 66 },
    { id: 'h4', title: '广泛使用的 PDF 解析库存在内存越界缺陷', summary: '影响范围初判覆盖 2.x 全系版本。', source: 'BleepingComputer', url: 'https://example.com/4', category: 'security', published_at: new Date().toISOString(), score: 95 },
    { id: 'h5', title: '常规快讯条目', summary: '', source: 'HN', url: 'https://example.com/5', category: 'tech', published_at: new Date().toISOString(), score: 55 },
  ],
  next_cursor: null,
  category_counts: {},
  fetched_at: new Date().toISOString(),
  latest_ingestion_count: 12,
  latest_ingestion_at: new Date().toISOString(),
};

const SOURCES_FIXTURE = {
  version: 'test',
  sources: [
    { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: new Date().toISOString() },
    { category: 'security', source_name: 'Krebs', status: 'stale', total_items: 30, last_seen_at: new Date().toISOString() },
    { category: 'tech', source_name: 'HN', status: 'active', total_items: 200, last_seen_at: new Date().toISOString() },
  ],
  summary: { total: 3, active_count: 2, stale_count: 1, dead_count: 0 },
};

function mockFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/hotspots')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(HOTSPOT_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/sources/health')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SOURCES_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/quality/summary')) {
      // 真实结构: {summary: {gate: {pass, total, avg_deduction}}}
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ summary: {
        SchemaGate: { pass: 40, total: 40, avg_deduction: 0 },
        AuthorVerification: { pass: 30, total: 40, avg_deduction: 0.65 },
      } }) } as Response);
    }
    if (url.startsWith('/api/todos')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

import { SentinelHomePage } from './SentinelHomePage';

describe('SentinelHomePage — 哨兵终端首页', () => {
  let fetchMock: ReturnType<typeof mockFetch>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as any).EventSource = MockEventSource;
    try { localStorage.removeItem('hotspot-theme'); } catch {}
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as any).EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('渲染哨兵骨架: 品牌 + 管道心跳 + 四态模式 + 频道 chips', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);

    // 品牌
    expect(screen.getByText('SecNews')).toBeInTheDocument();
    // PIPELINE LIVE 心跳
    expect(screen.getByText('PIPELINE LIVE')).toBeInTheDocument();
    // 四态阅读模式
    for (const label of ['简报', '扫描', '深度', '告警']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    // 频道 chips
    expect(screen.getByRole('button', { name: /全部/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /网络安全/ })).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('实时快讯')).toBeInTheDocument());
  });

  it('真实数据驱动: 头条来自 /api/hotspots, 管道统计来自 /api/sources/health', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);

    // 头条标题 (综合第一位, 不因告警抽取而降位)
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('企业自建大模型网关曝出未授权访问风险');
    });
    // 管道统计: 源在线 2/3, 今日收录 5 篇
    await waitFor(() => {
      expect(screen.getByText('5 篇')).toBeInTheDocument();
    });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    // 快讯计数
    expect(screen.getByText(/TODAY 5 ITEMS/)).toBeInTheDocument();
  });

  it('快讯池中安全类最高分条目渲染为可展开高危告警', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);

    await waitFor(() => {
      expect(screen.getByText('广泛使用的 PDF 解析库存在内存越界缺陷')).toBeInTheDocument();
    });
    // 默认收起, 点击展开
    const alertItem = screen.getByText('高危').closest('.alert-item')!;
    expect(alertItem).not.toHaveClass('open');
    fireEvent.click(alertItem);
    expect(alertItem).toHaveClass('open');
  });

  it('频道切换 → 以对应 category 重新拉取', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /网络安全/ }));
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(c => String(c[0]));
      expect(calls.some(c => c.includes('/api/hotspots') && c.includes('category=security'))).toBe(true);
    });
  });

  it('阅读模式四态切换 (data-mode 属性驱动版面密度)', async () => {
    const { container } = render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    // jsdom 不计算 CSS, 断言 data-mode 属性契约 (sentinel.css 按该属性切换版面)
    const root = container.querySelector('.sentinel')!;
    expect(root).toHaveAttribute('data-mode', 'brief');
    fireEvent.click(screen.getByRole('button', { name: '扫描' }));
    expect(root).toHaveAttribute('data-mode', 'scan');
    fireEvent.click(screen.getByRole('button', { name: '告警' }));
    expect(root).toHaveAttribute('data-mode', 'alert');
    fireEvent.click(screen.getByRole('button', { name: '深度' }));
    expect(root).toHaveAttribute('data-mode', 'deep');
  });

  it('空数据 → 空态面板, 不白屏', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ...HOTSPOT_FIXTURE, items: [], total: 0 }),
    } as Response)));

    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => {
      expect(screen.getByText('今日频道暂无收录')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /立即采集/ })).toBeInTheDocument();
  });
});
