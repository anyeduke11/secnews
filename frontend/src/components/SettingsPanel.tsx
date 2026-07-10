import React, { useState, useEffect, useCallback } from 'react';
import { REFRESH_INTERVAL_OPTIONS } from '../hooks/useRefreshInterval';

interface ProxySettings {
  mode: 'off' | 'auto';
  noProxy: string;
}

interface TestResult {
  url: string;
  status: number | string;
  ok: boolean;
  error?: string;
}

interface QualityRule {
  key: string;
  value: string | number | boolean;
  default: string | number | boolean;
}

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  onRefreshIntervalChange?: (minutes: number) => void;
}

const TEST_SITES = [
  { url: 'https://www.google.com', name: 'Google' },
  { url: 'https://news.ycombinator.com', name: 'Hacker News' },
  { url: 'https://api.github.com', name: 'GitHub API' },
  { url: 'https://thehackernews.com', name: 'The Hacker News' },
  { url: 'https://techcrunch.com', name: 'TechCrunch' },
];

export function SettingsPanel({ open, onClose, onRefreshIntervalChange }: SettingsPanelProps) {
  const [mode, setMode] = useState<'off' | 'auto'>('off');
  const [noProxy, setNoProxy] = useState('localhost,127.0.0.1,::1');
  const [detectedProxy, setDetectedProxy] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<TestResult[] | null>(null);
  const [message, setMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  // Phase 5: 质量设置状态
  const [qualityOpen, setQualityOpen] = useState(false);
  const [qualityRules, setQualityRules] = useState<QualityRule[]>([]);
  const [qualityEditing, setQualityEditing] = useState<Record<string, any>>({});
  const [savingQuality, setSavingQuality] = useState(false);
  const [qualityMessage, setQualityMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  // Phase 6: 自动刷新设置状态
  const [refreshOpen, setRefreshOpen] = useState(false);
  const [currentInterval, setCurrentInterval] = useState<number>(30);
  const [refreshMessage, setRefreshMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  // Phase 8 Addendum 8.4: 信源管理状态
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sources, setSources] = useState<any[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [sourceMessage, setSourceMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);
  const [addingSource, setAddingSource] = useState(false);

  // Phase 5: 打开面板时拉质量规则
  useEffect(() => {
    if (!open) return;
    fetch('/api/quality/rules')
      .then(r => r.json())
      .then(data => {
        const rules = (data.rules || []) as QualityRule[];
        setQualityRules(rules);
        const init: Record<string, any> = {};
        for (const r of rules) init[r.key] = r.value;
        setQualityEditing(init);
      })
      .catch(() => setQualityMessage({ type: 'error', text: '加载质量配置失败' }));

    // Phase 6: 读取已保存的自动刷新间隔
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
  }, [open]);

  const saveQuality = useCallback(async () => {
    setSavingQuality(true);
    setQualityMessage(null);
    try {
      const rules: Record<string, any> = {};
      for (const r of qualityRules) {
        if (qualityEditing[r.key] !== r.value) {
          rules[r.key] = qualityEditing[r.key];
        }
      }
      if (Object.keys(rules).length === 0) {
        setQualityMessage({ type: 'ok', text: '无变更' });
        setSavingQuality(false);
        return;
      }
      const resp = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setQualityMessage({ type: 'ok', text: `已更新: ${data.updated?.join(', ') || 'OK'}` });
        // 重新拉取
        const r2 = await fetch('/api/quality/rules');
        const d2 = await r2.json();
        const refreshed = (d2.rules || []) as QualityRule[];
        setQualityRules(refreshed);
        const init: Record<string, any> = {};
        for (const r of refreshed) init[r.key] = r.value;
        setQualityEditing(init);
      } else {
        setQualityMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setQualityMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSavingQuality(false);
    }
  }, [qualityRules, qualityEditing]);

  function renderQualityInput(rule: QualityRule) {
    const v = qualityEditing[rule.key];
    const setV = (val: any) => setQualityEditing(prev => ({ ...prev, [rule.key]: val }));
    if (typeof v === 'boolean') {
      return (
        <button
          onClick={() => setV(!v)}
          className="px-2 py-0.5 text-xs rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: v ? 'var(--color-ai)' : 'var(--bg-hover)',
            color: v ? '#fff' : 'var(--text-secondary)',
            border: `1px solid ${v ? 'var(--color-ai)' : 'var(--border-color)'}`,
            minWidth: 44,
          }}
        >
          {v ? '已开启' : '已关闭'}
        </button>
      );
    }
    if (typeof v === 'number') {
      if (rule.key.includes('sample_rate')) {
        return (
          <input
            type="range" min={0} max={1} step={0.05}
            value={v}
            onChange={e => setV(parseFloat(e.target.value))}
            className="flex-1"
          />
        );
      }
      return (
        <input
          type="number" value={v}
          onChange={e => setV(parseFloat(e.target.value) || 0)}
          className="w-20 px-2 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
      );
    }
    return (
      <input
        type="text" value={String(v)}
        onChange={e => setV(e.target.value)}
        className="flex-1 px-2 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
      />
    );
  }

  useEffect(() => {
    if (open) {
      fetch('/api/proxy/settings')
        .then(r => r.json())
        .then(data => {
          setMode(data.mode === 'auto' ? 'auto' : 'off');
          setNoProxy(data.noProxy || 'localhost,127.0.0.1,::1');
          if (data.detectedProxy) setDetectedProxy(data.detectedProxy);
          setTestResults(null);
          setMessage(null);
        })
        .catch(() => setMessage({ type: 'error', text: '加载代理配置失败' }));
    }
  }, [open]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setMessage(null);
    try {
      const resp = await fetch('/api/proxy/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, noProxy }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        setMessage({ type: 'ok', text: '代理配置已保存' });
        if (mode === 'auto') {
          const r = await fetch('/api/proxy/settings');
          const d = await r.json();
          if (d.detectedProxy) setDetectedProxy(d.detectedProxy);
        }
      } else {
        setMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSaving(false);
    }
  }, [mode, noProxy]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setTestResults(null);
    setMessage(null);
    try {
      const resp = await fetch('/api/proxy/test');
      const data = await resp.json();
      setTestResults(data.results || []);
      if (data.status === 'skipped') {
        setMessage({ type: 'ok', text: '代理未启用，无需测试' });
      } else {
        setMessage({ type: data.status === 'ok' ? 'ok' : 'error', text: `测试完成: ${data.summary}` });
      }
    } catch {
      setMessage({ type: 'error', text: '测试请求失败' });
    } finally {
      setTesting(false);
    }
  }, []);

  // ----------------------------------------------------------------
  // Phase 8 Addendum 8.4: 信源管理 handlers
  // ----------------------------------------------------------------
  const refreshSources = useCallback(async () => {
    try {
      const r = await fetch('/api/sources/custom');
      const d = await r.json();
      setSources(d.sources || []);
    } catch {
      // 静默失败 — 不打断面板其他操作
    }
  }, []);

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

  // 打开面板时拉取自定义信源列表
  useEffect(() => {
    if (open) refreshSources();
  }, [open, refreshSources]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const testResultMap: Record<string, TestResult> = {};
  if (testResults) {
    for (const r of testResults) testResultMap[r.url] = r;
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }} onClick={onClose} />
      <div
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-sm overflow-y-auto"
        style={{
          backgroundColor: 'var(--bg-primary)',
          borderLeft: '1px solid var(--border-color)',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.3)',
          animation: 'slide-in-right 0.25s ease',
        }}
      >
        <style>{`@keyframes slide-in-right{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>

        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <h2 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>代理设置</h2>
          <button onClick={onClose} className="btn-ghost px-2 py-1">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <div className="px-4 py-3 space-y-4">
          {/* Phase 5: 质量设置折叠区 */}
          <div className="rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
            <button
              onClick={() => setQualityOpen(o => !o)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs"
              style={{ color: 'var(--text-primary)' }}
            >
              <span className="font-medium">质量设置 ({qualityRules.length})</span>
              <span style={{ color: 'var(--text-muted)' }}>{qualityOpen ? '−' : '+'}</span>
            </button>
            {qualityOpen && (
              <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
                {qualityRules.length === 0 ? (
                  <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
                ) : qualityRules.map(rule => (
                  <div key={rule.key} className="flex items-center gap-2">
                    <span className="text-[11px] font-mono flex-1 truncate" style={{ color: 'var(--text-secondary)' }} title={rule.key}>
                      {rule.key.replace(/^quality\./, '')}
                    </span>
                    {renderQualityInput(rule)}
                  </div>
                ))}
                {qualityMessage && (
                  <p className="text-[10px]" style={{ color: qualityMessage.type === 'ok' ? 'var(--color-general)' : '#e85d5d' }}>
                    {qualityMessage.text}
                  </p>
                )}
                <button
                  onClick={saveQuality}
                  disabled={savingQuality}
                  className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
                  style={{
                    backgroundColor: 'var(--color-ai)', color: '#fff', border: 'none',
                    opacity: savingQuality ? 0.6 : 1, marginTop: 4,
                  }}
                >
                  {savingQuality ? '保存中...' : '应用质量配置'}
                </button>
              </div>
            )}
          </div>

          {/* Phase 8 Addendum 8.4: 信源管理折叠区（位于质量设置与自动刷新之间） */}
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
                  <input
                    type="text"
                    value={newUrl}
                    onChange={e => setNewUrl(e.target.value)}
                    placeholder="https://example.com/news"
                    className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)] focus-ring"
                    style={{
                      backgroundColor: 'var(--bg-hover)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                    }}
                  />
                  <input
                    type="text"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="名称（可选）"
                    className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)] focus-ring"
                    style={{
                      backgroundColor: 'var(--bg-hover)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                    }}
                  />
                  <button
                    onClick={addSource}
                    disabled={addingSource}
                    className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
                    style={{
                      backgroundColor: 'var(--color-ai)', color: '#fff', border: 'none',
                      opacity: addingSource ? 0.6 : 1,
                    }}
                  >
                    {addingSource ? '探测中...' : '添加（自动探测+分类）'}
                  </button>
                </div>
                {sourceMessage && (
                  <p className="text-[10px]" style={{ color: sourceMessage.type === 'ok' ? 'var(--color-general)' : '#e85d5d' }}>
                    {sourceMessage.text}
                  </p>
                )}
                <div className="space-y-1 max-h-60 overflow-y-auto">
                  {sources.length === 0 ? (
                    <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>尚未添加</p>
                  ) : sources.map(s => (
                    <div
                      key={s.id}
                      className="p-1.5 rounded-[var(--radius-sm)] text-[10px]"
                      style={{
                        backgroundColor: 'var(--bg-hover)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div className="flex items-center gap-1.5">
                        <span
                          className="font-mono truncate flex-1"
                          style={{ color: 'var(--text-primary)' }}
                          title={s.url}
                        >
                          {s.name || s.url}
                        </span>
                        <span
                          className="px-1 py-0.5 rounded text-[9px]"
                          style={{ backgroundColor: 'var(--color-ai)', color: '#fff' }}
                        >
                          {s.category}
                        </span>
                      </div>
                      <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {s.last_check_status || '未探测'} · {Math.round(s.last_check_latency_ms || 0)}ms
                      </div>
                      <div className="flex gap-1 mt-1">
                        <button
                          onClick={() => toggleSource(s.id, !s.enabled)}
                          className="px-1.5 py-0.5 text-[9px] rounded"
                          style={{
                            backgroundColor: s.enabled ? 'var(--color-ai)' : 'var(--bg-primary)',
                            color: s.enabled ? '#fff' : 'var(--text-muted)',
                          }}
                        >
                          {s.enabled ? '启用' : '禁用'}
                        </button>
                        <button
                          onClick={() => probeSource(s.id)}
                          className="px-1.5 py-0.5 text-[9px] rounded"
                          style={{
                            backgroundColor: 'var(--bg-primary)',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          探测
                        </button>
                        <button
                          onClick={() => deleteSource(s.id)}
                          className="px-1.5 py-0.5 text-[9px] rounded"
                          style={{ backgroundColor: 'var(--bg-primary)', color: '#e85d5d' }}
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Phase 6: 自动刷新折叠区（位于质量设置与代理设置之间） */}
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
                          color: active ? '#fff' : 'var(--text-secondary)',
                          border: `1px solid ${active ? 'var(--color-ai)' : 'var(--border-color)'}`,
                        }}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                {refreshMessage && (
                  <p className="text-[10px]" style={{ color: refreshMessage.type === 'ok' ? 'var(--color-general)' : '#e85d5d' }}>
                    {refreshMessage.text}
                  </p>
                )}
                <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  设置后立即生效，下次自动刷新按新间隔进行
                </p>
              </div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
          <p className="text-xs font-bold mb-3" style={{ color: 'var(--text-primary)' }}>代理设置</p>
          </div>
          <div>
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>代理模式</p>
            <div className="flex gap-2">
              {[
                { value: 'off', label: '关闭' },
                { value: 'auto', label: '系统代理' },
              ].map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setMode(opt.value as 'off' | 'auto')}
                  className="flex-1 px-3 py-2 text-xs font-medium rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: mode === opt.value ? 'var(--color-ai)' : 'var(--bg-hover)',
                    color: mode === opt.value ? '#fff' : 'var(--text-secondary)',
                    border: `1px solid ${mode === opt.value ? 'var(--color-ai)' : 'var(--border-color)'}`,
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Auto mode: detected proxy info */}
          {mode === 'auto' && detectedProxy && (
            <div className="p-2.5 rounded-[var(--radius-sm)] text-xs space-y-1" style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
              <p style={{ color: 'var(--text-secondary)' }}>检测到系统代理：</p>
              {detectedProxy.http && <p style={{ color: 'var(--text-muted)' }}>HTTP: <span style={{ color: 'var(--color-general)' }}>{detectedProxy.http}</span></p>}
              {detectedProxy.https && <p style={{ color: 'var(--text-muted)' }}>HTTPS: <span style={{ color: 'var(--color-general)' }}>{detectedProxy.https}</span></p>}
              {!detectedProxy.http && !detectedProxy.https && (
                <p style={{ color: 'var(--text-muted)' }}>未检测到系统代理，直连访问</p>
              )}
            </div>
          )}

          {/* Whitelist */}
          {mode === 'auto' && (
            <div>
              <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>绕过代理（白名单域名）</p>
              <input
                type="text"
                value={noProxy}
                onChange={e => setNoProxy(e.target.value)}
                placeholder="localhost,127.0.0.1,*.cn"
                className="w-full px-2.5 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                }}
              />
              <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                逗号分隔，支持通配符如 *.cn
              </p>
            </div>
          )}

          {/* Test results */}
          {mode === 'auto' && testResults && testResults.length > 0 && (
            <div className="p-2.5 rounded-[var(--radius-sm)] space-y-1" style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>连通性测试</p>
              {TEST_SITES.map(site => {
                const r = testResultMap[site.url];
                if (!r) return null;
                return (
                  <div key={site.url} className="flex items-center justify-between text-xs">
                    <span style={{ color: 'var(--text-primary)' }}>{site.name}</span>
                    <span style={{ color: r.ok ? 'var(--color-general)' : '#e85d5d', fontSize: 10 }}>
                      {r.ok ? `\u2713 ${r.status}` : `\u2717 ${r.error || r.status}`}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Message */}
          {message && (
            <div className="p-2.5 rounded-[var(--radius-sm)] text-xs" style={{
              backgroundColor: message.type === 'ok' ? 'rgba(0,201,106,0.08)' : 'rgba(232,93,93,0.08)',
              border: `1px solid ${message.type === 'ok' ? 'rgba(0,201,106,0.2)' : 'rgba(232,93,93,0.2)'}`,
              color: message.type === 'ok' ? 'var(--color-general)' : '#e85d5d',
            }}>
              {message.text}
            </div>
          )}

          <div className="p-2.5 rounded-[var(--radius-sm)] text-xs leading-relaxed" style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
            <p>开启"系统代理"后，采集器自动读取 Windows 系统代理设置或环境变量 HTTP_PROXY/HTTPS_PROXY，国外资讯源通过代理获取。</p>
            <p className="mt-1">未检测到代理时自动直连，不影响国内数据源采集。</p>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 px-4 py-3 flex items-center gap-2" style={{ backgroundColor: 'var(--bg-primary)', borderTop: '1px solid var(--border-color)' }}>
          <button
            onClick={handleTest}
            disabled={testing || mode === 'off'}
            className="btn-ghost px-3 py-1.5 text-xs flex-1"
            style={{ opacity: mode === 'off' ? 0.5 : 1 }}
          >
            {testing ? '测试中...' : '测试连通性'}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'var(--color-ai)',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              opacity: saving ? 0.6 : 1,
              flex: 1,
            }}
          >
            {saving ? '保存中...' : '保存设置'}
          </button>
        </div>
      </div>
    </>
  );
}
