/**
 * settings/ProxySettingsParts — ProxySettings 的私有子组件与常量。
 *
 * 从 ProxySettings.tsx 纯搬运 (拆分批次 B6-b, 单文件 ≤300 行):
 * 模式类型 / 状态网格 ProxyStatusGrid / 设置表单 ProxySettingsForm / 探测表 ProxyProbeTable。
 * 语义与 DOM 与拆分前一致。
 */
import type {
  ProxyHealth,
  ProxyProbeResult as ProbeResult,
  ProxyTestResult as TestResult,
} from '../../api/settings';

export type ProxyMode = 'off' | 'builtin' | 'auto' | 'manual';
export type ProxyMessage = { type: 'ok' | 'error' | 'mute'; text: string } | null;

export const MODE_LABEL: Record<ProxyMode, string> = {
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

/** 三格状态网格: MODE / EFFECTIVE / TEST。 */
export function ProxyStatusGrid({
  savedMode, proxyEnabled, circuitOpen, effectiveProxy, health, testResults, testStatus,
}: {
  savedMode: ProxyMode;
  proxyEnabled: boolean;
  circuitOpen: boolean;
  effectiveProxy: string;
  health: ProxyHealth | null;
  testResults: TestResult[] | null;
  testStatus: string | null;
}) {
  const testedCount = testResults?.length ?? 0;
  const passedCount = testResults?.filter(r => r.ok).length ?? 0;
  return (
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
  );
}

/** 模式选择 + 内置代理地址 + 系统代理检测 + 绕行清单 + 熔断器。 */
export function ProxySettingsForm({
  mode, savedMode, onModeChange, builtinProxy, detected, noProxy, onNoProxyChange, health,
}: {
  mode: ProxyMode;
  savedMode: ProxyMode;
  onModeChange: (m: ProxyMode) => void;
  builtinProxy: string;
  detected: Record<string, string> | null;
  noProxy: string;
  onNoProxyChange: (v: string) => void;
  health: ProxyHealth | null;
}) {
  return (
    <div className="st-section">
      <div className="st-section-body">
        <div className="st-rule">
          <span className="st-label">代理模式</span>
          <div className="st-ctrlrow">
            {(['off', 'builtin', 'auto'] as ProxyMode[]).map(m => (
              <button
                key={m}
                className={`st-btn ${mode === m ? 'primary' : ''}`}
                onClick={() => onModeChange(m)}
              >
                {MODE_LABEL[m]}
              </button>
            ))}
            {(mode === 'manual' || savedMode === 'manual') && (
              <button
                className={`st-btn ${mode === 'manual' ? 'primary' : ''}`}
                onClick={() => onModeChange('manual')}
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
                onChange={e => onNoProxyChange(e.target.value)}
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
  );
}

/** 连通性测试结果: 每站 直连 vs 经代理 并列。 */
export function ProxyProbeTable({ results }: { results: TestResult[] }) {
  return (
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
            {results.map(r => (
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
  );
}