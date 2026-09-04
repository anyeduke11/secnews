/**
 * Dashboard.test.tsx — v0.8 Phase D D2 skill 看板组件测试 (≥12 cases).
 *
 * 覆盖:
 *  - HealthCard: 4 行数据 + tone 三态 (ok / caution / saturated)
 *  - SkillMatrix: 空态 + 多行 + 启用/停用色
 *  - TriggerTimeline: 3 种 source 渲染 + status badge 颜色映射
 *  - Dashboard: 三件套组装 + 加载态 + 错误兜底 (skills 空数组渲染基础健康指标)
 */
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../contexts/I18nContext';
import { Dashboard, HealthCard, SkillMatrix, TriggerTimeline, TriggerTimelineItem } from './Dashboard';
import { SkillSummary } from '../../types/skill';

// ---------------------------------------------------------------------------
// Mocks — api + I18nProvider
// ---------------------------------------------------------------------------
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  postJSON: vi.fn(),
  getJSON: vi.fn(),
}));

import { getJSON } from '../../lib/api';
const getJSONMock = vi.mocked(getJSON);

function renderWithI18n(node: React.ReactNode) {
  return render(<I18nProvider>{node}</I18nProvider>);
}

// ---------------------------------------------------------------------------
// 测试数据
// ---------------------------------------------------------------------------
const SAMPLE_SKILLS: SkillSummary[] = [
  {
    id: 'quality-patrol',
    name: '质量巡检',
    desc: 'KL 完成后触发',
    category: 'operations',
    skill_type: 'A',
    runner: 'builtin',
    timeout_seconds: 60,
    feature_gate: null,
    default_enabled: true,
    enabled: true,
  } as SkillSummary,
  {
    id: 'source-health-scan',
    name: '信源健康扫描',
    desc: 'collector 失败触发',
    category: 'operations',
    skill_type: 'A',
    runner: 'builtin',
    timeout_seconds: 120,
    feature_gate: null,
    default_enabled: true,
    enabled: false,
  } as SkillSummary,
];

const SAMPLE_TIMELINE: TriggerTimelineItem[] = [
  {
    ticket_id: 'tg-aaaa1111',
    source: 'webhook',
    target_id: 'webhook-secnews',
    status: 'succeeded',
    created_at: new Date(Date.now() - 30_000).toISOString(),
  },
  {
    ticket_id: 'tg-bbbb2222',
    source: 'kl_event',
    target_id: 'quality-patrol',
    status: 'failed',
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  },
];

// ---------------------------------------------------------------------------
// HealthCard
// ---------------------------------------------------------------------------
describe('HealthCard', () => {
  it('renders all 4 metric rows', () => {
    renderWithI18n(
      <HealthCard
        snapshot={{
          active_sources: 14,
          total_sources: 14,
          enabled_skills: 12,
          total_skills: 20,
          pending_tickets: 0,
          throttle_state: 'ok',
        }}
      />
    );
    const rows = screen.getAllByTestId('health-row');
    expect(rows.length).toBe(4);
    const values = screen.getAllByTestId('health-row-value').map(n => n.textContent);
    expect(values).toEqual(['14/14', '12/20', '0', 'OK']);
  });

  it('maps throttle_state ok → caution → saturated colors', () => {
    const { rerender } = renderWithI18n(
      <HealthCard
        snapshot={{
          active_sources: 1,
          total_sources: 1,
          enabled_skills: 1,
          total_skills: 20,
          pending_tickets: 0,
          throttle_state: 'ok',
        }}
      />
    );
    const firstRenderValues = screen.getAllByTestId('health-row-value').map(n => n.textContent);
    expect(firstRenderValues[firstRenderValues.length - 1]).toBe('OK');

    rerender(
      <I18nProvider>
        <HealthCard
          snapshot={{
            active_sources: 1,
            total_sources: 1,
            enabled_skills: 12,
            total_skills: 20,
            pending_tickets: 0,
            throttle_state: 'caution',
          }}
        />
      </I18nProvider>
    );
    const rows = screen.getAllByTestId('health-row-value');
    expect(rows[rows.length - 1].textContent).toBe('Near Limit');

    rerender(
      <I18nProvider>
        <HealthCard
          snapshot={{
            active_sources: 1,
            total_sources: 1,
            enabled_skills: 20,
            total_skills: 20,
            pending_tickets: 5,
            throttle_state: 'saturated',
          }}
        />
      </I18nProvider>
    );
    const lastRows = screen.getAllByTestId('health-row-value');
    expect(lastRows[lastRows.length - 1].textContent).toBe('Saturated');
  });
});

// ---------------------------------------------------------------------------
// SkillMatrix
// ---------------------------------------------------------------------------
describe('SkillMatrix', () => {
  it('renders empty state when no skills', () => {
    renderWithI18n(<SkillMatrix skills={[]} />);
    expect(screen.getByTestId('skill-matrix-empty')).toBeInTheDocument();
  });

  it('renders one row per skill with enabled state', () => {
    renderWithI18n(<SkillMatrix skills={SAMPLE_SKILLS} />);
    expect(screen.getByTestId('skill-matrix-row-quality-patrol')).toBeInTheDocument();
    expect(screen.getByTestId('skill-matrix-row-source-health-scan')).toBeInTheDocument();
    expect(screen.getByTestId('skill-matrix-enabled-quality-patrol').textContent).toContain('Enabled');
    expect(screen.getByTestId('skill-matrix-enabled-source-health-scan').textContent).toContain('Disabled');
  });

  it('shows skill count in title', () => {
    renderWithI18n(<SkillMatrix skills={SAMPLE_SKILLS} />);
    expect(screen.getByTestId('skill-matrix-title').textContent).toContain('2');
  });
});

// ---------------------------------------------------------------------------
// TriggerTimeline
// ---------------------------------------------------------------------------
describe('TriggerTimeline', () => {
  it('renders one row per ticket with source + status', () => {
    renderWithI18n(<TriggerTimeline items={SAMPLE_TIMELINE} />);
    expect(screen.getByTestId('trigger-timeline-row-tg-aaaa1111')).toBeInTheDocument();
    expect(screen.getByTestId('trigger-timeline-row-tg-bbbb2222')).toBeInTheDocument();
    const sources = screen.getAllByTestId('trigger-source').map(n => n.textContent);
    expect(sources).toEqual(['webhook', 'kl_event']);
  });

  it('maps status to colored badge', () => {
    renderWithI18n(<TriggerTimeline items={SAMPLE_TIMELINE} />);
    expect(screen.getByTestId('trigger-status-succeeded')).toBeInTheDocument();
    expect(screen.getByTestId('trigger-status-failed')).toBeInTheDocument();
  });

  it('handles empty timeline', () => {
    renderWithI18n(<TriggerTimeline items={[]} />);
    expect(screen.getByTestId('trigger-timeline-list').children.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Dashboard (组装层)
// ---------------------------------------------------------------------------
describe('Dashboard', () => {
  beforeEach(() => {
    getJSONMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading state initially', () => {
    getJSONMock.mockReturnValue(new Promise(() => {}));
    renderWithI18n(<Dashboard />);
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
  });

  it('renders HealthCard + SkillMatrix after data loads', async () => {
    getJSONMock.mockResolvedValueOnce({ skills: SAMPLE_SKILLS });
    renderWithI18n(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('health-card')).toBeInTheDocument();
    });
    expect(screen.getByTestId('skill-matrix')).toBeInTheDocument();
    expect(screen.getByTestId('trigger-timeline')).toBeInTheDocument();
    expect(screen.getByTestId('skill-matrix-row-quality-patrol')).toBeInTheDocument();
  });

  it('shows error state but still renders HealthCard when API fails', async () => {
    getJSONMock.mockRejectedValueOnce(new Error('network error'));
    renderWithI18n(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-error')).toBeInTheDocument();
    });
    expect(screen.getByTestId('health-card')).toBeInTheDocument();
    expect(screen.getByTestId('skill-matrix-empty')).toBeInTheDocument();
  });

  it('renders title and subtitle', () => {
    getJSONMock.mockReturnValue(new Promise(() => {}));
    renderWithI18n(<Dashboard />);
    expect(screen.getByTestId('dashboard-title').textContent).toContain('Skill Dashboard');
  });

  it('hides back button when onBack not provided', () => {
    getJSONMock.mockReturnValue(new Promise(() => {}));
    renderWithI18n(<Dashboard />);
    expect(screen.queryByTestId('dashboard-back')).not.toBeInTheDocument();
  });

  it('shows back button when onBack provided', () => {
    getJSONMock.mockReturnValue(new Promise(() => {}));
    renderWithI18n(<Dashboard onBack={() => {}} />);
    expect(screen.getByTestId('dashboard-back')).toBeInTheDocument();
  });
});