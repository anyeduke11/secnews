/**
 * dashboardModel — skill 看板的纯类型 / 常量 / 计算 (B5.6 拆分自 Dashboard)。
 *
 * 只放无 React 依赖的内容, 供容器 (Dashboard.tsx) 与展示区块共享。
 */
import type { SkillSummary } from '../../types/skill';

/** 触发时间线条目 (mock-friendly; 真实 ticket 由 /api/trigger/tickets 提供). */
export interface TriggerTimelineItem {
  ticket_id: string;
  source: 'manual' | 'cron' | 'webhook' | 'kl_event' | 'collector_event';
  target_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'partial';
  created_at: string;
}

/** 健康指标. */
export interface HealthSnapshot {
  active_sources: number;
  total_sources: number;
  enabled_skills: number;
  total_skills: number;
  pending_tickets: number;
  throttle_state: 'ok' | 'caution' | 'saturated';
}

/** 触发状态 → 徽标配色 / 文案. */
export const TRIGGER_STATUS_META: Record<
  TriggerTimelineItem['status'],
  { color: string; label: string }
> = {
  pending: { color: 'var(--sn-ink-3,#8a929c)', label: 'pending' },
  running: { color: 'var(--sn-amber,#c8a44a)', label: 'running' },
  succeeded: { color: 'var(--sn-mint,#5fb88a)', label: 'succeeded' },
  failed: { color: 'var(--sn-red,#d96b6b)', label: 'failed' },
  partial: { color: 'var(--sn-amber,#c8a44a)', label: 'partial' },
};

/** 时间线 mock 数据 (真实 /api/trigger/tickets 未落地前的兜底). */
export const MOCK_TIMELINE: TriggerTimelineItem[] = [
  {
    ticket_id: 'tg-aaaa1111',
    source: 'webhook',
    target_id: 'webhook-secnews',
    status: 'succeeded',
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  },
  {
    ticket_id: 'tg-bbbb2222',
    source: 'kl_event',
    target_id: 'quality-patrol',
    status: 'succeeded',
    created_at: new Date(Date.now() - 23 * 60_000).toISOString(),
  },
  {
    ticket_id: 'tg-cccc3333',
    source: 'collector_event',
    target_id: 'source-health-scan',
    status: 'running',
    created_at: new Date(Date.now() - 60 * 60_000).toISOString(),
  },
];

/** 由 skill 清单派生健康指标 (容器 useMemo 的纯计算). */
export function buildHealthSnapshot(skills: SkillSummary[]): HealthSnapshot {
  const enabled = skills.filter(s => s.enabled).length;
  return {
    active_sources: 14, // 来自 collector 数 (静态基线)
    total_sources: 14,
    enabled_skills: enabled,
    total_skills: skills.length,
    pending_tickets: 0, // 后端未实装前固定 0
    throttle_state: enabled > 18 ? 'saturated' : enabled > 10 ? 'caution' : 'ok',
  };
}

/** 相对时间 (s / m / h). */
export function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`;
  if (ms < 60 * 60_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / (60 * 60_000))}h ago`;
}
