/**
 * MaintPage 健康卡 — 只读 DB 健康仪表 (从 MaintPage.tsx 拆出)。
 *
 * 纯展示: 拉取结果由父组件注入, 失败态 fail-loud, 本卡不发起请求.
 */

import { useI18n } from '../contexts/I18nContext';
import type { DirtyReportResp, HealthResp } from './MaintPage.types';

type MaintPageHealthCardProps = {
  health: HealthResp | null;
  dirty: DirtyReportResp | null;
  healthError: boolean;
  onRefresh: () => void;
};

export function MaintPageHealthCard({ health, dirty, healthError, onRefresh }: MaintPageHealthCardProps) {
  const { t } = useI18n();

  return (
    <section
      data-testid="maint-card-health"
      className="rounded-lg p-5"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-mono" style={{ color: 'var(--ink-3)' }}>
          {t('maint.health.title')}
        </h2>
        <button
          type="button"
          onClick={onRefresh}
          className="text-xs font-mono px-2 py-0.5 rounded"
          style={{ background: 'var(--bg-elevated)', color: 'var(--ink-2)' }}
        >
          {t('maint.refresh')}
        </button>
      </div>
      {healthError && !health ? (
        <p className="text-xs font-mono" role="alert" style={{ color: 'var(--color-error)' }}>
          {t('maint.health.error')}
        </p>
      ) : health ? (
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.dbSize')}</dt>
            <dd className="font-mono" style={{ color: 'var(--ink)' }}>
              {health.size_mb?.toFixed(1) ?? '—'} MB
            </dd>
          </div>
          <div className="flex justify-between">
            <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.freePages')}</dt>
            <dd className="font-mono" style={{ color: 'var(--ink)' }}>
              {health.freelist_pages ?? '—'}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.fragmentation')}</dt>
            <dd className="font-mono" style={{ color: 'var(--ink)' }}>
              {health.fragmentation_pct != null ? `${health.fragmentation_pct.toFixed(1)}%` : '—'}
            </dd>
          </div>
          {dirty && (
            <div className="pt-2 mt-2" style={{ borderTop: '1px solid var(--border-color)' }}>
              <div className="flex justify-between">
                <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.cleanupCandidates')}</dt>
                <dd className="font-mono" style={{ color: (dirty.quality_check_logs?.older_than_retention ?? 0) > 100 ? 'var(--color-warning)' : 'var(--ink)' }}>
                  {dirty.quality_check_logs?.older_than_retention ?? '—'}
                </dd>
              </div>
            </div>
          )}
        </dl>
      ) : (
        <p className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
          {t('maint.health.loading')}
        </p>
      )}
    </section>
  );
}