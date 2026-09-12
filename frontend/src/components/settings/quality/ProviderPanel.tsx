/**
 * quality/ProviderPanel — 默认 LLM Provider 切换 (Batch 2)
 *
 * 数据源: GET /api/llm/status → providers / effective_provider / config_source
 * 写入: POST /api/settings/llm-provider { provider, actor } → settings.kv + audit_log
 *
 * 设计: 沿用 settings-shell.css 的 st-section / st-rule / st-btn;
 *       chip 徽章显示 config_source (env > settings.kv > router > yaml) 三档
 */
import { useState, useCallback } from 'react';
import { getJSON, postJSON } from '../../../lib/api';

export interface ProviderPanelProps {
  providerOptions: string[];
  defaultProvider: string;
  providerSource: string;
  onChange: (p: string) => void;
  onSource: (s: string) => void;
}

export function ProviderPanel({
  providerOptions,
  defaultProvider,
  providerSource,
  onChange,
  onSource,
}: ProviderPanelProps) {
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setMsg(null);
    try {
      const data = await postJSON<{ status?: string; old_provider?: string; new_provider?: string; message?: string }>(
        '/api/settings/llm-provider',
        { provider: defaultProvider, actor: 'web' },
      );
      if (data.status === 'ok') {
        setMsg({ type: 'ok', text: `已切换: ${data.old_provider ?? '(无)'} → ${data.new_provider}` });
        // 重拉确认
        const d2 = await getJSON<{
          effective_provider?: unknown;
          config_source?: unknown;
        }>('/api/llm/status');
        if (typeof d2.effective_provider === 'string') onChange(d2.effective_provider);
        if (typeof d2.config_source === 'string') onSource(d2.config_source);
      } else {
        setMsg({ type: 'error', text: data.message || '切换失败' });
      }
    } catch (e) {
      // apiFetch 非 ok 抛错, message 即后端 detail — 原实现同样展示 data.message
      setMsg({ type: 'error', text: e instanceof Error && e.message ? e.message : '切换失败 (网络错误)' });
    } finally {
      setSaving(false);
    }
  }, [defaultProvider, onChange, onSource]);

  const chipClass =
    providerSource === 'env' ? 'st-chip ok'
    : providerSource === 'settings.kv' ? 'st-chip ok'
    : providerSource === 'router' ? 'st-chip warn'
    : 'st-chip mute';

  return (
    <section className="st-section" aria-label="默认 LLM Provider" data-testid="provider-panel">
      <h3>默认 LLM Provider</h3>
      <p className="st-section-desc">
        优先级: env AI_PROVIDER &gt; 本设置 (settings.kv) &gt; llm.yaml default_provider。
        切换写入 settings 表 + audit_log, 进程内立即生效, 无需重启。
      </p>
      <div className="st-section-body">
        <div className="st-rule">
          <div>
            <p className="st-label">当前生效</p>
            <p className="st-key">effective_provider</p>
          </div>
          <div className="st-ctrl">
            <div className="st-ctrlrow">
              <select
                value={defaultProvider}
                onChange={e => onChange(e.target.value)}
                className="st-select"
                style={{ maxWidth: 220 }}
                aria-label="选择默认 provider"
              >
                {providerOptions.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <span className={chipClass} title={`config_source: ${providerSource}`}>
                <i aria-hidden />{providerSource}
              </span>
            </div>
          </div>
        </div>
        <div className="st-actionbar">
          {msg && (
            <span className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`}>
              {msg.text}
            </span>
          )}
          <button
            type="button"
            className="st-btn primary"
            onClick={handleSave}
            disabled={saving}
            aria-label="切换默认 LLM Provider"
          >
            {saving ? '保存中...' : '切换默认 LLM Provider'}
          </button>
        </div>
      </div>
    </section>
  );
}

export default ProviderPanel;