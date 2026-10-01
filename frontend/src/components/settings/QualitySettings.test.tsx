/**
 * QualitySettings 组件测试 — 2026-09-22 IA 重构后修剪.
 *
 * 2026-09-22 IA 重构: Provider/密钥/场景模型面板迁出至 ModelsSettings (模型配置唯一入口),
 * 对应用例 (ProviderPanel 切换 / SecretsPanel CRUD / ScenarioModelsPanel) 已删除,
 * 面板行为契约由 ModelsSettings 装配测试 + 面板未改动的既有实现兜底。
 *
 * 覆盖 (DEV-0243 改版):
 *  A. open 门控: open=false 不触发顶层状态拉取 (/api/quality/rules + /api/llm/status)
 *  B. LLM 检测真实状态化: 无假开关/无 PUT; chip 反映 gate_detect_available;
 *     未启用时给出长期生效指引
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
  gateDetectAvailable = false,
) {
  return {
    ok: true,
    json: () => Promise.resolve({
      providers,
      effective_provider: effective,
      config_source: source,
      key_source: keySource,
      gate_detect_available: gateDetectAvailable,
      scenario: 'NORMAL',
    }),
  };
}

function mockQualityRules() {
  return {
    ok: true,
    json: () => Promise.resolve({
      rules: [
        { key: 'quality.min_score', value: 30, default: 30 },
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
// B. LLM 检测真实状态化 (DEV-0243) — 假开关清退契约
// ===================================================================

describe('QualitySettings — LLM 检测真实状态 (DEV-0243)', () => {
  it('凭据就绪 → chip 显示「检测中」; 无任何 PUT quality/rules 写入 (假开关已清退)', async () => {
    let putCalled = false;
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules' && init?.method === 'PUT') {
        putCalled = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
      }
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'env', 'env', true));
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      // 真实开关 = gate_detect_available=true → 状态 chip「检测中」
      expect(screen.getByTestId('llm-detect-state')).toHaveTextContent('检测中');
    });
    // 假开关与保存按钮不复存在
    expect(screen.queryByTestId('llm-enabled-switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '应用 LLM 配置' })).not.toBeInTheDocument();
    // 面板自身不触发 PUT (挂载阶段)
    expect(putCalled).toBe(false);
  });

  it('凭据缺失 → chip「未启用」+ 展示长期生效指引; 说明块可展开', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp({}, 'sensenova', 'default', 'none', false));
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('llm-detect-state')).toHaveTextContent('未启用');
    });
    expect(screen.getByText(/完成任一项即长期生效/)).toBeInTheDocument();

    // 展开说明 — 交代假开关清退原因
    fireEvent.click(screen.getByRole('button', { name: '为什么没有开关?' }));
    expect(screen.getByTestId('llm-detect-explain')).toHaveTextContent('DEV-0243');
  });

  it('status 拉取失败 → 面板不崩, chip 保持「未启用」诚实口径', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      return Promise.reject(new Error('backend down'));
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('llm-detect-state')).toHaveTextContent('未启用');
    });
    expect(screen.getByText(/完成任一项即长期生效/)).toBeInTheDocument();
  });
});
