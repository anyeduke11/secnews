/**
 * MaintPage 清理卡 — 分档统计 + 档宽输入 + 二次确认归档 (从 MaintPage.tsx 拆出)。
 *
 * 展示态与确认弹层状态均由父组件注入; 点击仅回调, 请求逻辑留在父组件.
 */

import { useI18n } from '../contexts/I18nContext';
import { fmtBytes, statusBadge } from './MaintPageParts';
import type { CleanupResp, TiersResp, ToolStatus } from './MaintPage.types';

type MaintPageCleanupCardProps = {
  tiers: TiersResp | null;
  tiersError: boolean;
  cleanup: ToolStatus;
  cleanupInfo: CleanupResp | null;
  cutoffDays: number;
  cleanupConfirm: boolean;
  onCutoffDaysChange: (days: number) => void;
  onRunCleanup: () => void;
  onRequestConfirm: () => void;
  onCancelConfirm: () => void;
};

export function MaintPageCleanupCard({
  tiers,
  tiersError,
  cleanup,
  cleanupInfo,
  cutoffDays,
  cleanupConfirm,
  onCutoffDaysChange,
  onRunCleanup,
  onRequestConfirm,
  onCancelConfirm,
}: MaintPageCleanupCardProps) {
  const { t } = useI18n();

  return (
    <section
      data-testid="maint-card-cleanup"
      className="rounded-lg p-5"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-mono" style={{ color: 'var(--ink-3)' }}>
          {t('maint.cleanup.title')}
        </h2>
        <span
          className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ background: statusBadge(t, cleanup).bg, color: statusBadge(t, cleanup).fg }}
        >
          {statusBadge(t, cleanup).text}
        </span>
      </div>
      <p className="text-xs mb-4" style={{ color: 'var(--ink-3)' }}>
        {t('maint.cleanup.desc')}
      </p>
      {/* DEV-0322: 近三档 + 超窗口档真实统计 (口径与清理执行同源,
          超窗口行 = 此刻点清理将真实归档的量; 失败态独立 fail-loud) */}
      <div className="mb-4 rounded p-3" style={{ background: 'var(--bg-elevated)' }} data-testid="maint-tier-status">
        {tiersError && !tiers ? (
          <p className="text-xs font-mono" role="alert" style={{ color: 'var(--color-error)' }}>
            {t('maint.cleanup.tierError')}
          </p>
        ) : tiers?.bands ? (
          <div className="space-y-1.5">
            <div className="text-xs font-mono mb-2" style={{ color: 'var(--ink-3)' }}>
              {t('maint.cleanup.tierTitle')}
            </div>
            {tiers.bands.map((b) => {
              const out = !b.in_window;
              return (
                <div
                  key={b.index}
                  data-testid={`maint-tier-row-${b.index}`}
                  className="text-xs font-mono flex items-baseline justify-between gap-2"
                >
                  <span className="shrink-0" style={{ color: out && b.rows > 0 ? 'var(--color-warning)' : 'var(--ink-2)' }}>
                    {out
                      ? `${t('maint.cleanup.tierOut')} >${b.to_days}${t('maint.cleanup.daysUnit')}`
                      : `${t('maint.cleanup.tier')} ${b.index} · ${b.to_days}–${b.from_days}${t('maint.cleanup.daysUnit')}`}
                  </span>
                  <span className="text-right" style={{ color: 'var(--ink-2)' }}>
                    {b.rows}{t('maint.cleanup.rowsUnit')} · ~{fmtBytes(b.est_bytes)}
                  </span>
                </div>
              );
            })}
            <div className="text-xs font-mono pt-1.5" style={{ borderTop: '1px solid var(--border-color)', color: 'var(--ink-3)' }}>
              {t('maint.cleanup.windowLabel')}: {tiers.window_days}{t('maint.cleanup.daysUnit')}
              {' · '}
              {t('maint.cleanup.ledgerLabel')}: {tiers.ledger_retention_days}{t('maint.cleanup.daysUnit')}
              {' · ~'}{fmtBytes(tiers.total_est_bytes ?? 0)}
            </div>
          </div>
        ) : (
          <p className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
            {t('maint.cleanup.tierChecking')}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3 mb-3">
        <label className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
          {t('maint.cleanup.cutoffDays')}
        </label>
        <input
          type="number"
          data-testid="maint-cleanup-days"
          min={7}
          max={365}
          value={cutoffDays}
          onChange={(e) => onCutoffDaysChange(Number(e.target.value))}
          className="w-20 px-2 py-1 text-sm font-mono rounded"
          style={{
            background: 'var(--bg-input)',
            color: 'var(--ink)',
            border: '1px solid var(--border-color)',
          }}
        />
      </div>
      {cleanupConfirm ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRunCleanup}
            disabled={cleanup === 'running'}
            className="text-sm px-3 py-2 rounded font-mono disabled:opacity-50"
            style={{ background: 'var(--color-error)', color: 'var(--text-on-warning, #fff)' }}
          >
            {t('maint.cleanup.confirm')}
          </button>
          <button
            type="button"
            onClick={onCancelConfirm}
            className="text-sm px-3 py-2 rounded font-mono"
            style={{ background: 'var(--bg-elevated)', color: 'var(--ink-2)' }}
          >
            {t('maint.cleanup.cancel')}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onRequestConfirm}
          disabled={cleanup === 'running'}
          className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
          style={{ background: 'var(--bg-elevated)', color: 'var(--ink)' }}
        >
          {cleanup === 'running' ? t('maint.status.running') : t('maint.cleanup.cta')}
        </button>
      )}
      {cleanupInfo && (
        <div className="mt-3 text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
          {cleanupInfo.rows_archived != null && (
            <div>{t('maint.cleanup.archived')}: {cleanupInfo.rows_archived}</div>
          )}
          {cleanupInfo.rows_remaining_after != null && (
            <div>{t('maint.cleanup.remaining')}: {cleanupInfo.rows_remaining_after}</div>
          )}
        </div>
      )}
    </section>
  );
}