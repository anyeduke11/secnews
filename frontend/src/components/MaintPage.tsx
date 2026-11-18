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
 *
 * B6-a 拆分: 类型 → MaintPage.types.ts, 共享小件 → MaintPageParts.tsx,
 * 三张卡 → MaintPageHealthCard / MaintPageVacuumCard / MaintPageCleanupCard.
 * 本文件只保留请求编排与页面骨架 (行为未变)。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  cleanupQualityLogs,
  getMaintenanceDirtyReport,
  getMaintenanceHealth,
  getMaintenanceIndexHealth,
  getMaintenanceQualityLogTiers,
  runMaintenanceVacuum,
} from '../api/settings';
import { useI18n } from '../contexts/I18nContext';
import { useAbortGuard } from '../hooks/useAbortGuard';
import { MaintPageCleanupCard } from './MaintPageCleanupCard';
import { MaintPageHealthCard } from './MaintPageHealthCard';
import { MaintPageVacuumCard } from './MaintPageVacuumCard';
import { PageHeader } from '../primitives/PageHeader';
import type {
  CleanupResp,
  DirtyReportResp,
  HealthResp,
  IndexHealthResp,
  TiersResp,
  ToolStatus,
  VacuumResp,
} from './MaintPage.types';

export function MaintPage() {
  const { t } = useI18n();
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [dirty, setDirty] = useState<DirtyReportResp | null>(null);
  const [healthError, setHealthError] = useState(false); // DEV-0317: 监控 fail-loud
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
          getMaintenanceHealth<HealthResp>(),
          getMaintenanceDirtyReport<DirtyReportResp>(),
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
        const ih = await getMaintenanceIndexHealth<IndexHealthResp>();
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
        const tr = await getMaintenanceQualityLogTiers<TiersResp>(cutoffDays);
        if (dead.current) return;
        setTiers(tr);
        setTiersError(false);
      } catch {
        if (dead.current) return;
        setTiersError(true);
      }
    })();
    await Promise.all([healthP, indexP, tiersP]);
  }, [dead, cutoffDays]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const runVacuum = useCallback(async () => {
    setVacuum('running');
    try {
      const r = await runMaintenanceVacuum<VacuumResp>({});
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
      const r = await cleanupQualityLogs<CleanupResp>(cutoffDays * 3);
      if (dead.current) return;
      setCleanupInfo(r);
      setCleanup('ok');
      fetchHealth();
    } catch {
      if (dead.current) return;
      setCleanup('error');
    }
  }, [cutoffDays, fetchHealth, dead]);

  return (
    <div className="px-6 py-8 max-w-7xl mx-auto">
      <PageHeader title={t('maint.title')} description={t('maint.subtitle')} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 健康: 只读 */}
        <MaintPageHealthCard
          health={health}
          dirty={dirty}
          healthError={healthError}
          onRefresh={fetchHealth}
        />

        {/* 索引重建 */}
        <MaintPageVacuumCard
          indexHealth={indexHealth}
          indexHealthError={indexHealthError}
          vacuum={vacuum}
          vacuumInfo={vacuumInfo}
          onRunVacuum={runVacuum}
        />

        {/* 清理 */}
        <MaintPageCleanupCard
          tiers={tiers}
          tiersError={tiersError}
          cleanup={cleanup}
          cleanupInfo={cleanupInfo}
          cutoffDays={cutoffDays}
          cleanupConfirm={cleanupConfirm}
          onCutoffDaysChange={setCutoffDays}
          onRunCleanup={runCleanup}
          onRequestConfirm={() => setCleanupConfirm(true)}
          onCancelConfirm={() => setCleanupConfirm(false)}
        />
      </div>
    </div>
  );
}