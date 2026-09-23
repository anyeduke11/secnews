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
 * 2026-09-22 IA 重构: Provider/密钥/场景模型面板迁出至 ModelsSettings (模型配置唯一入口), 本组件只留质量规则与 LLM 检测。
 */
import { useState, useEffect } from 'react';
import { getJSON } from '../../lib/api';
import { LlmDetectionPanel } from './quality/LlmDetectionPanel';
import { QualityRulesPanel } from './quality/QualityRulesPanel';
import type { QualityRule } from './quality/QualityRulesPanel';

interface QualitySettingsProps {
  open: boolean;
}

const FALLBACK_PROVIDERS = ['sensenova', 'ollama'];

export function QualitySettings({ open }: QualitySettingsProps) {
  const [providerOptions, setProviderOptions] = useState<string[]>(FALLBACK_PROVIDERS);
  const [rules, setRules] = useState<QualityRule[]>([]);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [llmProvider, setLlmProvider] = useState('sensenova');

  // 拉 /api/quality/rules — 同时给 QualityRulesPanel + LlmDetectionPanel 喂初值
  useEffect(() => {
    if (!open) return;
    getJSON<{ rules?: QualityRule[] }>('/api/quality/rules')
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

  // 拉 /api/llm/status — 给 LlmDetectionPanel 喂 providerOptions
  useEffect(() => {
    if (!open) return;
    getJSON<{
      providers?: Record<string, unknown>;
    }>('/api/llm/status')
      .then(data => {
        const ps = data.providers ? Object.keys(data.providers) : [];
        if (ps.length > 0) setProviderOptions(ps);
      })
      .catch(() => { /* keep fallback */ });
  }, [open]);

  return (
    <div className="space-y-3" data-testid="quality-settings">
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