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
import { LlmDetectionPanel, type LlmDetectionStatus } from './quality/LlmDetectionPanel';
import { QualityRulesPanel } from './quality/QualityRulesPanel';
import type { QualityRule } from './quality/QualityRulesPanel';

interface QualitySettingsProps {
  open: boolean;
}

export function QualitySettings({ open }: QualitySettingsProps) {
  const [rules, setRules] = useState<QualityRule[]>([]);
  const [llmStatus, setLlmStatus] = useState<LlmDetectionStatus | null>(null);
  const [llmLoading, setLlmLoading] = useState(true);

  // 拉 /api/quality/rules — 喂 QualityRulesPanel (llm_enabled/provider 是死字段, 不再消费)
  useEffect(() => {
    if (!open) return;
    getJSON<{ rules?: QualityRule[] }>('/api/quality/rules')
      .then(data => {
        setRules((data.rules || []) as QualityRule[]);
      })
      .catch(() => { /* 子组件自己 fallback */ });
  }, [open]);

  // 拉 /api/llm/status — 检测真实开关 (gate_detect_available) + providerOptions 共享
  useEffect(() => {
    if (!open) return;
    setLlmLoading(true);
    getJSON<{
      gate_detect_available?: boolean;
      effective_provider?: string | null;
      key_source?: string;
    }>('/api/llm/status')
      .then(data => {
        setLlmStatus({
          gate_detect_available: data.gate_detect_available === true,
          effective_provider: data.effective_provider ?? null,
          key_source: data.key_source ?? 'none',
        });
      })
      .catch(() => { setLlmStatus(null); })
      .finally(() => setLlmLoading(false));
  }, [open]);

  return (
    <div className="space-y-3" data-testid="quality-settings">
      <LlmDetectionPanel status={llmStatus} loading={llmLoading} />
      <QualityRulesPanel initialRules={rules} />
    </div>
  );
}

export default QualitySettings;