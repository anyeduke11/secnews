/**
 * MaintPage 索引重建卡 — 索引真实状态展示 + VACUUM 触发 (从 MaintPage.tsx 拆出)。
 *
 * 展示态 (indexHealth/vacuum) 全部由父组件注入; 点击仅回调 onRunVacuum.
 */

import { useI18n } from '../contexts/I18nContext';
import { statusBadge } from './MaintPageParts';
import type { IndexHealthResp, ToolStatus, VacuumResp } from './MaintPage.types';

type MaintPageVacuumCardProps = {
  indexHealth: IndexHealthResp | null;
  indexHealthError: boolean;
  vacuum: ToolStatus;
  vacuumInfo: VacuumResp | null;
  onRunVacuum: () => void;
};

export function MaintPageVacuumCard({
  indexHealth,
  indexHealthError,
  vacuum,
  vacuumInfo,
  onRunVacuum,
}: MaintPageVacuumCardProps) {
  const { t } = useI18n();

  return (
    <section
      data-testid="maint-card-vacuum"
      className="rounded-lg p-5"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-mono" style={{ color: 'var(--ink-3)' }}>
          {t('maint.vacuum.title')}
        </h2>
        <span
          className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ background: statusBadge(t, vacuum).bg, color: statusBadge(t, vacuum).fg }}
        >
          {statusBadge(t, vacuum).text}
        </span>
      </div>
      <p className="text-xs mb-4" style={{ color: 'var(--ink-3)' }}>
        {t('maint.vacuum.desc')}
      </p>
      {/* DEV-0320: 重建前先看到索引真实状态 (curl 实测契约, fail-loud) */}
      <div className="mb-4 rounded p-3" style={{ background: 'var(--bg-elevated)' }} data-testid="maint-index-status">
        {indexHealthError && !indexHealth ? (
          <p className="text-xs font-mono" role="alert" style={{ color: 'var(--color-error)' }}>
            {t('maint.vacuum.indexError')}
          </p>
        ) : indexHealth?.schemas ? (
          <div className="space-y-1.5">
            <div className="text-xs font-mono mb-2" style={{ color: 'var(--ink-3)' }}>
              {t('maint.vacuum.indexTitle')}
            </div>
            {indexHealth.schemas.map((s) => {
              const ok = s.check === 'ok';
              return (
                <div key={s.schema} data-testid={`maint-index-row-${s.schema}`} className="text-xs font-mono flex items-baseline justify-between gap-2">
                  <span className="shrink-0" style={{ color: 'var(--ink-2)' }}>
                    {s.schema}
                    {s.file && <span style={{ color: 'var(--ink-3)' }}> ({s.file})</span>}
                  </span>
                  <span className="text-right" style={{ color: ok ? 'var(--ink-2)' : 'var(--color-warning)' }}>
                    {t('maint.vacuum.idx')} {s.user_indexes}
                    <span style={{ color: 'var(--ink-3)' }}>+{s.auto_indexes}</span>
                    {' · '}
                    {s.check}
                    {` ${s.check_ms}ms`}
                    {' · '}
                    {t('maint.vacuum.stats')} {s.stat1_covered}
                  </span>
                </div>
              );
            })}
            {indexHealth.schemas.some((s) => s.check !== 'ok' && s.check_errors.length > 0) && (
              <p className="text-xs font-mono" style={{ color: 'var(--color-warning)', wordBreak: 'break-all' }}>
                {indexHealth.schemas
                  .filter((s) => s.check !== 'ok' && s.check_errors.length > 0)
                  .map((s) => `${s.schema}: ${s.check_errors[0]}`)
                  .join(' | ')}
              </p>
            )}
            <div className="text-xs font-mono pt-1.5" style={{ borderTop: '1px solid var(--border-color)', color: 'var(--ink-3)' }}>
              {indexHealth.mode === 'full' ? t('maint.vacuum.modeFull') : t('maint.vacuum.modeQuick')}
              {' · '}
              {indexHealth.totals?.schemas_ok}/{indexHealth.totals?.schemas_total} {t('maint.vacuum.schemasOk')}
            </div>
          </div>
        ) : (
          <p className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
            {t('maint.vacuum.checking')}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onRunVacuum}
        disabled={vacuum === 'running'}
        className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
        style={{ background: 'var(--mint)', color: 'var(--text-on-success, #fff)' }}
      >
        {vacuum === 'running' ? t('maint.status.running') : t('maint.vacuum.cta')}
      </button>
      {vacuumInfo && (
        <div className="mt-3 text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
          {vacuumInfo.total_seconds != null && (
            <div>{t('maint.vacuum.duration')}: {vacuumInfo.total_seconds}s</div>
          )}
        </div>
      )}
    </section>
  );
}