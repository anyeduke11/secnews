/**
 * SourceSettings — 自定义信源管理 + 自动刷新间隔 (V2 哨兵化)
 *
 * Phase 1B 拆自原 SettingsPanel.tsx; V2 三个 st-section:
 *   1. 数据源健康 (healthStats + deadSources 明细)
 *   2. 信源管理 (新增/启用/禁用/探测/删除) — SourceItem 嵌入保留
 *   3. 自动刷新 (localStorage + 回调)
 */
import { useState, useEffect, useCallback } from 'react';
import { REFRESH_INTERVAL_OPTIONS } from '../../hooks/useRefreshInterval';
import { SourceItem, SourceItemData } from './SourceItem';

interface SourceSettingsProps {
  open: boolean;
  onRefreshIntervalChange?: (minutes: number) => void;
}

type SourceMessage = { type: 'ok' | 'error'; text: string } | null;

export function SourceSettings({ open, onRefreshIntervalChange }: SourceSettingsProps) {
  const [sources, setSources] = useState<SourceItemData[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [sourceMessage, setSourceMessage] = useState<SourceMessage>(null);
  const [addingSource, setAddingSource] = useState(false);

  // P5-3: 源健康汇总
  const [healthStats, setHealthStats] = useState<{
    total?: number; active?: number; grace?: number;
    stale?: number; dead?: number; unknown?: number; disabled?: number;
  } | null>(null);
  const [deadSources, setDeadSources] = useState<Array<{
    id?: string; name?: string; category?: string; status?: string;
    last_error?: string | null;
  }>>([]);

  useEffect(() => {
    if (!open) return;
    fetch('/api/sources/stats')
      .then(r => r.ok ? r.json() : null)
      .then(d => setHealthStats(d))
      .catch(() => {});
    fetch('/api/sources/health/v2')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const all = d?.sources ?? [];
        setDeadSources(all.filter((s: any) => s.status === 'dead' || s.status === 'stale'));
      })
      .catch(() => {});
  }, [open]);

  const resetSource = useCallback(async (cat: string, name: string) => {
    try {
      const r = await fetch(
        `/api/sources/health/by-source/${encodeURIComponent(cat)}/${encodeURIComponent(name)}/reset`,
        { method: 'POST' },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await (await fetch('/api/sources/health/v2')).json();
      setDeadSources((d?.sources ?? []).filter((s: any) => s.status === 'dead' || s.status === 'stale'));
    } catch (e: any) {
      setSourceMessage({ type: 'error', text: `重置失败: ${e?.message || e}` });
    }
  }, []);

  const [currentInterval, setCurrentInterval] = useState<number>(30);
  const [refreshMessage, setRefreshMessage] = useState<SourceMessage>(null);

  const refreshSources = useCallback(async () => {
    try {
      const r = await fetch('/api/sources/custom');
      const d = await r.json();
      setSources(d.sources || []);
    } catch { /* 静默 */ }
  }, []);

  useEffect(() => {
    if (!open) return;
    refreshSources();
    try {
      const stored = localStorage.getItem('hotspot-refresh-interval');
      if (stored) {
        const parsed = JSON.parse(stored);
        const v = Number(parsed?.value);
        if (REFRESH_INTERVAL_OPTIONS.some(o => o.value === v)) {
          setCurrentInterval(v);
        }
      }
    } catch {}
    setRefreshMessage(null);
  }, [open, refreshSources]);

  const addSource = useCallback(async () => {
    if (!newUrl.trim()) {
      setSourceMessage({ type: 'error', text: 'URL 不能为空' });
      return;
    }
    setAddingSource(true);
    setSourceMessage(null);
    try {
      const r = await fetch('/api/sources/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: newUrl.trim(), name: newName.trim() }),
      });
      const d = await r.json();
      if (r.ok && d.status === 'ok') {
        setSourceMessage({
          type: 'ok',
          text: `已添加 (分类=${d.category}, 延迟=${d.probe.latency_ms}ms)`,
        });
        setNewUrl('');
        setNewName('');
        refreshSources();
      } else {
        const msg = d.detail?.message || d.message || '添加失败';
        setSourceMessage({ type: 'error', text: msg });
      }
    } catch {
      setSourceMessage({ type: 'error', text: '请求失败' });
    } finally {
      setAddingSource(false);
    }
  }, [newUrl, newName, refreshSources]);

  const deleteSource = useCallback(async (id: number) => {
    if (!confirm(`确定删除 source #${id}?`)) return;
    try {
      await fetch(`/api/sources/custom/${id}`, { method: 'DELETE' });
    } catch {}
    refreshSources();
  }, [refreshSources]);

  const toggleSource = useCallback(async (id: number, enabled: boolean) => {
    try {
      await fetch(`/api/sources/custom/${id}/toggle?enabled=${enabled}`, { method: 'POST' });
    } catch {}
    refreshSources();
  }, [refreshSources]);

  const probeSource = useCallback(async (id: number) => {
    try {
      const r = await fetch(`/api/sources/custom/${id}/probe`, { method: 'POST' });
      const d = await r.json();
      if (d.status === 'ok') {
        setSourceMessage({ type: 'ok', text: `探测成功: ${d.probe.latency_ms}ms` });
      } else {
        setSourceMessage({ type: 'error', text: `探测失败: ${d.probe?.error || 'unknown'}` });
      }
    } catch {
      setSourceMessage({ type: 'error', text: '探测请求失败' });
    }
    refreshSources();
  }, [refreshSources]);

  return (
    <div className="space-y-3" data-testid="source-settings">
      {/* 数据源健康 */}
      {healthStats && (healthStats.total ?? 0) > 0 && (
        <section className="st-section" aria-label="数据源健康">
          <h3>数据源健康: 共 {healthStats.total} 源</h3>
          <p className="st-section-desc">
            失效源由源级调度器跳过; 可手动重置或等待每日 03:30 探活恢复。
          </p>
          <div className="st-section-body">
            <div className="st-ctrlrow" style={{ gap: 8 }}>
              <span className="st-chip ok"><i aria-hidden />活跃 {healthStats.active ?? 0}</span>
              {(healthStats.grace ?? 0) > 0 && <span className="st-chip mute"><i aria-hidden />观察 {healthStats.grace}</span>}
              {(healthStats.stale ?? 0) > 0 && <span className="st-chip warn"><i aria-hidden />滞后 {healthStats.stale}</span>}
              {(healthStats.dead ?? 0) > 0 && <span className="st-chip bad"><i aria-hidden />失效 {healthStats.dead}</span>}
              {(healthStats.unknown ?? 0) > 0 && <span className="st-chip mute"><i aria-hidden />待定 {healthStats.unknown}</span>}
              {(healthStats.disabled ?? 0) > 0 && <span className="st-chip mute"><i aria-hidden />禁用 {healthStats.disabled}</span>}
            </div>
            {deadSources.length > 0 && (
              <table className="st-table" aria-label="失效/滞后源明细">
                <thead>
                  <tr><th>源</th><th>错误</th><th style={{ width: 80 }}>操作</th></tr>
                </thead>
                <tbody>
                  {deadSources.map(s => (
                    <tr key={s.id || `${s.category}/${s.name}`} className={s.status === 'dead' ? 'is-warn' : ''}>
                      <td>
                        <span className="st-nm">{s.category}/{s.name}</span>
                        <span className={`st-chip ${s.status === 'dead' ? 'bad' : 'warn'}`} style={{ marginLeft: 8 }}>
                          <i aria-hidden />{s.status}
                        </span>
                      </td>
                      <td style={{ color: 'var(--sn-ink-3)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis' }}
                          title={s.last_error ?? ''}>
                        {s.last_error || '—'}
                      </td>
                      <td>
                        <button type="button" className="st-btn primary" onClick={() => resetSource(s.category || '', s.name || '')}>
                          重置
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* 信源管理 */}
      <section className="st-section" aria-label="信源管理">
        <h3>信源管理 ({sources.length})</h3>
        <p className="st-section-desc">
          增删改查自定义信源 — 添加时自动探测延迟与分类, 启用/禁用即时生效。
        </p>
        <div className="st-section-body">
          <div className="st-rule">
            <div>
              <p className="st-label">URL</p>
              <p className="st-key">https://example.com/news</p>
            </div>
            <div className="st-ctrl">
              <input
                type="text" value={newUrl} onChange={e => setNewUrl(e.target.value)}
                placeholder="https://example.com/news"
                className="st-input" aria-label="新信源 URL"
                data-testid="source-url-input"
              />
            </div>
          </div>
          <div className="st-rule">
            <div><p className="st-label">名称</p><p className="st-key">可选</p></div>
            <div className="st-ctrl">
              <input
                type="text" value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="名称（可选）"
                className="st-input" aria-label="新信源 名称"
              />
            </div>
          </div>
          <div className="st-actionbar">
            {sourceMessage && (
              <span className={`st-ab-msg ${sourceMessage.type === 'ok' ? 'ok' : 'bad'}`}>{sourceMessage.text}</span>
            )}
            <button type="button" className="st-btn primary" onClick={addSource} disabled={addingSource}>
              {addingSource ? '探测中...' : '添加（自动探测+分类）'}
            </button>
          </div>

          {sources.length === 0 ? (
            <p className="st-cellnote">尚未添加</p>
          ) : (
            <div className="st-section-body">
              {sources.map(s => (
                <SourceItem key={s.id} source={s} onToggle={toggleSource} onProbe={probeSource} onDelete={deleteSource} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* 自动刷新 */}
      <section className="st-section" aria-label="自动刷新">
        <h3>自动刷新</h3>
        <p className="st-section-desc">
          设置后立即生效, 下次自动刷新按新间隔进行 (写入 localStorage `hotspot-refresh-interval`)。
        </p>
        <div className="st-section-body">
          <div className="st-cellgrid">
            {REFRESH_INTERVAL_OPTIONS.map(opt => {
              const active = currentInterval === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  className={active ? 'st-btn primary' : 'st-btn'}
                  onClick={() => {
                    setCurrentInterval(opt.value);
                    const fullOpt = { value: opt.value, label: opt.label };
                    try { localStorage.setItem('hotspot-refresh-interval', JSON.stringify(fullOpt)); } catch {}
                    onRefreshIntervalChange?.(opt.value);
                    setRefreshMessage({ type: 'ok', text: `已选择: ${opt.label}` });
                  }}
                  aria-pressed={active}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          {refreshMessage && (
            <p className={`st-cellnote`} style={{ color: refreshMessage.type === 'ok' ? 'var(--sn-mint)' : 'var(--sn-red)' }}>
              {refreshMessage.text}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

export default SourceSettings;