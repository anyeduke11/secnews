/**
 * ProxySettings 契约测试 (cadence 修正批 T5)。
 * 后端契约: GET /api/proxy/settings → {settings:{mode,no_proxy}, effective_proxy, health, builtin}
 *           GET /api/proxy/test → {status, summary, results:[{name,url,policy,direct,proxy,ok}]}
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ProxySettings } from './ProxySettings';

const SETTINGS = {
  version: '0.8.5',
  settings: { mode: 'builtin', http_proxy: '', https_proxy: '', socks_proxy: '', no_proxy: 'localhost,*.cn,36kr.com' },
  valid_modes: ['off', 'builtin', 'auto', 'manual'],
  effective_proxy: 'http://127.0.0.1:7897',
  builtin: { proxy_url: 'http://127.0.0.1:7897', no_proxy: 'localhost,*.cn' },
  health: { circuit_open: false, open_remaining_seconds: 0, consecutive_failures: 0, fail_threshold: 3, open_seconds: 300, opened_count: 0, total_failures: 0, total_successes: 0, last_error: '' },
  detected_system_proxy: null,
};

const TEST = {
  status: 'degraded',
  summary: '经代理 4/5 可达, 直连 3/5 可达; 国外站经代理 2/3',
  health: SETTINGS.health,
  results: [
    { name: 'GitHub Trending', host: 'github.com', url: 'https://github.com/trending', policy: 'proxy', direct: { ok: false, error: 'timeout>8s', ms: 8001 }, proxy: { ok: true, status: 200, ms: 4700 }, ok: true },
    { name: '36氪', host: '36kr.com', url: 'https://36kr.com/', policy: 'direct', direct: { ok: true, status: 200, ms: 300 }, proxy: { ok: true, status: 200, ms: 380 }, ok: true },
  ],
};

function makeFetch(overrides: Record<string, unknown> = {}) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    let body: unknown = {};
    if (url.endsWith('/api/proxy/settings') && (!init || init.method === undefined)) body = overrides.settings ?? SETTINGS;
    else if (url.endsWith('/api/proxy/settings') && init?.method === 'PUT') body = { status: 'ok', ...SETTINGS, settings: { ...SETTINGS.settings, ...JSON.parse(String(init.body)) } };
    else if (url.endsWith('/api/proxy/test')) body = overrides.test ?? TEST;
    else if (url.endsWith('/api/proxy/health/reset')) body = { status: 'ok', health: SETTINGS.health };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
}

describe('ProxySettings (T5 契约)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('加载后显示内置模式、生效代理与绕行清单 (读 settings.mode / settings.no_proxy / effective_proxy)', async () => {
    render(<ProxySettings open />);
    await waitFor(() => expect(screen.getAllByText('内置代理').length).toBeGreaterThan(0));
    expect(screen.getByText('代理就位')).toBeInTheDocument();
    expect(screen.getAllByText('http://127.0.0.1:7897').length).toBeGreaterThan(0);
    expect((screen.getByPlaceholderText(/localhost,127.0.0.1/) as HTMLInputElement).value).toBe('localhost,*.cn,36kr.com');
  });

  it('熔断中显示 "熔断 → 直连" 与闭合按钮', async () => {
    fetchMock = makeFetch({ settings: { ...SETTINGS, health: { ...SETTINGS.health, circuit_open: true, open_remaining_seconds: 120, consecutive_failures: 3, total_failures: 3 } } });
    vi.stubGlobal('fetch', fetchMock);
    render(<ProxySettings open />);
    await waitFor(() => expect(screen.getByText('熔断 → 直连')).toBeInTheDocument());
    expect(screen.getByText(/剩余 120s/)).toBeInTheDocument();
    expect(screen.getByText('闭合熔断')).toBeInTheDocument();
  });

  it('测试连通性渲染 直连/经代理 并列表与汇总', async () => {
    render(<ProxySettings open />);
    await waitFor(() => expect(screen.getByText('测试连通性')).toBeInTheDocument());
    fireEvent.click(screen.getByText('测试连通性'));
    await waitFor(() => expect(screen.getByText('GitHub Trending')).toBeInTheDocument());
    expect(screen.getByText('timeout>8s')).toBeInTheDocument();
    expect(screen.getByText('200 · 4700ms')).toBeInTheDocument();
    expect(screen.getByText(/国外站经代理 2\/3/)).toBeInTheDocument();
    expect(screen.getByText('2/2')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(c => String(c[0]).endsWith('/api/proxy/test'))).toBe(true);
  });

  it('保存以后端字段名提交 {mode, no_proxy}', async () => {
    render(<ProxySettings open />);
    await waitFor(() => expect(screen.getByText('关闭')).toBeInTheDocument());
    fireEvent.click(screen.getByText('关闭'));
    fireEvent.click(screen.getByText('保存设置'));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(c => (c[1] as RequestInit | undefined)?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({ mode: 'off', no_proxy: 'localhost,*.cn,36kr.com' });
    });
  });
});
