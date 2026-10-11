/**
 * NAV4 P3 (2026-09-13, DEV-0178): 维护诊断 /maint
 *
 * 4 工具卡 (备份/索引/清理/健康), 走 /api/maintenance/* 真实端点.
 * 后端 10 端点已存在 (backend/api/maintenance.py), 本页是它们的
 * 顶层直达入口 (与 /settings?cat=maintenance 共存).
 *
 * DEV-0317 契约修正: 健康卡字段类型按 maintenance_service 真实响应重写
 * (旧版凭想象写 db_size_mb/table_count/fragmentation/cleanup_candidates,
 * 全部对不上 → 恒显「—」且无测试, 静默两个月)。监控呈现 fail-loud:
 * 接口失败显式报错, 不再与"数据缺失"共用「—」。
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

/** 后端权威形状 = maintenance_service.db_health() (fragmentation_pct 已是百分数)。 */
interface HealthResp {
  size_mb?: number;
  page_count?: number;
  freelist_pages?: number;
  fragmentation_pct?: number;
  journal_mode?: string;
}

/** 后端权威形状 = maintenance_service.dirty_data_report() (嵌套;
 * DEV-0322: older_than_7_days → older_than_retention, 口径改台账动态
 * retention 且与 archive_quality_logs 同 isoformat cutoff)。 */
interface DirtyReportResp {
  quality_check_logs?: { total?: number; older_than_retention?: number; retention_days?: number };
  duplicate_hotspots?: number;
  duplicate_knowledge_items?: number;
  orphan_raw_items?: number;
  invalid_urls?: number;
}

/** 后端权威形状 = GET /quality-log-tiers (DEV-0322 进程内实测:
 * bands 末档 in_window=false 的 rows = 此刻点"清理"将真实归档的量)。 */
interface TierBand {
  index: number;
  in_window: boolean;
  from_days: number | null;
  to_days: number;
  rows: number;
  est_bytes: number;
}

interface TiersResp {
  tier_days?: number;
  tiers?: number;
  window_days?: number;
  ledger_retention_days?: number;
  total_rows?: number;
  avg_row_bytes?: number;
  total_est_bytes?: number;
  bands?: TierBand[];
}

/** 后端权威形状 = backup_verify_service.verify_latest_backup() (DEV-0323 实测:
 * 旧 {latest_backup, age_hours, message} 为想象契约 — 三个字段后端从不返回,
 * 校验成功也恒显示空结果)。 */
interface BackupVerifyResp {
  ok?: boolean;
  checked_at?: string;
  backup_path?: string;
  errors?: string[];
  duration_ms?: number;
  integrity_check?: string;
  knowledge_zip?: { present: boolean; ok: boolean };
}

/** 后端权威形状 = GET /api/maintenance/backups (backup_inventory, DEV-0323
 * 进程内实测: fulls 倒序 / chain.files 含 pages / policy 不变量声明)。 */
interface BackupInventoryResp {
  checked_at?: string;
  policy?: { full_keep?: number; incremental_keep?: number; side_db_keep?: number; invariant?: string };
  fulls?: { name: string; size_mb: number; age_hours: number }[];
  chain?: { count: number; files: { name: string; size_kb: number; pages: number; age_hours: number }[] };
  side_dbs?: { warm: number; cold: number };
  knowledge?: { full_zip_count: number; inc_zip_count: number };
  last_integrity_marker?: { name: string; age_hours: number } | null;
  totals?: { bytes: number; mb: number };
}

/** 后端权威形状 = POST /api/maintenance/backups/compact (compact_backup_chain)。 */
interface CompactResp {
  ok?: boolean;
  compacted?: boolean;
  error?: string | null;
  new_full?: string | null;
  absorbed_bins?: string[];
  removed_fulls?: string[];
  removed_stale_bins?: string[];
  removed_knowledge_inc?: number;
  chain_active?: number;
}

/** 后端权威形状 = maintenance_service.run_vacuum() (DEV-0318: 旧 ok/duration_ms/reindexed 为想象契约)。 */
interface VacuumResp {
  status?: string;
  total_seconds?: number;
}

/** 后端权威形状 = GET /api/maintenance/index-health (DEV-0320, 进程内实测:
 * check=ok|\"N issues\"|probe_failed:*; user/auto 索引分列;
 * stat1_covered 为绝对数展示 — 小表/纯 autoindex 表 ANALYZE 有意跳过,
 * 覆盖率分母会制造"欠 stats"假异常, 前端不用 tables_with_indexes 组成比率)。 */
interface IndexHealthSchema {
  schema: string;
  file: string;
  user_indexes: number;
  auto_indexes: number;
  tables_with_indexes: number;
  stat1_covered: number;
  check: string;
  check_errors: string[];
  check_ms: number;
}

interface IndexHealthResp {
  mode?: string;
  checked_at?: string;
  schemas?: IndexHealthSchema[];
  totals?: {
    user_indexes: number;
    auto_indexes: number;
    schemas_ok: number;
    schemas_total: number;
  };
}

/** 后端权威形状 = cleanup_quality_logs() (薄包装 archive_quality_logs;
 * DEV-0318: 旧 /cleanup + {deleted} 全对不上 → 按钮永远空跑)。 */
interface CleanupResp {
  dry_run?: boolean;
  retention_days?: number;
  rows_to_delete?: number;
  rows_archived?: number;
  rows_remaining_after?: number;
}

type ToolStatus = 'idle' | 'running' | 'ok' | 'error';

function fmtBytes(n: number): string {
  // avg 宽度估算展示 (后端口径: 文本列 SUM(LENGTH) + 数值列 ~10B/行)
  if (n <= 0) return '0 KB';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function MaintPage() {
  const { t } = useI18n();
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [dirty, setDirty] = useState<DirtyReportResp | null>(null);
  const [healthError, setHealthError] = useState(false); // DEV-0317: 监控 fail-loud
  const [backup, setBackup] = useState<ToolStatus>('idle');
  const [backupInfo, setBackupInfo] = useState<BackupVerifyResp | null>(null);
  const [backupInv, setBackupInv] = useState<BackupInventoryResp | null>(null);
  const [backupInvError, setBackupInvError] = useState(false); // DEV-0323: fail-loud
  const [compactInfo, setCompactInfo] = useState<CompactResp | null>(null);
  const [vacuum, setVacuum] = useState<ToolStatus>('idle');
  const [vacuumInfo, setVacuumInfo] = useState<VacuumResp | null>(null);
  const [indexHealth, setIndexHealth] = useState<IndexHealthResp | null>(null);
  const [indexHealthError, setIndexHealthError] = useState(false); // DEV-0320: fail-loud
  const [cleanup, setCleanup] = useState<ToolStatus>('idle');
  const [cleanupInfo, setCleanupInfo] = useState<CleanupResp | null>(null);
  const [tiers, setTiers] = useState<TiersResp | null>(null);
  const [tiersError, setTiersError] = useState(false); // DEV-0322: fail-loud
  const [cleanupConfirm, setCleanupConfirm] = useState(false);
  const [cutoffDays, setCutoffDays] = useState(7); // DEV-0322: 档宽 (台账 21=3档×7), 窗口=档宽×3
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const fetchHealth = useCallback(async () => {
    // 三路并行、失败态互不影响 (DEV-0320/0322: 索引探测与分档统计各自 ~1s)
    const healthP = (async () => {
      try {
        const [h, d] = await Promise.all([
          getJSON<HealthResp>('/api/maintenance/health'),
          getJSON<DirtyReportResp>('/api/maintenance/dirty-report'),
        ]);
        if (dead.current) return;
        setHealth(h);
        setDirty(d);
        setHealthError(false);
      } catch {
        // DEV-0317: 不再静默显示「—」— 监控页把"接口失败"如实呈现为错误态
        if (dead.current) return;
        setHealthError(true);
      }
    })();
    const indexP = (async () => {
      try {
        const ih = await getJSON<IndexHealthResp>('/api/maintenance/index-health');
        if (dead.current) return;
        setIndexHealth(ih);
        setIndexHealthError(false);
      } catch {
        if (dead.current) return;
        setIndexHealthError(true);
      }
    })();
    const tiersP = (async () => {
      try {
        const tr = await getJSON<TiersResp>(`/api/maintenance/quality-log-tiers?days=${cutoffDays}`);
        if (dead.current) return;
        setTiers(tr);
        setTiersError(false);
      } catch {
        if (dead.current) return;
        setTiersError(true);
      }
    })();
    // DEV-0323: 备份盘点 (纯 stat 毫秒级, stat 密集仍让出主线程走 fetch)
    const backupP = (async () => {
      try {
        const bi = await getJSON<BackupInventoryResp>('/api/maintenance/backups');
        if (dead.current) return;
        setBackupInv(bi);
        setBackupInvError(false);
      } catch {
        if (dead.current) return;
        setBackupInvError(true);
      }
    })();
    await Promise.all([healthP, indexP, tiersP, backupP]);
  }, [dead, cutoffDays]);

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

  const runBackupCompact = useCallback(async () => {
    setBackup('running');
    try {
      const r = await postJSON<CompactResp>('/api/maintenance/backups/compact', {});
      if (dead.current) return;
      setCompactInfo(r);
      setBackup(r.ok ? 'ok' : 'error');
      // 整理结果直接影响盘点数字 → 刷新状态块
      const bi = await getJSON<BackupInventoryResp>('/api/maintenance/backups');
      if (!dead.current) setBackupInv(bi);
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
      setVacuum(r.status === 'ok' ? 'ok' : 'error');
      if (r.status === 'ok') fetchHealth(); // DEV-0320: 重建后索引状态/统计覆盖闭环刷新
    } catch {
      if (dead.current) return;
      setVacuum('error');
    }
  }, [dead, fetchHealth]);

  const runCleanup = useCallback(async () => {
    setCleanup('running');
    setCleanupConfirm(false);
    try {
      // DEV-0318: 旧调用 POST /cleanup + body{cutoff_days} 参数被后端全忽略、
      // dry_run 默认 true → 永不真实删除。改调 qcl 归档端点 (与 /settings 版
      // DatabaseMaintenance 一致), query 参数 + dry_run=false。
      // DEV-0322 三档模型: 保留窗口 = 档宽(cutoffDays) × 3 档; 每次清理
      // 归档滚出窗口的最旧一档 (与分档展示"超窗口"行同一 cutoff 口径)。
      const r = await postJSON<CleanupResp>(
        `/api/maintenance/cleanup-quality-logs?days=${cutoffDays * 3}&dry_run=false`,
        undefined,
      );
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
          {/* DEV-0323: 备份现状 (滚动保留不变量 1 full + ≤3 增量档, 真实盘点) */}
          <div className="mb-4 rounded p-3" style={{ background: 'var(--bg-elevated)' }} data-testid="maint-backup-status">
            {backupInvError && !backupInv ? (
              <p className="text-xs font-mono" role="alert" style={{ color: 'var(--color-error)' }}>
                {t('maint.backup.inventoryError')}
              </p>
            ) : backupInv?.fulls ? (
              <div className="space-y-1.5">
                {backupInv.fulls.map((f, i) => (
                  <div key={f.name} data-testid={`maint-backup-full-${i}`} className="text-xs font-mono flex items-baseline justify-between gap-2">
                    <span className="shrink-0" style={{ color: 'var(--ink-2)' }}>
                      {i === 0 ? t('maint.backup.fullLatest') : t('maint.backup.fullOld')}
                      {' · '}{f.name}
                    </span>
                    <span style={{ color: i === 0 ? 'var(--ink-2)' : 'var(--color-warning)' }}>
                      {f.size_mb} MB · {f.age_hours}{t('maint.backup.hoursUnit')}
                    </span>
                  </div>
                ))}
                <div data-testid="maint-backup-chain" className="text-xs font-mono flex items-baseline justify-between gap-2">
                  <span style={{ color: 'var(--ink-2)' }}>
                    {t('maint.backup.chain')} {backupInv.chain?.count ?? 0}/{backupInv.policy?.incremental_keep ?? 3}
                    {t('maint.backup.tiersUnit')}
                  </span>
                  {(backupInv.chain?.files.length ?? 0) > 0 && (
                    <span className="text-right" style={{ color: 'var(--ink-3)' }}>
                      ~{Math.round((backupInv.chain?.files[0]?.size_kb ?? 0))} KB · {backupInv.chain?.files[0]?.pages ?? 0} {t('maint.backup.pages')}
                    </span>
                  )}
                </div>
                <div className="text-xs font-mono flex items-baseline justify-between gap-2">
                  <span style={{ color: 'var(--ink-2)' }}>
                    {t('maint.backup.knowledge')} {backupInv.knowledge?.inc_zip_count ?? 0}
                    {' · '}{t('maint.backup.sideDbs')} {(backupInv.side_dbs?.warm ?? 0) + (backupInv.side_dbs?.cold ?? 0)}
                  </span>
                  <span style={{ color: 'var(--ink-3)' }}>{t('maint.backup.total')} ~{((backupInv.totals?.mb ?? 0) / 1024).toFixed(2)} GB</span>
                </div>
                {backupInv.last_integrity_marker && (
                  <div className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
                    {t('maint.backup.marker')}: {Math.round(backupInv.last_integrity_marker.age_hours)}{t('maint.backup.hoursUnit')}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs font-mono" style={{ color: 'var(--ink-3)' }}>
                {t('maint.backup.inventoryLoading')}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 mb-3">
            <button
              type="button"
              onClick={runBackupVerify}
              disabled={backup === 'running'}
              className="text-sm px-4 py-2 rounded font-mono disabled:opacity-50"
              style={{ background: 'var(--mint)', color: 'var(--text-on-success, #fff)' }}
            >
              {backup === 'running' ? t('maint.status.running') : t('maint.backup.cta')}
            </button>
            <button
              type="button"
              onClick={runBackupCompact}
              disabled={backup === 'running'}
              className="text-sm px-3 py-2 rounded font-mono disabled:opacity-50"
              style={{ background: 'var(--bg-elevated)', color: 'var(--ink)' }}
              data-testid="maint-backup-compact"
            >
              {t('maint.backup.compact')}
            </button>
          </div>
          {compactInfo && (
            <div data-testid="maint-backup-compact-result" className="mb-2 text-xs font-mono" style={{ color: compactInfo.ok ? 'var(--ink-2)' : 'var(--color-error)' }}>
              {compactInfo.ok
                ? (compactInfo.compacted
                  ? `${t('maint.backup.compactedResult')} ${compactInfo.absorbed_bins?.length ?? 0} · ${t('maint.backup.removedFulls')} ${compactInfo.removed_fulls?.length ?? 0} · ${t('maint.backup.removedZips')} ${compactInfo.removed_knowledge_inc ?? 0}`
                  : `${t('maint.backup.noCompact')} (chain ${compactInfo.chain_active ?? 0})`)
                : `${t('maint.backup.compactFailed')}: ${compactInfo.error ?? ''}`}
            </div>
          )}
          {backupInfo && (
            <div className="mt-1 text-xs font-mono" data-testid="maint-backup-verify-result" style={{ color: backupInfo.ok ? 'var(--ink-2)' : 'var(--color-error)' }}>
              {backupInfo.ok ? (
                <>
                  <div style={{ wordBreak: 'break-all' }}>{backupInfo.backup_path}</div>
                  <div>
                    {t('maint.backup.integrity')}: {backupInfo.integrity_check ?? '?'} · {backupInfo.duration_ms}ms
                    {backupInfo.knowledge_zip ? ` · ${t('maint.backup.zip')}: ${backupInfo.knowledge_zip.ok ? 'ok' : 'bad'}` : ''}
                  </div>
                </>
              ) : (
                <div style={{ wordBreak: 'break-all' }}>
                  {(backupInfo.errors ?? []).slice(0, 2).join(' | ')}
                </div>
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
            onClick={runVacuum}
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
              {cleanupInfo.rows_archived != null && (
                <div>{t('maint.cleanup.archived')}: {cleanupInfo.rows_archived}</div>
              )}
              {cleanupInfo.rows_remaining_after != null && (
                <div>{t('maint.cleanup.remaining')}: {cleanupInfo.rows_remaining_after}</div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}