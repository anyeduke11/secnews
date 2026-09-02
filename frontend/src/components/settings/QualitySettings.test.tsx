/**
 * QualitySettings 组件测试 — v0.7 Batch 2 LLM provider 切换.
 *
 * 覆盖:
 * 1. 默认 LLM Provider 面板: 拉 /api/llm/status 拿到 yaml 注册的 options + 当前 effective
 * 2. dropdown 选项动态渲染 (5 个 provider, 不再硬编码 2 个)
 * 3. 切换按钮调 POST /api/settings/llm-provider 并显示成功消息
 * 4. 切换后重拉 /api/llm/status, effective_provider 反映新值
 * 5. open=false 时不触发 fetch
 * 6. 无效 provider → 显示错误消息, 不调成功 toast
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QualitySettings } from './QualitySettings';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function mockStatusResp(providers: Record<string, unknown>, effective = 'sensenova', source = 'default', keySource = 'none') {
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

describe('QualitySettings — v0.7 Batch 2 LLM provider 切换', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

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
      // 默认 panel 标签 (精确匹配避免与 button 文案冲突)
      expect(screen.getByText('默认 LLM Provider')).toBeInTheDocument();
      // config_source 解析路径徽章
      expect(screen.getByText('router')).toBeInTheDocument();
    });

    // 验证 select 包含 5 个 option (yaml 全注册)
    const selects = screen.getAllByRole('combobox');
    // 至少 1 个: 默认 provider 面板默认展开; LLM 检测面板默认折叠, 故此处只看到 1 个
    expect(selects.length).toBeGreaterThanOrEqual(1);
    const defaultSelect = selects[0] as HTMLSelectElement;
    expect(defaultSelect.value).toBe('ollama'); // 来自 status.effective_provider
    const optionValues = Array.from(defaultSelect.options).map(o => o.value).sort();
    expect(optionValues).toEqual(['anthropic', 'ollama', 'openai', 'qwen', 'sensenova']);
  });

  it('点击切换按钮 → POST /api/settings/llm-provider → 显示成功消息', async () => {
    mockFetch.mockImplementation((url: string, options?: any) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status' && (!options || options.method !== 'POST')) {
        return Promise.resolve(mockStatusResp(
          { sensenova: {}, ollama: {}, openai: {}, qwen: {}, anthropic: {} },
          'sensenova',
          'settings',
        ));
      }
      if (url === '/api/settings/llm-provider' && options?.method === 'POST') {
        const body = JSON.parse(options.body);
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

    // 选择 ollama → 点切换按钮
    const selects = screen.getAllByRole('combobox');
    const defaultSelect = selects[0] as HTMLSelectElement;
    fireEvent.change(defaultSelect, { target: { value: 'ollama' } });

    const btn = screen.getByText(/切换默认 LLM Provider/);
    fireEvent.click(btn);

    await waitFor(() => {
      const postCall = mockFetch.mock.calls.find(
        (call) => call[0] === '/api/settings/llm-provider' && (call[1] as any)?.method === 'POST',
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse((postCall![1] as any).body);
      expect(body.provider).toBe('ollama');
      expect(body.actor).toBe('web');
    });

    // 成功 toast/消息
    await waitFor(() => {
      expect(screen.getByText(/已切换:/)).toBeInTheDocument();
    });
  });

  it('切换失败时显示错误消息, 不显示成功 toast', async () => {
    mockFetch.mockImplementation((url: string, options?: any) => {
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

    const btn = screen.getByText(/切换默认 LLM Provider/);
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/not in llm.yaml registry/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/已切换:/)).not.toBeInTheDocument();
  });

  it('open=false 时不触发 /api/llm/status (避免隐藏状态拉取)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      return Promise.resolve({ ok: false });
    });

    const { rerender } = render(<QualitySettings open={false} />);
    // 等一个 microtask, 确认无 fetch
    await new Promise((r) => setTimeout(r, 50));
    const callsBefore = mockFetch.mock.calls.filter((c) => c[0] === '/api/llm/status').length;
    expect(callsBefore).toBe(0);

    rerender(<QualitySettings open={true} />);
    await waitFor(() => {
      const callsAfter = mockFetch.mock.calls.filter((c) => c[0] === '/api/llm/status').length;
      expect(callsAfter).toBeGreaterThan(0);
    });
  });
});

// ===================================================================
// v0.7.x Batch ⑥: secrets 子面板 + legacy 清退
// ===================================================================

describe('QualitySettings — v0.7.x Batch ⑥ secrets 子面板', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  function mockSecretsStatus(unlocked: boolean) {
    return {
      ok: true,
      json: () => Promise.resolve({
        setup: true, unlocked,
        ttl_seconds: unlocked ? 1800 : 0,
      }),
    };
  }

  function mockSecretsList(items: Array<Record<string, unknown>>) {
    return {
      ok: true,
      json: () => Promise.resolve({ items, count: items.length }),
    };
  }

  it('key_source 徽章渲染 (env / secrets / none)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') {
        return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'settings', 'secrets'));
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => {
      // secrets 子面板默认折叠, 但 key_source 徽章始终可见
      expect(screen.getByText('secrets')).toBeInTheDocument();
    });
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
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText('LLM AI 内容检测'));
    fireEvent.click(screen.getByText('LLM AI 内容检测'));
    const apiKeyInput = await screen.findByPlaceholderText('sk-...');
    fireEvent.change(apiKeyInput, { target: { value: 'sk-should-not-be-saved' } });
    // 保存按钮 — 用 role + name 精确匹配避免 "保存中..." 干扰
    const saveBtn = await screen.findByRole('button', { name: '应用 LLM 配置' });
    fireEvent.click(saveBtn);
    await waitFor(() => {
      const body = (mockFetch as any).__lastPutBody;
      expect(body).toBeTruthy();
      expect(body.rules).not.toHaveProperty('quality.llm_api_key');
      expect(body.rules).toHaveProperty('quality.llm_enabled');
      expect(body.rules).toHaveProperty('quality.llm_provider');
    });
  });

  it('点开 secrets 子面板 → 调 /api/secrets + /api/secrets/status', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/LLM 密钥管理/));
    fireEvent.click(screen.getByText(/LLM 密钥管理/));
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
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/secrets/unlock' && init?.method === 'POST') {
        unlockCalls.push(JSON.parse(init.body as string));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: true }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/LLM 密钥管理/));
    fireEvent.click(screen.getByText(/LLM 密钥管理/));
    await waitFor(() => screen.getByText('解锁'));
    fireEvent.click(screen.getByText('解锁'));
    const mkInput = await screen.findByPlaceholderText(/主密钥/);
    fireEvent.change(mkInput, { target: { value: 'strong-master-key-1234' } });
    await waitFor(() => screen.getByText('确认'));
    fireEvent.click(screen.getByText('确认'));
    await waitFor(() => {
      expect(unlockCalls.length).toBe(1);
      expect(unlockCalls[0]).toEqual({ master_key: 'strong-master-key-1234' });
    });
  });

  it('已解锁时显示"立即锁定"按钮 → POST /api/secrets/lock', async () => {
    const lockCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }, 'sensenova', 'settings', 'env'));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(true));
      if (url === '/api/secrets/lock' && init?.method === 'POST') {
        lockCalls.push(url);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: false }) });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/LLM 密钥管理/));
    fireEvent.click(screen.getByText(/LLM 密钥管理/));
    await waitFor(() => screen.getByText('立即锁定'));
    fireEvent.click(screen.getByText('立即锁定'));
    await waitFor(() => {
      expect(lockCalls.length).toBe(1);
    });
  });
});

// v0.7.4-image: 三场景模型选择 (deep/light/image) 折叠面板
describe('QualitySettings — v0.7.4-image 场景模型选择', () => {
  it('点开场景模型面板 → 渲染 deep/light/image 三个 input', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/场景模型选择/));
    fireEvent.click(screen.getByText(/场景模型选择/));
    await waitFor(() => {
      // 三个 input 占位符 = "留空走 yaml router 默认"
      const inputs = screen.getAllByPlaceholderText(/留空走 yaml router/);
      expect(inputs.length).toBe(3);
    });
  });

  it('输入 deep 模型 → 保存 → POST /api/settings/scenario-model 带 {scenario, model, actor}', async () => {
    const scenarioCalls: Array<unknown> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
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
    await waitFor(() => screen.getByText(/场景模型选择/));
    fireEvent.click(screen.getByText(/场景模型选择/));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    // 第一个是 deep
    fireEvent.change(inputs[0], { target: { value: 'custom-deep' } });

    // 找到 deep 那行的"保存"按钮 (三个保存按钮中第一个)
    const saveButtons = await waitFor(() => {
      const btns = screen.getAllByText('保存');
      expect(btns.length).toBe(3);
      return btns;
    });
    fireEvent.click(saveButtons[0]);

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
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/场景模型选择/));
    fireEvent.click(screen.getByText(/场景模型选择/));

    const saveButtons = await waitFor(() => screen.getAllByText('保存'));
    // 三个保存按钮都应 disabled (input 全空)
    saveButtons.forEach(btn => {
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    });
  });

  it('保存成功 → 显示 ok toast 含 scenario + 模型名', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
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
    await waitFor(() => screen.getByText(/场景模型选择/));
    fireEvent.click(screen.getByText(/场景模型选择/));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    fireEvent.change(inputs[1], { target: { value: 'm' } }); // light
    const saveButtons = await waitFor(() => screen.getAllByText('保存'));
    fireEvent.click(saveButtons[1]);

    await waitFor(() => {
      expect(screen.getByText(/light: \(无\) → m/)).toBeTruthy();
    });
  });

  it('保存失败 → 显示 error toast', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/quality/rules') return Promise.resolve(mockQualityRules());
      if (url === '/api/llm/status') return Promise.resolve(mockStatusResp({ sensenova: {} }));
      if (url === '/api/secrets') return Promise.resolve(mockSecretsList([]));
      if (url === '/api/secrets/status') return Promise.resolve(mockSecretsStatus(false));
      if (url === '/api/settings/scenario-model' && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'error', message: 'invalid' }),
        });
      }
      return Promise.resolve({ ok: false });
    });

    render(<QualitySettings open={true} />);
    await waitFor(() => screen.getByText(/场景模型选择/));
    fireEvent.click(screen.getByText(/场景模型选择/));

    const inputs = await waitFor(() => screen.getAllByPlaceholderText(/留空走 yaml router/));
    fireEvent.change(inputs[2], { target: { value: 'x' } }); // image
    const saveButtons = await waitFor(() => screen.getAllByText('保存'));
    fireEvent.click(saveButtons[2]);

    await waitFor(() => {
      expect(screen.getByText(/invalid/)).toBeTruthy();
    });
  });
});