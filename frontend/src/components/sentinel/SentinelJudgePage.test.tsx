/**
 * SentinelJudgePage — 哨兵终端 · 判断层判读台测试
 *
 * 测试意图:
 * - 布局契约: jd-grid 主区队列表 + 340px 右栏四模块 (本周信号 / 质量门禁 / 知识管线 / 时段吞吐) 常驻
 * - P0 语义锁: 仅 score≥80 且 category∈{security, ai_security} 才进 jd-p0 并挂「高危」red 徽标;
 *   非漏洞语境的高分条目不得染 red (设计纪律: red 专属漏洞告警)
 * - 「需注意」态: jd-state 只在条目自身有 url 校验异常 / 兜底来源 / 质量标记时出现, 不伪造判读状态
 * - 门禁口径如实标注: 拦截合计按「门禁次数」计 (同一条目可被多道门禁命中), 界面必须写明可大于检查条目
 * - 归档操作四态: 默认 → 请求中 disabled → 成功「已归档」锁定 / 失败「归档失败」可重试
 * - 时段吞吐点阵固定 7 天 × 5 时段 = 35 格, 无数据走空态; 图形层 role=img + aria-label 承载等价说明
 * - 外链 target=_blank 必带 rel=noopener noreferrer
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/** Mock EventSource (SentinelShell/useSSE 依赖) */
class MockEventSource {
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  close() {}
}

const HOUR = 3600000;
const iso = (hoursAgo: number) => new Date(Date.now() - hoursAgo * HOUR).toISOString();

/** 队列 fixture: 覆盖 P0 / 高分非安全 / 需注意态 / 干净条目 四类 */
const HOTSPOTS = [
  {
    id: 'a1', title: '广泛使用的 PDF 解析库存在内存越界缺陷，PoC 已公开传播',
    source: 'BleepingComputer', url: 'https://example.org/a1', category: 'security',
    published_at: iso(1), ingested_at: iso(0.5), score: 92,
  },
  {
    id: 'b2', title: 'AI 群体架构构建超越创造者的技术生态',
    source: 'AGI Hunt', url: 'https://example.org/b2', category: 'tech',
    published_at: iso(2), ingested_at: iso(2), score: 88,
    quality_flags: ['title_summary_inconsistent'],
  },
  {
    id: 'c3', title: '身份安全创企完成 B 轮 8000 万融资',
    source: '36氪', url: 'https://example.org/c3', category: 'startup',
    published_at: iso(3), ingested_at: iso(3), score: 61,
    url_check_status: 'pending',
  },
  {
    id: 'd4', title: 'OpenAI 新版模型卡引入红队披露章节',
    source: 'TechCrunch', url: 'https://example.org/d4', category: 'ai_security',
    published_at: iso(4), ingested_at: iso(4), score: 80,
  },
];

/** 168h 逐小时趋势: 仅最近 3 小时有量，其余为 0 */
function trendsFixture() {
  return Array.from({ length: 168 }, (_, h) => ({
    label: `-${h}h`, hours_ago: h,
    total: h === 0 ? 30 : h === 1 ? 10 : h === 2 ? 5 : 0,
    ai: h === 0 ? 20 : 0, ai_security: h === 1 ? 4 : 0, security: h === 0 ? 10 : 0,
    finance: 0, startup: 0, bid: 0, github: 0, tech: 0,
  }));
}

/** 12 道门禁真实形状; duplicate/AuthorVerification 有明显拦截 */
const QUALITY = {
  AuthorVerification: { pass: 60, total: 100, avg_deduction: 0.92 },
  duplicate: { pass: 30, total: 100, avg_deduction: 4.1 },
  FinalUrl: { pass: 100, total: 100, avg_deduction: 0 },
};

/** /api/kl/compounding → stage_distribution: 服务端 GROUP BY lifecycle 的全量计数 */
const KNOWLEDGE = {
  stage_distribution: {
    'kl:structure': 3512,
    'kl:publish': 284,
    'kl:raw': 2,
    generate: 124, // 历史遗留 lifecycle (迁移 046 只改过 DB), 应归入"其他"而非丢失
  },
};

const SOURCES = {
  sources: [
    { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: iso(1) },
    { category: 'tech', source_name: 'HN', status: 'stale', total_items: 200, last_seen_at: iso(30) },
  ],
};

let favoriteResponses: boolean[] = [];

function makeFetch() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith('/api/hotspots')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 186, items: HOTSPOTS }) } as Response);
    }
    if (url.startsWith('/api/trends')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ trends: trendsFixture() }) } as Response);
    }
    if (url.startsWith('/api/quality/summary')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ summary: QUALITY }) } as Response);
    }
    if (url.startsWith('/api/kl/compounding')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(KNOWLEDGE) } as Response);
    }
    if (url.startsWith('/api/sources/health')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SOURCES) } as Response);
    }
    if (url.startsWith('/api/favorites') && init?.method === 'POST') {
      const ok = favoriteResponses.length > 0 ? favoriteResponses.shift() === true : true;
      return Promise.resolve({ ok } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

import { SentinelJudgePage } from './SentinelJudgePage';

function renderPage() {
  return render(<MemoryRouter><SentinelJudgePage /></MemoryRouter>);
}

async function waitForQueue() {
  await waitFor(() => expect(screen.queryByText(/广泛使用的 PDF 解析库/)).toBeInTheDocument());
}

describe('SentinelJudgePage — 哨兵终端 · 判读台', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = makeFetch();
    favoriteResponses = [];
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;
    try { localStorage.removeItem('hotspot-theme'); } catch { /* jsdom 兜底 */ }
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as unknown as { EventSource: unknown }).EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('渲染队列表格七列与右栏四模块 (布局契约)', async () => {
    renderPage();
    await waitForQueue();
    for (const col of ['评分', '标题', '频道', '来源', '时间', '热度', '操作']) {
      expect(screen.getByRole('columnheader', { name: col })).toBeInTheDocument();
    }
    expect(screen.getByRole('heading', { name: /本周信号/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /质量门禁/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /知识管线/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /时段吞吐/ })).toBeInTheDocument();
  });

  it('队列按评分降序，评分列带 /100 量纲', async () => {
    const { container } = renderPage();
    await waitForQueue();
    const scores = Array.from(container.querySelectorAll('td.jd-id')).map(td => td.textContent);
    expect(scores).toEqual(['92/100', '88/100', '80/100', '61/100']);
  });

  it('P0 red 语义锁: 仅高分安全/AI安全条目进 jd-p0 并挂高危徽标', async () => {
    const { container } = renderPage();
    await waitForQueue();
    const p0Rows = container.querySelectorAll('tr.jd-p0');
    // a1(security 92) + d4(ai_security 80) 命中; b2(tech 88) 高分但非漏洞语境不得染 red
    expect(p0Rows.length).toBe(2);
    expect(screen.getAllByText('高危').length).toBe(2);
    expect(container.querySelector('tr.jd-p0 .jd-rowtitle a')?.textContent).toMatch(/PDF 解析库/);
  });

  it('「需注意」态只来自条目自身字段，且不带前缀噪声', async () => {
    renderPage();
    await waitForQueue();
    expect(screen.getByText('来源待校验')).toBeInTheDocument();
    expect(screen.getByText('title_summary_inconsistent')).toBeInTheDocument();
    expect(screen.queryByText(/质量标记/)).not.toBeInTheDocument();
    // d4 无异常字段 → 不渲染态徽标
    expect(screen.getAllByText(/来源待校验|title_summary_inconsistent|标题待核|兜底来源/).length).toBe(2);
  });

  it('门禁拦截合计按门禁计并写明口径', async () => {
    renderPage();
    await waitForQueue();
    // (100-60) + (100-30) + (100-100) = 110 次，检查条目取最大 total=100
    expect(screen.getByText('110')).toBeInTheDocument();
    expect(screen.getByText(/口径：拦截按门禁计/)).toBeInTheDocument();
    expect(screen.getByText('检查条目')).toBeInTheDocument();
  });

  it('门禁分布条 role=img 且 aria-label 逐门禁列出拦截数', async () => {
    renderPage();
    await waitForQueue();
    const dist = screen.getByLabelText(/^拦截分布/);
    expect(dist).toHaveAttribute('role', 'img');
    expect(dist.getAttribute('aria-label')).toContain('duplicate 70 次');
    expect(dist.getAttribute('aria-label')).toContain('AuthorVerification 40 次');
    // 无拦截的 FinalUrl 不进图例
    expect(dist.getAttribute('aria-label')).not.toContain('FinalUrl');
  });

  it('语义三色锁: 拒因分布段统一 amber，不得借用分类色/告警红', async () => {
    const { container } = renderPage();
    await waitForQueue();
    const segs = Array.from(container.querySelectorAll('.jd-dist i'));
    expect(segs.length).toBeGreaterThan(1);
    for (const seg of segs) {
      expect(seg.getAttribute('style')).toContain('--sn-amber');
    }
  });

  it('时段吞吐点阵固定 35 格 (7 天 × 5 时段)', async () => {
    const { container } = renderPage();
    await waitForQueue();
    expect(container.querySelectorAll('.jd-heat i').length).toBe(35);
    expect(screen.getByLabelText(/过去 7 天 5 个时段的收录吞吐/)).toHaveAttribute('role', 'img');
  });

  it('屏尾结算行数字全部来自实测数据', async () => {
    renderPage();
    await waitForQueue();
    // 168h total 合计 = 30+10+5 = 45; kl:publish = 284 (全量聚合); 队列 = 4
    const settled = screen.getByText(/过去 168 小时共收录/);
    expect(settled.textContent).toContain('45');
    expect(settled.textContent).toContain('284');
    expect(settled.textContent).toContain('4');
  });

  it('知识管线用服务端全量聚合，不是 200 条样本', async () => {
    renderPage();
    await waitForQueue();
    // 全库 kl:structure = 3512 —— 旧实现抓 limit=200 样本再数, 绝不可能显示这个量级
    expect(screen.getByText('KL PIPELINE · 全库')).toBeInTheDocument();
    const bars = screen.getAllByText(/^3512$|^284$|^124$/);
    expect(bars.length).toBeGreaterThanOrEqual(3);
    // 不在五段口径内的历史遗留值必须可见, 不能被静默丢弃
    expect(screen.getByText('其他')).toBeInTheDocument();
  });

  it('归档成功: POST 带 hotspot_id，按钮锁定为已归档 + disabled', async () => {
    renderPage();
    await waitForQueue();
    fireEvent.click(screen.getAllByText('归档')[0]);
    const done = await screen.findByText('已归档');
    expect(done).toBeDisabled();
    const call = fetchMock.mock.calls.find(([u, init]) => String(u).startsWith('/api/favorites') && (init as RequestInit)?.method === 'POST');
    expect(call).toBeDefined();
    const body = JSON.parse(String((call![1] as RequestInit).body));
    expect(body).toMatchObject({ hotspot_id: 'a1', category: 'security', source: 'BleepingComputer' });
  });

  it('归档失败: 显示归档失败且保持可重试', async () => {
    favoriteResponses = [false];
    renderPage();
    await waitForQueue();
    fireEvent.click(screen.getAllByText('归档')[0]);
    const failed = await screen.findByText('归档失败');
    expect(failed).toBeEnabled();
  });

  it('外链标题带 rel=noopener noreferrer', async () => {
    renderPage();
    await waitForQueue();
    const link = screen.getByText(/OpenAI 新版模型卡/) as HTMLAnchorElement;
    expect(link.closest('a')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('空队列走空态面板并给出回资料层入口', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.startsWith('/api/hotspots') ? { total: 0, items: [] } : {};
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    }));
    renderPage();
    expect(await screen.findByText('今日队列已清空')).toBeInTheDocument();
    expect(screen.getByText('返回资料层')).toBeInTheDocument();
    expect(screen.getByText('暂无逐小时趋势数据')).toBeInTheDocument();
    expect(screen.getByText('暂无门禁数据')).toBeInTheDocument();
  });

  it('逐行 AI 评测 → POST /api/llm/evaluate; ok=false 时原样显示错误', async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push([url, init]);
      if (url.startsWith('/api/hotspots')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          total: 1, items: [{
            id: 'j1', title: '供应链投毒事件通报', summary: '一段足够长的正文用于评测。',
            source: 'FreeBuf', url: 'https://e.com/1', category: 'security',
            score: 88, published_at: new Date().toISOString(),
          }],
        }) } as Response);
      }
      if (url.startsWith('/api/llm/evaluate')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          ok: true, quality_score: 9.2, verdict: '值得沉淀',
          key_points: ['攻击面扩大', '影响面广'], provider: 'sensenova',
        }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));

    renderPage();
    const btn = await screen.findByRole('button', { name: 'AI 评测：供应链投毒事件通报' });
    fireEvent.click(btn);

    await waitFor(() => {
      const post = calls.find(([u, i]) => u.startsWith('/api/llm/evaluate') && i?.method === 'POST');
      expect(post, '未发出评测请求').toBeTruthy();
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({
        title: '供应链投毒事件通报',
        content: '一段足够长的正文用于评测。',
      });
    });
    expect(await screen.findByText(/AI 9/)).toBeInTheDocument();
    expect(screen.getByText('值得沉淀')).toBeInTheDocument();
    expect(screen.getByText('影响面广')).toBeInTheDocument();
    expect(screen.getByText('sensenova')).toBeInTheDocument();
  });

  it('AI 评测失败 (ok=false) 不得被吞掉, 要原样呈现错误', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/hotspots')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          total: 1, items: [{
            id: 'j2', title: '另一条待评测条目', summary: '正文内容足够长可以送去评测。',
            source: 'HN', url: 'https://e.com/2', category: 'ai',
            score: 60, published_at: new Date().toISOString(),
          }],
        }) } as Response);
      }
      if (url.startsWith('/api/llm/evaluate')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          ok: false, error: 'ConnectionError: provider 不可达',
        }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));

    renderPage();
    const btn = await screen.findByRole('button', { name: 'AI 评测：另一条待评测条目' });
    fireEvent.click(btn);
    expect(await screen.findByText(/评测未成功：ConnectionError/)).toBeInTheDocument();
  });
});
