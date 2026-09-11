/**
 * ProxySettings — 网络代理设置 (Sentinel V2)。
 *
 * cadence 修正批 T5: 代理成为内置可选项 (默认开启), 失效自动切回直连。
 * - 模式: 关闭 / 内置代理 (本机 127.0.0.1:7897 + 内置国内绕行清单) / 系统代理 / 手动 (配置文件)
 * - 生效代理 + 熔断器状态 (连续失败 → 熔断 N 秒全部直连 → 半开探测), 可一键闭合
 * - 连通性测试: 每站 直连 vs 经代理 并列 (与后端 /api/proxy/test 契约一致)
 * - 字段与后端契约对齐: settings.mode / settings.no_proxy / effective_proxy / health / results[]
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 */
import { useState, useEffect, useCallback } from 'react';
import '../settings/settings-shell.css';

type ProxyMode = 'off' | 'builtin' | 'auto' | 'manual';
type ProxyMessage = { type: 'ok' | 'error' | 'mute'; text: string } | null;

interface ProbeResult {
  ok: boolean;
  status?: number;
  error?: string;
  ms?: number;
}

export interface TestResult {
  name: string;
  host: string;
  url: string;
  policy: 'proxy' | 'direct';
  direct: ProbeResult;
  proxy: ProbeResult | null;
  ok: boolean;
}

interface ProxyHealth {
  circuit_open: boolean;
  open_remaining_seconds: number;
  consecutive_failures: number;
  fail_threshold: number;
  open_seconds: number;
  opened_count: number;
  total_failures: number;
  total_successes: number;
  last_error: string;
}

interface ProxySettingsProps {
  open: boolean;
}

const MODE_LABEL: Record<ProxyMode, string> = {
  off: '关闭',
  builtin: '内置代理',
  auto: '系统代理',
  manual: '手动',
};

function probeText(p: ProbeResult | null | undefined): string {
  if (!p) return '—';
  if (p.ok) return `${p.status ?? 'OK'} · ${p.ms ?? 0}ms`;
  return p.error || String(p.status ?? 'FAIL');
}

export function ProxySettings({ open }: ProxySettingsProps) {
  const [mode, setMode] = useState<ProxyMode>('builtin');
  const [savedMode, setSavedMode] = useState<ProxyMode>('builtin');
  const [noProxy, setNoProxy] = useState('');
  const [effectiveProxy, setEffectiveProxy] = useState('');
  const [builtinProxy, setBuiltinProxy] = useState('');
  const [health, setHealth] = useState<ProxyHealth | null>(null);
  const [detected, setDetected] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<TestResult[] | null>(null);
  const [testStatus, setTestStatus] = useState<string | null>(null);
  const [message, setMessage] = useState<ProxyMessage>(null);

  const applySettings = useCallback((data: any) => {
    const s = data?.settings || {};
    const m: ProxyMode = (['off', 'builtin', 'auto', 'manual'] as ProxyMode[]).includes(s.mode) ? s.mode : 'builtin';
    setMode(m);
    setSavedMode(m);
    setNoProxy(s.no_proxy || '');
    setEffectiveProxy(data?.effective_proxy || '');
    setBuiltinProxy(data?.builtin?.proxy_url || '');
    setHealth(data?.health || null);
    setDetected(data?.detected_system_proxy || null);
  }, []);

  const load = useCallback(async () => {
    const r = await fetch('/api/proxy/settings');
    const data = await r.json();
    applySettings(data);
  }, [applySettings]);

  // 打开面板时拉取代理配置
  useEffect(() => {
    if (!open) return;
    setTestResults(null);
    setTestStatus(null);
    setMessage(null);
    load().catch(() => setMessage({ type: 'error', text: '加载代理配置失败' }));
  }, [open, load]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setMessage(null);
    try {
      const resp = await fetch('/api/proxy/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, no_proxy: noProxy }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        applySettings(data);
        setMessage({ type: 'ok', text: `代理配置已保存 (${MODE_LABEL[mode]})` });
      } else {
        setMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSaving(false);
    }
  }, [mode, noProxy, applySettings]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setTestResults(null);
    setTestStatus(null);
    setMessage(null);
    try {
      const resp = await fetch('/api/proxy/test');
      const data = await resp.json();
      setTestResults(data.results || []);
      setTestStatus(data.status || null);
      if (data.health) setHealth(data.health);
      if (data.status === 'skipped') {
        setMessage({ type: 'mute', text: data.summary || '代理未启用, 仅直连探测' });
      } else {
        setMessage({ type: data.status === 'ok' ? 'ok' : 'error', text: data.summary || `测试完成: ${data.status}` });
      }
    } catch {
      setMessage({ type: 'error', text: '测试请求失败' });
    } finally {
      setTesting(false);
    }
  }, []);

  const handleResetHealth = useCallback(async () => {
    try {
      const resp = await fetch('/api/proxy/health/reset', { method: 'POST' });
      const data = await resp.json();
      if (data.health) setHealth(data.health);
      setMessage({ type: 'ok', text: '熔断器已闭合, 下一次请求重新尝试代理' });
    } catch {
      setMessage({ type: 'error', text: '重置失败' });
    }
  }, []);

  const proxyEnabled = savedMode !== 'off' && !!effectiveProxy;
  const circuitOpen = !!health?.circuit_open;
  const testedCount = testResults?.length ?? 0;
  const passedCount = testResults?.filter(r => r.ok).length ?? 0;

  return (
    <div className="settings-shell" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sn-row)' }}>
      <div className="st-head">
        <h2 className="st-title">网络代理</h2>
        <p className="st-sub2">
          代理是兜底: 所有源先直连, 直连失败且不在绕行清单的国外源才走代理.
          内置代理指向本机 Clash 类混合端口 (默认开启); 代理连续失败会自动熔断切回直连, 窗口过后自动再试.
          国内站命中绕行清单永远直连, 不会被送到海外出口.
        </p>
      </div>

      <div className="st-cellgrid">
        <div className="st-cell">
          <span className="st-cellk">MODE</span>
          <span className={`st-cellv ${proxyEnabled ? 'mint' : ''}`}>{MODE_LABEL[savedMode]}</span>
          <span className="st-cellnote">{proxyEnabled ? '直连优先 · 代理兜底' : '全部直连'}</span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">EFFECTIVE</span>
          <span className={`st-cellv ${circuitOpen ? 'amber' : proxyEnabled ? 'mint' : 'sm'}`}>
            {circuitOpen ? '熔断 → 直连' : proxyEnabled ? '代理就位' : '—'}
          </span>
          <span className="st-cellnote" style={{ fontFamily: 'var(--sn-mono)' }}>
            {circuitOpen
              ? `剩余 ${Math.ceil(health?.open_remaining_seconds ?? 0)}s · 连续失败 ${health?.consecutive_failures ?? 0}`
              : effectiveProxy || '未配置代理'}
          </span>
        </div>
        <div className="st-cell">
          <span className="st-cellk">TEST</span>
          <span className={`st-cellv ${testResults && passedCount === testedCount && testedCount > 0 ? 'mint' : testedCount > 0 ? 'amber' : 'sm'}`}>
            {testResults ? `${passedCount}/${testedCount}` : '—'}
          </span>
          <span className="st-cellnote">{testStatus ? `连通性: ${testStatus}` : '尚未测试'}</span>
        </div>
      </div>

      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">代理模式</span>
            <div className="st-ctrlrow">
              {(['off', 'builtin', 'auto'] as ProxyMode[]).map(m => (
                <button
                  key={m}
                  className={`st-btn ${mode === m ? 'primary' : ''}`}
                  onClick={() => setMode(m)}
                >
                  {MODE_LABEL[m]}
                </button>
              ))}
              {(mode === 'manual' || savedMode === 'manual') && (
                <button
                  className={`st-btn ${mode === 'manual' ? 'primary' : ''}`}
                  onClick={() => setMode('manual')}
                  title="手动代理地址在 backend/proxy_config.json 中配置"
                >
                  手动 (配置文件)
                </button>
              )}
            </div>
          </div>

          {mode === 'builtin' && (
            <div className="st-rule">
              <span className="st-label">内置代理</span>
              <div className="st-ctrl" style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                {builtinProxy || 'http://127.0.0.1:7897'}
                <span className="st-cellnote" style={{ marginLeft: 8 }}>
                  可用环境变量 HOTSPOT_BUILTIN_PROXY_URL 换端口
                </span>
              </div>
            </div>
          )}

          {mode === 'auto' && (
            <div className="st-rule">
              <span className="st-label">系统代理检测</span>
              <div className="st-ctrl" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {detected?.http && (
                  <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                    HTTP · <span style={{ color: 'var(--sn-mint)' }}>{detected.http}</span>
                  </span>
                )}
                {detected?.https && (
                  <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                    HTTPS · <span style={{ color: 'var(--sn-mint)' }}>{detected.https}</span>
                  </span>
                )}
                {!detected?.http && !detected?.https && (
                  <span style={{ fontSize: 'var(--sn-fs-mute)', color: 'var(--sn-ink-3)' }}>
                    未检测到系统代理 (仅识别 HTTP_PROXY/HTTPS_PROXY 环境变量), 将走直连; 保存后重新检测
                  </span>
                )}
              </div>
            </div>
          )}

          {mode !== 'off' && (
            <div className="st-rule">
              <span className="st-label">绕过代理 (直连清单)</span>
              <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                <input
                  className="st-input"
                  type="text"
                  value={noProxy}
                  onChange={e => setNoProxy(e.target.value)}
                  placeholder="localhost,127.0.0.1,*.cn,36kr.com"
                />
                <span className="st-cellnote" style={{ marginTop: 2 }}>
                  逗号分隔; 支持 *.cn 通配、.local 后缀、域名子串. 留空恢复内置清单
                </span>
              </div>
            </div>
          )}

          {health && (health.total_failures > 0 || health.total_successes > 0) && (
            <div className="st-rule">
              <span className="st-label">熔断器</span>
              <div className="st-ctrl" style={{ fontFamily: 'var(--sn-mono)', fontSize: 12, color: 'var(--sn-ink-2)' }}>
                成功 {health.total_successes} · 失败 {health.total_failures} · 熔断 {health.opened_count} 次
                {' '}(阈值 {health.fail_threshold} 连败 / 窗口 {Math.round(health.open_seconds)}s)
                {health.last_error && (
                  <span className="st-cellnote" style={{ display: 'block', marginTop: 2, color: 'var(--sn-ink-3)' }}>
                    最近错误: {health.last_error}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {testResults && testResults.length > 0 && (
        <div className="st-section">
          <div className="st-section-body" style={{ padding: 0 }}>
            <table className="st-table">
              <thead>
                <tr>
                  <th>目标</th>
                  <th style={{ width: 64 }}>策略</th>
                  <th>直连</th>
                  <th>经代理</th>
                  <th style={{ width: 80 }}>结果</th>
                </tr>
              </thead>
              <tbody>
                {testResults.map(r => (
                  <tr key={r.url}>
                    <td title={r.url}>{r.name}</td>
                    <td style={{ fontFamily: 'var(--sn-mono)' }}>{r.policy === 'proxy' ? '代理' : '直连'}</td>
                    <td style={{ fontFamily: 'var(--sn-mono)', color: r.direct?.ok ? 'var(--sn-ink-2)' : 'var(--sn-red)' }}>
                      {probeText(r.direct)}
                    </td>
                    <td style={{ fontFamily: 'var(--sn-mono)', color: r.proxy?.ok ? 'var(--sn-ink-2)' : r.proxy ? 'var(--sn-red)' : 'var(--sn-ink-3)' }}>
                      {probeText(r.proxy)}
                    </td>
                    <td>
                      <span className={`st-chip ${r.ok ? 'ok' : 'bad'}`}>
                        <i /> {r.ok ? 'OK' : 'FAIL'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="st-actionbar">
        {message && <span className={`st-ab-msg ${message.type}`}>{message.text}</span>}
        {circuitOpen && (
          <button className="st-btn" onClick={handleResetHealth} title="代理已修好时手动闭合熔断器">
            闭合熔断
          </button>
        )}
        <button className="st-btn" onClick={handleTest} disabled={testing}>
          {testing ? '测试中...' : '测试连通性'}
        </button>
        <button className="st-btn primary" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存设置'}
        </button>
      </div>
    </div>
  );
}
