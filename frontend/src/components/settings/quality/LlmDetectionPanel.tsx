/**
 * quality/LlmDetectionPanel — LLM AI 内容检测 (v4.4 + Batch ⑥ legacy 清退)
 *
 * 数据源: GET /api/quality/rules → quality.llm_enabled / quality.llm_provider
 * 写入: PUT /api/quality/rules
 *
 * Batch ⑥ 改动: 不再写 'quality.llm_api_key' (legacy 清退);
 *                密钥改走 SecretsPanel 加密保险箱。
 *
 * 设计: st-rule 布局 + st-switch + 状态 chip; 主密钥路径已禁用, 提示跳 SecretsPanel
 */
import { useState, useCallback } from 'react';

export interface LlmDetectionPanelProps {
  initialEnabled: boolean;
  initialProvider: string;
  providerOptions: string[];
}

export function LlmDetectionPanel({
  initialEnabled,
  initialProvider,
  providerOptions,
}: LlmDetectionPanelProps) {
  const [enabled, setEnabled] = useState(initialEnabled);
  const [provider, setProvider] = useState(initialProvider);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  const save = useCallback(async () => {
    setSaving(true);
    setMsg(null);
    try {
      const rules = {
        'quality.llm_enabled': enabled,
        'quality.llm_provider': provider,
      };
      const r = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const d = await r.json();
      if (r.ok && d.status === 'ok') {
        setMsg({ type: 'ok', text: 'LLM 检测配置已保存 (密钥请到下方加密保险箱配置)' });
      } else {
        setMsg({ type: 'error', text: d.message || '保存失败' });
      }
    } catch {
      setMsg({ type: 'error', text: '保存失败' });
    } finally {
      setSaving(false);
    }
  }, [enabled, provider]);

  return (
    <section className="st-section" aria-label="LLM AI 内容检测" data-testid="llm-detection-panel">
      <h3>
        LLM AI 内容检测
        <span className={enabled ? 'st-chip ok' : 'st-chip mute'} title={`enabled: ${enabled}`}>
          <i aria-hidden />{enabled ? '开启' : '关闭'}
        </span>
      </h3>
      <p className="st-section-desc">
        启用后, 采集管线会用 LLM 对通过质量规则的热点做二次 AI 批量/软文识别。
        {provider === 'sensenova'
          ? '需配置 sensenova API Key — 改用下方加密保险箱 (SecretsPanel)。'
          : '本地 Ollama 路径 — 需先启动 ollama 服务 (qwen2.5:7b)。'}
      </p>
      <div className="st-section-body">
        <div className="st-rule">
          <div><p className="st-label">启用检测</p><p className="st-key">quality.llm_enabled</p></div>
          <div className="st-ctrl">
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              onClick={() => setEnabled(v => !v)}
              className="st-switch"
              style={{ width: 32, height: 18 }}
              data-testid="llm-enabled-switch"
            />
          </div>
        </div>
        <div className="st-rule">
          <div><p className="st-label">提供方</p><p className="st-key">quality.llm_provider</p></div>
          <div className="st-ctrl">
            <select
              value={provider}
              onChange={e => setProvider(e.target.value)}
              className="st-select"
              style={{ maxWidth: 220 }}
              aria-label="LLM Provider"
            >
              {providerOptions.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>
        <div className="st-actionbar">
          {msg && <span className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`}>{msg.text}</span>}
          <button type="button" className="st-btn primary" onClick={save} disabled={saving}>
            {saving ? '保存中...' : '应用 LLM 配置'}
          </button>
        </div>
      </div>
    </section>
  );
}

export default LlmDetectionPanel;