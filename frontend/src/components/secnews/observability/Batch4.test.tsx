// frontend/src/components/secnews/observability/Batch4.test.tsx
// v0.7 Batch ④: 告警横幅 + 阈值编辑器 + StatusBar 角标
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ActiveAlertsBanner } from './ActiveAlertsBanner';
import { ThresholdEditor } from './ThresholdEditor';

const alertsMock = {
  items: [
    {
      id: 1,
      level: 'critical',
      metric: 'api.error_rate_pct',
      value: 20,
      threshold: 15,
      window_minutes: 60,
      detail: null,
      fired_at: '2026-08-31T12:00:00Z',
      cooldown_until: '2026-08-31T12:15:00Z',
    },
    {
      id: 2,
      level: 'warn',
      metric: 'api.p95_latency_ms',
      value: 900,
      threshold: 800,
      window_minutes: 60,
      detail: null,
      fired_at: '2026-08-31T12:01:00Z',
      cooldown_until: '2026-08-31T12:16:00Z',
    },
  ],
  critical_count: 1,
  warn_count: 1,
  as_of: '2026-08-31T12:02:00Z',
};

const emptyAlerts = { items: [], critical_count: 0, warn_count: 0, as_of: '2026-08-31T12:02:00Z' };

const thresholdsMock = {
  thresholds: {
    api: { error_rate_pct: { warn: 5, critical: 15, window_minutes: 60 }, p95_latency_ms: { warn: 800, critical: 2000 } },
    llm: { error_rate_pct: { warn: 10, critical: 30 } },
    job: {},
    audit: {},
    alerts: { channels: ['status_bar'], cooldown_minutes: 15 },
  },
  defaults: {},
  as_of: '2026-08-31T12:00:00Z',
};

describe('ActiveAlertsBanner', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.startsWith('/api/observability/alerts/active') && (!init || init.method !== 'POST')) {
        return new Response(JSON.stringify(alertsMock), { status: 200 });
      }
      if (url.startsWith('/api/observability/alerts/') && init?.method === 'POST') {
        return new Response(JSON.stringify({ ok: true, id: 1 }), { status: 200 });
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch);
  });

  it('renders critical + warn items with ack buttons', async () => {
    render(<ActiveAlertsBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('active-alerts-banner')).toBeInTheDocument();
    });
    expect(screen.getByText(/\[critical\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[warn\]/)).toBeInTheDocument();
    expect(screen.getByTestId('ack-button-1')).toBeInTheDocument();
    expect(screen.getByTestId('ack-button-2')).toBeInTheDocument();
  });

  it('renders nothing when no active alerts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(emptyAlerts), { status: 200 })) as unknown as typeof fetch);
    const { container } = render(<ActiveAlertsBanner />);
    await waitFor(() => {
      expect(container.querySelector('[data-testid="active-alerts-banner"]')).toBeNull();
    });
  });

  it('clicking ack triggers POST and refreshes', async () => {
    let postCount = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.startsWith('/api/observability/alerts/active') && (!init || init.method !== 'POST')) {
        return new Response(JSON.stringify(alertsMock), { status: 200 });
      }
      if (init?.method === 'POST') {
        postCount += 1;
        return new Response(JSON.stringify({ ok: true, id: 1 }), { status: 200 });
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch);
    render(<ActiveAlertsBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('ack-button-1')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('ack-button-1'));
    await waitFor(() => {
      expect(postCount).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('ThresholdEditor', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.endsWith('/api/observability/thresholds') && (!init || init.method === 'GET')) {
        return new Response(JSON.stringify(thresholdsMock), { status: 200 });
      }
      if (init?.method === 'PUT') {
        return new Response(JSON.stringify({ ok: true, thresholds: thresholdsMock.thresholds }), { status: 200 });
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch);
  });

  it('renders collapsed by default; click expands inputs', async () => {
    render(<ThresholdEditor />);
    await waitFor(() => {
      expect(screen.getByTestId('threshold-toggle')).toBeInTheDocument();
    });
    // 默认折叠, editor 不存在
    expect(screen.queryByTestId('threshold-editor')).toBeNull();
    fireEvent.click(screen.getByTestId('threshold-toggle'));
    expect(screen.getByTestId('threshold-editor')).toBeInTheDocument();
    // warn + critical 输入框可见
    expect(screen.getByTestId('input-warn-api-error_rate_pct')).toBeInTheDocument();
    expect(screen.getByTestId('input-critical-api-error_rate_pct')).toBeInTheDocument();
  });

  it('saves thresholds via PUT and shows success message', async () => {
    let putCount = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.endsWith('/api/observability/thresholds') && (!init || init.method === 'GET')) {
        return new Response(JSON.stringify(thresholdsMock), { status: 200 });
      }
      if (init?.method === 'PUT') {
        putCount += 1;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch);
    render(<ThresholdEditor />);
    await waitFor(() => {
      expect(screen.getByTestId('threshold-toggle')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('threshold-toggle'));
    fireEvent.click(screen.getByTestId('threshold-save'));
    await waitFor(() => {
      expect(putCount).toBe(1);
    });
    expect(screen.getByTestId('threshold-message').textContent).toContain('已保存');
  });
});