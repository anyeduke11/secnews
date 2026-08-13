/**
 * Phase13Dashboard.test.tsx — Phase 13 复利仪表盘测试
 *
 * 覆盖: KnowledgeCompoundingDashboard
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { KnowledgeCompoundingDashboard } from './KnowledgeCompoundingDashboard';

const mockTrendData = [
  { day: '07-28', count: 5, avg_score: 0.6 },
  { day: '07-29', count: 8, avg_score: 0.7 },
  { day: '07-30', count: 12, avg_score: 0.75 },
  { day: '07-31', count: 6, avg_score: 0.8 },
];

const mockCompoundingData = {
  daily_trend: mockTrendData,
  weekly_trend: [],
  monthly_trend: [],
  top_concepts: [
    { name: 'LLM Security', score: 95 },
    { name: 'Zero Trust', score: 78 },
    { name: 'Supply Chain', score: 62 },
  ],
  trigger_health: {
    t1_failed: 0,
    t2_failed: 2,
    t3_failed: 0,
    t4_failed: 1,
    dead_letter_count: 0,
  },
  stage_distribution: {
    'kl:raw': 45,
    'kl:refine': 30,
    'kl:link': 18,
    'kl:structure': 10,
    'kl:publish': 5,
  },
};

describe('KnowledgeCompoundingDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('test_dashboard_renders', async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify(mockCompoundingData),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as any;

    render(<KnowledgeCompoundingDashboard />);

    // 等待数据加载完成
    await waitFor(() => {
      expect(screen.getByText('每日摄入趋势')).toBeInTheDocument();
    });

    // Top 概念
    await waitFor(() => {
      expect(screen.getByText('Top 概念')).toBeInTheDocument();
      expect(screen.getByText('LLM Security')).toBeInTheDocument();
      expect(screen.getByText('Zero Trust')).toBeInTheDocument();
    });

    // 触发器健康度
    await waitFor(() => {
      expect(screen.getByText('触发器健康度')).toBeInTheDocument();
      // T1-T4 标签
      expect(screen.getByText('T1')).toBeInTheDocument();
      expect(screen.getByText('T2')).toBeInTheDocument();
      expect(screen.getByText('T3')).toBeInTheDocument();
      expect(screen.getByText('T4')).toBeInTheDocument();
    });

    // 生命周期阶段分布
    await waitFor(() => {
      expect(screen.getByText('生命周期阶段分布')).toBeInTheDocument();
    });
  });

  it('test_dashboard_trend_chart', async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify(mockCompoundingData),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as any;

    render(<KnowledgeCompoundingDashboard />);

    // 趋势图区域渲染
    await waitFor(() => {
      expect(screen.getByText('每日摄入趋势')).toBeInTheDocument();
    });

    // 趋势数据已加载 → 图表容器存在
    const dashboard = document.querySelector('[data-compounding-dashboard="loaded"]');
    expect(dashboard).toBeInTheDocument();
  });

  it('test_dashboard_empty', async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          daily_trend: [],
          weekly_trend: [],
          monthly_trend: [],
          top_concepts: [],
          trigger_health: { t1_failed: 0, t2_failed: 0, t3_failed: 0, t4_failed: 0, dead_letter_count: 0 },
          stage_distribution: {},
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as any;

    render(<KnowledgeCompoundingDashboard />);

    await waitFor(() => {
      expect(screen.getByText('暂无复利数据')).toBeInTheDocument();
    });
  });
});