/**
 * ImageStudio 组件测试 — DEPRECATED 验证
 *
 * v0.7.x SettingsHub: ImageStudio 路由层不可达, 仅作 legacy 留存。
 * 测试目标: deprecated 警告可见 + 仍渲染 ScenarioModelsPanel (供未来回滚参考)。
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ImageStudio } from './ImageStudio';

describe('ImageStudio (DEPRECATED, v0.7.x SettingsHub)', () => {
  it('显示 DEPRECATED 警告 + 指向 /settings?cat=image_models', () => {
    render(<ImageStudio />);
    expect(screen.getByText(/DEPRECATED/)).toBeTruthy();
    const link = screen.getByRole('link', { name: /设置 → 图片模型/ });
    expect(link.getAttribute('href')).toBe('/settings?cat=image_models');
  });

  it('仍渲染 ScenarioModelsPanel (scope=image-studio) 三场景输入行', () => {
    render(<ImageStudio />);
    for (const s of ['deep', 'light', 'image']) {
      expect(screen.getByTestId(`image-studio-input-${s}`)).toBeTruthy();
      expect(screen.getByTestId(`image-studio-save-${s}`)).toBeTruthy();
    }
  });
});