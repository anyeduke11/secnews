/**
 * SourceSettings — 自定义信源管理（Phase 8 8.4）+ 自动刷新间隔（Phase 6）。
 *
 * Phase 1B: 拆自原 SettingsPanel.tsx 信源管理 + 自动刷新折叠区。
 * 信源管理：增删改查 + 探测 + 启用/禁用（单条渲染在 SourceItem.tsx）。
 * 自动刷新：选择 localStorage 缓存的刷新间隔。
 * 两个折叠区组合在一起 — 都是"配置列表"语义。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { REFRESH_INTERVAL_OPTIONS } from '../../hooks/useRefreshInterval';
import { SourceItem, SourceItemData } from './SourceItem';

interface SourceSettingsProps {
  open: boolean;
  onRefreshIntervalChange?: (minutes: number) => void;
}

type SourceMessage = { type: 'ok' | 'error'; text: string } | null;
type RefreshMessage = { type: 'ok' | 'error'; text: string } | null;

// 共享样式常量
const inputStyle = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
} as const;
const btnStyle = {
  backgroundColor: 'var(--color-ai)',
  color: 'var(--text-on-color)',
  border: 'none',
} as const;

export function SourceSettings({ open, onRefreshIntervalChange }: SourceSettingsProps) {
  // 信源管理
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sources, setSources] = useState<SourceItemData[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [sourceMessage, setSourceMessage] = useState<SourceMessage>(null);
  const [addingSource, setAddingSource] = useState(false);

  // 自动刷新
  const [refreshOpen, setRefreshOpen] = useState(false);
  const [currentInterval, setCurrentInterval] = useState<number>(30);
  const [refreshMessage, setRefreshMessage] = useState<RefreshMessage>(null);

  // 打开面板时拉取自定义信源列表
  const refreshSources = useCallback(async () => {
    try {
      const r = await fetch('/api/sources/custom');
      const d = await r.json();
      setSources(d.sources || []);
    } catch {
      // 静默失败 — 不打断面板其他操作
    }
  }, []);

  // 打开面板时读取已保存的自动刷新间隔
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
    } catch {
      // ignore
    }
    refreshSources();
  }, [refreshSources]);

  const toggleSource = useCallback(async (id: number, enabled: boolean) => {
    try {
      await fetch(`/api/sources/custom/${id}/toggle?enabled=${enabled}`, {
        method: 'POST',
      });
    } catch {
      // ignore
    }
    refreshSources();
  }, [refreshSources]);

  const probeSource = useCallback(async (id: number) => {
    try {
      const r = await fetch(`/api/sources/custom/${id}/probe`, {
        method: 'POST',
      });
      const d = await r.json();
      if (d.status === 'ok') {
        setSourceMessage({
          type: 'ok',
          text: `探测成功: ${d.probe.latency_ms}ms`,
        });
      } else {
        setSourceMessage({
          type: 'error',
          text: `探测失败: ${d.probe?.error || 'unknown'}`,
        });
      }
    } catch {
      setSourceMessage({ type: 'error', text: '探测请求失败' });
    }
    refreshSources();
  }, [refreshSources]);

  return (
    <>
      {/* 信源管理折叠区 */}
      <div className="rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <button
          onClick={() => setSourceOpen(o => !o)}
          className="w-full flex items-center justify-between px-3 py-2 text-xs"
          style={{ color: 'var(--text-primary)' }}
        >
          <span className="font-medium">信源管理 ({sources.length})</span>
          <span style={{ color: 'var(--text-muted)' }}>{sourceOpen ? '−' : '+'}</span>
        </button>
        {sourceOpen && (
          <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
            <div className="space-y-1.5">
              <input type="text" value={newUrl} onChange={e => setNewUrl(e.target.value)}
                placeholder="https://example.com/news"
                className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)] focus-ring"
                style={inputStyle} />
              <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="名称（可选）"
                className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)] focus-ring"
                style={inputStyle} />
              <button onClick={addSource} disabled={addingSource}
                className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
                style={btnStyle}>
                {addingSource ? '探测中...' : '添加（自动探测+分类）'}
              </button>
            </div>
            {sourceMessage && (
              <p className="text-[10px]" style={{ color: sourceMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
                {sourceMessage.text}
              </p>
            )}
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {sources.length === 0 ? (
                <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>尚未添加</p>
              ) : sources.map(s => (
                <SourceItem
                  key={s.id}
                  source={s}
                  onToggle={toggleSource}
                  onProbe={probeSource}
                  onDelete={deleteSource}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 自动刷新折叠区 */}
      <div className="rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
        <button
          onClick={() => setRefreshOpen(o => !o)}
          className="w-full flex items-center justify-between px-3 py-2 text-xs"
          style={{ color: 'var(--text-primary)' }}
        >
          <span className="font-medium">自动刷新</span>
          <span style={{ color: 'var(--text-muted)' }}>{refreshOpen ? '−' : '+'}</span>
        </button>
        {refreshOpen && (
          <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
            <div className="grid grid-cols-3 gap-1.5">
              {REFRESH_INTERVAL_OPTIONS.map(opt => {
                const active = currentInterval === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setCurrentInterval(opt.value);
                      const fullOpt = { value: opt.value, label: opt.label };
                      try { localStorage.setItem('hotspot-refresh-interval', JSON.stringify(fullOpt)); } catch {}
                      onRefreshIntervalChange?.(opt.value);
                      setRefreshMessage({ type: 'ok', text: `已选择: ${opt.label}` });
                    }}
                    className="px-2 py-1.5 text-[11px] font-medium rounded-[var(--radius-sm)] transition-colors"
                    style={{
                      backgroundColor: active ? 'var(--color-ai)' : 'var(--bg-hover)',
                      color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                      border: `1px solid ${active ? 'var(--color-ai)' : 'var(--border-color)'}`,
                    }}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            {refreshMessage && (
              <p className="text-[10px]" style={{ color: refreshMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
                {refreshMessage.text}
              </p>
            )}
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              设置后立即生效，下次自动刷新按新间隔进行
            </p>
          </div>
        )}
      </div>
    </>
  );
}
