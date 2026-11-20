/**
 * QualitySettings 组件测试 — 2026-09-22 IA 重构后修剪.
 *
 * 2026-09-22 IA 重构: Provider/密钥/场景模型面板迁出至 ModelsSettings (模型配置唯一入口),
 * 对应用例 (ProviderPanel 切换 / SecretsPanel CRUD / ScenarioModelsPanel) 已删除
 * (SecretsPanel 本身 2026-11-19 随密钥域一并删除),
 * 面板行为契约由 ModelsSettings 装配测试 + 面板未改动的既有实现兜底。
 *
 * 覆盖 (DEV-0243 改版):
 *  A. open 门控: open=false 不触发顶层状态拉取 (/api/quality/rules + /api/llm/status)
 *  B. LLM 检测真实状态化: 无假开关/无 PUT; chip 反映 gate_detect_available;
 *     未启用时给出长期生效指引
 *  C. 质量规则面板渲染回归 (2026-11-20): 异步 initialRules 同步渲染, 失效不崩
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
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
// C. 规则行渲染回归 (2026-11-20 失效修复) — 异步 initialRules 必须同步进面板
//    失效模式: QualityRulesPanel 用 useState(initialRules) 捕获首帧空数组,
//    父组件 fetch 完成后不再生效 → 「质量设置 (0) / 加载中...」永驻,
//    编辑与应用质量配置整链死锁。此用例锁定该链路第一环。
// ===================================================================

describe('QualitySettings — 质量规则面板渲染', () => {
  it('open=true 且 GET /api/quality/rules 返回后, 面板渲染规则行而非「加载中」', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'env', 'env', true));
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    const panel = await waitFor(() => {
      const el = screen.getByTestId('quality-rules-panel');
      expect(el).toHaveTextContent('质量设置 (1)');
      return el;
    });
    expect(panel).not.toHaveTextContent('加载中');
    // 规则行控件存在且带初始值 (number → st-input)
    const input = within(panel).getByLabelText('quality.min_score');
    expect(input).toHaveValue(30);
  });

  it('GET 失败时面板保持「加载中 (0)」不崩, 应用按钮不误报变更', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.reject(new Error('backend down'));
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({}));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    // flush GET reject 引发的 promise 状态收敛, 避免 act 警告
    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    const panel = screen.getByTestId('quality-rules-panel');
    expect(panel).toHaveTextContent('质量设置 (0)');
    fireEvent.click(within(panel).getByRole('button', { name: '应用质量配置' }));
    await waitFor(() => {
      expect(panel).toHaveTextContent('无变更');
    });
    // 失败路径未发出 PUT (rules 为空 → changed 为空)
    const putCalls = mockFetch.mock.calls.filter(
      c => c[0] === '/api/quality/rules' && (c[1] as RequestInit)?.method === 'PUT',
    );
    expect(putCalls).toHaveLength(0);
  });
});

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
