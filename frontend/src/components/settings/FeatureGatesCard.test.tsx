/**
 * FeatureGatesCard — 能力开关卡测试
 * 意图: 16 gate 从 /api/settings/feature-gates 富信息呈现 (enabled/source/scope);
 * toggle 经 PUT /api/settings/feature-gates/{name} 可写化 — 成功更新行状态,
 * 失败 (409 env 覆盖 / 404 未知键) 行内展示 note; source=env 只读。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { FeatureGatesCard } from './FeatureGatesCard';

type GateItem = { name: string; enabled: boolean; source: string; effective_scope: string };

const NAMES = [
  'secnews', 'codegarden', 'codegarden_phase2b', 'mcp', 'sync', 'tech_stack',
  'security_graph', 'dsh', 'info_filter', 'skill_registry', 'trigger_gate',
  'user_skills', 'interest_engine', 'semantic_filter', 'ai_classify', 'pipeline_ner',
];

const GATES_RESPONSE = {
  version: 'test', count: 16,
  items: NAMES.map<GateItem>(name => ({
    name,
    enabled: name !== 'mcp',
    source: 'toml',
    effective_scope: 'startup',
  })),
};

function mockFetch(putHandler?: (name: string, body: unknown) => Response) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'PUT' && url.startsWith('/api/settings/feature-gates/')) {
      const name = url.replace('/api/settings/feature-gates/', '');
      const resp = putHandler?.(name, JSON.parse(String(init.body))) ??
        new Response(JSON.stringify({ name, enabled: true, note: '运行时读数 5s 内生效; 路由注册与 job 调度需重启后端' }), { status: 200 });
      return Promise.resolve(resp);
    }
    if (url.startsWith('/api/settings/feature-gates')) {
      return Promise.resolve(new Response(JSON.stringify(GATES_RESPONSE), { status: 200 }));
    }
    return Promise.resolve(new Response('{}', { status: 200 }));
  });
}

describe('FeatureGatesCard — 能力开关 (可写化)', () => {
  beforeEach(() => { vi.stubGlobal('fetch', mockFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染 16 个 gate 与启停状态, mcp=false 显示 OFF', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => expect(screen.getByText('能力开关')).toBeInTheDocument());
    expect(screen.getByText('secnews')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('mcp')).toBeInTheDocument());
    await waitFor(() => {
      const rows = screen.getAllByRole('switch');
      expect(rows).toHaveLength(16);
    });
  });

  it('非 env gate 的 switch 可写 (不再一律 disabled), 提示来源与重启语义', async () => {
    render(<FeatureGatesCard />);
    await waitFor(() => {
      const sw = screen.getAllByRole('switch')[0] as HTMLButtonElement;
      expect(sw.disabled).toBe(false);
    });
    expect(screen.getByText(/feature_gates\.toml/)).toBeInTheDocument();
  });

  it('source=env 的 gate switch 禁用并提示 env 优先', async () => {
    // 重 stub: mcp 标记为 env 覆盖
    const envItems = GATES_RESPONSE.items.map(g =>
      g.name === 'mcp' ? { ...g, source: 'env' } : g,
    );
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/settings/feature-gates')) {
        return Promise.resolve(new Response(
          JSON.stringify({ ...GATES_RESPONSE, items: envItems }), { status: 200 },
        ));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    }));
    render(<FeatureGatesCard />);
    await waitFor(() => expect(screen.getByText('mcp')).toBeInTheDocument());
    const sw = screen.getByRole('switch', { name: /mcp：已停用（env 覆盖，只读）/ }) as HTMLButtonElement;
    expect(sw.disabled).toBe(true);
    expect(screen.getByText(/HOTSPOT_FEATURE_GATES env 覆盖中/)).toBeInTheDocument();
  });

  it('toggle 成功: PUT 携带翻转值, 行状态更新并显示 note', async () => {
    const putSpy = vi.fn();
    vi.stubGlobal('fetch', mockFetch((name, body) => {
      putSpy(name, body);
      return new Response(JSON.stringify({ name, enabled: true, note: '运行时读数 5s 内生效; 路由注册与 job 调度需重启后端' }), { status: 200 });
    }));
    render(<FeatureGatesCard />);
    const sw = await waitFor(() => {
      const el = screen.getByRole('switch', { name: 'mcp：已停用' }) as HTMLButtonElement;
      expect(el.disabled).toBe(false);
      return el;
    });
    fireEvent.click(sw);
    await waitFor(() => expect(putSpy).toHaveBeenCalledWith('mcp', { enabled: true }));
    await waitFor(() => {
      expect((screen.getByRole('switch', { name: 'mcp：已启用' }) as HTMLButtonElement).getAttribute('aria-checked')).toBe('true');
    });
    expect(screen.getByText(/运行时读数 5s 内生效/)).toBeInTheDocument();
  });

  it('toggle 409 (env 覆盖拒绝): 状态不变, 行内展示后端 message', async () => {
    vi.stubGlobal('fetch', mockFetch(() => new Response(
      JSON.stringify({ detail: { message: 'mcp 被 HOTSPOT_FEATURE_GATES 环境变量覆盖, TOML 写入无效; 请改 env 后重启' } }),
      { status: 409 },
    )));
    render(<FeatureGatesCard />);
    const sw = await waitFor(() => {
      const el = screen.getByRole('switch', { name: 'mcp：已停用' }) as HTMLButtonElement;
      expect(el.disabled).toBe(false);
      return el;
    });
    fireEvent.click(sw);
    await waitFor(() => {
      expect(screen.getByText(/被 HOTSPOT_FEATURE_GATES 环境变量覆盖/)).toBeInTheDocument();
    });
    // 失败后状态不翻转
    expect((screen.getByRole('switch', { name: 'mcp：已停用' }) as HTMLButtonElement).getAttribute('aria-checked')).toBe('false');
  });
});
