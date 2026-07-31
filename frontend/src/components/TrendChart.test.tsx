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
    const card = document.querySelector('.stat-card');
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
      expect(container.querySelector('.stat-card')).not.toBeInTheDocument();
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

  // 锁定意图: 6 个分类色 token 必须被 useThemeColors 请求
  // 否则 Bar 渲染时 `colors[token]` 为 undefined → 全部 fallback 到 'var(--color-ai)' (青色)
  // 历史上曾因只请求 'color-ai' 导致网络安全 bar 渲染成青色而非红色 (#ff6b6b)。
  it('requests all 5 distinct category color tokens from useThemeColors', async () => {
    // 设置 5 个分类 CSS 变量 (test fixture 值, 区别于 AI 色)
    document.documentElement.style.setProperty('--color-ai', '#00d4e0');
    document.documentElement.style.setProperty('--color-security', '#ff6b6b');
    document.documentElement.style.setProperty('--color-finance', '#f5c542');
    document.documentElement.style.setProperty('--color-startup', '#a78bfa');
    document.documentElement.style.setProperty('--color-bid', '#fb923c');

    // 拦截 getComputedStyle 返回的对象, 在 getPropertyValue 入口记录所有 --color-* 读取
    const seen = new Set<string>();
    const originalGCS = window.getComputedStyle.bind(window);
    const csSpy = vi.spyOn(window, 'getComputedStyle').mockImplementation((el) => {
      const real = originalGCS(el) as CSSStyleDeclaration;
      return new Proxy(real, {
        get(target, prop, receiver) {
          if (prop === 'getPropertyValue') {
            return (name: string) => {
              if (name.startsWith('--color-')) seen.add(name);
              return (target as any).getPropertyValue(name);
            };
          }
          return Reflect.get(target, prop, receiver);
        },
        getPrototypeOf() {
          return CSSStyleDeclaration.prototype;
        },
      }) as CSSStyleDeclaration;
    });

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

    // 必须包含 5 个分类色 (github 复用 color-ai, 不重复)
    for (const tok of ['--color-ai', '--color-security', '--color-finance', '--color-startup', '--color-bid']) {
      expect(seen.has(tok), `useThemeColors must request ${tok}`).toBe(true);
    }

    csSpy.mockRestore();
  });
});
