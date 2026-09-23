/**
 * QualitySettings 组件测试 — 2026-09-22 IA 重构后修剪.
 *
 * 2026-09-22 IA 重构: Provider/密钥/场景模型面板迁出至 ModelsSettings (模型配置唯一入口),
 * 对应用例 (ProviderPanel 切换 / SecretsPanel CRUD / ScenarioModelsPanel) 已删除,
 * 面板行为契约由 ModelsSettings 装配测试 + 面板未改动的既有实现兜底。
 *
 * 覆盖 (2 用例):
 *  A. open 门控: open=false 不触发顶层状态拉取 (/api/quality/rules + /api/llm/status)
 *  B. LLM 检测 (LlmDetectionPanel): saveLlm 不再写 quality.llm_api_key 到 settings.kv (legacy 清退)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QualitySettings } from './QualitySettings';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function mockStatusResp(
  providers: Record<string, unknown>,
  effective = 'sensenova',
  source = 'default',
  keySource = 'none',
) {
  return {
    ok: true,
    json: () => Promise.resolve({
      providers,
      effective_provider: effective,
      config_source: source,
      key_source: keySource,
      scenario: 'NORMAL',
    }),
  };
}

function mockQualityRules() {
  return {
    ok: true,
    json: () => Promise.resolve({
      rules: [
        { key: 'quality.llm_enabled', value: false, default: false },
        { key: 'quality.llm_provider', value: 'sensenova', default: 'sensenova' },
      ],
    }),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

// ===================================================================
// A. open 门控 — 顶层状态拉取
// ===================================================================

describe('QualitySettings — open 门控', () => {
  it('open=false 时不触发顶层状态拉取 (/api/quality/rules + /api/llm/status)', async () => {
    // 真正被 open 门控的是 QualitySettings 顶层状态拉取, 防止隐藏状态拉取。
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      return Promise.resolve({ ok: false });
    });

    const { rerender } = render(<QualitySettings open={false} />);
    await new Promise((r) => setTimeout(r, 50));
    const callsBefore = mockFetch.mock.calls.filter(
      (c) => c[0] === '/api/llm/status' || c[0] === '/api/quality/rules',
    ).length;
    expect(callsBefore).toBe(0);

    rerender(<QualitySettings open={true} />);
    await waitFor(() => {
      const callsAfter = mockFetch.mock.calls.filter((c) => c[0] === '/api/llm/status').length;
      expect(callsAfter).toBeGreaterThan(0);
    });
  });
});

// ===================================================================
// B. LLM 检测 (LlmDetectionPanel) — legacy 清退契约
// ===================================================================

describe('QualitySettings — LLM 检测 (LlmDetectionPanel)', () => {
  it('saveLlm 不再写 quality.llm_api_key 到 settings.kv (legacy 清退)', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules' && init?.method === 'GET') {
        return Promise.resolve(mockQualityRules());
      }
      if (url === '/api/quality/rules' && init?.method === 'PUT') {
        const body = JSON.parse(init.body as string);
        (mockFetch as any).__lastPutBody = body;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
      }
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    // V2: LlmDetectionPanel 默认展开, 无需点击
    await waitFor(() => {
      expect(screen.getByLabelText('LLM AI 内容检测')).toBeInTheDocument();
    });

    // 切换启用开关 → 改 provider → 保存
    const enabledSwitch = screen.getByTestId('llm-enabled-switch');
    fireEvent.click(enabledSwitch);
    const providerSelect = screen.getByLabelText('LLM Provider') as HTMLSelectElement;
    fireEvent.change(providerSelect, { target: { value: 'ollama' } });

    const saveBtn = screen.getByRole('button', { name: '应用 LLM 配置' });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      const body = (mockFetch as any).__lastPutBody;
      expect(body).toBeTruthy();
      expect(body.rules).not.toHaveProperty('quality.llm_api_key');
      expect(body.rules).toHaveProperty('quality.llm_enabled');
      expect(body.rules).toHaveProperty('quality.llm_provider');
    });

    // 显式断言: 不应再有任何 placeholder="sk-..." 的输入框
    expect(screen.queryByPlaceholderText(/^sk-/)).not.toBeInTheDocument();
  });
});
