/**
 * ImageStudio 组件测试 (v0.7.4-image).
 *
 * 覆盖 8 例:
 * 1. 渲染两 section (文生图 + 图理解)
 * 2. 空 prompt 时生成按钮 disabled
 * 3. 生成调用 API 带正确 payload
 * 4. 200 响应渲染 <img>
 * 5. 失败响应显示 error
 * 6. 图理解要求 file + prompt
 * 7. 图理解调用 API 带 b64
 * 8. 延迟角标显示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ImageStudio } from './ImageStudio';

// FileReader mock (test environment 默认无 DOM)
class MockFileReader {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  result: string | null = null;
  readAsDataURL(_file: File) {
    // 模拟 base64 编码
    this.result = 'data:image/png;base64,aGVsbG8=';
    if (this.onload) this.onload();
  }
}

// @ts-ignore
global.FileReader = MockFileReader;

beforeEach(() => {
  vi.resetAllMocks();
});

describe('ImageStudio', () => {
  it('渲染文生图 + 图理解两 section', () => {
    render(<ImageStudio />);
    expect(screen.getByText(/文生图/)).toBeTruthy();
    expect(screen.getByText(/图理解/)).toBeTruthy();
  });

  it('空 prompt 时生成按钮 disabled', () => {
    render(<ImageStudio />);
    const btn = screen.getByTestId('image-gen-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('点生成 → POST /api/image/generate 带 {prompt, size, n, watermark, actor}', async () => {
    const calls: Array<{ url: string; body: any }> = [];
    const mockFetch = vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(init?.body as string || '{}') });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          images: [{ url: 'https://img/x.png' }],
          provider: 'sensenova',
          model: 'sensenova-u1.5-lite',
          latency_ms: 1234,
        }),
      });
    });
    global.fetch = mockFetch as any;

    render(<ImageStudio />);
    fireEvent.change(screen.getByTestId('image-gen-prompt'), { target: { value: 'a cat' } });
    fireEvent.click(screen.getByTestId('image-gen-submit'));

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    const c = calls[0];
    expect(c.url).toBe('/api/image/generate');
    expect(c.body.prompt).toBe('a cat');
    expect(c.body.size).toBe('1024x1024');
    expect(c.body.n).toBe(1);
    expect(c.body.watermark).toBe(false);
    expect(c.body.actor).toBe('web');
  });

  it('生成 200 响应 → 渲染 <img> + 角标', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        ok: true,
        images: [{ url: 'https://img/x.png' }],
        provider: 'sensenova',
        model: 'sensenova-u1.5-lite',
        latency_ms: 1234,
      }),
    })) as any;

    render(<ImageStudio />);
    fireEvent.change(screen.getByTestId('image-gen-prompt'), { target: { value: 'a cat' } });
    fireEvent.click(screen.getByTestId('image-gen-submit'));

    await waitFor(() => screen.getByTestId('image-gen-result'));
    // 角标内容: {provider} · {model} · {latency}ms — 在 image-gen-result 内
    const resultBox = screen.getByTestId('image-gen-result');
    expect(resultBox.textContent).toMatch(/sensenova-u1.5-lite/);
    expect(resultBox.textContent).toMatch(/1234ms/);
    expect(screen.getByAltText('')).toBeTruthy();
  });

  it('生成失败 (ok=false) → 显示 error', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: false, error: 'invalid api key' }),
    })) as any;

    render(<ImageStudio />);
    fireEvent.change(screen.getByTestId('image-gen-prompt'), { target: { value: 'a cat' } });
    fireEvent.click(screen.getByTestId('image-gen-submit'));

    await waitFor(() => screen.getByTestId('image-gen-error'));
    expect(screen.getByText(/invalid api key/)).toBeTruthy();
  });

  it('图理解: 无文件 + 无 prompt 时按钮 disabled', () => {
    render(<ImageStudio />);
    const btn = screen.getByTestId('image-und-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('图理解: 选择文件 + 输入 prompt → POST /api/image/understand 带 image_b64', async () => {
    const calls: Array<{ url: string; body: any }> = [];
    global.fetch = vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(init?.body as string || '{}') });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          text: '图中是一只猫',
          provider: 'sensenova',
          model: 'sensenova-u1.5-lite',
          latency_ms: 800,
        }),
      });
    }) as any;

    render(<ImageStudio />);
    // 模拟上传文件
    const file = new File(['x'], 'test.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('image-und-file'), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByTestId('image-und-prompt'), {
      target: { value: '描述这张图' },
    });
    fireEvent.click(screen.getByTestId('image-und-submit'));

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    const c = calls[0];
    expect(c.url).toBe('/api/image/understand');
    expect(c.body.prompt).toBe('描述这张图');
    expect(c.body.image_b64).toBe('aGVsbG8='); // 来自 MockFileReader
    expect(c.body.actor).toBe('web');
  });

  it('图理解 200 响应 → 显示文本 + 角标', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        ok: true,
        text: '图中是一只橘猫',
        provider: 'sensenova',
        model: 'sensenova-u1.5-lite',
        latency_ms: 800,
      }),
    })) as any;

    render(<ImageStudio />);
    const file = new File(['x'], 'test.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('image-und-file'), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByTestId('image-und-prompt'), {
      target: { value: '描述' },
    });
    fireEvent.click(screen.getByTestId('image-und-submit'));

    await waitFor(() => screen.getByTestId('image-und-result'));
    expect(screen.getByTestId('image-und-text').textContent).toBe('图中是一只橘猫');
    const resultBox = screen.getByTestId('image-und-result');
    expect(resultBox.textContent).toMatch(/sensenova-u1.5-lite/);
    expect(resultBox.textContent).toMatch(/800ms/);
  });
});
