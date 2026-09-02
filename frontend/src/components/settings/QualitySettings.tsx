/**
 * QualitySettings — 质量设置主入口 / 组合层 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2:
 *  - 原 879 行单体拆为 quality/ProviderPanel + quality/SecretsPanel +
 *    quality/LlmDetectionPanel + quality/QualityRulesPanel + ScenarioModelsPanel
 *  - 本文件只负责初始数据加载 + providerOptions 共享 + 5 子组件组合
 *  - 全部走 settings-shell.css 的 st-* 原子样式
 *
 * 历史: v0.6.x 原 SettingsPanel.tsx 1065 行; v0.7.0 拆 12 文件; V2 拆 5 子组件 + 哨兵化
 */
import { useState, useEffect } from 'react';
import { ProviderPanel } from './quality/ProviderPanel';
import { SecretsPanel } from './quality/SecretsPanel';
import { LlmDetectionPanel } from './quality/LlmDetectionPanel';
import { QualityRulesPanel } from './quality/QualityRulesPanel';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';
import type { QualityRule } from './quality/QualityRulesPanel';

interface QualitySettingsProps {
  open: boolean;
}

const FALLBACK_PROVIDERS = ['sensenova', 'ollama'];

export function QualitySettings({ open }: QualitySettingsProps) {
  const [providerOptions, setProviderOptions] = useState<string[]>(FALLBACK_PROVIDERS);
  const [defaultProvider, setDefaultProvider] = useState('sensenova');
  const [providerSource, setProviderSource] = useState<string>('default');
  const [keySource, setKeySource] = useState<string>('none');
  const [rules, setRules] = useState<QualityRule[]>([]);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [llmProvider, setLlmProvider] = useState('sensenova');

  // 拉 /api/quality/rules — 同时给 QualityRulesPanel + LlmDetectionPanel 喂初值
  useEffect(() => {
    if (!open) return;
    fetch('/api/quality/rules')
      .then(r => r.json())
      .then(data => {
        const list = (data.rules || []) as QualityRule[];
        setRules(list);
        for (const r of list) {
          if (r.key === 'quality.llm_enabled') setLlmEnabled(Boolean(r.value));
          else if (r.key === 'quality.llm_provider') setLlmProvider(String(r.value));
        }
      })
      .catch(() => { /* 子组件自己 fallback */ });
  }, [open]);

  // 拉 /api/llm/status — 给 ProviderPanel 喂 providerOptions / defaultProvider / source
  useEffect(() => {
    if (!open) return;
    fetch('/api/llm/status')
      .then(r => r.json())
      .then(data => {
        const ps = data.providers ? Object.keys(data.providers) : [];
        if (ps.length > 0) setProviderOptions(ps);
        if (typeof data.effective_provider === 'string' && data.effective_provider) {
          setDefaultProvider(data.effective_provider);
        }
        if (typeof data.config_source === 'string') setProviderSource(data.config_source);
        if (typeof data.key_source === 'string') setKeySource(data.key_source);
      })
      .catch(() => { /* keep fallback */ });
  }, [open]);

  return (
    <div className="space-y-3" data-testid="quality-settings">
      <ProviderPanel
        providerOptions={providerOptions}
        defaultProvider={defaultProvider}
        providerSource={providerSource}
        onChange={setDefaultProvider}
        onSource={setProviderSource}
      />
      <SecretsPanel providerOptions={providerOptions} initialKeySource={keySource} />
      <section className="st-section" aria-label="场景模型选择" data-testid="scenario-models-section">
        <h3>🎯 场景模型选择 (深度 / 轻度 / 图片)</h3>
        <p className="st-section-desc">三场景模型选择 — 与 /settings?cat=image_models 同源。</p>
        <ScenarioModelsPanel scope="settings-scenario" />
      </section>
      <LlmDetectionPanel
        initialEnabled={llmEnabled}
        initialProvider={llmProvider}
        providerOptions={providerOptions}
      />
      <QualityRulesPanel initialRules={rules} />
    </div>
  );
}

export default QualitySettings;