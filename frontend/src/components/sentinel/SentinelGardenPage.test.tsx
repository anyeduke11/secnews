/**
 * SentinelGardenPage — 哨兵终端 · 05 CodeGarden 屏测试
 *
 * 测试意图:
 * - 真实数据驱动: 泳道来自 /api/codegarden/projects 的 lifecycle_stage 分组,
 *   服务带来自 /api/codegarden/services (含 project_id=null 的「未归属」如实呈现)
 * - 只读契约: 本屏不得出现任何写操作入口 (重启 / 删除 / 立项 / 扫描 / 执行)
 * - 空表如实空态: cg_events / cg_dependencies 0 行 → 空态文案, 不造假事件行
 * - 门控关闭 → 运维端点 404 呈现为「端点未注册」, 而不是谎报「0 条」
 * - 零霓虹纪律: 后端 topology 的 status_color / runtime_color 十六进制值不得涂到 DOM 上
 * - href 白名单: 非 http(s) 来源 (javascript: / 本地路径) 不得成为可点链接
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

class MockEventSource {
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  close() {}
}

const now = new Date('2026-08-28T05:30:00Z').toISOString();

const PROJECTS_FIXTURE = {
  version: 'test',
  total: 6,
  items: [
    { id: 'aaaa1111-0000', name: 'secnews-web', display_name: 'secnews-web', description: '安全看板 Web 端', type: 'web_application', source_type: 'imported', lifecycle_stage: 'ideation', health_score: 0, local_path: '/Users/duke/secnews-web', repo_url: null, upstream_url: null, tech_stack: ['react'], tags: [], last_activity_at: now, archived_at: null },
    { id: 'bbbb2222-0000', name: 'SOC-kanban', display_name: 'SOC-kanban', description: 'SOC 安全运营看板', type: 'library', source_type: 'imported', lifecycle_stage: 'development', health_score: 58, local_path: '/Users/duke/SOC-kanban', repo_url: 'https://github.com/example/soc-kanban', upstream_url: null, tech_stack: ['typescript', 'vite'], tags: ['scanned'], last_activity_at: now, archived_at: null },
    { id: 'cccc3333-0000', name: 'hotspot', display_name: 'hotspot', description: null, type: 'api_service', source_type: 'imported', lifecycle_stage: 'testing', health_score: 0, local_path: '/Users/duke/hotspot', repo_url: 'javascript:alert(1)', upstream_url: null, tech_stack: [], tags: [], last_activity_at: now, archived_at: null },
    { id: 'dddd4444-0000', name: 'thinking-coach-trae', display_name: null, description: '教练式思维模型', type: 'cli', source_type: 'imported', lifecycle_stage: 'running', health_score: 0, local_path: null, repo_url: null, upstream_url: null, tech_stack: null, tags: null, last_activity_at: now, archived_at: null },
    { id: 'eeee5555-0000', name: 'ThreatMapper', display_name: 'ThreatMapper', description: '威胁建模工具', type: 'cli', source_type: 'imported', lifecycle_stage: 'maintenance', health_score: 0, local_path: null, repo_url: null, upstream_url: null, tech_stack: ['go'], tags: [], last_activity_at: now, archived_at: null },
    { id: 'ffff6666-0000', name: 'old-tool', display_name: 'old-tool', description: '已退役工具', type: 'library', source_type: 'reference', lifecycle_stage: 'deprecated', health_score: 0, local_path: null, repo_url: null, upstream_url: null, tech_stack: [], tags: [], last_activity_at: now, archived_at: 'x' },
  ],
};

/** 实测缺陷复刻: 自动发现的 cg_services 全部 project_id = null */
const SERVICES_FIXTURE = {
  total: 3,
  items: [
    { id: 's1', project_id: null, name: 'agent-bro', namespace: null, type: 'http', runtime: 'bare', status: 'running', endpoint_host: '127.0.0.1', endpoint_port: 63305, endpoint_domain: null, health_check_type: null, health_check_path: null, health_check_interval: 30, cpu_limit: null, memory_limit: null, created_at: now, last_checked_at: now },
    { id: 's2', project_id: null, name: 'ollama', namespace: null, type: 'http', runtime: 'docker', status: 'stopped', endpoint_host: '127.0.0.1', endpoint_port: null, endpoint_domain: null, health_check_type: 'http', health_check_path: '/health', health_check_interval: 60, cpu_limit: null, memory_limit: null, created_at: now, last_checked_at: now },
    { id: 's3', project_id: 'bbbb2222-0000', name: 'grafana', namespace: null, type: 'http', runtime: 'docker', status: 'error', endpoint_host: '127.0.0.1', endpoint_port: 3000, endpoint_domain: null, health_check_type: null, health_check_path: null, health_check_interval: 30, cpu_limit: null, memory_limit: null, created_at: now, last_checked_at: now },
  ],
};

/** 后端 get_topology() 附带硬编码 hex —— 本屏必须只把它当数据, 不涂色 */
const TOPOLOGY_FIXTURE = {
  nodes: [
    { id: 'svc:s1', type: 'serviceNode', position: { x: 0, y: 100 }, data: { label: 'agent-bro', service_id: 's1', runtime: 'bare', status: 'running', endpoint_port: 63305, runtime_color: '#6b7280', status_color: '#10b981' } },
    { id: 'svc:s2', type: 'serviceNode', position: { x: 200, y: 100 }, data: { label: 'ollama', service_id: 's2', runtime: 'docker', status: 'stopped', endpoint_port: null, runtime_color: '#2496ed', status_color: '#9ca3af' } },
    { id: 'svc:s3', type: 'serviceNode', position: { x: 400, y: 100 }, data: { label: 'grafana', service_id: 's3', runtime: 'docker', status: 'error', endpoint_port: 3000, runtime_color: '#2496ed', status_color: '#ef4444' } },
  ],
  edges: [],
};

const SOURCES_FIXTURE = {
  sources: [{ category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: now }],
};

function mockFetch(opts: { opsUnavailable?: boolean } = {}) {
  return vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
    const notFound = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'Not Found' }) } as Response);

    if (url.startsWith('/api/codegarden/projects')) return json(PROJECTS_FIXTURE);
    if (url.startsWith('/api/codegarden/services/topology')) return opts.opsUnavailable ? notFound() : json(TOPOLOGY_FIXTURE);
    if (url.startsWith('/api/codegarden/services')) return opts.opsUnavailable ? notFound() : json(SERVICES_FIXTURE);
    if (url.startsWith('/api/codegarden/events')) return opts.opsUnavailable ? notFound() : json({ items: [], total: 0 });
    if (url.startsWith('/api/codegarden/dependencies')) return opts.opsUnavailable ? notFound() : json({ items: [], total: 0 });
    if (url.startsWith('/api/sources/health')) return json(SOURCES_FIXTURE);
    if (url.startsWith('/api/hotspots')) return json({ total: 186, items: [] });
    if (url.startsWith('/api/settings/features')) return json({ codegarden: true, codegarden_phase2b: false, sync: true, secnews: true, crm: true });
    return json({});
  });
}

import { SentinelGardenPage } from './SentinelGardenPage';

/** testing-library 默认只匹配元素的直接文本子节点; 混合 span 的整段文案用 textContent 断言 */
function textOf(container: HTMLElement, selector: string): string {
  return container.querySelector(selector)?.textContent ?? '';
}

async function renderGarden() {
  const utils = render(<MemoryRouter><SentinelGardenPage /></MemoryRouter>);
  await waitFor(() => expect(utils.container.querySelector('.cg-h1')).not.toBeNull());
  return utils;
}

describe('SentinelGardenPage — 哨兵终端 · 05 CodeGarden', () => {
  let fetchMock: ReturnType<typeof mockFetch>;
  let originalEventSource: typeof EventSource;

  beforeEach(() => {
    fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;
    try { localStorage.removeItem('hotspot-theme'); localStorage.removeItem('hotspot-feature-flags'); } catch {}
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as unknown as { EventSource: unknown }).EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('渲染壳 + 屏标题 + 四条泳道 (布局契约 PH.01-PH.04)', async () => {
    const { container } = await renderGarden();
    expect(screen.getByText('SecNews')).toBeInTheDocument();
    expect(screen.getByText('PIPELINE LIVE')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /返回资料层/ })).toBeInTheDocument();
    expect(textOf(container, '.cg-h1')).toBe('CODEGARDEN');

    expect(container.querySelectorAll('.cg-lanes > .cg-lane')).toHaveLength(4);
    expect([...container.querySelectorAll('.cg-ph')].map(el => el.textContent))
      .toEqual(['PH.01', 'PH.02', 'PH.03', 'PH.04']);
    for (const label of ['孵化', '构建', '联调', '服役']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('泳道按真实 lifecycle_stage 分组且计数可对账 (泳道外阶段走溢出条不丢失)', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('6 PROJECTS')).toBeInTheDocument());

    const counts = [...container.querySelectorAll('.cg-lc')].map(el => Number(el.textContent));
    expect(counts).toEqual([1, 1, 1, 2]); // 构想 / 开发 / 测试 / 运行+维护
    expect(counts.reduce((a, b) => a + b, 0)).toBe(5);
    // deprecated 不在四泳道内 → 溢出条对账 5 + 1 = 6
    expect(textOf(container, '.cg-rest')).toContain('另有 1 个项目处于泳道外阶段');
    expect(textOf(container, '.cg-rest')).toContain('退役');
    expect(textOf(container, '.cg-sub')).toContain('在园 6 个');
  });

  it('卡片只渲染真实字段: health_score=0 显示「未评分」而不是 0% 进度条', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('SOC-kanban')).toBeInTheDocument());

    expect(container.querySelectorAll('[role="progressbar"]')).toHaveLength(1); // 仅 58 分那条
    // 四泳道共 5 张卡 (deprecated 走溢出条不出卡), 其中 4 张 health_score=0
    // → 全部如实显示「未评分」, 不伪造 0% 进度条
    expect(screen.getAllByText('健康度 未评分')).toHaveLength(4);
    expect(screen.getByText(/API 服务 · 导入 来源，无描述/)).toBeInTheDocument();
  });

  it('href 白名单: https 可点、javascript: 不可点、local_path 永不成为链接', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('SOC-kanban')).toBeInTheDocument());

    expect(container.querySelector('a[href="https://github.com/example/soc-kanban"]')).not.toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(container.innerHTML).not.toContain('javascript:alert');
    expect(container.innerHTML).not.toContain('/Users/duke/');
  });

  it('服务网格如实呈现「未归属」这一类 + 端口/运行时/调度周期为等宽数据', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('3 SERVICES')).toBeInTheDocument());

    expect(textOf(container, '.cg-note')).toContain('项目归属：已归属 1 / 未归属 2');
    expect(screen.getAllByText('未归属')).toHaveLength(2);
    expect(screen.getByText('已归属')).toBeInTheDocument();
    expect(screen.getByText('bare · :63305 · 30s')).toBeInTheDocument();
    expect(screen.getByText('docker · 无端口 · 60s')).toBeInTheDocument();
  });

  it('语义三色锁: 服务停止/异常不着红色 (红专属漏洞语境)', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('3 SERVICES')).toBeInTheDocument());

    const st = [...container.querySelectorAll('.cg-svcst')].map(el => [el.textContent, el.className]);
    expect(st).toEqual([
      ['运行中', 'cg-svcst cg-ok'],
      ['已停止', 'cg-svcst cg-idle'],
      ['异常', 'cg-svcst cg-warn'],
    ]);
    expect(container.innerHTML).not.toContain('--sn-red');
    expect(container.innerHTML).not.toContain('sn-red');
  });

  it('后端 topology 的 status_color / runtime_color 当数据处理, 不参与着色', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('3 NODES · 0 EDGES')).toBeInTheDocument());

    const nodes = container.querySelectorAll('.cg-node');
    expect(nodes).toHaveLength(3);
    expect(nodes[0]).toHaveClass('cg-ok');
    expect(nodes[1]).toHaveClass('cg-idle');
    expect(nodes[2]).toHaveClass('cg-warn');
    for (const hex of ['#10b981', '#ef4444', '#fbbf24', '#2496ed', '#6b7280', '#9ca3af']) {
      expect(container.innerHTML).not.toContain(hex);
    }
    expect(screen.getByText(/status_color \/ runtime_color 十六进制值不参与着色/)).toBeInTheDocument();
    // edges=0 → 明确声明这是占用矩阵而非拓扑布局
    expect(textOf(container, '.cg-topo .cg-note')).toContain('此图为占用矩阵而非拓扑布局');
  });

  it('cg_events / cg_dependencies 空表 → 如实空态, 不伪造事件行', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('TODAY 0')).toBeInTheDocument());

    expect(textOf(container, '.cg-empty-block p')).toContain('cg_events 表当前 0 行');
    expect(textOf(container, '.cg-dep .cg-note')).toContain('cg_dependencies 表 0 行');
    expect(textOf(container, '.cg-dep .cg-note')).toContain('影响分析（BFS 反向追溯）当前无输入');
    expect(container.querySelectorAll('.cg-evrow')).toHaveLength(0);
  });

  it('只读契约: 无可交互写操作入口, 且全部请求都是 GET', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('6 PROJECTS')).toBeInTheDocument());

    // 壳层仅主题切换 + 设置两个 iconbtn; 本页不新增任何 button / role=button
    expect(container.querySelectorAll('button')).toHaveLength(2);
    expect(container.querySelectorAll('[role="button"]')).toHaveLength(0);

    const interactiveText = [...container.querySelectorAll('button, a, [role="button"]')]
      .map(el => el.textContent ?? '').join(' | ');
    for (const verb of ['重启', '删除', '立项', '新建', '扫描', '执行', '归档', '保存', '立即采集']) {
      expect(interactiveText).not.toMatch(new RegExp(verb));
    }

    const calls = fetchMock.mock.calls.map(c => {
      const init = c[1] as RequestInit | undefined;
      return `${init?.method ?? 'GET'} ${String(c[0])}`;
    });
    expect(calls.every(c => c.startsWith('GET '))).toBe(true);
    expect(calls.some(c => c.includes('/api/codegarden/projects'))).toBe(true);
  });

  it('门控关闭致运维端点 404 → 呈现「端点未注册」而非谎报 0 条', async () => {
    fetchMock = mockFetch({ opsUnavailable: true });
    vi.stubGlobal('fetch', fetchMock);
    const { container } = await renderGarden();

    await waitFor(() => expect(textOf(container, '.cg-blk')).toContain('服务网格端点未注册（404）'));
    expect(container.innerHTML).toContain('事件总线端点未注册（404）');
    expect(container.innerHTML).toContain('依赖列表端点未注册（404）');
    expect(container.innerHTML).toContain('codegarden_phase2b');
    // 项目泳道仍可用 (gate codegarden=true)
    expect(screen.getByText('6 PROJECTS')).toBeInTheDocument();
    expect(screen.getByText('0 SERVICES')).toBeInTheDocument();
    expect(container.querySelectorAll('.cg-svcrow')).toHaveLength(0);
  });

  it('如实声明运维门控状态与只读定位', async () => {
    const { container } = await renderGarden();
    await waitFor(() => expect(screen.getByText('codegarden_phase2b')).toBeInTheDocument());
    expect(textOf(container, '.cg-gate')).toContain('关闭（backend/config/feature_gates.toml）');
    expect(textOf(container, '.cg-gate')).toContain('本屏为只读观测台');
  });
});
