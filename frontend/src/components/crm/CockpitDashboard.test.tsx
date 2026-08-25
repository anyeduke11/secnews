// CockpitDashboard.test.tsx — 座舱复盘组件测试 (v0.6 方案 C)
// 覆盖: 8 KPI 卡渲染 (含 null 口径显示 —)、3 图表区块、错误态
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CockpitDashboard } from './CockpitDashboard';

const MOCK_STATS = {
  kpi: {
    annual_revenue: 1800000,
    gross_margin: 0.6667,
    customers_total: 12,
    repeat_rate: null,
    in_pipeline: 5,
    win_rate: 0.75,
    avg_deal_size: 60000,
    nps: 33,
  },
  charts: {
    monthly_revenue: [{ month: '2026-08', revenue: 180000 }],
    region_distribution: [
      { region: '华东', amount: 150000 },
      { region: '华南', amount: 30000 },
    ],
    funnel: [
      { stage: '需求沟通', count: 2, amount: 280000 },
      { stage: '方案提交', count: 1, amount: 80000 },
      { stage: '商务谈判', count: 0, amount: 0 },
      { stage: '合同签订', count: 0, amount: 0 },
    ],
  },
};

describe('CockpitDashboard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders all 8 KPI cards from /api/crm/stats', async () => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify(MOCK_STATS), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<CockpitDashboard />);
    expect(await screen.findByTestId('kpi-annual_revenue')).toHaveTextContent('¥1,800,000');
    expect(screen.getByTestId('kpi-gross_margin')).toHaveTextContent('66.7%');
    expect(screen.getByTestId('kpi-customers_total')).toHaveTextContent('12');
    expect(screen.getByTestId('kpi-repeat_rate')).toHaveTextContent('—'); // null 口径
    expect(screen.getByTestId('kpi-in_pipeline')).toHaveTextContent('5');
    expect(screen.getByTestId('kpi-win_rate')).toHaveTextContent('75.0%');
    expect(screen.getByTestId('kpi-avg_deal_size')).toHaveTextContent('¥60,000');
    expect(screen.getByTestId('kpi-nps')).toHaveTextContent('33');
  });

  it('renders the three chart blocks with seeded data', async () => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify(MOCK_STATS), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<CockpitDashboard />);
    await screen.findByTestId('kpi-nps');
    expect(screen.getByText('月度营收 (近 12 月)')).toBeTruthy();
    expect(screen.getByText('区域分布 (本年赢单)')).toBeTruthy();
    expect(screen.getByText('商机漏斗')).toBeTruthy();
    // 漏斗 SVG 内的阶段标签
    expect(screen.getByText(/需求沟通 · 2 单/)).toBeTruthy();
    // 区域图金额
    expect(screen.getByText('¥30,000')).toBeTruthy();
  });

  it('shows error state when stats fetch fails', async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ detail: { message: 'CRM token 无效' } }), { status: 401 }));
    render(<CockpitDashboard />);
    expect(await screen.findByText(/CRM token 无效/)).toBeTruthy();
  });
});
