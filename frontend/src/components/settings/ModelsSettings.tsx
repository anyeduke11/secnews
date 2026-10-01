/**
 * ModelsSettings — 模型配置区 (2026-09-22 IA 重构: LLM 模型配置唯一入口)
 *
 * 装配: ProviderPanel (provider 切换) + SecretsPanel (LLM 密钥 CRUD)
 *      + ModelPoolPanel (DEV-0244 模型池: 内置平台 + key 探测, pi Agent 单列)
 *      + ScenarioModelsPanel (三场景)。
 * 数据流: 本组件拉 /api/llm/status 后以 props 喂 ProviderPanel/SecretsPanel。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';
import { ProviderPanel } from './quality/ProviderPanel';
import { SecretsPanel } from './quality/SecretsPanel';
import { ModelPoolPanel } from './ModelPoolPanel';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';

interface LLMStatus {
  providers?: Record<string, { status?: string; model?: string }>;
  effective_provider?: unknown;
  config_source?: unknown;
  key_source?: unknown;
}

export function ModelsSettings() {
  const [providerOptions, setProviderOptions] = useState<string[]>([]);
  const [defaultProvider, setDefaultProvider] = useState('');
  const [providerSource, setProviderSource] = useState('');
  const [keySource, setKeySource] = useState('none');

  useEffect(() => {
    let dead = false;
    getJSON<LLMStatus>('/api/llm/status')
      .then(data => {
        if (dead) return;
        const ps = data?.providers ? Object.keys(data.providers) : [];
        if (ps.length > 0) setProviderOptions(ps);
        if (typeof data?.effective_provider === 'string' && data.effective_provider) {
          setDefaultProvider(data.effective_provider);
        }
        if (typeof data?.config_source === 'string') setProviderSource(data.config_source);
        if (typeof data?.key_source === 'string') setKeySource(data.key_source);
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
      <SecretsPanel providerOptions={providerOptions} initialKeySource={keySource} />
      <ModelPoolPanel />
      <ScenarioModelsPanel scope="settings-models" compact />
    </div>
  );
}
