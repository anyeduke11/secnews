/**
 * ModelsSettings — 模型配置区 (2026-09-22 IA 重构: LLM 模型配置唯一入口)
 *
 * 装配: ProviderPanel (provider 切换) + SecretsPanel (LLM 密钥 CRUD)
 *      + LlmPoolCard (模型池状态, /api/llm/status) + ScenarioModelsPanel (三场景)。
 * 来源: 原采集分区 Provider/Secrets 面板 + 采集模型档位 + 旧图片模型 cat, 按裁决归一。
 * 数据流与原 QualitySettings 相同: 本组件拉 /api/llm/status 后以 props 喂 ProviderPanel/SecretsPanel。
 */
import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';
import { ProviderPanel } from './quality/ProviderPanel';
import { SecretsPanel } from './quality/SecretsPanel';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';

interface LLMStatus {
  providers?: Record<string, { status?: string; model?: string }>;
  effective_provider?: unknown;
  config_source?: unknown;
  key_source?: unknown;
}

function LlmPoolCard() {
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  useEffect(() => {
    let dead = false;
    getJSON<LLMStatus>('/api/llm/status')
      .then(d => { if (!dead) setLlm(d ?? null); })
      .catch(() => { if (!dead) setLlm(null); });
    return () => { dead = true; };
  }, []);
  const providers = Object.entries(llm?.providers ?? {});
  return (
    <div className="st-card">
      <h3>模型池</h3>
      <p className="st-section-desc">已配置 provider 的实时状态（来源 /api/llm/status）。</p>
      {providers.length === 0 ? (
        <p className="st-cellnote">模型状态不可用 — 后端不可达或未配置 provider。</p>
      ) : (
        <div className="st-rule-list">
          {providers.map(([name, p]) => (
            <div className="st-rule" key={name}>
              <div><p className="st-label">{name}</p></div>
              <div className="st-ctrl">
                <span className={`st-chip${p.status === 'ok' ? ' ok' : ' bad'}`}>
                  <i aria-hidden />{p.model ?? name} [{p.status ?? '?'}]
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
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
      <LlmPoolCard />
      <ScenarioModelsPanel scope="settings-models" compact />
    </div>
  );
}
