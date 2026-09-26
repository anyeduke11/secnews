/**
 * FunnelBar 测试 (治理 T3) — 吞吐主视图 + 停摆黄条 + 旧后端降级。
 *
 * 意图锚定: 漏斗必须区分存量与流量 — 存量快照在管线停摆 13 天时依然
 * "看起来健康", 唯有吞吐口径 + 停摆黄条能让断供在 UI 上可见。
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FunnelBar, type StageThroughput } from './FunnelBar';

const FUNNEL = [
  { stage: 'kl:raw', count: 1 },
  { stage: 'kl:refine', count: 0 },
  { stage: 'kl:link', count: 117 },
  { stage: 'kl:structure', count: 51 },
  { stage: 'kl:publish', count: 4179 },
];

function daysAgoIso(n: number): string {
  return new Date(Date.now() - n * 86_400_000).toISOString();
}

const FLOWING: StageThroughput = {
  throughput_7d: { 'kl:raw': 8, 'kl:refine': 4, 'kl:link': 2, 'kl:structure': 1, 'kl:publish': 1 },
  conversion: { raw_to_refine: 0.5, refine_to_link: 0.5, link_to_structure: 0.5, structure_to_publish: 1 },
  last_transition_at: daysAgoIso(1),
};

const STALLED: StageThroughput = {
  throughput_7d: { 'kl:raw': 0, 'kl:refine': 0, 'kl:link': 0, 'kl:structure': 0, 'kl:publish': 0 },
  conversion: { raw_to_refine: null, refine_to_link: null, link_to_structure: null, structure_to_publish: null },
  last_transition_at: daysAgoIso(13),
};

describe('FunnelBar 吞吐主视图 (有 throughput 字段)', () => {
  it('每阶段显示近 7 天转化量, 存量降为次要小字', () => {
    render(<FunnelBar funnel={FUNNEL} throughput={FLOWING} />);

    expect(screen.getByText('管线漏斗')).toBeInTheDocument();
    // 主数字 = 近 7 天流量 (raw=8), 不是存量 (raw=1)
    expect(screen.getByText(/近7天 8/)).toBeInTheDocument();
    // 存量仍在, 但以小字次要展示 (publish 存量 4179)
    expect(screen.getByText(/存量 4,179/)).toBeInTheDocument();
    // 停摆判定: 1 天前有心跳 → 不提示
    expect(screen.queryByText(/管线停摆/)).not.toBeInTheDocument();
  });

  it('显示阶段间转化率', () => {
    render(<FunnelBar funnel={FUNNEL} throughput={FLOWING} />);

    // raw(8)→refine(4) / refine(4)→link(2) / link(2)→structure(1) 均 50%
    expect(screen.getAllByText('50%').length).toBe(3);
  });

  it('转化率除零 (前项 0) 显示 — 而非编造百分比', () => {
    render(<FunnelBar funnel={FUNNEL} throughput={STALLED} />);

    // 所有转化率都是 null → 行尾只渲染占位符, 不出现任何百分比
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument();
  });
});

describe('FunnelBar 停摆黄条 (治理 T4 防再犯展示面)', () => {
  it('last_transition_at 距今 >7 天 → 顶部黄条提示停摆 N 天', () => {
    render(<FunnelBar funnel={FUNNEL} throughput={STALLED} />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(/管线停摆 13 天/);
  });

  it('刚好 7 天内有心跳 → 不提示', () => {
    const borderline: StageThroughput = { ...STALLED, last_transition_at: daysAgoIso(3) };
    render(<FunnelBar funnel={FUNNEL} throughput={borderline} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('无心跳 (last_transition_at=null) → 不误报停摆天数', () => {
    const noHeartbeat: StageThroughput = { ...STALLED, last_transition_at: null };
    render(<FunnelBar funnel={FUNNEL} throughput={noHeartbeat} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('FunnelBar 旧后端降级 (无 throughput 字段)', () => {
  it('缺字段时回退存量条形, 不渲染吞吐文案与停摆条', () => {
    render(<FunnelBar funnel={FUNNEL} throughput={null} />);

    expect(screen.getByText('4,179')).toBeInTheDocument();
    expect(screen.queryByText(/近7天/)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('throughput 缺省 (undefined) 同样降级', () => {
    render(<FunnelBar funnel={FUNNEL} />);

    expect(screen.getByText('4,179')).toBeInTheDocument();
    expect(screen.queryByText(/近7天/)).not.toBeInTheDocument();
  });
});

describe('FunnelBar 时间健壮性', () => {
  it('非法 last_transition_at → 不误报', () => {
    const bad: StageThroughput = { ...STALLED, last_transition_at: 'not-a-date' };
    const spy = vi.spyOn(Date, 'parse');
    render(<FunnelBar funnel={FUNNEL} throughput={bad} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    spy.mockRestore();
  });
});
