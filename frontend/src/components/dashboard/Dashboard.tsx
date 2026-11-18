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
 *
 * B5.6 拆分: 容器只保留取数 (getSkillRegistrySummary) / 加载与错误态 / 健康指标派生;
 * 纯类型与计算 → dashboardModel.ts, 展示区块 → HealthCard / SkillMatrix / TriggerTimeline。
 */
import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { getSkillRegistrySummary } from '../../api/settings';
import { SkillSummary } from '../../types/skill';
import { HealthCard } from './HealthCard';
import { SkillMatrix } from './SkillMatrix';
import { TriggerTimeline } from './TriggerTimeline';
import { buildHealthSnapshot, MOCK_TIMELINE } from './dashboardModel';
import type { HealthSnapshot, TriggerTimelineItem } from './dashboardModel';

interface DashboardProps {
  onBack?: () => void;
}

// 区块与类型沿用原对外出口 (Dashboard.test.tsx 直接从本文件取用)。
export { HealthCard, SkillMatrix, TriggerTimeline };
export type { HealthSnapshot, TriggerTimelineItem };

export function Dashboard({ onBack }: DashboardProps) {
  const { t } = useI18n();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await getSkillRegistrySummary<SkillSummary>();
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

  const health = useMemo<HealthSnapshot>(() => buildHealthSnapshot(skills), [skills]);

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
