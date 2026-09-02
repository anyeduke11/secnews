/**
 * SettingsDashboard 组件测试 — V2 哨兵化总览。
 *
 * 覆盖:
 * 1. Q1 面板渲染 (用途 / 不加的代价 / 用户习惯 / 业务逻辑)
 * 2. 4 张系统子状态卡渲染 (DATABASE / COLLECT / KEYS / SCHEDULER)
 * 3. 8 张区段跳转 tile
 * 4. 源健康概览区段
 * 5. data-testid 可被上层 SettingsPage 用作 smoke anchor
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SettingsDashboard } from './SettingsDashboard';

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockFetch.mockReset();
});

function mockHealth() {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      ok: true, uptime_s: 3600,
      db: { ok: true, latency_ms: 2.3, size_mb: 128.5, hotspots_count: 42 },
      scheduler: { ok: true, jobs: ['collect', 'wiki_sync', 'cg_scan'] },
    }),
  });
}

function mockSecrets() {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ initialized: true, unlocked: true, source: 'os_keyring' }),
  });
}

function mockStats() {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      collect_runs_24h: 288, success_rate_24h: 0.995,
      avg_collect_duration_ms: 42, total_hotspots: 1200,
    }),
  });
}

function mockSources() {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve([
      { status: 'healthy' }, { status: 'healthy' }, { status: 'warning' }, { status: 'dead' },
    ]),
  });
}

describe('SettingsDashboard — V2 哨兵化总览', () => {
  it('Q1 面板渲染 (用途 / 不加的代价 / 用户习惯 / 业务逻辑)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/health') return mockHealth();
      if (url === '/api/secrets/status') return mockSecrets();
      if (url === '/api/stats') return mockStats();
      if (url === '/api/sources/health') return mockSources();
      return Promise.resolve({ ok: false });
    });

    render(<SettingsDashboard onJump={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('dash-purpose')).toBeInTheDocument();
    });

    // 4 个 Q1 要点全部可见
    expect(screen.getByText(/用途/)).toBeInTheDocument();
    expect(screen.getByText(/不打开会怎样/)).toBeInTheDocument();
    expect(screen.getByText(/用户习惯契合/)).toBeInTheDocument();
    expect(screen.getByText(/业务逻辑对齐/)).toBeInTheDocument();
    expect(screen.getByText(/Vercel/)).toBeInTheDocument();
  });

  it('4 张系统子状态卡渲染', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/health') return mockHealth();
      if (url === '/api/secrets/status') return mockSecrets();
      if (url === '/api/stats') return mockStats();
      if (url === '/api/sources/health') return mockSources();
      return Promise.resolve({ ok: false });
    });

    render(<SettingsDashboard onJump={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('dash-db')).toBeInTheDocument();
      expect(screen.getByTestId('dash-collect')).toBeInTheDocument();
      expect(screen.getByTestId('dash-secrets')).toBeInTheDocument();
      expect(screen.getByTestId('dash-scheduler')).toBeInTheDocument();
    });

    expect(screen.getByText('DATABASE')).toBeInTheDocument();
    expect(screen.getByText('ONLINE')).toBeInTheDocument();
    expect(screen.getByText('UNLOCKED')).toBeInTheDocument();
    expect(screen.getByText('3 JOBS')).toBeInTheDocument();
  });

  it('8 张区段跳转 tile', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/health') return mockHealth();
      if (url === '/api/secrets/status') return mockSecrets();
      if (url === '/api/stats') return mockStats();
      if (url === '/api/sources/health') return mockSources();
      return Promise.resolve({ ok: false });
    });

    render(<SettingsDashboard onJump={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('快速跳转')).toBeInTheDocument();
    });

    expect(screen.getByTestId('dash-tile-collection')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-secrets')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-alerts')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-sync')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-pipeline')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-sentinel')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-maintenance')).toBeInTheDocument();
    expect(screen.getByTestId('dash-tile-feedback')).toBeInTheDocument();
  });

  it('源健康概览区段', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === '/api/health') return mockHealth();
      if (url === '/api/secrets/status') return mockSecrets();
      if (url === '/api/stats') return mockStats();
      if (url === '/api/sources/health') return mockSources();
      return Promise.resolve({ ok: false });
    });

    render(<SettingsDashboard onJump={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('源健康概览')).toBeInTheDocument();
    });

    expect(screen.getByText('TOTAL')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument(); // total sources
    expect(screen.getByText('HEALTHY')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument(); // healthy
    expect(screen.getByText('WARNING')).toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1); // warning + dead both 1
    expect(screen.getByText('DEAD')).toBeInTheDocument();
    const deadRow = screen.getByText('DEAD').closest('.st-cell')!;
    expect(deadRow.textContent).toContain('DEAD');
    expect(deadRow.textContent).toContain('1');
  });

  it('加载态显示占位', async () => {
    mockFetch.mockImplementation((_url: string) => {
      return new Promise(() => {}); // 永远 pending
    });

    render(<SettingsDashboard onJump={() => {}} />);
    expect(screen.getByTestId('settings-dashboard')).toBeInTheDocument();
    // loading state — 4 个卡都显示 …
    const loadingDots = screen.getAllByText('…');
    expect(loadingDots.length).toBeGreaterThanOrEqual(1);
  });
});
