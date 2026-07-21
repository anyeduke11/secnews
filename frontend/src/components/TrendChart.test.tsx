// frontend/src/components/TrendChart.test.tsx
// Phase 6 — TrendChart 暗/亮主题适配 + loading 状态测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { TrendChart } from './TrendChart';
import type { TrendResponse, TrendPoint } from '../types';

const mkPoint = (label: string, ai: number): TrendPoint => ({
  label,
  hours_ago: 0,
  ai,
  security: 0,
  finance: 0,
  startup: 0,
  bid: 0,
  github: 0,
  total: ai,
});

describe('TrendChart', () => {
  beforeEach(() => {
    // 设置 CSS 变量 (useThemeColors 通过 getComputedStyle 读取)
    document.documentElement.style.setProperty('--color-ai', '#5b8def');
    document.documentElement.style.setProperty('--text-primary', '#eaeaea');
    document.documentElement.style.setProperty('--text-secondary', '#aaa');
    document.documentElement.style.setProperty('--text-muted', '#888');
    document.documentElement.style.setProperty('--bg-elevated', '#1a1a1f');
    document.documentElement.style.setProperty('--border-color', '#333');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading skeleton initially', () => {
    // 阻止 fetch resolve, 保持 loading=true
    globalThis.fetch = vi.fn(() => new Promise(() => {})) as any;
    render(<TrendChart />);
    // 加载中显示占位: h-3.5 w-28 + h-36 两个 div
    const card = document.querySelector('.stat-card.corner-brackets');
    expect(card).toBeInTheDocument();
  });

  it('renders chart title after data loads', async () => {
    const mockData: TrendResponse = {
      version: '1.0',
      hours: 24,
      fetched_at: '2026-07-21T00:00:00Z',
      trends: [mkPoint('00', 1), mkPoint('01', 2), mkPoint('02', 3)],
    };
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(mockData),
      } as any)
    ) as any;

    render(<TrendChart />);
    // 等待 fetch resolve + 状态更新
    await waitFor(() => {
      expect(screen.getByText('24小时热度趋势')).toBeInTheDocument();
    });
    expect(screen.getByText('每小时热点分布')).toBeInTheDocument();
  });

  it('renders nothing when API returns empty trends', async () => {
    const mockData: TrendResponse = {
      version: '1.0',
      hours: 24,
      fetched_at: '2026-07-21T00:00:00Z',
      trends: [],
    };
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(mockData),
      } as any)
    ) as any;

    const { container } = render(<TrendChart />);
    await waitFor(() => {
      // 加载完成后空数据 → 返回 null
      // 验证 stat-card 不在文档里
      expect(container.querySelector('.stat-card.corner-brackets')).not.toBeInTheDocument();
    });
  });

  it('handles fetch error gracefully (no crash)', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network'))) as any;
    const { container } = render(<TrendChart />);
    // 等 useEffect 中的 catch 跑完
    await waitFor(() => {
      // catch 后 setLoading(false), 但 data 仍为空 → 返回 null
      expect(container.querySelector('.stat-card.corner-brackets')).not.toBeInTheDocument();
    });
  });

  it('reads theme colors via useThemeColors (token → literal)', async () => {
    // 验证 useThemeColors 在挂载时读 CSS 变量
    const csSpy = vi.spyOn(window, 'getComputedStyle');
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve({
          version: '1.0',
          hours: 24,
          fetched_at: '2026-07-21T00:00:00Z',
          trends: [mkPoint('00', 1)],
        }),
      } as any)
    ) as any;
    render(<TrendChart />);
    await waitFor(() => {
      expect(screen.getByText('24小时热度趋势')).toBeInTheDocument();
    });
    // 至少一次 getComputedStyle (useThemeColors 内部)
    expect(csSpy).toHaveBeenCalled();
  });
});
