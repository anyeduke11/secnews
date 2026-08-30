/**
 * SentinelSettingsPage — 06 设置屏测试
 *
 * 测试意图 (本仓安全现实驱动, 不是普通渲染快照):
 *  1. 只读契约: 页面发出的**每一个**请求都是 GET /api/{settings/features,llm/status,
 *     health,secrets,status,sources/health}; 断言不存在 POST/PUT/DELETE 调用。
 *  2. 零密钥面: 不出现 key / token / master_key 字样的输入框, 也不写
 *     localStorage / sessionStorage。
 *  3. 真实数据驱动: 采集间隔来自 /api/health、开关态来自 /api/settings/features、
 *     KEY READY 来自 /api/secrets/status、源健康复用壳的 usePipe。
 *  4. 破坏性 UI 缺席: DANGER ZONE 只做能力盘点, 无触发按钮。
 *  5. 后端不可达时降级为占位, 不白屏。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

class MockEventSource {
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(url: string) { this.url = url; }
  close() {}
}

const FEATURES_FIXTURE = {
  codegarden: true,
  codegarden_phase2b: false,
  mcp: false,
  sync: true,
  tech_stack: false,
  security_graph: false,
  secnews: true,
  crm: true,
  enabled_extensions: ['sync', 'secnews', 'crm'],
};

const LLM_FIXTURE = {
  scenario: 'S2',
  description: '仅 T1 评分可用，T3 生成交由外部 agent',
  requires_external_agent: true,
  t1_available: true,
  t3_available: false,
  llm_enabled: true,
  default_provider: 'sensenova',
  fallback_order: ['sensenova', 'ollama'],
  providers: {
    sensenova: { type: 'openai_compatible', model_score: 'deepseek-v3', model_summary: 'deepseek-r1', configured: true },
    ollama: { type: 'local', model_score: 'qwen2.5', model_summary: 'qwen2.5', configured: false },
  },
};

const HEALTH_FIXTURE = {
  version: '0.6.2',
  status: 'ok',
  uptime_s: 93784,
  collect_interval_seconds: 300,
  components: {
    db: { ok: true },
    scheduler: {
      ok: true,
      jobs: ['collect_all', 'trend_rebuild'],
      details: [
        { id: 'collect_all', name: 'Collect all', next: new Date(Date.now() + 42_000).toISOString() },
        { id: 'trend_rebuild', name: 'Trend rebuild', next: new Date(Date.now() + 120_000).toISOString() },
      ],
    },
    cache: { ok: true },
    collectors: { ok: true },
    proxy: { ok: true, mode: 'off' },
  },
  time: new Date().toISOString(),
};

const SECRETS_FIXTURE = { version: '1.0', setup: true, unlocked: false, expires_at: null, remaining_seconds: 0, keychain_persisted: true };

const SOURCES_FIXTURE = {
  sources: [
    { category: 'security', source_name: 'FreeBuf', status: 'active', total_items: 120, last_seen_at: new Date(Date.now() - 12 * 60_000).toISOString() },
    { category: 'security', source_name: 'Krebs', status: 'stale', total_items: 30, last_seen_at: new Date(Date.now() - 2 * 3600_000).toISOString() },
    { category: 'tech', source_name: 'HN', status: 'dead', total_items: 200, last_seen_at: new Date(Date.now() - 3 * 86400_000).toISOString() },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = (url.startsWith('/api/settings/features') ? FEATURES_FIXTURE
      : url.startsWith('/api/llm/status') ? LLM_FIXTURE
        : url.startsWith('/api/health') ? HEALTH_FIXTURE
          : url.startsWith('/api/secrets/status') ? SECRETS_FIXTURE
            : url.startsWith('/api/sources/health') ? SOURCES_FIXTURE
              : {}) as unknown;
    void init;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
}

import { SentinelSettingsPage } from './SentinelSettingsPage';

describe('SentinelSettingsPage — 哨兵终端设置屏 (只读)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  let originalEventSource: typeof EventSource;
  let lsSpy: ReturnType<typeof vi.spyOn>;
  let ssSpy: ReturnType<typeof vi.spyOn>;

  const openTab = (label: string) => fireEvent.click(screen.getByRole('tab', { name: label }));

  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
    originalEventSource = globalThis.EventSource;
    (globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;
    lsSpy = vi.spyOn(window.localStorage, 'setItem');
    ssSpy = vi.spyOn(window.sessionStorage, 'setItem');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (globalThis as unknown as { EventSource: unknown }).EventSource = originalEventSource;
    vi.restoreAllMocks();
  });

  it('渲染骨架: 只读徽标 + 四个分区 tab + 右栏三卡', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);

    expect(screen.getByText('SecNews')).toBeInTheDocument();
    expect(screen.getByText('PIPELINE LIVE')).toBeInTheDocument();
    expect(screen.getByText('READ-ONLY CONSOLE')).toBeInTheDocument();
    for (const label of ['采集与调度', '能力开关', '模型与密钥', '危险区']) {
      expect(screen.getByRole('tab', { name: label })).toBeInTheDocument();
    }
    await waitFor(() => expect(screen.getByRole('tabpanel')).toBeInTheDocument());
    expect(screen.getByText('管道体检')).toBeInTheDocument();
    expect(screen.getByText('安全姿态')).toBeInTheDocument();
    expect(screen.getByText('本机与版本')).toBeInTheDocument();
    // 安全姿态三条: 密钥就绪 / 直连 / 绑定地址需自查
    expect(screen.getByText('KEY READY')).toBeInTheDocument();
    expect(screen.getByText('DIRECT CONNECT')).toBeInTheDocument();
    expect(screen.getByText('CHECK BIND HOST')).toBeInTheDocument();
  });

  it('采集间隔与调度来自 /api/health 真实字段, 源健康复用壳的 usePipe', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText('*/300s').length).toBeGreaterThan(1));

    // 四格调度数据
    expect(screen.getByText('5 min / 轮 · collect_all + trend_rebuild 同频')).toBeInTheDocument();
    expect(screen.getByText('v0.6.2')).toBeInTheDocument();
    // 心跳条统计 (1 active / 1 stale / 1 dead)
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    // 源清单来自壳已拉的 /api/sources/health, 本页不再请求该端点
    const called = fetchMock.mock.calls.map(c => String(c[0]));
    expect(called.filter(u => u.startsWith('/api/sources/health')).length).toBe(1);
    expect(screen.getByText('FreeBuf')).toBeInTheDocument();
    expect(screen.getAllByText('重试中').length).toBeGreaterThan(0);
  });

  it('能力开关标签页: features 真实态映射为 chip, 且全部开关为 disabled 只读', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('tab', { name: '能力开关' })).toBeInTheDocument());
    openTab('能力开关');

    await waitFor(() => expect(screen.getByText('SecNews 情报核心')).toBeInTheDocument());
    expect(document.querySelector('.st-tblfoot')?.textContent).toBe('enabled_extensions · sync · secnews · crm');
    expect(screen.getByText('backend/config/feature_gates.toml')).toBeInTheDocument();

    const switches = document.querySelectorAll<HTMLButtonElement>('.st-switch');
    expect(switches.length).toBeGreaterThan(0);
    for (const sw of Array.from(switches)) {
      expect(sw.disabled).toBe(true);
      expect(sw.getAttribute('role')).toBe('switch');
    }
  });

  it('模型与密钥标签页: KEY READY 与场景来自非敏感状态字段', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('tab', { name: '模型与密钥' })).toBeInTheDocument());
    openTab('模型与密钥');

    await waitFor(() => expect(screen.getAllByText('KEY READY').length).toBeGreaterThan(0));
    expect(screen.getAllByText('S2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('sensenova').length).toBeGreaterThan(0);
    expect(screen.getByText(/回退序 sensenova → ollama/)).toBeInTheDocument();
    expect(screen.getByText('deepseek-v3 / deepseek-r1')).toBeInTheDocument();
    // 密钥说明存在, 但不出现任何密钥输入控件
    expect(screen.getByText(/新增、轮换或导出请到密钥管理页/)).toBeInTheDocument();
  });

  it('危险区只做只读盘点: 列端点与「本屏可达=否」, 无任何触发按钮', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('tab', { name: '危险区' })).toBeInTheDocument());
    openTab('危险区');

    await waitFor(() => expect(screen.getByText('DANGER ZONE')).toBeInTheDocument());
    expect(screen.getByText('POST /api/maintenance/cleanup')).toBeInTheDocument();
    expect(screen.getByText('POST /api/secrets/reset')).toBeInTheDocument();
    expect(screen.getAllByText('否').length).toBeGreaterThanOrEqual(10);
    expect(screen.getByText(/操作请在本地终端完成|需要执行时请在本地终端完成/)).toBeInTheDocument();

    // 面板内除 tab / 顶部两个只读导航按钮外没有额外动作按钮
    const panel = screen.getByRole('tabpanel');
    expect(panel.querySelectorAll('button').length).toBe(0);
    for (const word of ['清空', '重置全部', '删除', '立即同步', '推送', 'VACUUM 现在执行']) {
      expect(screen.queryByRole('button', { name: new RegExp(word) })).toBeNull();
    }
  });

  it('安全硬约束: 全程只发 GET, 不写 localStorage/sessionStorage, 无密钥输入框', async () => {
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText('*/300s').length).toBeGreaterThan(1));
    openTab('能力开关');
    openTab('模型与密钥');
    openTab('危险区');
    const beforeRefresh = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '刷新状态' }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(beforeRefresh));

    const methods = fetchMock.mock.calls.map(c => String((c[1] as { method?: string })?.method ?? 'GET').toUpperCase());
    expect(methods.every(m => m === 'GET')).toBe(true);
    const urls = fetchMock.mock.calls.map(c => String(c[0]));
    expect(urls.every(u => u.startsWith('/api/'))).toBe(true);
    expect(urls.some(u => /master_key|reveal|export|unlock|password/i.test(u))).toBe(false);

    expect(lsSpy).not.toHaveBeenCalled();
    expect(ssSpy).not.toHaveBeenCalled();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.querySelector('input[name*="key" i]')).toBeNull();
    expect(document.body.innerHTML).not.toMatch(/dangerouslySetInnerHTML/);
  });

  it('后端不可达 → 全部降级为占位且不崩溃', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<MemoryRouter><SentinelSettingsPage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText('采集节奏与源状态')).toBeInTheDocument());
    expect(screen.getByText(/后端未响应/)).toBeInTheDocument();
    openTab('能力开关');
    await waitFor(() => expect(screen.getByText(/未能读取 \/api\/settings\/features/)).toBeInTheDocument());
    openTab('模型与密钥');
    await waitFor(() => expect(screen.getAllByText('--').length).toBeGreaterThan(3));
  });
});
