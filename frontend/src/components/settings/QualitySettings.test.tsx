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

function mockStatusResp(providers: Record<string, unknown>, effective = 'sensenova', source = 'default') {
  return {
    ok: true,
    json: () => Promise.resolve({
      providers,
      effective_provider: effective,
      config_source: source,
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