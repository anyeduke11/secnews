/**
 * SentinelGraphPage — 哨兵终端知识图谱屏测试
 *
 * 测试意图:
 * - 布局契约: kg-grid 主区 + 340px 右栏三模块 (选中节点详情 / 关联条目 / 本周增长) 常驻
 * - 真实数据驱动: 节点/边来自 /api/knowledge/graph; 关联条目标题来自 /api/knowledge/concepts/{slug}
 *   (fixture 用真实响应形状: node.type 恒为 concept, edge.type 恒为 related)
 * - SVG 无障碍: 图形层 aria-hidden + svg role="img" aria-label 携带数量与分布; 等价操作走节点索引
 * - 数据面如实标注: 界面必须写出实测的边类型分布, 不伪造多种边类型
 * - 缺接口/空字段 → 走空态文案, 不造假数据
 * - API 外链必须过 ^https?: 白名单 (local_wiki_ref 非 http(s) 时不得成为 href)
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

const DAY = 86400000;
const iso = (daysAgo: number) => new Date(Date.now() - daysAgo * DAY).toISOString();

/** 12 节点真实形状 fixture: type 全为 concept, domain 覆盖 ai/security + 1 个 CVE 实体 */
const NODES = [
  { id: 'ai-agent', label: 'AI Agent', domain: 'ai', count: 9, wiki: 'hotspot', type: 'concept' },
  { id: 'developer-tools', label: '开发者工具', domain: 'ai', count: 5, wiki: 'hotspot', type: 'concept' },
  { id: 'llm-cost', label: '大模型成本', domain: 'ai', count: 6, wiki: 'hotspot', type: 'concept' },
  { id: 'agent-skills', label: 'Agent Skills', domain: 'ai', count: 3, wiki: 'hotspot', type: 'concept' },
  { id: 'penetration-testing', label: '渗透测试', domain: 'security', count: 4, wiki: 'hotspot', type: 'concept' },
  { id: 'ai-driven-attack', label: 'AI 驱动攻击', domain: 'security', count: 4, wiki: 'hotspot', type: 'concept' },
  { id: 'payment-gateway', label: '支付网关', domain: 'security', count: 1, wiki: 'hotspot', type: 'concept' },
  { id: 'financial-regulation', label: '金融监管', domain: 'finance', count: 3, wiki: 'hotspot', type: 'concept' },
  { id: 'knowledge-management', label: '知识管理', domain: 'startup', count: 2, wiki: 'hotspot', type: 'concept' },
  { id: 'cve-cve-2017-0199', label: 'CVE-2017-0199', domain: 'security', count: 0, wiki: 'hotspot', type: 'concept' },
  { id: 'orphan-node', label: '孤立概念', domain: 'general', count: 0, wiki: 'hotspot', type: 'concept' },
  { id: 'self-media-platform', label: '自媒体平台', domain: 'security', count: 1, wiki: 'hotspot', type: 'concept' },
];

/** 实测: edges 随响应返回, type 恒为 related, weight 为同现次数 */
const EDGES = [
  { source: 'ai-agent', target: 'developer-tools', weight: 16, type: 'related' },
  { source: 'ai-agent', target: 'ai-driven-attack', weight: 4, type: 'related' },
  { source: 'ai-agent', target: 'penetration-testing', weight: 6, type: 'related' },
  { source: 'ai-agent', target: 'agent-skills', weight: 3, type: 'related' },
  { source: 'ai-agent', target: 'llm-cost', weight: 2, type: 'related' },
  { source: 'developer-tools', target: 'penetration-testing', weight: 1, type: 'related' },
  { source: 'llm-cost', target: 'agent-skills', weight: 2, type: 'related' },
  { source: 'payment-gateway', target: 'financial-regulation', weight: 1, type: 'related' },
  { source: 'payment-gateway', target: 'self-media-platform', weight: 1, type: 'related' },
  { source: 'knowledge-management', target: 'llm-cost', weight: 1, type: 'related' },
];

const GRAPH_FIXTURE = { nodes: NODES, edges: EDGES };

/** local_wiki_ref 三种真实形态: 相对路径 / 合法 https / javascript: 注入串 */
const WIKI_REF: Record<string, string | null> = {
  'llm-cost': 'wiki/hotspot/大模型成本.md',
  'ai-agent': 'https://wiki.example.org/hotspot/ai-agent.md',
  'agent-skills': 'javascript:alert(1)',
};

const CONCEPTS_FIXTURE = {
  concepts: NODES.map(n => ({
    slug: n.id,
    title: n.label,
    domain: n.domain,
    // CVE 节点 source_items 为空 — 真实数据面如此
    source_items: n.id.startsWith('cve-') || n.id === 'orphan-node' ? [] : ['8c40203b708e', '4a62e2696ce4'].slice(0, Math.max(1, Math.min(2, n.count))),
    local_wiki_ref: WIKI_REF[n.id] ?? null,
    updated_at: n.id === 'ai-agent' ? iso(2) : iso(13),
    entity_type: n.id.startsWith('cve-') ? 'cve' : 'generic',
    external_id: n.id.startsWith('cve-') ? 'cve:CVE-2017-0199' : null,
    external_ref: n.id.startsWith('cve-') ? 'security_entity:cve:CVE-2017-0199' : null,
  })),
};

/** /api/knowledge/concepts/{slug} 比列表多一个已解析标题的 items */
function detailOf(slug: string) {
  const base = (CONCEPTS_FIXTURE.concepts as { slug: string; title: string; domain: string }[]).find(c => c.slug === slug)!;
  return {
    ...base,
    source_items: slug.startsWith('cve-') ? [] : ['8c40203b708e'],
    local_wiki_ref: WIKI_REF[slug] ?? null,
    updated_at: slug === 'ai-agent' ? iso(2) : iso(13),
    entity_type: slug.startsWith('cve-') ? 'cve' : 'generic',
    external_id: slug.startsWith('cve-') ? 'cve:CVE-2017-0199' : null,
    external_ref: slug.startsWith('cve-') ? 'security_entity:cve:CVE-2017-0199' : null,
    items: slug.startsWith('cve-') ? [] : [
      { id: '8c40203b708e', title: '多家银行披露日均Token消耗量！AI大模型应用成本如何控制？', domain: 'ai' },
    ],
  };
}

const SOURCES_FIXTURE = {
  sources: [
    { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: iso(0) },
    { category: 'tech', source_name: 'HN', status: 'stale', total_items: 200, last_seen_at: iso(1) },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/knowledge/graph')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(GRAPH_FIXTURE) } as Response);
    }
    if (/^\/api\/knowledge\/concepts\/[^/]+$/.test(url)) {
      const slug = decodeURIComponent(url.split('?')[0].split('/').pop()!);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(detailOf(slug)) } as Response);
    }
    if (url.startsWith('/api/knowledge/concepts')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(CONCEPTS_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/hotspots')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ total: 106, items: [] }) } as Response);
    }
    if (url.startsWith('/api/sources/health')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SOURCES_FIXTURE) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

import { SentinelGraphPage } from './SentinelGraphPage';

describe('SentinelGraphPage — 哨兵终端 · 知识图谱', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = makeFetch();
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

  /** 等待图谱首屏渲染完成 (骨架 → 实际 SVG) */
  async function rendered() {
    await waitFor(() => expect(document.querySelector('svg.kg-graphsvg')).toBeTruthy());
  }

  it('复用 SentinelShell 且标记判断层 active', async () => {
    const { container } = render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();
    expect(screen.getByText('SecNews')).toBeInTheDocument();
    expect(screen.getByText('PIPELINE LIVE')).toBeInTheDocument();
    const judge = screen.getByRole('link', { name: /判断层/ });
    expect(judge.closest('.layer-link')).toHaveClass('active');
    expect(judge).toHaveAttribute('aria-current', 'page');
    // 今日收录口径由 /api/hotspots total 提供, 不自造数字
    expect(container.textContent).toContain('106 篇');
  });

  it('真实数据驱动: 节点/边计数与今日更新时间出现在界面上', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    expect(screen.getByRole('heading', { name: '知识图谱' })).toBeInTheDocument();
    // 12 节点 / 10 边 / 域数 5 / 引用合计
    const settle = document.querySelector('.kg-settle')!;
    expect(settle.textContent).toContain('12');
    expect(settle.textContent).toContain('10');
    // ai-agent updated_at = 2 天前 → 近 7 天更新 1 个
    expect(screen.getByText('本周增长')).toBeInTheDocument();
    expect(document.querySelector('.kg-growth')!.textContent).toContain('近 7 天更新概念');
    expect(document.querySelectorAll('line.kg-edge').length).toBe(10);
    expect(document.querySelectorAll('g.kg-node').length).toBe(12);
  });

  it('SVG 无障碍: 根为 role=img 且 aria-label 含数量与分布, 图形层 aria-hidden', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    const svg = document.querySelector('svg.kg-graphsvg')!;
    expect(svg).toHaveAttribute('role', 'img');
    expect(svg.getAttribute('aria-label')).toContain('12 个概念节点');
    expect(svg.getAttribute('aria-label')).toContain('10 条关联边');
    expect(svg.getAttribute('aria-label')).toContain('related 10/10');
    // 所有图元对 AT 隐藏, 等价操作在文字索引里
    expect(svg.querySelector('g.kg-layer-edges')).toHaveAttribute('aria-hidden', 'true');
    expect(svg.querySelector('g.kg-layer-nodes')).toHaveAttribute('aria-hidden', 'true');
    const indexRows = await screen.findAllByRole('button', { name: /AI Agent/ });
    expect(indexRows.length).toBeGreaterThan(0);
  });

  it('数据面如实标注: 显示实测的节点/边类型分布与孤立节点数', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    const dist = document.querySelector('.kg-dist')!;
    expect(dist.textContent).toContain('concept 12/12');
    expect(dist.textContent).toContain('related 10/10');
    expect(dist.textContent).toContain('同现关联，当前响应仅此一类');
    expect(dist.textContent).toContain('孤立节点 2');
    expect(dist.textContent).toContain('cve 1 / generic 11');
  });

  it('点击节点索引 → 拉取 concepts/{slug} 并渲染真名关联条目 (内部路由链接)', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    fireEvent.click(screen.getByRole('button', { name: /^大模型成本/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '大模型成本' })).toBeInTheDocument());

    const called = Array.from(fetchMock.mock.calls).map(c => String(c[0])).find(u => u.includes('/api/knowledge/concepts/'));
    expect(called).toContain('/api/knowledge/concepts/llm-cost');

    await waitFor(() => expect(screen.getByText(/多家银行披露日均Token消耗量/)).toBeInTheDocument());
    const link = screen.getByText(/多家银行披露日均Token消耗量/).closest('a')!;
    expect(link).toHaveAttribute('href', '/knowledge/deep-read/8c40203b708e');
    // 关联边数由前端从 edges 反推 (llm-cost: ai-agent + agent-skills + knowledge-management = 3)
    expect(document.querySelector('.kg-facts')!.textContent).toContain('关联边3');
  });

  it('API 外链白名单: 只有 ^https?: 的 local_wiki_ref 才能成为 href', async () => {
    const { container } = render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    // 1) 相对 wiki 路径 → 文字说明, 无链接
    fireEvent.click(screen.getByRole('button', { name: /^大模型成本/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '大模型成本' })).toBeInTheDocument());
    let refLine = Array.from(container.querySelectorAll('.kg-ref')).find(el => el.textContent?.includes('wiki 引用'))!;
    expect(refLine.textContent).toContain('非 http(s) 引用，不作为链接');
    expect(refLine.querySelector('a')).toBeNull();

    // 2) javascript: 注入串 → 同样不得成为链接
    fireEvent.click(screen.getByRole('button', { name: /^Agent Skills/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Agent Skills' })).toBeInTheDocument());
    refLine = Array.from(container.querySelectorAll('.kg-ref')).find(el => el.textContent?.includes('wiki 引用'))!;
    expect(refLine.querySelector('a')).toBeNull();
    expect(container.innerHTML).not.toContain('href="javascript:');

    // 3) 合法 https → 渲染外链且带 noopener
    fireEvent.click(screen.getByRole('button', { name: /^AI Agent/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'AI Agent' })).toBeInTheDocument());
    refLine = Array.from(container.querySelectorAll('.kg-ref')).find(el => el.textContent?.includes('wiki 引用'))!;
    const anchor = refLine.querySelector('a')!;
    expect(anchor).toHaveAttribute('href', 'https://wiki.example.org/hotspot/ai-agent.md');
    expect(anchor).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('按域过滤 chip 只影响渲染集合, 且带 aria-pressed', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    const chip = screen.getByRole('button', { name: /^AI 4$/ });
    fireEvent.click(chip);
    // ai 域 4 个节点保留, 其余 8 个降透明; 跨域边全部标 kg-dim
    await waitFor(() => expect(document.querySelectorAll('g.kg-node[data-dim="1"]').length).toBe(8));
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelectorAll('line.kg-edge:not(.kg-dim)').length).toBe(4);

    fireEvent.click(screen.getByRole('button', { name: /^全部 12$/ }));
    await waitFor(() => expect(document.querySelectorAll('g.kg-node[data-dim="1"]').length).toBe(0));
  });

  it('source_items 为空的 CVE 节点 → 如实空态, 不造条目', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    fireEvent.click(screen.getByRole('button', { name: /CVE-2017-0199/ }));
    await waitFor(() => expect(screen.getByText('漏洞实体')).toBeInTheDocument());
    expect(screen.getByText(/source_items 为空/)).toBeInTheDocument();
    expect(document.querySelectorAll('.kg-links a').length).toBe(0);
    // red 专属漏洞语境: 仅该实体取红色三角, 图例按实测数量说明
    expect(document.querySelectorAll('polygon.kg-shape.kg-f-vuln').length).toBe(1);
    expect(document.querySelector('.kg-legend')!.textContent).toContain('漏洞实体 1');
  });

  it('隐藏节点后恢复显示', async () => {
    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await rendered();

    fireEvent.click(screen.getByRole('button', { name: /自媒体平台/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /在图谱中隐藏/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /在图谱中隐藏/ }));
    await waitFor(() => expect(document.querySelectorAll('g.kg-node').length).toBe(11));
    fireEvent.click(screen.getByRole('button', { name: /显示已隐藏的 1 个/ }));
    await waitFor(() => expect(document.querySelectorAll('g.kg-node').length).toBe(12));
  });

  it('graph 接口失败 → 错误空态 + 重试入口, 不白屏', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/graph')) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [], concepts: [], sources: [], total: 0, items: [] }) } as Response);
    }));

    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('图谱数据加载失败')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
    expect(document.querySelector('svg.kg-graphsvg')).toBeNull();
  });

  it('graph 返回空集合 → 空态面板指向判读台', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/knowledge/graph')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ concepts: [], sources: [], total: 0, items: [] }) } as Response);
    }));

    render(<MemoryRouter><SentinelGraphPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('图谱暂无节点')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /返回判读台/ })).toBeInTheDocument();
  });
});
