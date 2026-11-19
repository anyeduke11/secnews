/**
 * CompoundingCards — 复利仪表盘 4 个展示区块 (B5 续拆自 KnowledgeCompoundingDashboard)
 *
 * 纯展示: JSX 逐字搬运, 数据 / option / 色值由容器与 compoundingDashboardModel 提供。
 */
import { EChart } from '../shared/EChart';
import { Icon } from '../../primitives/Icon';
import {
  healthColor,
  healthLabel,
  type StageChartOption,
  type StageDatum,
  type TopConcept,
  type TrendChartOption,
  type TriggerHealth,
} from './compoundingDashboardModel';

/* ── 每日摄入趋势 ───────────────────────────────────────────── */

export function TrendCard({ option }: { option: TrendChartOption }) {
  return (
    <section
      className="lg:col-span-2 rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
        <span
          className="w-5 h-5 rounded-sm flex items-center justify-center"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
            color: 'var(--area-accent, var(--color-success))',
          }}
        >
          <Icon size={11}>
            <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
            <polyline points="17 6 23 6 23 12" />
          </Icon>
        </span>
        每日摄入趋势
      </h3>
      <div className="h-44">
        <EChart option={option} style={{ height: '100%', width: '100%' }} />
      </div>
    </section>
  );
}

/* ── Top 概念 ───────────────────────────────────────────────── */

export function TopConceptsCard({ top_concepts, textMuted }: { top_concepts: TopConcept[]; textMuted: string }) {
  return (
    <section
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
        <span
          className="w-5 h-5 rounded-sm flex items-center justify-center"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
            color: 'var(--area-accent, var(--color-success))',
          }}
        >
          <Icon size={11}>
            <circle cx="12" cy="12" r="10" />
            <polygon points="10 8 16 12 10 16 10 8" />
          </Icon>
        </span>
        Top 概念
      </h3>
      <div className="space-y-1.5">
        {top_concepts.length === 0 ? (
          <p className="text-xs" style={{ color: textMuted }}>暂无关联概念</p>
        ) : (
          top_concepts.map((c, i) => {
            const maxScore = top_concepts[0]?.score || 1;
            const barWidth = (c.score / maxScore) * 100;
            return (
              <div key={c.name} className="flex items-center gap-2">
                <span
                  className="text-[10px] font-mono w-4 text-right shrink-0"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <span
                      className="text-[11px] truncate"
                      style={{ color: 'var(--text-primary)' }}
                      title={c.name}
                    >
                      {c.name}
                    </span>
                    <span
                      className="text-[10px] font-mono tabular-nums ml-2 shrink-0"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {c.score}
                    </span>
                  </div>
                  <div
                    className="h-1 rounded-full"
                    style={{
                      backgroundColor: 'var(--border-color)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${barWidth}%`,
                        backgroundColor: 'var(--area-accent, var(--color-success))',
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

/* ── 触发器健康度 ───────────────────────────────────────────── */

export function TriggerHealthCard({ trigger_health }: { trigger_health: TriggerHealth }) {
  return (
    <section
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
        <span
          className="w-5 h-5 rounded-sm flex items-center justify-center"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
            color: 'var(--area-accent, var(--color-success))',
          }}
        >
          <Icon size={11}>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </Icon>
        </span>
        触发器健康度
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {(['t1_failed', 't2_failed', 't3_failed', 't4_failed'] as const).map((key) => {
          const val = trigger_health[key];
          const color = healthColor(val);
          const label = key.replace('_failed', '').toUpperCase();
          return (
            <div
              key={key}
              className="rounded-[var(--radius-sm)] p-2.5 text-center"
              style={{
                backgroundColor: 'color-mix(in srgb, ' + color + ' 8%, transparent)',
                border: '1px solid color-mix(in srgb, ' + color + ' 25%, transparent)',
              }}
            >
              <div className="text-lg font-bold font-mono tabular-nums" style={{ color }}>
                {val}
              </div>
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                {label}
              </div>
              <div
                className="inline-block w-1.5 h-1.5 rounded-full mt-1"
                style={{ backgroundColor: color }}
                title={healthLabel(val)}
              />
            </div>
          );
        })}
        <div
          className="rounded-[var(--radius-sm)] p-2.5 text-center"
          style={{
            backgroundColor: 'color-mix(in srgb, ' + healthColor(trigger_health.dead_letter_count) + ' 8%, transparent)',
            border: '1px solid color-mix(in srgb, ' + healthColor(trigger_health.dead_letter_count) + ' 25%, transparent)',
          }}
        >
          <div
            className="text-lg font-bold font-mono tabular-nums"
            style={{ color: healthColor(trigger_health.dead_letter_count) }}
          >
            {trigger_health.dead_letter_count}
          </div>
          <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            Dead
          </div>
          <div
            className="inline-block w-1.5 h-1.5 rounded-full mt-1"
            style={{ backgroundColor: healthColor(trigger_health.dead_letter_count) }}
            title={healthLabel(trigger_health.dead_letter_count)}
          />
        </div>
      </div>
    </section>
  );
}

/* ── 生命周期阶段分布 ───────────────────────────────────────── */

export function StageDistributionCard({
  stageData,
  option,
  textMuted,
}: {
  stageData: StageDatum[];
  option: StageChartOption;
  textMuted: string;
}) {
  return (
    <section
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <h3 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: 'var(--text-primary)' }}>
        <span
          className="w-5 h-5 rounded-sm flex items-center justify-center"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 14%, transparent)',
            color: 'var(--area-accent, var(--color-success))',
          }}
        >
          <Icon size={11}>
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
          </Icon>
        </span>
        生命周期阶段分布
      </h3>
      {stageData.length === 0 ? (
        <p className="text-xs" style={{ color: textMuted }}>暂无阶段分布数据</p>
      ) : (
        <div className="h-36">
          <EChart option={option} style={{ height: '100%', width: '100%' }} />
        </div>
      )}
    </section>
  );
}
