/**
 * ModelsSettings — 模型配置区装配测试
 * 意图: LLM 模型配置唯一入口 — Provider/密钥/模型池/三场景四卡齐全;
 *       模型池如实渲染 provider 状态; llm 不可达时空态不造假。
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

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/llm/status')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LLM_STATUS) } as Response);
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

  it('装配: 密钥面板 + 模型池 + provider 状态可见', async () => {
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText('模型池')).toBeInTheDocument());
    // 模型池标题先渲染, 池内容 (deepseek 模型) 异步到达 — 需 waitFor (全量并发下裸断言会时序 flake)
    await waitFor(() => expect(screen.getByText(/deepseek-v4-pro/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('secrets-panel')).toBeInTheDocument());
    // 四卡之 provider 卡: st-section aria-label 即可访问名
    expect(screen.getByRole('region', { name: '默认 LLM Provider' })).toBeInTheDocument();
    // 四卡之三场景卡: ScenarioModelsPanel data-testid = `${scope}-panel`, scope="settings-models"
    expect(screen.getByTestId('settings-models-panel')).toBeInTheDocument();
  });

  it('llm 不可达 → 模型池如实空态', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response)));
    render(<ModelsSettings />);
    await waitFor(() => expect(screen.getByText(/模型状态不可用/)).toBeInTheDocument());
  });
});
