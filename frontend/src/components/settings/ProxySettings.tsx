/**
 * ProxySettings — 代理设置区（核心功能 + footer 测试/保存按钮）。
 *
 * Phase 1B: 拆自原 SettingsPanel.tsx 代理设置段（最重的一段）。
 * 包含：代理模式切换、白名单输入、检测到的代理展示、连通性测试、保存按钮。
 * 自包含状态 + handlers + footer；通过 props.open 触发数据加载。
 */
import React, { useState, useEffect, useCallback } from 'react';

export interface TestResult {
  url: string;
  status: number | string;
  ok: boolean;
  error?: string;
}

interface ProxySettingsProps {
  open: boolean;
}

type ProxyMode = 'off' | 'auto';
type ProxyMessage = { type: 'ok' | 'error'; text: string } | null;

const TEST_SITES = [
  { url: 'https://www.google.com', name: 'Google' },
  { url: 'https://news.ycombinator.com', name: 'Hacker News' },
  { url: 'https://api.github.com', name: 'GitHub API' },
  { url: 'https://thehackernews.com', name: 'The Hacker News' },
  { url: 'https://techcrunch.com', name: 'TechCrunch' },
];

export function ProxySettings({ open }: ProxySettingsProps) {
  const [mode, setMode] = useState<ProxyMode>('off');
  const [noProxy, setNoProxy] = useState('localhost,127.0.0.1,::1');
  const [detectedProxy, setDetectedProxy] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<TestResult[] | null>(null);
  const [message, setMessage] = useState<ProxyMessage>(null);

  // 打开面板时拉取代理配置
  useEffect(() => {
    if (!open) return;
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

  const testResultMap: Record<string, TestResult> = {};
  if (testResults) {
    for (const r of testResults) testResultMap[r.url] = r;
  }

  return (
    <>
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
              onClick={() => setMode(opt.value as ProxyMode)}
              className="flex-1 px-3 py-2 text-xs font-medium rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: mode === opt.value ? 'var(--color-ai)' : 'var(--bg-hover)',
                color: mode === opt.value ? 'var(--text-on-color)' : 'var(--text-secondary)',
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
                <span style={{ color: r.ok ? 'var(--color-general)' : 'var(--color-error)', fontSize: 10 }}>
                  {r.ok ? `✓ ${r.status}` : `✗ ${r.error || r.status}`}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Message */}
      {message && (
        <div className="p-2.5 rounded-[var(--radius-sm)] text-xs" style={{
          backgroundColor: message.type === 'ok' ? 'color-mix(in srgb, var(--color-success) 8%, transparent)' : 'color-mix(in srgb, var(--color-error) 8%, transparent)',
          border: `1px solid ${message.type === 'ok' ? 'color-mix(in srgb, var(--color-success) 20%, transparent)' : 'color-mix(in srgb, var(--color-error) 20%, transparent)'}`,
          color: message.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)',
        }}>
          {message.text}
        </div>
      )}

      <div className="p-2.5 rounded-[var(--radius-sm)] text-xs leading-relaxed" style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
        <p>开启"系统代理"后，采集器自动读取 Windows 系统代理设置或环境变量 HTTP_PROXY/HTTPS_PROXY，国外资讯源通过代理获取。</p>
        <p className="mt-1">未检测到代理时自动直连，不影响国内数据源采集。</p>
      </div>

      {/* Footer - 测试连通性 + 保存设置 */}
      <div className="sticky bottom-0 px-4 py-3 flex items-center gap-2 -mx-4 mt-4" style={{ backgroundColor: 'var(--bg-primary)', borderTop: '1px solid var(--border-color)' }}>
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
            color: 'var(--text-on-color)',
            border: 'none',
            cursor: 'pointer',
            opacity: saving ? 0.6 : 1,
            flex: 1,
          }}
        >
          {saving ? '保存中...' : '保存设置'}
        </button>
      </div>
    </>
  );
}
