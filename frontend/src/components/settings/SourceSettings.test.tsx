/**
 * SourceSettings — 手动添加入口 (custom 源) 提交链路测试 (治理 T3 核验)。
 *
 * 锁定契约: "信源管理"添加卡 (URL + 名称可选) → addCustomSource
 * → POST /api/sources/custom (body 带 url/name), 成功后显式提示 + 清空输入。
 * 这是 /api/sources/custom 的唯一前端消费者 — 手动添加入口已存在, 无需新卡。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SourceSettings } from './SourceSettings';

function jsonResponse(payload: unknown): Response {
  return { ok: true, json: () => Promise.resolve(payload) } as unknown as Response;
}

describe('SourceSettings — 手动添加源入口 (治理 T3 核验)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  type AddResp = { status: string; id: number; url: string; category: string; probe: Record<string, unknown> };

  function stubFetch(postCustom: AddResp) {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();
      if (url.includes('/api/sources/custom') && method === 'POST') {
        return Promise.resolve(jsonResponse(postCustom));
      }
      // GET /api/sources/custom (列表) / /api/sources/stats / health/v2 / /api/health
      return Promise.resolve(jsonResponse({}));
    }));
  }

  it('添加卡提交: URL+名称 → POST /api/sources/custom, 成功提示', async () => {
    const user = userEvent.setup();
    stubFetch({
      status: 'ok', id: 7, url: 'https://example.com/news',
      category: 'security', probe: { ok: true, latency_ms: 120 },
    });
    render(<SourceSettings open />);

    await user.type(screen.getByLabelText('新信源 URL'), 'https://example.com/news');
    await user.type(screen.getByLabelText('新信源 名称'), '示例源');
    await user.click(screen.getByRole('button', { name: /添加（自动探测\+分类）/ }));

    await waitFor(() =>
      expect(screen.getByTestId('source-settings').textContent).toContain('已添加'),
    );
    const postCall = vi.mocked(fetch).mock.calls.find(
      ([u, init]) => String(u).includes('/api/sources/custom') && (init?.method === 'POST'),
    );
    expect(postCall).toBeTruthy();
    expect(JSON.parse(String(postCall![1]!.body))).toEqual({
      url: 'https://example.com/news',
      name: '示例源',
    });
    // 成功后输入清空
    expect(screen.getByLabelText('新信源 URL')).toHaveValue('');
  });

  it('URL 为空时前端拦截, 不发请求', async () => {
    const user = userEvent.setup();
    stubFetch({ status: 'ok', id: 1, url: '', category: 'ai', probe: {} });
    render(<SourceSettings open />);

    await user.click(screen.getByRole('button', { name: /添加（自动探测\+分类）/ }));

    expect(screen.getByTestId('source-settings').textContent).toContain('URL 不能为空');
    const postCall = vi.mocked(fetch).mock.calls.find(
      ([u, init]) => String(u).includes('/api/sources/custom') && (init?.method === 'POST'),
    );
    expect(postCall).toBeUndefined();
  });
});
