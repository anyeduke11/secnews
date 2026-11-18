/**
 * ProxySettings — 网络代理设置 (Sentinel V2)。
 *
 * cadence 修正批 T5: 代理成为内置可选项 (默认开启), 失效自动切回直连。
 * - 模式: 关闭 / 内置代理 (本机 127.0.0.1:7897 + 内置国内绕行清单) / 系统代理 / 手动 (配置文件)
 * - 生效代理 + 熔断器状态 (连续失败 → 熔断 N 秒全部直连 → 半开探测), 可一键闭合
 * - 连通性测试: 每站 直连 vs 经代理 并列 (与后端 /api/proxy/test 契约一致)
 * - 字段与后端契约对齐: settings.mode / settings.no_proxy / effective_proxy / health / results[]
 * - Sentinel 5 disciplines: zero-neon / semantic-3-color / mono-data / mute-text / reduced-motion
 *
 * 展示层子组件已搬运至同目录 ProxySettingsParts.tsx (拆分批次 B6-b, 单文件 ≤300 行)。
 */
import { useState, useEffect, useCallback } from 'react';
import {
  getProxySettings,
  getProxyTest,
  putProxySettings,
  resetProxyHealth,
} from '../../api/settings';
import type {
  ProxyHealth,
  ProxyTestResult as TestResult,
} from '../../api/settings';
import '../settings/settings-shell.css';
import {
  MODE_LABEL,
  ProxyProbeTable,
  ProxySettingsForm,
  ProxyStatusGrid,
} from './ProxySettingsParts';
import type { ProxyMessage, ProxyMode } from './ProxySettingsParts';

export type { TestResult };

interface ProxySettingsProps {
  open: boolean;
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
    const data = await getProxySettings();
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
      const data = await putProxySettings(mode, noProxy);
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
      const data = await getProxyTest();
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
      const data = await resetProxyHealth();
      if (data.health) setHealth(data.health);
      setMessage({ type: 'ok', text: '熔断器已闭合, 下一次请求重新尝试代理' });
    } catch {
      setMessage({ type: 'error', text: '重置失败' });
    }
  }, []);

  const proxyEnabled = savedMode !== 'off' && !!effectiveProxy;
  const circuitOpen = !!health?.circuit_open;

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

      <ProxyStatusGrid
        savedMode={savedMode}
        proxyEnabled={proxyEnabled}
        circuitOpen={circuitOpen}
        effectiveProxy={effectiveProxy}
        health={health}
        testResults={testResults}
        testStatus={testStatus}
      />

      <ProxySettingsForm
        mode={mode}
        savedMode={savedMode}
        onModeChange={setMode}
        builtinProxy={builtinProxy}
        detected={detected}
        noProxy={noProxy}
        onNoProxyChange={setNoProxy}
        health={health}
      />

      {testResults && testResults.length > 0 && <ProxyProbeTable results={testResults} />}

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