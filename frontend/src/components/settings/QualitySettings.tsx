/**
 * QualitySettings — 质量规则折叠区（Phase 5）。
 *
 * Phase 1B: 拆自原 SettingsPanel.tsx 质量设置段。
 * 包含质量规则列表 + 多种输入类型（boolean/number/text/sample_rate slider）。
 * 自包含状态 + handlers；通过 props.open 触发数据加载。
 */
import { useState, useEffect, useCallback } from 'react';

export interface QualityRule {
  key: string;
  value: string | number | boolean;
  default: string | number | boolean;
}

interface QualitySettingsProps {
  open: boolean;
}

type QualityMessage = { type: 'ok' | 'error'; text: string } | null;

export function QualitySettings({ open }: QualitySettingsProps) {
  const [qualityOpen, setQualityOpen] = useState(false);
  const [qualityRules, setQualityRules] = useState<QualityRule[]>([]);
  const [qualityEditing, setQualityEditing] = useState<Record<string, any>>({});
  const [savingQuality, setSavingQuality] = useState(false);
  const [qualityMessage, setQualityMessage] = useState<QualityMessage>(null);

  // v4.4: LLM AI 内容检测状态（与质量规则并列的子面板）
  const [llmOpen, setLlmOpen] = useState(false);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [llmProvider, setLlmProvider] = useState('sensenova');
  const [llmKey, setLlmKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [savingLlm, setSavingLlm] = useState(false);
  const [llmMessage, setLlmMessage] = useState<QualityMessage>(null);

  // v0.7 Batch 2: 默认 provider 切换（独立面板，与质量规则解耦）
  // 数据源：/api/llm/status 返回 providers（yaml 注册）+ effective_provider（实际生效）
  // + config_source（解析路径打标）。动态拉避免硬编码 5 项与 yaml 漂移。
  const [defaultProvider, setDefaultProvider] = useState('sensenova');
  const [providerOptions, setProviderOptions] = useState<string[]>(['sensenova', 'ollama']);
  const [providerSource, setProviderSource] = useState<string>('default');
  const [savingDefaultProvider, setSavingDefaultProvider] = useState(false);
  const [providerMessage, setProviderMessage] = useState<QualityMessage>(null);

  // 打开面板时拉质量规则 + LLM 初始配置
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
        // 同步 LLM 配置（rules 是同一份列表，按 key 取值）
        for (const r of rules) {
          if (r.key === 'quality.llm_enabled') setLlmEnabled(Boolean(r.value));
          else if (r.key === 'quality.llm_provider') setLlmProvider(String(r.value));
        }
      })
      .catch(() => setQualityMessage({ type: 'error', text: '加载质量配置失败' }));
  }, [open]);

  // v0.7 Batch 2: 拉 /api/llm/status 拿到 yaml 注册的 provider 列表 + 当前 effective
  useEffect(() => {
    if (!open) return;
    fetch('/api/llm/status')
      .then(r => r.json())
      .then(data => {
        const providers = data.providers ? Object.keys(data.providers) : [];
        if (providers.length > 0) setProviderOptions(providers);
        if (typeof data.effective_provider === 'string' && data.effective_provider) {
          setDefaultProvider(data.effective_provider);
        }
        if (typeof data.config_source === 'string') setProviderSource(data.config_source);
      })
      .catch(() => {
        // fallback 已在 useState 初始值里 (sensenova/ollama)
      });
  }, [open]);

  // v0.7 Batch 2: 切换默认 provider → POST /api/settings/llm-provider
  const switchDefaultProvider = useCallback(async () => {
    setSavingDefaultProvider(true);
    setProviderMessage(null);
    try {
      const resp = await fetch('/api/settings/llm-provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: defaultProvider, actor: 'web' }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setProviderMessage({
          type: 'ok',
          text: `已切换: ${data.old_provider ?? '(无)'} → ${data.new_provider}`,
        });
        // 重拉 /api/llm/status 确认 effective_provider 已变
        const r2 = await fetch('/api/llm/status');
        const d2 = await r2.json();
        if (typeof d2.effective_provider === 'string') setDefaultProvider(d2.effective_provider);
        if (typeof d2.config_source === 'string') setProviderSource(d2.config_source);
      } else {
        setProviderMessage({ type: 'error', text: data.message || '切换失败' });
      }
    } catch {
      setProviderMessage({ type: 'error', text: '切换失败 (网络错误)' });
    } finally {
      setSavingDefaultProvider(false);
    }
  }, [defaultProvider]);

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

  // v4.4: 保存 LLM AI 内容检测配置
  const saveLlm = useCallback(async () => {
    setSavingLlm(true);
    setLlmMessage(null);
    try {
      const rules: Record<string, any> = {
        'quality.llm_enabled': llmEnabled,
        'quality.llm_provider': llmProvider,
      };
      // 仅当显式输入了 key 才写入（避免覆盖已存 key 为空串）
      if (llmKey.trim()) rules['quality.llm_api_key'] = llmKey.trim();
      const resp = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setLlmMessage({ type: 'ok', text: 'LLM 检测配置已保存' });
      } else {
        setLlmMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setLlmMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSavingLlm(false);
    }
  }, [llmEnabled, llmProvider, llmKey]);

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
            color: v ? 'var(--text-on-color)' : 'var(--text-secondary)',
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

  return (
    <div className="rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      {/* v0.7 Batch 2: 默认 LLM Provider 切换（settings.kv 持久化 + audit_log 写入） */}
      <div className="px-3 py-2 space-y-2" style={{ borderBottom: '1px solid var(--border-color)' }}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            默认 LLM Provider
          </span>
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--bg-hover)',
              color: 'var(--text-muted)',
            }}
            title={`解析路径: ${providerSource}`}
          >
            {providerSource}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>当前生效</span>
          <select
            value={defaultProvider}
            onChange={e => setDefaultProvider(e.target.value)}
            className="text-xs px-2 py-1 rounded-[var(--radius-sm)]"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          >
            {providerOptions.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          优先级: env AI_PROVIDER &gt; 本设置 (settings.kv) &gt; llm.yaml default_provider。
          切换写入 settings 表 + audit_log，进程内立即生效，无需重启。
        </p>
        {providerMessage && (
          <p className="text-[10px]" style={{ color: providerMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
            {providerMessage.text}
          </p>
        )}
        <button
          onClick={switchDefaultProvider}
          disabled={savingDefaultProvider}
          className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: 'var(--color-general)', color: 'var(--text-on-color)', border: 'none',
            opacity: savingDefaultProvider ? 0.6 : 1, marginTop: 4,
          }}
        >
          {savingDefaultProvider ? '保存中...' : '切换默认 LLM Provider'}
        </button>
      </div>

      {/* v4.4: LLM AI 内容检测（独立配置，默认关闭） */}
      <button
        onClick={() => setLlmOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs"
        style={{ color: 'var(--text-primary)' }}
      >
        <span className="font-medium flex items-center gap-2">
          LLM AI 内容检测
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: llmEnabled ? 'var(--color-ai)' : 'var(--bg-hover)',
              color: llmEnabled ? 'var(--text-on-color)' : 'var(--text-muted)',
            }}
          >
            {llmEnabled ? '开启' : '关闭'}
          </span>
        </span>
        <span style={{ color: 'var(--text-muted)' }}>{llmOpen ? '−' : '+'}</span>
      </button>
      {llmOpen && (
        <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>启用检测</span>
            <button
              onClick={() => setLlmEnabled(v => !v)}
              className="px-3 py-0.5 text-xs rounded-[var(--radius-sm)]"
              style={{
                backgroundColor: llmEnabled ? 'var(--color-ai)' : 'var(--bg-hover)',
                color: llmEnabled ? 'var(--text-on-color)' : 'var(--text-secondary)',
                border: `1px solid ${llmEnabled ? 'var(--color-ai)' : 'var(--border-color)'}`,
                minWidth: 54,
              }}
            >
              {llmEnabled ? '已开启' : '已关闭'}
            </button>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>提供方</span>
            <select
              value={llmProvider}
              onChange={e => setLlmProvider(e.target.value)}
              className="text-xs px-2 py-1 rounded-[var(--radius-sm)]"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            >
              {/* v0.7 Batch 2: 动态从 yaml 注册的 provider 列表渲染（与上方默认切换面板共用 providerOptions） */}
              {providerOptions.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          {llmProvider === 'sensenova' && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>API Key</span>
              <input
                type={showKey ? 'text' : 'password'}
                value={llmKey}
                onChange={e => setLlmKey(e.target.value)}
                placeholder="sk-..."
                className="flex-1 px-2 py-1 text-xs rounded-[var(--radius-sm)] focus-ring"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
              />
              <button onClick={() => setShowKey(v => !v)} className="text-[11px]" style={{ color: 'var(--text-muted)' }} title={showKey ? '隐藏' : '显示'}>
                {showKey ? '隐藏' : '显示'}
              </button>
            </div>
          )}
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {llmProvider === 'sensenova'
              ? '需填入商汤日日新 API Key（存储在本机 settings 表）。开启后用于识别 AI 批量生成/软文。'
              : '使用本地 Ollama（qwen2.5:7b），需已在本机启动 ollama 服务。'}
          </p>
          {llmMessage && (
            <p className="text-[10px]" style={{ color: llmMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
              {llmMessage.text}
            </p>
          )}
          <button
            onClick={saveLlm}
            disabled={savingLlm}
            className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'var(--color-ai)', color: 'var(--text-on-color)', border: 'none',
              opacity: savingLlm ? 0.6 : 1, marginTop: 4,
            }}
          >
            {savingLlm ? '保存中...' : '应用 LLM 配置'}
          </button>
        </div>
      )}
      {/* 通用质量规则 */}
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
            <p className="text-[10px]" style={{ color: qualityMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
              {qualityMessage.text}
            </p>
          )}
          <button
            onClick={saveQuality}
            disabled={savingQuality}
            className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'var(--color-ai)', color: 'var(--text-on-color)', border: 'none',
              opacity: savingQuality ? 0.6 : 1, marginTop: 4,
            }}
          >
            {savingQuality ? '保存中...' : '应用质量配置'}
          </button>
        </div>
      )}
    </div>
  );
}
