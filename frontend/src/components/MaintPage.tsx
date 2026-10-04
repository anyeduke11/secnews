/**
 * NAV4 P3 (2026-09-13, DEV-0178): 维护诊断 /maint
 *
 * 4 工具卡 (备份/索引/清理/健康), 走 /api/maintenance/* 真实端点.
 * 后端 10 端点已存在 (backend/api/maintenance.py), 本页是它们的
 * 顶层直达入口 (与 /settings?cat=maintenance 共存).
 *
 * 设计契约:
 * - 错误不抛 — 显示状态徽章, 不阻塞 SSE 心跳条
 * - 健康卡为只读仪表 (拉取后展示, 不触发操作)
 * - 清理类操作需二次确认 (本地 useState, 不阻塞 UI)
 */

import { useCallback, useEffect, useState } from 'react';
import { getJSON, postJSON } from '../lib/api';
import { useI18n } from '../contexts/I18nContext';
import { useAbortGuard } from '../hooks/useAbortGuard';

interface HealthResp {
  db_size_mb?: number;
  table_count?: number;
  page_count?: number;
  fragmentation?: number;
  status?: 'ok' | 'warn' | 'fail';
}

interface DirtyReportResp {
  cleanup_candidates?: number;
  log_count?: number;
  stale_rows?: number;
  last_check?: string;
}

interface BackupVerifyResp {
  ok?: boolean;
  latest_backup?: string;
  age_hours?: number;
  message?: string;
}

interface VacuumResp {
  ok?: boolean;
  duration_ms?: number;
  reindexed?: number;
}

interface CleanupResp {
  deleted?: number;
  cutoff_days?: number;
}

type ToolStatus = 'idle' | 'running' | 'ok' | 'error';

export function MaintPage() {
  const { t } = useI18n();
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [dirty, setDirty] = useState<DirtyReportResp | null>(null);
  const [backup, setBackup] = useState<ToolStatus>('idle');
  const [backupInfo, setBackupInfo] = useState<BackupVerifyResp | null>(null);
  const [vacuum, setVacuum] = useState<ToolStatus>('idle');
  const [vacuumInfo, setVacuumInfo] = useState<VacuumResp | null>(null);
  const [cleanup, setCleanup] = useState<ToolStatus>('idle');
  const [cleanupInfo, setCleanupInfo] = useState<CleanupResp | null>(null);
  const [cleanupConfirm, setCleanupConfirm] = useState(false);
  const [cutoffDays, setCutoffDays] = useState(30);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const fetchHealth = useCallback(async () => {
    try {
      const [h, d] = await Promise.all([
        getJSON<HealthResp>('/api/maintenance/health'),
        getJSON<DirtyReportResp>('/api/maintenance/dirty-report'),
      ]);
      if (dead.current) return;
      setHealth(h);
      setDirty(d);
    } catch {
      // 不抛错 — 静默显示空
    }
  }, [dead]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const runBackupVerify = useCallback(async () => {
    setBackup('running');
    try {
      const r = await postJSON<BackupVerifyResp>('/api/maintenance/backup-verify', {});
      if (dead.current) return;
      setBackupInfo(r);
      setBackup(r.ok ? 'ok' : 'error');
    } catch {
      if (dead.current) return;
      setBackup('error');
    }
  }, [dead]);

  const runVacuum = useCallback(async () => {
    setVacuum('running');
    try {
      const r = await postJSON<VacuumResp>('/api/maintenance/vacuum', {});
      if (dead.current) return;
      setVacuumInfo(r);
      setVacuum(r.ok ? 'ok' : 'error');
    } catch {
      if (dead.current) return;
      setVacuum('error');
    }
  }, [dead]);

  const runCleanup = useCallback(async () => {
    setCleanup('running');
    setCleanupConfirm(false);
    try {
      const r = await postJSON<CleanupResp>('/api/maintenance/cleanup', { cutoff_days: cutoffDays });
      if (dead.current) return;
      setCleanupInfo(r);
      setCleanup('ok');
      fetchHealth();
    } catch {
      if (dead.current) return;
      setCleanup('error');
    }
  }, [cutoffDays, fetchHealth, dead]);

  const statusBadge = (s: ToolStatus): { bg: string; fg: string; text: string } => {
    switch (s) {
      case 'running': return { bg: 'var(--bg-info, var(--bg-elevated))', fg: 'var(--text-on-info, var(--ink))', text: t('maint.status.running') };
      case 'ok': return { bg: 'var(--bg-success, var(--bg-elevated))', fg: 'var(--text-on-success, var(--mint))', text: t('maint.status.ok') };
      case 'error': return { bg: 'var(--bg-warning)', fg: 'var(--text-on-warning, var(--color-error))', text: t('maint.status.error') };
      default: return { bg: 'var(--bg-elevated)', fg: 'var(--ink-3)', text: t('maint.status.idle') };
    }
  };

  return (
    <div className="px-6 py-8 max-w-7xl mx-auto">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--ink)' }}>
          {t('maint.title')}
        </h1>
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          {t('maint.subtitle')}
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 健康: 只读 */}
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
              onClick={fetchHealth}
              className="text-xs font-mono px-2 py-0.5 rounded"
              style={{ background: 'var(--bg-elevated)', color: 'var(--ink-2)' }}
            >
              {t('maint.refresh')}
            </button>
          </div>
          {health ? (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.dbSize')}</dt>
                <dd className="font-mono" style={{ color: 'var(--ink)' }}>
                  {health.db_size_mb?.toFixed(1) ?? '—'} MB
                </dd>
              </div>
              <div className="flex justify-between">
                <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.tables')}</dt>
                <dd className="font-mono" style={{ color: 'var(--ink)' }}>
                  {health.table_count ?? '—'}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.fragmentation')}</dt>
                <dd className="font-mono" style={{ color: 'var(--ink)' }}>
                  {health.fragmentation != null ? `${(health.fragmentation * 100).toFixed(1)}%` : '—'}
                </dd>
              </div>
              {dirty && (
                <div className="pt-2 mt-2" style={{ borderTop: '1px solid var(--border-color)' }}>
                  <div className="flex justify-between">
                    <dt style={{ color: 'var(--ink-3)' }}>{t('maint.health.cleanupCandidates')}</dt>
                    <dd className="font-mono" style={{ color: dirty.cleanup_candidates && dirty.cleanup_candidates > 100 ? 'var(--color-warning)' : 'var(--ink)' }}>
                      {dirty.cleanup_candidates ?? '—'}
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

        {/* 备份验证 */}
        <section
          data-testid="maint-card-backup"
          className="rounded-lg p-5"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-mono" style={{ color: 'var(--ink-3)' }}>
              {t('maint.backup.title')}
            </h2>
            <span
              className="text-xs px-2 py-0.5 rounded font-mono"
              style={{ background: statusBadge(backup).bg, color: statusBadge(backup).fg }}
            >
              {statusBadge(backup).text}
            </span>
          </div>
          <p className="text-xs mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('maint.backup.desc')}
          </p>
          <button
            type="button"
            onClick={runBackupVerify}
            disabled={backup === 'running'}
            className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
            style={{ background: 'var(--mint)', color: 'var(--text-on-success, #fff)' }}
          >
            {backup === 'running' ? t('maint.status.running') : t('maint.backup.cta')}
          </button>
          {backupInfo && (
            <div className="mt-3 text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
              {backupInfo.latest_backup && (
                <div>{t('maint.backup.latest')}: {backupInfo.latest_backup}</div>
              )}
              {backupInfo.age_hours != null && (
                <div>{t('maint.backup.age')}: {backupInfo.age_hours.toFixed(1)}h</div>
              )}
            </div>
          )}
        </section>

        {/* 索引重建 */}
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
              style={{ background: statusBadge(vacuum).bg, color: statusBadge(vacuum).fg }}
            >
              {statusBadge(vacuum).text}
            </span>
          </div>
          <p className="text-xs mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('maint.vacuum.desc')}
          </p>
          <button
            type="button"
            onClick={runVacuum}
            disabled={vacuum === 'running'}
            className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
            style={{ background: 'var(--mint)', color: 'var(--text-on-success, #fff)' }}
          >
            {vacuum === 'running' ? t('maint.status.running') : t('maint.vacuum.cta')}
          </button>
          {vacuumInfo && (
            <div className="mt-3 text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
              {vacuumInfo.duration_ms != null && (
                <div>{t('maint.vacuum.duration')}: {vacuumInfo.duration_ms}ms</div>
              )}
              {vacuumInfo.reindexed != null && (
                <div>{t('maint.vacuum.reindexed')}: {vacuumInfo.reindexed}</div>
              )}
            </div>
          )}
        </section>

        {/* 清理 */}
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
              style={{ background: statusBadge(cleanup).bg, color: statusBadge(cleanup).fg }}
            >
              {statusBadge(cleanup).text}
            </span>
          </div>
          <p className="text-xs mb-4" style={{ color: 'var(--ink-3)' }}>
            {t('maint.cleanup.desc')}
          </p>
          <div className="flex items-center gap-3 mb-3">
            <label className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
              {t('maint.cleanup.cutoffDays')}
            </label>
            <input
              type="number"
              min={7}
              max={365}
              value={cutoffDays}
              onChange={(e) => setCutoffDays(Number(e.target.value))}
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
                onClick={runCleanup}
                disabled={cleanup === 'running'}
                className="text-sm px-3 py-2 rounded font-mono disabled:opacity-50"
                style={{ background: 'var(--color-error)', color: 'var(--text-on-warning, #fff)' }}
              >
                {t('maint.cleanup.confirm')}
              </button>
              <button
                type="button"
                onClick={() => setCleanupConfirm(false)}
                className="text-sm px-3 py-2 rounded font-mono"
                style={{ background: 'var(--bg-elevated)', color: 'var(--ink-2)' }}
              >
                {t('maint.cleanup.cancel')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setCleanupConfirm(true)}
              disabled={cleanup === 'running'}
              className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
              style={{ background: 'var(--bg-elevated)', color: 'var(--ink)' }}
            >
              {cleanup === 'running' ? t('maint.status.running') : t('maint.cleanup.cta')}
            </button>
          )}
          {cleanupInfo && (
            <div className="mt-3 text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
              {cleanupInfo.deleted != null && (
                <div>{t('maint.cleanup.deleted')}: {cleanupInfo.deleted}</div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}