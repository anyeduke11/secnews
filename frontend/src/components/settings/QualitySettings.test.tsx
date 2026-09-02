/**
 * QualitySettings 组件测试 — V2 哨兵化 (settings-shell.css + 5 子组件拆分).
 *
 * V2 行为差异 (vs 旧 v0.7.x):
 *  1. ProviderPanel 默认展开 (always-rendered), 不再有折叠 toggle。
 *  2. SecretsPanel 默认展开, key_source 徽章常驻; 主操作按钮随 unlock 态变化
 *     (未解锁 → "解锁保险箱"; 已解锁 → "+ 新增密钥"), 没有 "LLM 密钥管理" 折叠面板。
 *  3. LlmDetectionPanel 默认展开 (always-rendered), sk-... 输入框已彻底删除
 *     (Batch ⑥ legacy 清退), 密钥路径只在 SecretsPanel 出现。
 *  4. ScenarioModelsPanel 默认展开 (always-rendered), 无 "场景模型选择" 折叠点击。
 *  5. QualityRulesPanel 默认展开。
 *
 * 覆盖 (14 用例):
 *  A. ProviderPanel: status 拉取 / dropdown / 切换 / 失败 / open=false
 *  B. SecretsPanel: key_source 徽章 / legacy 清退 / 面板 / unlock / lock
 *  C. ScenarioModelsPanel: 三行 / 保存 / disabled / 成功 / 失败
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

function mockSecretsStatus(unlocked: boolean) {
  return {
    ok: true,
    json: () => Promise.resolve({
      setup: true,
      unlocked,
      ttl_seconds: unlocked ? 1800 : 0,
    }),
  };
}

function mockSecretsList(items: Array<Record<string, unknown>> = []) {
  return {
    ok: true,
    json: () => Promise.resolve({ items, count: items.length }),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

// ===================================================================
// A. ProviderPanel — 默认 LLM Provider 切换
// ===================================================================

describe('QualitySettings — ProviderPanel (V2 默认展开)', () => {
  it('拉 /api/llm/status 拿 yaml 注册的 provider 列表 + 当前 effective', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp(
          {
            sensenova: { type: 'sensenova' },
            ollama: { type: 'ollama' },
            openai: { type: 'openai' },
            qwen: { type: 'dashscope' },
            anthropic: { type: 'anthropic' },
          },
          'ollama',
          'router',
        ));
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);

    await waitFor(() => {
      expect(screen.getByText('默认 LLM Provider')).toBeInTheDocument();
      expect(screen.getByText('router')).toBeInTheDocument();
    });

    // aria-label="选择默认 provider" — 锁定 ProviderPanel 自己的 select
    const defaultSelect = screen.getByLabelText('选择默认 provider') as HTMLSelectElement;
    expect(defaultSelect.value).toBe('ollama');
    const optionValues = Array.from(defaultSelect.options).map(o => o.value).sort();
    expect(optionValues).toEqual(['anthropic', 'ollama', 'openai', 'qwen', 'sensenova']);
  });

  it('点击切换按钮 → POST /api/settings/llm-provider → 显示成功消息', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status' && (!options || options.method !== 'POST')) {
        return Promise.resolve(mockStatusResp(
          { sensenova: {}, ollama: {}, openai: {}, qwen: {}, anthropic: {} },
          'sensenova',
          'settings',
        ));
      }
      if (url === '/api/settings/llm-provider' && options?.method === 'POST') {
        const body = JSON.parse(options.body as string);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'ok',
            old_provider: body.provider === 'ollama' ? 'sensenova' : null,
            new_provider: body.provider,
            valid_providers: ['sensenova', 'ollama', 'openai', 'qwen', 'anthropic'],
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);

    await waitFor(() => {
      expect(screen.getByText('默认 LLM Provider')).toBeInTheDocument();
    });

    const defaultSelect = screen.getByLabelText('选择默认 provider') as HTMLSelectElement;
    fireEvent.change(defaultSelect, { target: { value: 'ollama' } });

    const btn = screen.getByRole('button', { name: '切换默认 LLM Provider' });
    fireEvent.click(btn);

    await waitFor(() => {
      const postCall = mockFetch.mock.calls.find(
        (call) => call[0] === '/api/settings/llm-provider' && (call[1] as RequestInit)?.method === 'POST',
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse((postCall![1] as RequestInit).body as string);
      expect(body.provider).toBe('ollama');
      expect(body.actor).toBe('web');
    });

    // V2 成功 toast: "已切换: sensenova → ollama" (ProviderPanel handleSave)
    await waitFor(() => {
      expect(screen.getByText(/已切换:.*sensenova.*→.*ollama/)).toBeInTheDocument();
    });
  });

  it('切换失败时显示错误消息, 不显示成功 toast', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp(
          { sensenova: {}, ollama: {} },
          'sensenova',
          'default',
        ));
      }
      if (url === '/api/settings/llm-provider' && options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({
            code: 'INVALID_PARAM',
            message: "provider 'unknown' not in llm.yaml registry",
            trace_id: 'test-trace',
            version: '0.7.0',
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);

    await waitFor(() => {
      expect(screen.getByText('默认 LLM Provider')).toBeInTheDocument();
    });

    const btn = screen.getByRole('button', { name: '切换默认 LLM Provider' });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/not in llm.yaml registry/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/已切换:/)).not.toBeInTheDocument();
  });

  it('open=false 时不触发顶层状态拉取 (/api/quality/rules + /api/llm/status)', async () => {
    // V2: SecretsPanel 自身默认展开 (always-rendered) — 仍会在 mount 时拉 /api/secrets。
    //     真正被 open 门控的是 QualitySettings 顶层状态拉取, 防止隐藏状态拉取。
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
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
// B. SecretsPanel — LLM 密钥管理 (Batch ⑥ + V2 始终展开)
// ===================================================================

describe('QualitySettings — SecretsPanel (V2 默认展开, 无折叠)', () => {
  it('key_source 徽章渲染 (env / secrets / none)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'settings', 'secrets'));
      }
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      // SecretsPanel aria-label="LLM 密钥管理" — 确认 section 渲染
      expect(screen.getByLabelText('LLM 密钥管理')).toBeInTheDocument();
    });
    // key_source 徽章 — 通过 title 属性锁定 (title="key_source: secrets")
    const badge = await screen.findByTitle('key_source: secrets');
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toContain('secrets');
  });

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
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
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

  it('默认展开即拉 /api/secrets + /api/secrets/status', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    // V2: 无需点击任何折叠, 等 useEffect 触发
    await waitFor(() => {
      expect(mockFetch.mock.calls.some((c) => c[0] === '/api/secrets')).toBe(true);
      expect(mockFetch.mock.calls.some((c) => c[0] === '/api/secrets/status')).toBe(true);
    });
  });

  it('解锁按钮 → POST /api/secrets/unlock 带 master_key', async () => {
    const unlockCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/secrets/unlock' && init?.method === 'POST') {
        unlockCalls.push(JSON.parse(init.body as string));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: true }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      expect(screen.getByLabelText('LLM 密钥管理')).toBeInTheDocument();
    });

    // V2: 未解锁状态下, 主操作按钮文案是 "解锁保险箱"
    const unlockBtn = await screen.findByRole('button', { name: '解锁保险箱' });
    fireEvent.click(unlockBtn);

    // 弹窗出现 → 输主密钥 → 确认
    const mkInput = await screen.findByTestId('master-key-input');
    fireEvent.change(mkInput, { target: { value: 'strong-master-key-1234' } });
    const confirmBtn = screen.getByRole('button', { name: '确认' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(unlockCalls.length).toBe(1);
      expect(unlockCalls[0]).toEqual({ master_key: 'strong-master-key-1234' });
    });
  });

  it('已解锁时显示"立即锁定"按钮 → POST /api/secrets/lock', async () => {
    const lockCalls: string[] = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'settings', 'env'));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(true));
      if (url === '/api/secrets/lock' && init?.method === 'POST') {
        lockCalls.push(url);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: false }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      expect(screen.getByLabelText('LLM 密钥管理')).toBeInTheDocument();
    });

    // V2: 已解锁状态, "立即锁定" 按钮直接可见
    const lockBtn = await screen.findByRole('button', { name: '立即锁定' });
    fireEvent.click(lockBtn);

    await waitFor(() => {
      expect(lockCalls.length).toBe(1);
    });
  });
});

// ===================================================================
// C. ScenarioModelsPanel — 三场景模型 (V2 默认展开, 无折叠)
// ===================================================================

describe('QualitySettings — ScenarioModelsPanel (V2 默认展开)', () => {
  it('默认展开即渲染 deep/light/image 三个 input', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    // V2: 无需点击任何折叠
    await waitFor(() => {
      const inputs = screen.getAllByPlaceholderText(/留空走 yaml router/);
      expect(inputs.length).toBe(3);
    });
    // 确认三个 scenario section 存在
    expect(screen.getByLabelText('场景模型选择')).toBeInTheDocument();
  });

  it('输入 deep 模型 → 保存 → POST /api/settings/scenario-model 带 {scenario, model, actor}', async () => {
    const scenarioCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/settings/scenario-model' && init?.method === 'POST') {
        scenarioCalls.push(JSON.parse(init.body as string));
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'ok', scenario: 'deep', old_model: null, new_model: 'custom-deep',
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByLabelText('场景模型选择'));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    fireEvent.change(inputs[0], { target: { value: 'custom-deep' } });

    // data-testid="settings-scenario-save-deep" 锁定 deep 行保存按钮
    const saveBtn = await screen.findByTestId('settings-scenario-save-deep');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(scenarioCalls.length).toBe(1);
      const body = scenarioCalls[0] as Record<string, unknown>;
      expect(body.scenario).toBe('deep');
      expect(body.model).toBe('custom-deep');
      expect(body.actor).toBe('web');
    });
  });

  it('input 为空时, "保存" 按钮 disabled', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByLabelText('场景模型选择'));

    // 三个保存按钮都应 disabled (input 全空, isDirty=false)
    const deep = await screen.findByTestId('settings-scenario-save-deep');
    const light = await screen.findByTestId('settings-scenario-save-light');
    const image = await screen.findByTestId('settings-scenario-save-image');
    expect((deep as HTMLButtonElement).disabled).toBe(true);
    expect((light as HTMLButtonElement).disabled).toBe(true);
    expect((image as HTMLButtonElement).disabled).toBe(true);
  });

  it('保存成功 → 显示 ok toast 含 scenario + 模型名', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/settings/scenario-model' && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'ok', scenario: 'light', old_model: null, new_model: 'm',
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByLabelText('场景模型选择'));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    fireEvent.change(inputs[1], { target: { value: 'm' } }); // light
    const lightSaveBtn = await screen.findByTestId('settings-scenario-save-light');
    fireEvent.click(lightSaveBtn);

    // V2 toast 格式: "light: (无) → m"
    await waitFor(() => {
      expect(screen.getByText(/light:.*\(无\).*→.*m/)).toBeInTheDocument();
    });
  });

  it('保存失败 → 显示 error toast', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList());
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/settings/scenario-model' && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'error', message: 'invalid scenario model' }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByLabelText('场景模型选择'));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    fireEvent.change(inputs[2], { target: { value: 'x' } }); // image
    const imageSaveBtn = await screen.findByTestId('settings-scenario-save-image');
    fireEvent.click(imageSaveBtn);

    await waitFor(() => {
      expect(screen.getByText(/invalid/)).toBeInTheDocument();
    });
  });
});
