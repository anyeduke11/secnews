/**
 * settings/DatabaseMaintenance — 数据库维护 (Sentinel V2)。
 *
 * 拆分自原 SettingsPage.tsx (1065 行) 中 DatabaseMaintenance 段.
 *
 * 设计原则:
 * - 顶部 4 格状态卡 (SIZE / FRAG / LOGS / DUPS) 取代零碎分布
 * - 维护动作区 st-section + st-rule 编辑行 + st-actionbar footer
 * - 危险动作 (清理历史) 用 st-dangerline + danger label 区分
 * - 重复数据详情用 st-table 列表
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useCallback, useEffect } from 'react';
import '../settings/settings-shell.css';

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

  type Msg = { kind: 'ok' | 'bad' | 'mute'; text: string } | null;
  const [vacuumMsg, setVacuumMsg] = useState<Msg>(null);
  const [cacheMsg, setCacheMsg] = useState<Msg>(null);
  const [dedupMsg, setDedupMsg] = useState<Msg>(null);
  const [cleanLogsMsg, setCleanLogsMsg] = useState<Msg>(null);
  const [cleanMsg, setCleanMsg] = useState<Msg>(null);

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
      const r = await fetch(`/api/maintenance/cleanup-quality-logs?days=${qualityLogDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
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
      const r = await fetch('/api/maintenance/cleanup-duplicates?dry_run=false', { method: 'POST' });
      const d = await r.json();
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
      const r = await fetch(`/api/maintenance/cleanup?days=${retentionDays}&dry_run=false`, { method: 'POST' });
      const d = await r.json();
      setCleanMsg({ kind: 'ok', text: `历史清理完成: ${d.total_rows || 0} 条` });
      await loadData();
    } catch { setCleanMsg({ kind: 'bad', text: '清理请求失败' }); }
    finally { setCleaning(false); }
  };

  const handleClearCache = async () => {
    setCacheClearing(true);
    setCacheMsg(null);
    try {
      const r = await fetch('/api/cache/clear', { method: 'POST' });
      const d = await r.json();
      setCacheMsg(d.status === 'ok' ? { kind: 'ok', text: '缓存已清除' } : { kind: 'bad', text: '清除失败' });
    } catch { setCacheMsg({ kind: 'bad', text: '清除请求失败' }); }
    finally { setCacheClearing(false); }
  };

  const topTables = tableStats?.filter(t => t.rows > 0).sort((a, b) => b.rows - a.rows).slice(0, 10) || [];
  const dupCount = duplicates?.hotspots?.length ?? 0;
  const kiDupCount = duplicates?.knowledge_items?.length ?? 0;

  // 派生语义三色: 数据体积 / 碎片 / 脏数据
  const sizeMB = dbHealth?.size_mb ?? 0;
  const fragPct = dbHealth?.fragmentation_pct ?? 0;
  const cleanableLogs = dirtyReport?.quality_check_logs?.older_than_7_days ?? 0;
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
      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">SIZE</span>
          <span className={`st-cellv ${sizeTone === 'mint' ? '' : sizeTone}`}>
            {sizeMB ? `${sizeMB.toFixed(1)} MB` : '—'}
          </span>
          <span className="st-cellnote">{dbHealth?.journal_mode || 'journal'} · {sizeTone === 'red' ? '过大' : sizeTone === 'amber' ? '关注' : '健康'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">FRAGMENTATION</span>
          <span className={`st-cellv ${fragTone === 'mint' ? '' : fragTone}`}>
            {dbHealth?.fragmentation_pct != null ? `${dbHealth.fragmentation_pct.toFixed(1)}%` : '—'}
          </span>
          <span className="st-cellnote">{fragTone === 'red' ? '建议 VACUUM' : fragTone === 'amber' ? '可压缩' : 'OK'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">CLEANABLE LOGS</span>
          <span className={`st-cellv ${cleanableLogs > 1000 ? 'red' : cleanableLogs > 100 ? 'amber' : ''}`}>
            {cleanableLogs.toLocaleString()}
          </span>
          <span className="st-cellnote">超过 7 天可清理</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">DIRTY DATA</span>
          <span className={`st-cellv ${dirtyTone === 'mint' ? '' : dirtyTone}`}>
            {dupCount + kiDupCount + invalidUrls || '—'}
          </span>
          <span className="st-cellnote">
            {dupCount} 重复URL + {kiDupCount} 重复标题 + {invalidUrls} 无效URL
          </span>
        </div>
      </div>

      {/* 大表 Top 10 */}
      {topTables.length > 0 && (
        <div className="st-section">
          <div className="st-section-body" style={{ padding: 0 }}>
            <table className="st-table">
              <thead>
                <tr>
                  <th>表名</th>
                  <th style={{ width: 120, textAlign: 'right' }}>行数</th>
                </tr>
              </thead>
              <tbody>
                {topTables.map(t => (
                  <tr key={t.table}>
                    <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 12 }}>{t.table}</td>
                    <td style={{ fontFamily: 'var(--sn-mono)', textAlign: 'right', color: 'var(--sn-ink-2)' }}>
                      {t.rows.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 维护操作 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">维护操作</span>
            <div className="st-ctrlrow" style={{ flexWrap: 'wrap', gap: 6 }}>
              <button
                className="st-btn"
                onClick={handleVacuum}
                disabled={vacuuming}
              >
                {vacuuming ? '压缩中...' : 'VACUUM 压缩'}
              </button>
              <button
                className="st-btn"
                onClick={handleClearCache}
                disabled={cacheClearing}
              >
                {cacheClearing ? '清除中...' : '清除缓存'}
              </button>
              <button
                className="st-btn"
                onClick={handleDedup}
                disabled={deduping}
              >
                {deduping ? '去重中...' : '重复数据去重'}
              </button>
            </div>
          </div>

          {(vacuumMsg || cacheMsg || dedupMsg) && (
            <div className="st-rule" style={{ borderBottom: 'none' }}>
              <span className="st-label">结果</span>
              <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
                {vacuumMsg && <span className={`st-ab-msg ${vacuumMsg.kind}`}>{vacuumMsg.text}</span>}
                {cacheMsg && <span className={`st-ab-msg ${cacheMsg.kind}`}>{cacheMsg.text}</span>}
                {dedupMsg && <span className={`st-ab-msg ${dedupMsg.kind}`}>{dedupMsg.text}</span>}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 质量日志保留期 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">质量日志保留期</span>
            <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input
                  type="range" min={1} max={90} step={1}
                  value={qualityLogDays}
                  onChange={e => setQualityLogDays(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 13, color: 'var(--sn-mint)', minWidth: 56, textAlign: 'right' }}>
                  {qualityLogDays} 天
                </span>
              </div>
              <span className="st-cellnote">保留最近 {qualityLogDays} 天的质量检测日志</span>
            </div>
          </div>

          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">立即清理</span>
            <div className="st-ctrl">
              <button
                className="st-btn"
                onClick={handleCleanupQualityLogs}
                disabled={cleaningLogs}
              >
                {cleaningLogs ? '清理中...' : `清理质量日志 (保留 ${qualityLogDays} 天)`}
              </button>
              {cleanLogsMsg && <span className={`st-ab-msg ${cleanLogsMsg.kind}`}>{cleanLogsMsg.text}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* 历史数据保留期 — 危险动作 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label" style={{ color: 'var(--sn-red)' }}>历史数据保留期</span>
            <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input
                  type="range" min={7} max={365} step={1}
                  value={retentionDays}
                  onChange={e => setRetentionDays(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 13, color: 'var(--sn-red)', minWidth: 56, textAlign: 'right' }}>
                  {retentionDays} 天
                </span>
              </div>
              <span className="st-cellnote" style={{ color: 'var(--sn-amber)' }}>
                保留期外数据将永久删除, 不可恢复
              </span>
            </div>
          </div>

          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">立即清理</span>
            <div className="st-ctrl">
              <button
                className="st-btn danger"
                onClick={handleCleanup}
                disabled={cleaning}
              >
                {cleaning ? '清理中...' : `清理历史数据 (保留 ${retentionDays} 天)`}
              </button>
              {cleanMsg && <span className={`st-ab-msg ${cleanMsg.kind}`}>{cleanMsg.text}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* 重复数据详情 */}
      {(dupCount > 0 || kiDupCount > 0) && (
        <div className="st-section">
          <h3 style={{ margin: '0 0 var(--sn-row) 0', fontSize: 'var(--sn-fs-h3)', color: 'var(--sn-ink)' }}>
            重复数据详情
          </h3>
          <div className="st-section-body" style={{ padding: 0 }}>
            {duplicates?.hotspots && duplicates.hotspots.length > 0 && (
              <div>
                <div style={{
                  padding: '8px 12px',
                  fontFamily: 'var(--sn-mono)',
                  fontSize: 11,
                  color: 'var(--sn-amber)',
                  borderBottom: '1px solid var(--sn-line)',
                  letterSpacing: '0.03em',
                }}>
                  HOTSPOTS 重复 URL · {duplicates.hotspots.length} 组
                </div>
                <table className="st-table">
                  <tbody>
                    {duplicates.hotspots.slice(0, 5).map((d: any, i: number) => (
                      <tr key={i}>
                        <td style={{ width: 56 }}>
                          <span className="st-chip bad">
                            <i /> {d.count}×
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>
                          {d.url?.substring(0, 80)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {duplicates?.knowledge_items && duplicates.knowledge_items.length > 0 && (
              <div>
                <div style={{
                  padding: '8px 12px',
                  fontFamily: 'var(--sn-mono)',
                  fontSize: 11,
                  color: 'var(--sn-amber)',
                  borderBottom: '1px solid var(--sn-line)',
                  letterSpacing: '0.03em',
                }}>
                  KNOWLEDGE 重复标题 · {duplicates.knowledge_items.length} 组
                </div>
                <table className="st-table">
                  <tbody>
                    {duplicates.knowledge_items.slice(0, 5).map((d: any, i: number) => (
                      <tr key={i}>
                        <td style={{ width: 56 }}>
                          <span className="st-chip bad">
                            <i /> {d.count}×
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>
                          {d.title}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}