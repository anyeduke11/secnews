/** AutoIntakeCard — 自动入管配置卡 (渲染 / 今日已入管展示 / 保存走 PATCH) */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { AutoIntakeCard } from './AutoIntakeCard';

const getConfig = {
  enabled: false,
  min_quality_score: 85,
  daily_limit: 20,
  require_domain_hit: true,
  today_intaken: 3,
};

function stubFetch(patchSpy: ReturnType<typeof vi.fn>) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith('/api/settings/auto-intake') && init?.method === 'PATCH') {
      patchSpy(...(init.body ? [JSON.parse(String(init.body))] : []));
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ ...getConfig, enabled: true, today_intaken: 3 }),
      } as Response);
    }
    if (url.startsWith('/api/settings/auto-intake')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(getConfig),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('AutoIntakeCard — 自动入管配置卡', () => {
  const patchSpy = vi.fn();
  beforeEach(() => {
    patchSpy.mockClear();
    vi.stubGlobal('fetch', stubFetch(patchSpy));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染配置与今日已入管数', async () => {
    render(<AutoIntakeCard />);
    await waitFor(() =>
      expect(screen.getByTestId('auto-intake-today')).toHaveTextContent('3'),
    );
    expect(screen.getByTestId('auto-intake-score')).toHaveValue(85);
    expect(screen.getByTestId('auto-intake-limit')).toHaveValue(20);
    expect(screen.getByTestId('auto-intake-toggle')).toHaveTextContent('已关闭');
  });

  it('开关 toggle 后保存 → PATCH 携带全量配置', async () => {
    render(<AutoIntakeCard />);
    await waitFor(() => expect(screen.getByTestId('auto-intake-toggle')).toBeEnabled());
    fireEvent.click(screen.getByTestId('auto-intake-toggle'));
    fireEvent.click(screen.getByTestId('auto-intake-save'));
    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    expect(patchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true, min_quality_score: 85, daily_limit: 20 }),
    );
  });

  it('修改阈值与上限后保存 → PATCH 携带新值', async () => {
    render(<AutoIntakeCard />);
    await waitFor(() => expect(screen.getByTestId('auto-intake-save')).toBeEnabled());
    fireEvent.change(screen.getByTestId('auto-intake-score'), { target: { value: '90' } });
    fireEvent.change(screen.getByTestId('auto-intake-limit'), { target: { value: '5' } });
    fireEvent.click(screen.getByTestId('auto-intake-save'));
    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    expect(patchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ min_quality_score: 90, daily_limit: 5 }),
    );
  });
});
