/**
 * settings/DatabaseMaintenance — 数据库维护。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 DatabaseMaintenance (~683-946 行)。
 * 纯结构拆分: 全部状态 (13 个 useState) 与 fetch/渲染逻辑逐字迁移。
 */
import React, { useState, useCallback, useEffect } from 'react';

export function DatabaseMaintenance() {
  const [dbHealth, setDbHealth] = useState<{ size_mb?: number; fragmentation_pct?: number; journal_mode?: string } | null>(null);
  const [tableStats, setTableStats] = useState<any[] | null>(null);
  const [dirtyReport, setDirtyReport] = useState<any | null>(null);
  const [duplicates, setDuplicates] = useState<{ hotspots?: any[]; knowledge_items?: any[] } | null>(null);

  // 操作状态
  const [vacuuming, setVacuuming] = useState(false);
  const [vacuumMsg, setVacuumMsg] = useState<string | null>(null);
  const [cleaningLogs, setCleaningLogs] = useState(false);
  const [cleanLogsMsg, setCleanLogsMsg] = useState<string | null>(null);
  const [deduping, setDeduping] = useState(false);
  const [dedupMsg, setDedupMsg] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanMsg, setCleanMsg] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState(90);
  const [qualityLogDays, setQualityLogDays] = useState(7);
  const [cacheClearing, setCacheClearing] = useState(false);
  const [cacheMsg, setCacheMsg] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [h, t, d, dup] = await Promise.all([
        fetch('/api/maintenance/health').then(r => r.json()),
        fetch('/api/maintenance/table-stats').then(r => r.json()),
        fetch('/api/maintenance/dirty-report').then(r => r.json()),
        fetch('/api/maintenance/duplicates').then(r => r.json()),
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
      const r = await fetch('/api/maintenance/vacuum', { method: 'POST' });
      const d = await r.json();
      setVacuumMsg(d.status === 'ok' ? `VACUUM 完成 (${d.total_seconds}s)` : 'VACUUM 失败');
      await loadData();
    } catch { setVacuumMsg('VACUUM 请求失败'); }
    finally { setVacuuming(false); }
  };

  const handleCleanupQualityLogs = async () => {
    setCleaningLogs(true);
    setCleanLogsMsg(null);
    try {
      const r = await fetch(`/api/maintenance/cleanup-quality-logs?days=${qualityLogDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
      setCleanLogsMsg(`已清理 ${d.rows_to_delete} 条 quality 日志，剩余 ${d.rows_remaining_after} 条`);
      await loadData();
    } catch { setCleanLogsMsg('清理请求失败'); }
    finally { setCleaningLogs(false); }
  };

  const handleDedup = async () => {
    setDeduping(true);
    setDedupMsg(null);
    try {
      const r = await fetch('/api/maintenance/cleanup-duplicates?dry_run=false', { method: 'POST' });
      const d = await r.json();
      setDedupMsg(`已删除 ${d.total_deleted} 条重复记录 (hotspots ${d.hotspots?.total_deleted || 0} + 知识库 ${d.knowledge_items?.total_deleted || 0})`);
      await loadData();
    } catch { setDedupMsg('去重请求失败'); }
    finally { setDeduping(false); }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanMsg(null);
    try {
      const r = await fetch(`/api/maintenance/cleanup?days=${retentionDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
      setCleanMsg(`历史清理完成: ${d.total_rows || 0} 条`);
      await loadData();
    } catch { setCleanMsg('清理请求失败'); }
    finally { setCleaning(false); }
  };

  const handleClearCache = async () => {
    setCacheClearing(true);
    setCacheMsg(null);
    try {
      const r = await fetch('/api/cache/clear', { method: 'POST' });
      const d = await r.json();
      setCacheMsg(d.status === 'ok' ? '缓存已清除' : '清除失败');
    } catch { setCacheMsg('清除请求失败'); }
    finally { setCacheClearing(false); }
  };

  const topTables = tableStats?.filter(t => t.rows > 0).sort((a, b) => b.rows - a.rows).slice(0, 10) || [];
  const dupCount = duplicates?.hotspots?.length ?? 0;
  const kiDupCount = duplicates?.knowledge_items?.length ?? 0;

  return (
    <div className="space-y-2">
      {/* DB 概览 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>数据库概览</span>
            {dbHealth && (
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {dbHealth.size_mb?.toFixed(1)} MB · 碎片 {dbHealth.fragmentation_pct?.toFixed(1)}%
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-1 text-[9px] font-mono mb-1.5">
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>总行数</span>
              <span style={{ color: 'var(--text-primary)' }}>{dirtyReport?.quality_check_logs?.total?.toLocaleString() || '-'}</span>
            </div>
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>质量日志</span>
              <span style={{ color: 'var(--color-warning)' }}>{dirtyReport?.quality_check_logs?.older_than_7_days?.toLocaleString() || '-'} 条可清理</span>
            </div>
            <div style={{ color: 'var(--text-muted)' }}>
              <span className="block" style={{ color: 'var(--text-secondary)' }}>脏数据</span>
              <span style={{ color: dupCount > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
                {dirtyReport?.duplicate_hotspots || 0} 重复URL · {dirtyReport?.duplicate_knowledge_items || 0} 重复标题
                {dirtyReport?.invalid_urls ? ` · ${dirtyReport.invalid_urls} 无效URL` : ''}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 大表 Top 10 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <span className="text-[11px] font-medium mb-1 block" style={{ color: 'var(--text-primary)' }}>大表 Top 10</span>
          <div className="space-y-0.5 text-[9px] font-mono">
            {topTables.map(t => (
              <div key={t.table} className="flex items-center justify-between px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <span className="truncate" style={{ color: 'var(--text-primary)' }}>{t.table}</span>
                <span style={{ color: 'var(--text-muted)' }}>{t.rows.toLocaleString()} 行</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 操作按钮组 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <span className="text-[11px] font-medium mb-1.5 block" style={{ color: 'var(--text-primary)' }}>维护操作</span>
          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
            <button onClick={handleVacuum} disabled={vacuuming} className="btn-secondary btn-sm">
              {vacuuming ? '压缩中...' : 'VACUUM 压缩'}
            </button>
            <button onClick={handleClearCache} disabled={cacheClearing} className="btn-secondary btn-sm">
              {cacheClearing ? '清除中...' : '清除缓存'}
            </button>
            <button onClick={handleDedup} disabled={deduping} className="btn-secondary btn-sm">
              {deduping ? '去重中...' : '重复数据去重'}
            </button>
            <button onClick={() => { handleCleanupQualityLogs(); }} disabled={cleaningLogs} className="btn-secondary btn-sm" style={{ color: 'var(--color-warning)' }}>
              {cleaningLogs ? '清理中...' : '清理质量日志'}
            </button>
          </div>
          {vacuumMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{vacuumMsg}</p>}
          {cacheMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{cacheMsg}</p>}
          {dedupMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{dedupMsg}</p>}
          {cleanLogsMsg && <p className="text-[9px]" style={{ color: 'var(--color-general)' }}>{cleanLogsMsg}</p>}
        </div>
      </div>

      {/* 质量日志保留期 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>质量日志保留期</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{qualityLogDays} 天</span>
          </div>
          <input
            type="range" min={1} max={90} step={1} value={qualityLogDays}
            onChange={e => setQualityLogDays(Number(e.target.value))}
            className="w-full h-1 accent-[var(--accent)] mb-1.5"
            style={{ accentColor: 'var(--accent)' }}
          />
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>1 天</span>
            <span className="flex-1 text-[9px] text-center" style={{ color: 'var(--text-muted)' }}>
              保留最近 {qualityLogDays} 天的质量日志
            </span>
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>90 天</span>
          </div>
          <button
            onClick={handleCleanupQualityLogs}
            disabled={cleaningLogs}
            className="btn-secondary btn-sm w-full mt-1.5"
          >
            {cleaningLogs ? '清理中...' : `立即清理质量日志 (保留 ${qualityLogDays} 天)`}
          </button>
        </div>
      </div>

      {/* 历史数据保留期 */}
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>历史数据保留期</span>
            <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{retentionDays} 天</span>
          </div>
          <input
            type="range" min={7} max={365} step={1} value={retentionDays}
            onChange={e => setRetentionDays(Number(e.target.value))}
            className="w-full h-1 accent-[var(--accent)] mb-1.5"
            style={{ accentColor: 'var(--accent)' }}
          />
          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className="btn-secondary btn-sm w-full mt-1.5"
          >
            {cleaning ? '清理中...' : `清理历史数据 (保留 ${retentionDays} 天)`}
          </button>
          {cleanMsg && <p className="text-[9px] mt-1" style={{ color: 'var(--color-general)' }}>{cleanMsg}</p>}
        </div>
      </div>

      {/* 重复数据详情 */}
      {(dupCount > 0 || kiDupCount > 0) && (
        <div className="card-compact">
          <div className="px-2.5 py-1.5">
            <span className="text-[11px] font-medium mb-1 block" style={{ color: 'var(--text-primary)' }}>重复数据详情</span>
            {duplicates?.hotspots && duplicates.hotspots.length > 0 && (
              <div className="mb-1">
                <span className="text-[9px] font-medium" style={{ color: 'var(--color-warning)' }}>Hotspots 重复 URL ({duplicates.hotspots.length} 组)</span>
                <div className="space-y-0.5 mt-0.5">
                  {duplicates.hotspots.slice(0, 5).map((d: any, i: number) => (
                    <div key={i} className="flex items-center gap-1 text-[9px] font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                      <span className="text-[8px] px-1 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>{d.count}×</span>
                      <span className="truncate flex-1" style={{ color: 'var(--text-muted)' }}>{d.url?.substring(0, 60)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {duplicates?.knowledge_items && duplicates.knowledge_items.length > 0 && (
              <div>
                <span className="text-[9px] font-medium" style={{ color: 'var(--color-warning)' }}>知识库重复标题 ({duplicates.knowledge_items.length} 组)</span>
                <div className="space-y-0.5 mt-0.5">
                  {duplicates.knowledge_items.slice(0, 5).map((d: any, i: number) => (
                    <div key={i} className="flex items-center gap-1 text-[9px] font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                      <span className="text-[8px] px-1 rounded" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>{d.count}×</span>
                      <span className="truncate flex-1" style={{ color: 'var(--text-muted)' }}>{d.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
