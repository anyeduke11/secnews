/**
 * ModelPoolPanel 测试 (DEV-0244)
 *
 * 契约: pi 永不出现在平台网格 (Agent 单列); 未配置平台显示 key 输入;
 * 探测结果渲染模型数; 密钥经 POST /api/secrets (保险箱同链)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ModelPoolPanel } from './ModelPoolPanel';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

const POOL_FIXTURE = {
  version: 'test',
  platforms: [
    { name: 'sensenova', label: '商汤日日新', base_url: 'https://token.sensenova.cn/v1',
      key_env: 'SENSENOVA_API_KEY', configured: true, key_source: 'env',
      available: true, models: ['sensenova-6.8-flash-lite', 'deepseek-v4-pro'],
      model_count: 2, latency_ms: 120, error: null },
    { name: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1',
      key_env: 'DEEPSEEK_API_KEY', configured: false, key_source: 'none',
      available: false, models: [], model_count: 0, latency_ms: null, error: 'no_key' },
  ],
  agent_channels: [
    { name: 'pi', kind: 'subprocess-agent', desc: 'pi 子进程 (非模型池成员)' },
  ],
  probed: true,
};

beforeEach(() => {
  mockFetch.mockReset();
});

function renderPanel() {
  return render(<ModelPoolPanel />);
}

describe('ModelPoolPanel — 模型池 (DEV-0244)', () => {
  it('平台网格渲染 + pi 只在 Agent 通道单列, 不混入模型平台', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/llm/pool') return Promise.resolve({ ok: true, json: () => Promise.resolve(POOL_FIXTURE) });
      if (url === '/api/secrets/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: true }) });
      return Promise.resolve({ ok: false });
    });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('pool-sensenova')).toBeInTheDocument();
      expect(screen.getByTestId('pool-deepseek')).toBeInTheDocument();
    });
    // 可用平台: 模型数 chip
    expect(screen.getByTestId('pool-sensenova')).toHaveTextContent('可用 2 款模型');
    // 未配置平台: key 输入 + 保存并检测
    expect(screen.getByLabelText('DeepSeek API Key')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存并检测 DeepSeek' })).toBeInTheDocument();
    // pi 只出现在 agent 区
    expect(screen.getByTestId('agent-pi')).toBeInTheDocument();
    expect(screen.getByTestId('agent-pi')).toHaveTextContent('Agent 通道');
    // 平台网格里没有 pi
    expect(screen.queryByTestId('pool-pi')).not.toBeInTheDocument();
  });

  it('保存并检测: 密钥走 POST /api/secrets + 探测结果回填 chip', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.startsWith('/api/llm/pool?probe=1&only=')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ...POOL_FIXTURE,
            platforms: [{ ...POOL_FIXTURE.platforms[1], configured: true, key_source: 'secrets',
              available: true, model_count: 3, models: ['m1', 'm2', 'm3'] }],
          }),
        });
      }
      if (url === '/api/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 1 }) });
      }
      if (url === '/api/llm/pool') return Promise.resolve({ ok: true, json: () => Promise.resolve(POOL_FIXTURE) });
      if (url === '/api/secrets/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: true }) });
      return Promise.resolve({ ok: false });
    });
    renderPanel();
    const input = await screen.findByLabelText('DeepSeek API Key');
    fireEvent.change(input, { target: { value: 'sk-test-123' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并检测 DeepSeek' }));

    await waitFor(() => {
      expect(screen.getByTestId('pool-msg')).toHaveTextContent('检测成功: 3 款模型可用');
    });
    // 密钥写入保险箱端点 (provider=平台名), 不落 settings.kv
    const save = calls.find(c => c.url === '/api/secrets' && c.init?.method === 'POST');
    expect(save).toBeTruthy();
    const body = JSON.parse(save!.init!.body as string);
    expect(body.provider).toBe('deepseek');
    expect(body.api_key).toBe('sk-test-123');
  });

  it('force 写入成功 → 提示走 warn 色 (未经验证), 非 ok 绿', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === '/api/llm/pool/route') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'ok',
            message: '已写入 t1_score → sensenova/m1; 热重载 ≤5s 生效; 已跳过在线探测 (force) — 模型可用性未经验证, 若调用失败请回到模型池探测或检查模型名',
          }),
        });
      }
      if (url === '/api/llm/pool') return Promise.resolve({ ok: true, json: () => Promise.resolve(POOL_FIXTURE) });
      if (url === '/api/secrets/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ unlocked: true }) });
      return Promise.resolve({ ok: false });
    });
    renderPanel();
    // sensenova 已配置可用 → 写入路由按钮直接可见
    const routeBtn = await screen.findByRole('button', { name: '写入路由 商汤日日新' });
    fireEvent.click(routeBtn);
    fireEvent.click(await screen.findByRole('button', { name: '确认写入 商汤日日新 路由' }));

    await waitFor(() => {
      expect(screen.getByTestId('pool-msg')).toHaveTextContent('已跳过在线探测 (force)');
    });
    // warn 态断言: 未经验证的写入不得渲染成绿色成功
    expect(screen.getByTestId('pool-msg')).toHaveClass('warn');
    expect(screen.getByTestId('pool-msg')).not.toHaveClass('ok');
  });
});
