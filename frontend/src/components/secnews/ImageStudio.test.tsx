/**
 * ImageStudio 组件测试 (v0.7.4-image 重构版)
 *
 * 2026-09-02 用户裁决: 删文生图 + 图理解, 只保留三场景模型配置。
 * 现 ImageStudio 仅渲染 ScenarioModelsPanel (与 /settings 同源)。
 *
 * 覆盖 6 例:
 * 1. 渲染标题与说明文案
 * 2. 渲染三场景输入行 (deep / light / image)
 * 3. 初始值全空 (用户未配置) — 保存按钮 disabled
 * 4. 输入 deep 模型 → 保存 → POST /api/settings/scenario-model
 * 5. 保存成功显示消息
 * 6. 文生图/图理解功能确实未渲染 (data-testid 不存在)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ImageStudio } from './ImageStudio';

beforeEach(() => {
  vi.resetAllMocks();
});

describe('ImageStudio (v0.7.4-image 重构后)', () => {
  it('渲染页面标题 + 说明文案 (含功能下线声明)', () => {
    render(<ImageStudio />);
    expect(screen.getByText(/图片工具 · 模型配置/)).toBeTruthy();
    expect(screen.getByText(/文生图与图理解功能已下线/)).toBeTruthy();
    // 提到 /settings 绑定关系
    expect(screen.getByText(/secnews\/settings/)).toBeTruthy();
  });

  it('渲染三场景输入行 (deep / light / image) 与保存按钮', () => {
    render(<ImageStudio />);
    for (const s of ['deep', 'light', 'image']) {
      expect(screen.getByTestId(`image-studio-input-${s}`)).toBeTruthy();
      expect(screen.getByTestId(`image-studio-save-${s}`)).toBeTruthy();
    }
  });

  it('初始值全空 → 三个保存按钮全部 disabled', () => {
    render(<ImageStudio />);
    for (const s of ['deep', 'light', 'image']) {
      const btn = screen.getByTestId(`image-studio-save-${s}`) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    }
  });

  it('输入 deep 模型 → 保存 → POST /api/settings/scenario-model 带 {scenario, model, actor}', async () => {
    const calls: Array<{ url: string; body: any }> = [];
    global.fetch = vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(init?.body as string || '{}') });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          status: 'ok',
          scenario: 'deep',
          old_model: null,
          new_model: 'deepseek-v4-pro',
        }),
      });
    }) as any;

    render(<ImageStudio />);
    const input = screen.getByTestId('image-studio-input-deep') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'deepseek-v4-pro' } });

    const btn = screen.getByTestId('image-studio-save-deep') as HTMLButtonElement;
    expect(btn.disabled).toBe(false); // 输入后 dirty
    fireEvent.click(btn);

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    const c = calls[0];
    expect(c.url).toBe('/api/settings/scenario-model');
    expect(c.body.scenario).toBe('deep');
    expect(c.body.model).toBe('deepseek-v4-pro');
    expect(c.body.actor).toBe('web');
  });

  it('保存成功 → 显示 ok 消息含 old → new', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        status: 'ok',
        scenario: 'image',
        old_model: 'sensenova-u1.5-lite',
        new_model: 'sensenova-u2-lite',
      }),
    })) as any;

    render(<ImageStudio />);
    fireEvent.change(screen.getByTestId('image-studio-input-image'), {
      target: { value: 'sensenova-u2-lite' },
    });
    fireEvent.click(screen.getByTestId('image-studio-save-image'));

    await waitFor(() => screen.getByTestId('image-studio-message'));
    const msg = screen.getByTestId('image-studio-message');
    expect(msg.textContent).toMatch(/image/);
    expect(msg.textContent).toMatch(/sensenova-u1\.5-lite.*→.*sensenova-u2-lite/);
  });

  it('确认文生图/图理解 UI 已下线 (老 data-testid 不再存在)', () => {
    render(<ImageStudio />);
    // S9 阶段存在, 重构后必须全部不存在
    expect(screen.queryByTestId('image-gen-prompt')).toBeNull();
    expect(screen.queryByTestId('image-gen-submit')).toBeNull();
    expect(screen.queryByTestId('image-gen-result')).toBeNull();
    expect(screen.queryByTestId('image-und-file')).toBeNull();
    expect(screen.queryByTestId('image-und-prompt')).toBeNull();
    expect(screen.queryByTestId('image-und-submit')).toBeNull();
    expect(screen.queryByTestId('image-und-result')).toBeNull();
  });
});