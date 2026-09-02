/**
 * ProxySettings — 系统代理设置 (Sentinel V2)。
 *
 * 设计原则:
 * - off 模式: 仅展示状态 + 模式切换, 无更多信息
 * - auto 模式: 检测结果 + 白名单输入 + 连通性测试 + 保存
 * - st-cellgrid 状态卡 + st-rule 编辑行 + st-actionbar footer
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useEffect, useCallback } from 'react';
import '../settings/settings-shell.css';

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
type ProxyMessage = { type: 'ok' | 'error' | 'mute'; text: string } | null;

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
        setMessage({ type: 'mute', text: '代理未启用, 无需测试' });
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

  const detectedHas = detectedProxy && (detectedProxy.http || detectedProxy.https);
  const testedCount = testResults?.length ?? 0;
  const passedCount = testResults?.filter(r => r.ok).length ?? 0;

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">系统代理</h2>
        <p className="st-sub2">
          关闭: 全部请求直连, 国内源最快, 国外源可能被墙.
          开启"系统代理": 自动读取 macOS/Windows 系统代理或 HTTP_PROXY/HTTPS_PROXY 环境变量,
          国外资讯源走代理, 国内源走白名单直连. 未检测到代理时 fallback 直连.
        </p>
      </div>

      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">MODE</span>
          <span className={`st-cellv ${mode === 'auto' ? 'mint' : ''}`}>
            {mode === 'auto' ? '系统代理' : '关闭'}
          </span>
          <span className="st-cellnote">{mode === 'auto' ? 'env / OS 接管' : '全部直连'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">DETECTED</span>
          <span className={`st-cellv ${detectedHas ? 'mint' : 'sm'}`}>
            {detectedHas ? '已识别' : '未检测到'}
          </span>
          <span className="st-cellnote">
            {detectedProxy?.http ? `HTTP ${detectedProxy.http}` : '无 HTTP 代理'}
          </span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">TEST</span>
          <span className={`st-cellv ${testResults && passedCount === testedCount && testedCount > 0 ? 'mint' : testedCount > 0 ? 'amber' : 'sm'}`}>
            {testResults ? `${passedCount}/${testedCount}` : '—'}
          </span>
          <span className="st-cellnote">{testResults ? '连通性测试结果' : '尚未测试'}</span>
        </div>
      </div>

      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">代理模式</span>
            <div className="st-ctrlrow">
              <button
                className={`st-btn ${mode === 'off' ? 'primary' : ''}`}
                onClick={() => setMode('off')}
              >
                关闭
              </button>
              <button
                className={`st-btn ${mode === 'auto' ? 'primary' : ''}`}
                onClick={() => setMode('auto')}
              >
                系统代理
              </button>
            </div>
          </div>

          {mode === 'auto' && detectedProxy && (
            <div className="st-rule">
              <span className="st-label">检测结果</span>
              <div className="st-ctrl" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {detectedProxy.http && (
                  <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                    HTTP · <span style={{ color: 'var(--sn-mint)' }}>{detectedProxy.http}</span>
                  </span>
                )}
                {detectedProxy.https && (
                  <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                    HTTPS · <span style={{ color: 'var(--sn-mint)' }}>{detectedProxy.https}</span>
                  </span>
                )}
                {!detectedProxy.http && !detectedProxy.https && (
                  <span style={{ fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-ink-3)' }}>
                    未检测到系统代理, 将走直连
                  </span>
                )}
              </div>
            </div>
          )}

          {mode === 'auto' && (
            <div className="st-rule">
              <span className="st-label">绕过代理 (白名单)</span>
              <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                <input
                  className="st-input"
                  type="text"
                  value={noProxy}
                  onChange={e => setNoProxy(e.target.value)}
                  placeholder="localhost,127.0.0.1,*.cn"
                />
                <span className="st-cellnote" style={{ marginTop: 2 }}>
                  逗号分隔, 支持通配符如 *.cn
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {mode === 'auto' && testResults && testResults.length > 0 && (
        <div className="st-section">
          <div className="st-section-body" style={{ padding: 0 }}>
            <table className="st-table">
              <thead>
                <tr>
                  <th>目标</th>
                  <th style={{ width: 80 }}>状态</th>
                  <th style={{ width: 100 }}>结果</th>
                </tr>
              </thead>
              <tbody>
                {TEST_SITES.map(site => {
                  const r = testResultMap[site.url];
                  if (!r) return null;
                  return (
                    <tr key={site.url}>
                      <td>{site.name}</td>
                      <td>
                        <span className={`st-chip ${r.ok ? 'ok' : 'bad'}`}>
                          <i /> {r.ok ? 'OK' : 'FAIL'}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'var(--sn-mono)', color: r.ok ? 'var(--sn-ink-2)' : 'var(--sn-red)' }}>
                        {r.ok ? String(r.status) : (r.error || String(r.status))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="st-actionbar">
        {message && (
          <span className={`st-ab-msg ${message.type}`}>{message.text}</span>
        )}
        <button
          className="st-btn"
          onClick={handleTest}
          disabled={testing || mode === 'off'}
        >
          {testing ? '测试中...' : '测试连通性'}
        </button>
        <button
          className="st-btn primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? '保存中...' : '保存设置'}
        </button>
      </div>
    </div>
  );
}