/**
 * SentinelHomePage — 哨兵终端首页测试
 *
 * 测试意图 (Rule 9):
 * - 首页骨架契约: 品牌/管道心跳/四态阅读模式/频道 chips 必须常驻 (设计稿结构)
 * - 真实数据驱动: 头条与快讯来自 /api/hotspots; 管道统计来自 /api/sources/health
 *   (避免首页退化为静态示意稿)
 * - 频道切换 → 重新以对应 category 拉取
 * - 报纸版移植的四项能力: 全文搜索 keyword / 时间窗 time_range / cursor 分页 / 收藏加星
 * - 空数据 → 空态面板 (含手动采集入口), 不白屏
 *
 * 全部网络请求由 mock fetch 承接 (含 /api/favorites), 测试内不发真实请求。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock EventSource (useSSE 依赖)
class MockEventSource {
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  close() {}
}

const nowIso = () => new Date().toISOString();

/** fetch mock 接受的响应体形状 (next_cursor 可为 cursor 字符串或 null) */
interface FixtureBody {
  version: string;
  total: number;
  time_range: string;
  category: string;
  keyword: string;
  items: {
    id: string; title: string; summary: string; source: string;
    url: string; category: string; published_at: string; score: number;
  }[];
  next_cursor: string | null;
  category_counts: Record<string, number>;
  fetched_at: string;
  latest_ingestion_count: number;
  latest_ingestion_at: string;
}

const HOTSPOT_FIXTURE: FixtureBody = {
  version: 'test',
  total: 5,
  time_range: '24h',
  category: 'all',
  keyword: '',
  items: [
    { id: 'h1', title: '企业自建大模型网关曝出未授权访问风险', summary: 'RAG 应用直接挂在内网索引上。', source: 'The Hacker News', url: 'https://example.com/1', category: 'ai_security', published_at: nowIso(), score: 88 },
    { id: 'h2', title: '次级重点条目一', summary: '', source: 'FreeBuf', url: 'https://example.com/2', category: 'security', published_at: nowIso(), score: 70 },
    { id: 'h3', title: '次级重点条目二', summary: '', source: '奇安信威胁情报', url: 'https://example.com/2b', category: 'security', published_at: nowIso(), score: 66 },
    { id: 'h4', title: '广泛使用的 PDF 解析库存在内存越界缺陷', summary: '影响范围初判覆盖 2.x 全系版本。', source: 'BleepingComputer', url: 'https://example.com/4', category: 'security', published_at: nowIso(), score: 95 },
    { id: 'h5', title: '常规快讯条目', summary: '', source: 'HN', url: 'https://example.com/5', category: 'tech', published_at: nowIso(), score: 55 },
  ],
  // 默认无 next_cursor → 单页; 分页用例用 PAGING_FIXTURE 覆盖
  next_cursor: null,
  category_counts: { security: 3, tech: 1 },
  fetched_at: nowIso(),
  latest_ingestion_count: 12,
  latest_ingestion_at: nowIso(),
};

/** 游标分页专用: total > pageSize(100) → totalPages=2 且首屏带 next_cursor */
const PAGING_FIXTURE: FixtureBody = { ...HOTSPOT_FIXTURE, total: 140, next_cursor: 'CURSOR_PAGE_1' };

const SOURCES_FIXTURE = {
  version: 'test',
  sources: [
    { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: nowIso() },
    { category: 'security', source_name: 'Krebs', status: 'stale', total_items: 30, last_seen_at: nowIso() },
    { category: 'tech', source_name: 'HN', status: 'active', total_items: 200, last_seen_at: nowIso() },
  ],
  summary: { total: 3, active_count: 2, stale_count: 1, dead_count: 0 },
};

/** fetch 调用记录 (url + init) */
type FetchCall = [RequestInfo | URL, RequestInit | undefined];

function mockFetch(hotspotBody: FixtureBody = HOTSPOT_FIXTURE) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.startsWith('/api/hotspots')) {
      // 第 2 页起返回不同条目, 用于验证 cursor 翻页真的换了数据集
      const hasCursor = url.includes('cursor=');
      const body: FixtureBody = hasCursor
        ? { ...hotspotBody, items: hotspotBody.items.map(i => ({ ...i, id: `${i.id}-p2`, title: `第二页 ${i.title}` })), next_cursor: null }
        : hotspotBody;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    }
    if (url === '/api/favorites' && method === 'POST') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok', created: true, item: {} }) } as Response);
    }
    if (url.startsWith('/api/favorites/') && method === 'DELETE') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok', hotspot_id: 'x', removed: true }) } as Response);
    }
    if (url.startsWith('/api/favorites')) {
      // GET /api/favorites?limit=1000 — 初始为空收藏
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 0, items: [] }) } as Response);
    }
    if (url.startsWith('/api/kl/pipeline/stats')) {
      // 真实返回口径 (实测 2026-08-29): funnel + queue 三态
      return Promise.resolve({ ok: true, json: () => Promise.resolve({
        funnel: [
          { stage: 'kl:raw', count: 175 }, { stage: 'kl:refine', count: 0 },
          { stage: 'kl:link', count: 2 }, { stage: 'kl:structure', count: 0 },
          { stage: 'kl:publish', count: 3973 },
        ],
        queue: { pending: 0, running: 0, error: 2 },
      }) } as Response);
    }
    if (url.startsWith('/api/kl/import/url') && method === 'POST') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({
        id: 'imported-abc123', title: 'x', url: 'https://example.com/a',
      }) } as Response);
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
import { resetFavoritesStore } from '../../hooks/useFavorites';

const hotspotCalls = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.startsWith('/api/hotspots'));

/** 指定端点 (精确匹配) + method 的调用记录 */
function callsWith(fetchMock: ReturnType<typeof mockFetch>, path: string, method: string): FetchCall[] {
  return (fetchMock.mock.calls as FetchCall[]).filter(
    c => c[0] === path && ((c[1]?.method ?? 'GET').toUpperCase() === method),
  );
}

describe('SentinelHomePage — 哨兵终端首页', () => {
  let fetchMock: ReturnType<typeof mockFetch>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as any).EventSource = MockEventSource;
    try { localStorage.removeItem('hotspot-theme'); } catch {}
    // useFavorites 是模块级单例 store — 每个用例前重置, 避免跨用例串状态
    resetFavoritesStore();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as any).EventSource = originalEventSource;
    resetFavoritesStore();
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
    expect(screen.getByRole('button', { name: /^全部/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^网络安全/ })).toBeInTheDocument();

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
    // 快讯计数 (hook 的 items.length + 页码口径)
    expect(screen.getByText(/PAGE 1 · 5 ITEMS/)).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('button', { name: /^网络安全/ }));
    await waitFor(() => {
      expect(hotspotCalls(fetchMock).some(c => c.includes('category=security'))).toBe(true);
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
      expect(screen.getByText('该范围暂无收录')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /立即采集/ })).toBeInTheDocument();
  });

  // ===== 报纸版能力移植 =====

  it('全文搜索: 输入关键词 → 防抖后以 keyword 重新拉取', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    // 首次拉取不带 keyword
    expect(hotspotCalls(fetchMock)[0]).not.toContain('keyword=');

    fireEvent.change(screen.getByLabelText('搜索热点关键词'), { target: { value: '勒索' } });

    await waitFor(() => {
      expect(hotspotCalls(fetchMock).some(c => c.includes(`keyword=${encodeURIComponent('勒索')}`))).toBe(true);
    });
  });

  it('时间范围切换: 仅 24h/3d/本周(7d)/30d 四值, 点击后 time_range 参数变化', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    // 默认 24h; 后端 TimeRange 枚举不含 1d
    expect(hotspotCalls(fetchMock)[0]).toContain('time_range=24h');
    const group = screen.getByRole('group', { name: '时间范围' });
    const chips = Array.from(group.querySelectorAll('button'));
    const byLabel = (label: string) => chips.find(b => b.textContent?.trim() === label)!;
    expect(chips.map(b => b.textContent?.trim())).toEqual(['24H', '3D', '本周', '30D']);
    expect(group).not.toHaveTextContent('1d');
    // 复用哨兵 .chip 外形 (与频道 chips 同一视觉语言)
    chips.forEach(b => expect(b.className).toContain('chip'));

    // 7d 语义如实标注为「本周周一 00:00 起」而非滚动 7 天
    expect(byLabel('本周')!.getAttribute('title')).toMatch(/本周周一 00:00 起算, 不是滚动 7 天/);
    expect(byLabel('24H')).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(byLabel('30D'));
    await waitFor(() => {
      expect(hotspotCalls(fetchMock).some(c => c.includes('time_range=30d'))).toBe(true);
    });
  });

  it('游标分页: 点下一页 → 带上上一页的 cursor 且页码推进', async () => {
    vi.stubGlobal('fetch', mockFetch(PAGING_FIXTURE));
    fetchMock = globalThis.fetch as unknown as ReturnType<typeof mockFetch>;
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const next = screen.getByRole('button', { name: '下一页' });
    const prev = screen.getByRole('button', { name: '上一页' });
    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();

    fireEvent.click(next);

    await waitFor(() => {
      expect(hotspotCalls(fetchMock).some(c => c.includes('cursor=CURSOR_PAGE_1'))).toBe(true);
    });
    // 第 2 页无 next_cursor → 下一页禁用, 页码指示器推进
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
    });
    const indicator = document.querySelector('.page-indicator')!.textContent!.replace(/\s+/g, ' ');
    expect(indicator).toBe('第 2 / 2 页 · 共 140 篇');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled();
    });
    // 第 2 页整份数据集换成 -p2 条目 → 至少一条渲染出对应加星按钮
    expect(screen.getAllByRole('button', { name: /^收藏：第二页/ }).length).toBeGreaterThan(0);
  });

  it('收藏加星: 点星标 → POST /api/favorites; 再点 → DELETE /api/favorites/{id}', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const starBtn = screen.getByRole('button', { name: `收藏：${HOTSPOT_FIXTURE.items[4].title}` });
    expect(starBtn).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(starBtn);

    await waitFor(() => {
      const post = callsWith(fetchMock, '/api/favorites', 'POST')[0];
      expect(post).toBeTruthy();
      expect(JSON.parse(String(post[1]!.body))).toMatchObject({
        hotspot_id: 'h5', category: 'tech', source: 'HN', url: 'https://example.com/5',
      });
    });
    // 乐观更新 → aria-pressed 翻转为已收藏
    await waitFor(() => {
      expect(screen.getByRole('button', { name: `取消收藏：${HOTSPOT_FIXTURE.items[4].title}` })).toHaveAttribute('aria-pressed', 'true');
    });

    fireEvent.click(screen.getByRole('button', { name: `取消收藏：${HOTSPOT_FIXTURE.items[4].title}` }));
    await waitFor(() => {
      expect(callsWith(fetchMock, '/api/favorites/h5', 'DELETE').length).toBeGreaterThan(0);
    });
  });

  it('报头/统计改用 hook 返回值: categoryCounts 渲染到频道 chip, latestIngestionCount 渲染到快讯头', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    // category_counts.security = 3 → 「网络安全」chip 带计数
    expect(screen.getByRole('button', { name: /^网络安全/ })).toHaveTextContent('3');
    // latest_ingestion_count = 12
    expect(screen.getByText(/最近一轮 \+12/)).toBeInTheDocument();
    // pageSize 由 hook 提供 (默认 100), 展示在页脚
    expect(screen.getByText(/每页 100/)).toBeInTheDocument();
  });

  it('壳层溢出菜单: 展开可达报纸版删除后失去入口的 11 项能力, Esc 收起', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const btn = screen.getByRole('button', { name: /更多/ });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    fireEvent.click(btn);
    const menu = screen.getByRole('menu');
    expect(btn).toHaveAttribute('aria-expanded', 'true');

    const hrefs = [...menu.querySelectorAll('a')].map(a => a.getAttribute('href'));
    for (const to of ['/report', '/history', '/reviews', '/secnews', '/knowledge',
                      '/skills', '/todos', '/garden', '/secrets', '/sync', '/settings']) {
      expect(hrefs, `菜单缺少 ${to}`).toContain(to);
    }

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(btn).toHaveAttribute('aria-expanded', 'false');
  });

  it('心跳条: 渲染生命周期漏斗与队列三态 (吸收自 workbench StatusBar)', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const funnel = document.querySelector('.pipe-funnel')!;
    expect(funnel.textContent).toContain('publish');
    expect(funnel.textContent).toContain('3973');
    expect(funnel.textContent).toContain('raw');
    // 阶段名去掉 kl: 前缀以保持可扫读
    expect(funnel.textContent).not.toContain('kl:');
    // 队列: error > 0 用 amber 提示 (red 专属漏洞语境)
    expect(screen.getByText(/2 异常/)).toBeInTheDocument();
  });

  it('URL 导入: 挡住非 http(s) 输入, 合法 URL 走 POST 并回显条目 id', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /导入 URL/ }));
    const input = screen.getByLabelText('待导入的文章 URL');
    const submit = screen.getByRole('button', { name: '导入' });

    // 后端 ImportUrlRequest 不校验 scheme, 故客户端必须挡住
    fireEvent.change(input, { target: { value: 'javascript:alert(1)' } });
    expect(submit).toBeDisabled();
    fireEvent.change(input, { target: { value: 'ftp://x' } });
    expect(submit).toBeDisabled();

    fireEvent.change(input, { target: { value: 'https://example.com/a' } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => {
      expect(callsWith(fetchMock, '/api/kl/import/url', 'POST').length).toBe(1);
    });
    const body = callsWith(fetchMock, '/api/kl/import/url', 'POST')[0][1]!.body;
    expect(JSON.parse(String(body))).toEqual({ url: 'https://example.com/a' });
    await waitFor(() => expect(screen.getByText(/已入库 imported-abc123/)).toBeInTheDocument());
  });

  it('每个 tag 右侧有金黄深度阅读入口, 点击进入 /deep 路由', async () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<SentinelHomePage />} />
          <Route path="/deep/:type/:id" element={<div>DEEP_ROUTE_MARKER</div>} />
        </Routes>
      </MemoryRouter>,
    );

    // 每个 tag 旁都应有深读 chip (头条 + 2 次级 + 快讯 >= 3)
    const chips = await waitFor(() => {
      const all = screen.getAllByRole('button', { name: /进入深度阅读/ });
      expect(all.length).toBeGreaterThanOrEqual(3);
      return all;
    });
    expect(screen.getByRole('button', { name: '对「企业自建大模型网关曝出未授权访问风险」进入深度阅读' })).toBeInTheDocument();
    const secondaryChip = screen.getByRole('button', { name: '对「次级重点条目一」进入深度阅读' });
    expect(secondaryChip).toBeInTheDocument();

    fireEvent.click(secondaryChip);
    await waitFor(() => expect(screen.getByText('DEEP_ROUTE_MARKER')).toBeInTheDocument());
    expect(chips.length).toBeGreaterThanOrEqual(3);
  });
});

/**
 * cadence 修正批 (2026-09-10) — 首页刷新节奏契约
 *
 * owner 反馈: 首页刷新频率过高, 存在多次页面刷新与抓取。根因是 SSE 路径对任意事件
 * 都在 3s 后调 refresh() → POST /api/refresh (= 同步跑一轮完整采集), 于是
 * "采集 → collect_done → 再采集" 自激, 30 分钟节奏被打成连续抓取。
 *
 * 契约:
 *  1. 只有 collect_done 触发首页重拉, 且是只读 GET /api/hotspots, 全程 0 次 POST /api/refresh
 *  2. 埋点 / extract_done / alert / job_done 等事件不刷首页、不刷右栏
 *  3. 用户显式点「立即采集」才会 POST /api/refresh (手动刷新是唯一例外)
 *  4. 页脚 / 空态展示 /api/settings/refresh-interval 的真实间隔, 不再硬编码 "每 5 分钟"
 */
describe('SentinelHomePage — SSE 刷新节奏契约 (cadence 修正批)', () => {
  class TrackingEventSource extends MockEventSource {
    static last: TrackingEventSource | null = null;
    constructor(url: string) { super(url); TrackingEventSource.last = this; }
  }

  let fetchMock: ReturnType<typeof mockFetch>;
  let originalEventSource: typeof EventSource;

  /** 在基础 mock 之上补 /api/settings/refresh-interval (真实后端口径) */
  function mockFetchWithInterval(minutes: number, hotspotBody: FixtureBody = HOTSPOT_FIXTURE) {
    const base = mockFetch(hotspotBody);
    return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith('/api/settings/refresh-interval')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          interval_seconds: minutes * 60, interval_minutes: minutes, persisted_seconds: minutes * 60,
        }) } as Response);
      }
      return base(input, init);
    }) as unknown as ReturnType<typeof mockFetch>;
  }

  function pushSse(type: string, data: Record<string, unknown> = {}) {
    const es = TrackingEventSource.last;
    expect(es, 'EventSource 应已由 useSSE 创建').not.toBeNull();
    act(() => {
      es!.onmessage?.({ data: JSON.stringify({ type, data, ts: nowIso() }) } as MessageEvent);
    });
  }

  beforeEach(() => {
    // shouldAdvanceTime: waitFor 靠真实时间推进仍可用, 同时能瞬时跳过 3s 合并窗口
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock = mockFetchWithInterval(30);
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    TrackingEventSource.last = null;
    (globalThis as any).EventSource = TrackingEventSource;
    try { localStorage.removeItem('hotspot-theme'); } catch {}
    resetFavoritesStore();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    (globalThis as any).EventSource = originalEventSource;
    resetFavoritesStore();
    vi.restoreAllMocks();
  });

  it('collect_done → 3s 合并后只读重拉 /api/hotspots + 右栏各 1 次, 全程 0 次 POST /api/refresh', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const hotspotsBefore = hotspotCalls(fetchMock).length;
    const qualityBefore = callsWith(fetchMock, '/api/quality/summary', 'GET').length;
    expect(callsWith(fetchMock, '/api/refresh', 'POST')).toHaveLength(0);

    // 重连回放可能连发多条 collect_done → 只该合并成一次重拉
    pushSse('collect_done', { total: 10 });
    pushSse('collect_done', { total: 11 });
    pushSse('collect_done', { total: 12 });

    // 右栏走 10s 节流: 三连发只重拉 1 次
    await waitFor(() => expect(callsWith(fetchMock, '/api/quality/summary', 'GET').length).toBe(qualityBefore + 1));
    // 3s 内主列还不该动
    expect(hotspotCalls(fetchMock).length).toBe(hotspotsBefore);

    await act(async () => { vi.advanceTimersByTime(3100); });
    await waitFor(() => expect(hotspotCalls(fetchMock).length).toBe(hotspotsBefore + 1));

    // 核心断言: SSE 路径绝不回触后端采集
    expect(callsWith(fetchMock, '/api/refresh', 'POST')).toHaveLength(0);
  });

  it('非采集事件 (extract_done / alert / job_done / 埋点) 不刷首页、不刷右栏、不触发采集', async () => {
    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument());

    const hotspotsBefore = hotspotCalls(fetchMock).length;
    const qualityBefore = callsWith(fetchMock, '/api/quality/summary', 'GET').length;
    const healthBefore = fetchMock.mock.calls.filter(c => String(c[0]).startsWith('/api/sources/health')).length;

    for (const t of ['extract_done', 'alert', 'job_done', 'task_done', 'view', 'scroll', 'dwell', 'review_due']) {
      pushSse(t, { any: 1 });
    }
    await act(async () => { vi.advanceTimersByTime(15_000); });

    expect(hotspotCalls(fetchMock).length).toBe(hotspotsBefore);
    expect(callsWith(fetchMock, '/api/quality/summary', 'GET').length).toBe(qualityBefore);
    expect(fetchMock.mock.calls.filter(c => String(c[0]).startsWith('/api/sources/health')).length).toBe(healthBefore);
    expect(callsWith(fetchMock, '/api/refresh', 'POST')).toHaveLength(0);
  });

  it('空态「立即采集」是唯一会 POST /api/refresh 的入口 (手动刷新例外)', async () => {
    fetchMock = mockFetchWithInterval(30, { ...HOTSPOT_FIXTURE, items: [], total: 0, category_counts: {} });
    vi.stubGlobal('fetch', fetchMock);

    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);
    const cta = await screen.findByRole('button', { name: /立即采集/ });
    expect(callsWith(fetchMock, '/api/refresh', 'POST')).toHaveLength(0);
    const hotspotsBefore = hotspotCalls(fetchMock).length;

    fireEvent.click(cta);

    await waitFor(() => expect(callsWith(fetchMock, '/api/refresh', 'POST')).toHaveLength(1));
    await waitFor(() => expect(hotspotCalls(fetchMock).length).toBe(hotspotsBefore + 1));
  });

  it('页脚 / 空态文案读取真实采集间隔 (/api/settings/refresh-interval), 不再硬编码 5 分钟', async () => {
    fetchMock = mockFetchWithInterval(60, { ...HOTSPOT_FIXTURE, items: [], total: 0, category_counts: {} });
    vi.stubGlobal('fetch', fetchMock);

    render(<MemoryRouter><SentinelHomePage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText(/每 60 分钟自动采集/)).toBeInTheDocument());
    expect(screen.getByText(/采集管线每 60 分钟自动运行一轮/)).toBeInTheDocument();
    expect(screen.queryByText(/每 5 分钟/)).toBeNull();
  });
});
