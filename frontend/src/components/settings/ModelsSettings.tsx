/**
 * ModelsSettings — 模型配置区 (2026-09-22 IA 重构: LLM 模型配置唯一入口)
 *
 * 装配: ProviderPanel (provider 切换)
 *      + ModelPoolPanel (DEV-0244 模型池: 内置平台 + key 探测, pi Agent 单列)
 *      + ScenarioModelsPanel (三场景)。
 * 数据流: 本组件拉 /api/llm/status 后以 props 喂 ProviderPanel。
 * 2026-11-19: 密钥域退役 — SecretsPanel 已删除, 密钥仅从环境变量读取。
 */
import { useEffect, useState } from 'react';
import { getLlmStatus } from '../../api/settings';
import { ProviderPanel } from './quality/ProviderPanel';
import { ModelPoolPanel } from './ModelPoolPanel';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';

export function ModelsSettings() {
  const [providerOptions, setProviderOptions] = useState<string[]>([]);
  const [defaultProvider, setDefaultProvider] = useState('');
  const [providerSource, setProviderSource] = useState('');

  useEffect(() => {
    let dead = false;
    getLlmStatus()
      .then(data => {
        if (dead) return;
        const ps = data?.providers ? Object.keys(data.providers) : [];
        if (ps.length > 0) setProviderOptions(ps);
        if (typeof data?.effective_provider === 'string' && data.effective_provider) {
          setDefaultProvider(data.effective_provider);
        }
        if (typeof data?.config_source === 'string') setProviderSource(data.config_source);
      })
      .catch(() => { /* 面板自己 fallback */ });
    return () => { dead = true; };
  }, []);

  return (
    <div className="space-y-2">
      <ProviderPanel
        providerOptions={providerOptions}
        defaultProvider={defaultProvider}
        providerSource={providerSource}
        onChange={setDefaultProvider}
        onSource={setProviderSource}
      />
      <ModelPoolPanel />
      <ScenarioModelsPanel scope="settings-models" compact />
    </div>
  );
}
