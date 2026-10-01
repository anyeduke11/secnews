/**
 * ModelsSettings — 模型配置区装配测试 (DEV-0244 契约)
 * 意图: LLM 模型配置唯一入口 — Provider/密钥/模型池(内置平台)/三场景四卡齐全;
 *       模型池 = 内置平台网格 + pi Agent 单列; pool 不可达时空态不造假。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ModelsSettings } from './ModelsSettings';

const LLM_STATUS = {
  enabled: true,
  scenario: 'deep',
  providers: { deepseek: { status: 'ok', model: 'deepseek-v4-pro' } },
  effective_provider: 'deepseek',
  config_source: 'settings.kv',
  key_source: 'settings.kv',
};

const POOL_FIXTURE = {
  version: 'test',
  platforms: [
    { name: 'sensenova', label: '商汤日日新', base_url: 'https://token.sensenova.cn/v1',
      key_env: 'SENSENOVA_API_KEY', configured: true, key_source: 'env',
      available: true, models: ['sensenova-6.8-flash-lite'], model_count: 1,
      latency_ms: 100, error: null },
  ],
  agent_channels: [{ name: 'pi', kind: 'subprocess-agent', desc: 'pi 子进程' }],
  probed: true,
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/llm/status')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LLM_STATUS) } as Response);
    }
    if (url.startsWith('/api/llm/pool')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(POOL_FIXTURE) } as Response);
    }
    if (url.startsWith('/api/secrets/status')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ initialized: true, unlocked: false }) } as Response);
    }
    if (url.startsWith('/api/secrets')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('ModelsSettings — 模型配置区', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('装配: 密钥面板 + 模型池(内置平台) + provider 状态可见', async () => {
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText('模型池 — 内置平台')).toBeInTheDocument());
    // 池内容异步到达: 内置平台网格 + pi Agent 单列
    await waitFor(() => expect(screen.getByTestId('pool-sensenova')).toBeInTheDocument());
    expect(screen.getByTestId('pool-sensenova')).toHaveTextContent('可用 1 款模型');
    expect(screen.getByTestId('agent-pi')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('secrets-panel')).toBeInTheDocument());
    // 四卡之 provider 卡: st-section aria-label 即可访问名
    expect(screen.getByRole('region', { name: '默认 LLM Provider' })).toBeInTheDocument();
    // 四卡之三场景卡: ScenarioModelsPanel data-testid = `${scope}-panel`, scope="settings-models"
    expect(screen.getByTestId('settings-models-panel')).toBeInTheDocument();
  });

  it('pool 不可达 → 模型池如实空态', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/llm/pool')) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }));
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText(/模型池不可用/)).toBeInTheDocument());
  });
});
