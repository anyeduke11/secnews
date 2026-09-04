/**
 * Dashboard — v0.8 Phase D D2 skill 看板主页面.
 *
 * 三块拼装:
 *  - <SkillMatrix/>      — 全部 skill 状态矩阵 (id | name | type | enabled | 上次触发)
 *  - <TriggerTimeline/>  — 最近触发事件时间线 (source + ticket_id + status)
 *  - <HealthCard/>       — 健康指标卡 (active_sources / enabled_count / throttle_state)
 *
 * 数据面 (Phase D 后端约定, mock 优先; 真实端点 v0.9):
 *  - /api/skill-registry           → SkillSummary[]
 *  - /api/skill-registry/runs       → SkillRun[] (B6 已落地, 复用)
 *  - /api/trigger/tickets          → TriggerTicket[] (待落地, mock 兜底)
 *
 * 文案暂硬编码中文 (i18n 接入为 D3 任务)。
 */
import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { getJSON } from '../../lib/api';
import { SkillSummary } from '../../types/skill';

interface DashboardProps {
  onBack?: () => void;
}

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

const MOCK_TIMELINE: TriggerTimelineItem[] = [
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

export function Dashboard({ onBack }: DashboardProps) {
  const { t } = useI18n();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await getJSON<{ skills: SkillSummary[] }>(
          '/api/skill-registry'
        );
        if (alive) setSkills(data.skills || []);
      } catch (e) {
        if (alive) {
          setError(e instanceof Error ? e.message : '加载技能列表失败');
          setSkills([]); // 兜底: 渲染空骨架
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const health = useMemo<HealthSnapshot>(() => {
    const enabled = skills.filter(s => s.enabled).length;
    return {
      active_sources: 14, // 来自 collector 数 (静态基线)
      total_sources: 14,
      enabled_skills: enabled,
      total_skills: skills.length,
      pending_tickets: 0, // 后端未实装前固定 0
      throttle_state: enabled > 18 ? 'saturated' : enabled > 10 ? 'caution' : 'ok',
    };
  }, [skills]);

  return (
    <div className="min-h-screen bg-[var(--sn-bg-0,#0b0d10)] text-[var(--sn-ink-1,#e6e8eb)] p-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight" data-testid="dashboard-title">
            {t('dashboard.title', '技能看板')}
          </h1>
          <p className="text-[12px] text-[var(--sn-ink-3,#8a929c)] mt-1">
            {t('dashboard.subtitle', 'skill 状态矩阵 + 触发器时间线 + 健康指标')}
          </p>
        </div>
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="rounded border border-[var(--sn-line,#3a3f45)] px-3 py-1 text-[12px] hover:bg-[var(--sn-bg-hover,#1a1d22)]"
            data-testid="dashboard-back"
          >
            {t('common.back', '返回')}
          </button>
        )}
      </header>

      {loading && (
        <p className="text-[12px] text-[var(--sn-ink-3,#8a929c)]" data-testid="dashboard-loading">
          {t('common.loading', '加载中…')}
        </p>
      )}
      {error && !loading && (
        <p className="text-[12px] text-[var(--sn-amber,#c8a44a)]" data-testid="dashboard-error">
          {t('dashboard.skillsError', '技能列表加载失败, 仅显示基础健康指标')}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <HealthCard snapshot={health} />
        <div className="lg:col-span-2">
          <SkillMatrix skills={skills} />
        </div>
        <div className="lg:col-span-3">
          <TriggerTimeline items={MOCK_TIMELINE} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// HealthCard — 健康指标卡
// ---------------------------------------------------------------------------
export function HealthCard({ snapshot }: { snapshot: HealthSnapshot }) {
  const { t } = useI18n();
  const tone =
    snapshot.throttle_state === 'saturated'
      ? 'var(--sn-red,#d96b6b)'
      : snapshot.throttle_state === 'caution'
        ? 'var(--sn-amber,#c8a44a)'
        : 'var(--sn-mint,#5fb88a)';
  return (
    <section
      className="rounded-md border border-[var(--sn-line,#3a3f45)] bg-[var(--sn-bg-1,#101316)] p-4"
      data-testid="health-card"
      aria-label="health snapshot"
    >
      <h2 className="text-[13px] font-medium mb-3" data-testid="health-card-title">
        {t('dashboard.health.title', '健康指标')}
      </h2>
      <dl className="space-y-2 text-[12px]">
        <Row label={t('dashboard.health.sources', '活跃信源')} value={`${snapshot.active_sources}/${snapshot.total_sources}`} />
        <Row label={t('dashboard.health.skills', '已启用技能')} value={`${snapshot.enabled_skills}/${snapshot.total_skills}`} />
        <Row label={t('dashboard.health.pending', '待处理票据')} value={`${snapshot.pending_tickets}`} />
        <Row
          label={t('dashboard.health.throttle', '限流状态')}
          value={
            snapshot.throttle_state === 'saturated'
              ? t('dashboard.health.throttle.saturated', '饱和')
              : snapshot.throttle_state === 'caution'
                ? t('dashboard.health.throttle.caution', '接近上限')
                : t('dashboard.health.throttle.ok', '正常')
          }
          tone={tone}
        />
      </dl>
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between" data-testid="health-row">
      <dt className="text-[var(--sn-ink-3,#8a929c)]">{label}</dt>
      <dd
        className="font-mono tabular-nums"
        style={tone ? { color: tone } : undefined}
        data-testid="health-row-value"
      >
        {value}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SkillMatrix — skill 状态矩阵
// ---------------------------------------------------------------------------
export function SkillMatrix({ skills }: { skills: SkillSummary[] }) {
  const { t } = useI18n();
  return (
    <section
      className="rounded-md border border-[var(--sn-line,#3a3f45)] bg-[var(--sn-bg-1,#101316)] p-4"
      data-testid="skill-matrix"
      aria-label="skill matrix"
    >
      <h2 className="text-[13px] font-medium mb-3" data-testid="skill-matrix-title">
        {t('dashboard.matrix.title', '技能状态矩阵')} · {skills.length}
      </h2>
      {skills.length === 0 ? (
        <p className="text-[12px] text-[var(--sn-ink-3,#8a929c)]" data-testid="skill-matrix-empty">
          {t('dashboard.matrix.empty', '暂无技能 (请确认 skill_registry gate 已开启)')}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]" data-testid="skill-matrix-table">
            <thead className="text-[var(--sn-ink-3,#8a929c)]">
              <tr className="border-b border-[var(--sn-line,#3a3f45)]">
                <th className="text-left py-2 pr-3 font-medium">id</th>
                <th className="text-left py-2 pr-3 font-medium">name</th>
                <th className="text-left py-2 pr-3 font-medium">type</th>
                <th className="text-left py-2 pr-3 font-medium">category</th>
                <th className="text-left py-2 font-medium">enabled</th>
              </tr>
            </thead>
            <tbody>
              {skills.map(s => (
                <tr
                  key={s.id}
                  className="border-b border-[var(--sn-line,#3a3f45)]/40"
                  data-testid={`skill-matrix-row-${s.id}`}
                >
                  <td className="py-2 pr-3 font-mono">{s.id}</td>
                  <td className="py-2 pr-3">{s.name}</td>
                  <td className="py-2 pr-3">
                    <span
                      className="rounded px-1.5 py-0.5 text-[11px] font-mono"
                      style={{
                        background: 'var(--sn-bg-2,#15181d)',
                        color: 'var(--sn-mint,#5fb88a)',
                      }}
                    >
                      {s.skill_type}
                    </span>
                  </td>
                  <td className="py-2 pr-3">{s.category}</td>
                  <td className="py-2" data-testid={`skill-matrix-enabled-${s.id}`}>
                    {s.enabled ? (
                      <span style={{ color: 'var(--sn-mint,#5fb88a)' }}>
                        ● {t('common.enabled', '已启用')}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--sn-ink-3,#8a929c)' }}>
                        ○ {t('common.disabled', '未启用')}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// TriggerTimeline — 最近触发事件时间线
// ---------------------------------------------------------------------------
export function TriggerTimeline({ items }: { items: TriggerTimelineItem[] }) {
  const { t } = useI18n();
  return (
    <section
      className="rounded-md border border-[var(--sn-line,#3a3f45)] bg-[var(--sn-bg-1,#101316)] p-4"
      data-testid="trigger-timeline"
      aria-label="trigger timeline"
    >
      <h2 className="text-[13px] font-medium mb-3" data-testid="trigger-timeline-title">
        {t('dashboard.timeline.title', '触发器时间线')} · {items.length}
      </h2>
      <ol className="space-y-2" data-testid="trigger-timeline-list">
        {items.map(item => (
          <li
            key={item.ticket_id}
            className="flex items-center justify-between text-[12px] border-b border-[var(--sn-line,#3a3f45)]/40 py-2"
            data-testid={`trigger-timeline-row-${item.ticket_id}`}
          >
            <span className="font-mono text-[var(--sn-ink-3,#8a929c)]">{item.ticket_id}</span>
            <span className="px-2 text-[11px] font-mono" data-testid="trigger-source">
              {item.source}
            </span>
            <span className="font-mono">{item.target_id}</span>
            <StatusBadge status={item.status} />
            <span className="text-[var(--sn-ink-3,#8a929c)] font-mono tabular-nums">
              {_relative_time(item.created_at)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StatusBadge({ status }: { status: TriggerTimelineItem['status'] }) {
  const map: Record<TriggerTimelineItem['status'], { color: string; label: string }> = {
    pending: { color: 'var(--sn-ink-3,#8a929c)', label: 'pending' },
    running: { color: 'var(--sn-amber,#c8a44a)', label: 'running' },
    succeeded: { color: 'var(--sn-mint,#5fb88a)', label: 'succeeded' },
    failed: { color: 'var(--sn-red,#d96b6b)', label: 'failed' },
    partial: { color: 'var(--sn-amber,#c8a44a)', label: 'partial' },
  };
  const meta = map[status];
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[11px] font-mono"
      style={{ background: 'var(--sn-bg-2,#15181d)', color: meta.color }}
      data-testid={`trigger-status-${status}`}
    >
      {meta.label}
    </span>
  );
}

function _relative_time(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`;
  if (ms < 60 * 60_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / (60 * 60_000))}h ago`;
}