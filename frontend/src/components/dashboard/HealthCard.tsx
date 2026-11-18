/**
 * HealthCard — 健康指标卡 (B5.6 拆分自 Dashboard)。
 *
 * 纯展示: 4 行指标 + 限流三态配色 (数据由容器派生后下传)。
 */
import { useI18n } from '../../contexts/I18nContext';
import type { HealthSnapshot } from './dashboardModel';

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
