/**
 * settings/DatabaseMaintenance — 数据库维护 (Sentinel V2)。
 *
 * 拆分自原 SettingsPage.tsx (1065 行) 中 DatabaseMaintenance 段.
 *
 * 设计原则:
 * - 顶部 4 格状态卡 (SIZE / FRAG / LOGS / DUPS) 取代零碎分布
 * - 维护动作区 st-section + st-rule 编辑行 + st-actionbar footer
 * - 危险区 (VACUUM / 去重 / 历史清理) 统一收口 + st-dangerline, 全部二次确认后才发请求
 * - 重复数据详情用 st-table 列表
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useCallback, useEffect } from 'react';
import {
  cleanupDuplicates,
  cleanupHistory,
  cleanupQualityLogs,
  clearCache,
  getMaintenanceDirtyReport,
  getMaintenanceDuplicates,
  getMaintenanceHealth,
  getMaintenanceTableStats,
  runMaintenanceVacuum,
} from '../../api/settings';
import '../settings/settings-shell.css';
import type { DangerAction, Msg } from './DatabaseMaintenance.types';
import { StatusCards, TopTables } from './DatabaseMaintenanceStatus';
import { MaintenanceActions } from './DatabaseMaintenanceActions';
import { DangerZone } from './DatabaseMaintenanceDangerZone';
import { DuplicateDetail } from './DatabaseMaintenanceDuplicates';

export function DatabaseMaintenance() {
  const [dbHealth, setDbHealth] = useState<{ size_mb?: number; fragmentation_pct?: number; journal_mode?: string } | null>(null);
  const [tableStats, setTableStats] = useState<any[] | null>(null);
  const [dirtyReport, setDirtyReport] = useState<any | null>(null);
  const [duplicates, setDuplicates] = useState<{ hotspots?: any[]; knowledge_items?: any[] } | null>(null);

  // 操作状态
  const [vacuuming, setVacuuming] = useState(false);
  const [cacheClearing, setCacheClearing] = useState(false);
  const [deduping, setDeduping] = useState(false);
  const [cleaningLogs, setCleaningLogs] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [retentionDays, setRetentionDays] = useState(90);
  const [qualityLogDays, setQualityLogDays] = useState(7);
  /** R-15: 危险区二次确认 — 首次点击只登记待确认动作, 不触达后端 */
  const [pendingDanger, setPendingDanger] = useState<DangerAction | null>(null);

  const [vacuumMsg, setVacuumMsg] = useState<Msg>(null);
  const [cacheMsg, setCacheMsg] = useState<Msg>(null);
  const [dedupMsg, setDedupMsg] = useState<Msg>(null);
  const [cleanLogsMsg, setCleanLogsMsg] = useState<Msg>(null);
  const [cleanMsg, setCleanMsg] = useState<Msg>(null);

  const loadData = useCallback(async () => {
    try {
      const [h, t, d, dup] = await Promise.all([
        getMaintenanceHealth(),
        getMaintenanceTableStats(),
        getMaintenanceDirtyReport(),
        getMaintenanceDuplicates(),
      ]);
      setDbHealth(h);
      setTableStats(t.tables || []);
      setDirtyReport(d);
      setDuplicates(dup);
    } catch {}
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleVacuum = async () => {
    setVacuuming(true);
    setVacuumMsg(null);
    try {
      const d = await runMaintenanceVacuum();
      setVacuumMsg(d.status === 'ok'
        ? { kind: 'ok', text: `VACUUM 完成 (${d.total_seconds}s)` }
        : { kind: 'bad', text: 'VACUUM 失败' });
      await loadData();
    } catch { setVacuumMsg({ kind: 'bad', text: 'VACUUM 请求失败' }); }
    finally { setVacuuming(false); }
  };

  const handleCleanupQualityLogs = async () => {
    setCleaningLogs(true);
    setCleanLogsMsg(null);
    try {
      const d = await cleanupQualityLogs(qualityLogDays);
      setCleanLogsMsg({
        kind: 'ok',
        text: `已清理 ${d.rows_to_delete} 条 quality 日志, 剩余 ${d.rows_remaining_after} 条`,
      });
      await loadData();
    } catch { setCleanLogsMsg({ kind: 'bad', text: '清理请求失败' }); }
    finally { setCleaningLogs(false); }
  };

  const handleDedup = async () => {
    setDeduping(true);
    setDedupMsg(null);
    try {
      const d = await cleanupDuplicates();
      setDedupMsg({
        kind: 'ok',
        text: `已删除 ${d.total_deleted} 条重复 (hotspots ${d.hotspots?.total_deleted || 0} + 知识库 ${d.knowledge_items?.total_deleted || 0})`,
      });
      await loadData();
    } catch { setDedupMsg({ kind: 'bad', text: '去重请求失败' }); }
    finally { setDeduping(false); }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanMsg(null);
    try {
      const d = await cleanupHistory(retentionDays);
      setCleanMsg({ kind: 'ok', text: `历史清理完成: ${d.total_rows || 0} 条` });
      await loadData();
    } catch { setCleanMsg({ kind: 'bad', text: '清理请求失败' }); }
    finally { setCleaning(false); }
  };

  const handleClearCache = async () => {
    setCacheClearing(true);
    setCacheMsg(null);
    try {
      const d = await clearCache();
      setCacheMsg(d.status === 'ok' ? { kind: 'ok', text: '缓存已清除' } : { kind: 'bad', text: '清除失败' });
    } catch { setCacheMsg({ kind: 'bad', text: '清除请求失败' }); }
    finally { setCacheClearing(false); }
  };

  /** 二次确认后分发到具体危险动作 (确认前不长任何请求) */
  const runPendingDanger = () => {
    const action = pendingDanger;
    setPendingDanger(null);
    if (action === 'vacuum') handleVacuum();
    else if (action === 'dedup') handleDedup();
    else if (action === 'cleanup') handleCleanup();
  };

  const topTables = tableStats?.filter(t => t.rows > 0).sort((a, b) => b.rows - a.rows).slice(0, 10) || [];
  const dupCount = duplicates?.hotspots?.length ?? 0;
  const kiDupCount = duplicates?.knowledge_items?.length ?? 0;

  // 派生语义三色: 数据体积 / 碎片 / 脏数据
  const sizeMB = dbHealth?.size_mb ?? 0;
  const fragPct = dbHealth?.fragmentation_pct ?? 0;
  const cleanableLogs = dirtyReport?.quality_check_logs?.older_than_retention ?? 0;
  const invalidUrls = dirtyReport?.invalid_urls ?? 0;

  const sizeTone: 'mint' | 'amber' | 'red' = sizeMB > 200 ? 'red' : sizeMB > 80 ? 'amber' : 'mint';
  const fragTone: 'mint' | 'amber' | 'red' = fragPct > 30 ? 'red' : fragPct > 10 ? 'amber' : 'mint';
  const dirtyTone: 'mint' | 'amber' | 'red' =
    dupCount + kiDupCount + invalidUrls > 50 ? 'red'
    : dupCount + kiDupCount + invalidUrls > 10 ? 'amber'
    : 'mint';

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">数据库维护</h2>
        <p className="st-sub2">
          体检 SQLite 数据库体积 / 碎片 / 脏数据; 提供 VACUUM 压缩 / 缓存清除 / 重复去重 /
          质量日志清理 / 历史数据保留期 等维护动作. 危险动作 (历史清理) 标红, 误操作不可逆.
        </p>
      </div>

      {/* 状态卡 — 4 格 */}
      <StatusCards
        dbHealth={dbHealth}
        sizeMB={sizeMB}
        sizeTone={sizeTone}
        fragTone={fragTone}
        cleanableLogs={cleanableLogs}
        dirtyTone={dirtyTone}
        dupCount={dupCount}
        kiDupCount={kiDupCount}
        invalidUrls={invalidUrls}
      />

      {/* 大表 Top 10 */}
      <TopTables topTables={topTables} />

      <MaintenanceActions
        cacheClearing={cacheClearing}
        onClearCache={handleClearCache}
        cacheMsg={cacheMsg}
        qualityLogDays={qualityLogDays}
        onQualityLogDaysChange={setQualityLogDays}
        cleaningLogs={cleaningLogs}
        onCleanupQualityLogs={handleCleanupQualityLogs}
        cleanLogsMsg={cleanLogsMsg}
      />

      {/* 危险区 — 不可逆动作统一收口, 全部二次确认 */}
      <DangerZone
        vacuuming={vacuuming}
        deduping={deduping}
        cleaning={cleaning}
        retentionDays={retentionDays}
        onRetentionDaysChange={setRetentionDays}
        pendingDanger={pendingDanger}
        onArmDanger={setPendingDanger}
        onCancelDanger={() => setPendingDanger(null)}
        onConfirmDanger={runPendingDanger}
        vacuumMsg={vacuumMsg}
        dedupMsg={dedupMsg}
        cleanMsg={cleanMsg}
      />

      {/* 重复数据详情 */}
      <DuplicateDetail duplicates={duplicates} dupCount={dupCount} kiDupCount={kiDupCount} />
    </div>
  );
}