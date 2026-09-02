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

  // v0.7.x Batch ⑥: LLM 密钥管理 (加密保险箱) — 替代 settings.kv 'quality.llm_api_key'
  // 数据源: /api/secrets (列表) + /api/secrets/unlock (状态) + /api/secrets/{id}/reveal (明文)
  //        + /api/secrets/{id}/test (连通性) + POST/PATCH/DELETE (CRUD)
  const [secretsOpen, setSecretsOpen] = useState(false);
  const [secretsList, setSecretsList] = useState<Array<Record<string, any>>>([]);
  const [secretsUnlocked, setSecretsUnlocked] = useState(false);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [secretsMessage, setSecretsMessage] = useState<QualityMessage>(null);
  const [secretsKeySource, setSecretsKeySource] = useState<string>('none');
  const [revealModal, setRevealModal] = useState<{ id: number; apiKey: string; ts: number } | null>(null);
  const [upsertModal, setUpsertModal] = useState<{ id?: number; provider: string; name: string; model: string; base_url: string; api_key: string; master_key: string } | null>(null);
  const [masterKeyPrompt, setMasterKeyPrompt] = useState<{ target: 'unlock' | 'reveal' | 'upsert'; secretId?: number } | null>(null);
  const [masterKeyInput, setMasterKeyInput] = useState('');

  // v0.7.4-image: 三场景模型选择 (deep / light / image) — 与 secrets 面板并列
  // 数据源: POST /api/settings/scenario-model {scenario, model, actor}
  // 优先级: env HOTSPOT_SCENARIO_*_MODEL > 本设置 (settings.kv) > yaml task_overrides > 兜底
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [scenarioModels, setScenarioModels] = useState<{
    deep: string; light: string; image: string;
  }>({ deep: '', light: '', image: '' });
  const [savingScenario, setSavingScenario] = useState<string | null>(null);
  const [scenarioMessage, setScenarioMessage] = useState<QualityMessage>(null);

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

  // v0.7.x Batch ⑥: secrets 子面板 — 拉列表 + 状态
  const loadSecrets = useCallback(async () => {
    setSecretsLoading(true);
    try {
      // secrets 列表 + 状态独立 try (失败不阻塞 llm/status 的 key_source 标)
      try {
        const [lr, sr] = await Promise.all([
          fetch('/api/secrets').then(r => r.json()),
          fetch('/api/secrets/status').then(r => r.json()),
        ]);
        setSecretsList(Array.isArray(lr?.items) ? lr.items : []);
        setSecretsUnlocked(Boolean(sr?.unlocked));
      } catch {
        setSecretsList([]);
      }
      // 从 /api/llm/status 拿 key_source 标 (env / secrets / none) — 独立 try
      try {
        const ls = await fetch('/api/llm/status').then(r => r.json());
        if (typeof ls?.key_source === 'string') setSecretsKeySource(ls.key_source);
      } catch {
        // keep prior key_source
      }
    } finally {
      setSecretsLoading(false);
    }
  }, []);

  const handleUnlock = useCallback(async (masterKey: string) => {
    const r = await fetch('/api/secrets/unlock', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ master_key: masterKey }),
    });
    if (!r.ok) throw new Error('INVALID_MASTER_KEY');
    setSecretsUnlocked(true);
    await loadSecrets();
  }, [loadSecrets]);

  const handleLock = useCallback(async () => {
    await fetch('/api/secrets/lock', { method: 'POST' });
    setSecretsUnlocked(false);
  }, []);

  const handleReveal = useCallback(async (secretId: number, masterKey: string) => {
    const r = await fetch(`/api/secrets/${secretId}/reveal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ master_key: masterKey }),
    });
    if (!r.ok) throw new Error('REVEAL_FAILED');
    const data = await r.json();
    return data.api_key as string;
  }, []);

  const handleTestConnection = useCallback(async (secretId: number) => {
    const r = await fetch(`/api/secrets/${secretId}/test`, { method: 'POST' });
    const data = await r.json();
    return data;
  }, []);

  const handleUpsertSecret = useCallback(async (body: Record<string, any>) => {
    const isUpdate = Boolean(body.id);
    const url = isUpdate ? `/api/secrets/${body.id}` : '/api/secrets';
    const method = isUpdate ? 'PATCH' : 'POST';
    const r = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error('UPSERT_FAILED');
    await loadSecrets();
  }, [loadSecrets]);

  const handleDeleteSecret = useCallback(async (secretId: number) => {
    const r = await fetch(`/api/secrets/${secretId}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('DELETE_FAILED');
    await loadSecrets();
  }, [loadSecrets]);

  useEffect(() => {
    if (!open) return;
    // 打开面板时拉 secrets 状态 + 列表 (key_source 徽章始终可见,
    // 即使 secretsOpen=false 也要从 /api/llm/status 拿 key_source 标)
    loadSecrets();
  }, [open, loadSecrets]);

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

  // v0.7.4-image: 场景模型保存 — POST /api/settings/scenario-model
  const saveScenarioModel = useCallback(async (
    scenario: 'deep' | 'light' | 'image',
    model: string,
  ) => {
    setSavingScenario(scenario);
    setScenarioMessage(null);
    try {
      const r = await fetch('/api/settings/scenario-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario, model, actor: 'web' }),
      });
      const d = await r.json();
      if (r.ok && d.status === 'ok') {
        setScenarioMessage({ type: 'ok', text: `${scenario}: ${d.old_model ?? '(无)'} → ${d.new_model}` });
      } else {
        setScenarioMessage({ type: 'error', text: d.message || '保存失败' });
      }
    } catch {
      setScenarioMessage({ type: 'error', text: '保存失败 (网络错误)' });
    } finally {
      setSavingScenario(null);
    }
  }, []);

  // v4.4: 保存 LLM AI 内容检测配置
  // v0.7.x Batch ⑥: legacy 清退 — 不再写 'quality.llm_api_key' 到 settings.kv,
  // 仅写 llm_enabled/llm_provider; 密钥改走下方加密保险箱 (secrets 子面板).
  const saveLlm = useCallback(async () => {
    setSavingLlm(true);
    setLlmMessage(null);
    try {
      const rules: Record<string, any> = {
        'quality.llm_enabled': llmEnabled,
        'quality.llm_provider': llmProvider,
      };
      const resp = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setLlmMessage({ type: 'ok', text: 'LLM 检测配置已保存 (密钥请到下方加密保险箱配置)' });
      } else {
        setLlmMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setLlmMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSavingLlm(false);
    }
  }, [llmEnabled, llmProvider]);

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

      {/* v0.7.x Batch ⑥: LLM 密钥管理 (加密保险箱) — 替代 settings.kv 'quality.llm_api_key' */}
      <button
        onClick={() => setSecretsOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs"
        style={{ color: 'var(--text-primary)', borderTop: '1px solid var(--border-color)' }}
      >
        <span className="font-medium flex items-center gap-2">
          🔐 LLM 密钥管理 (加密保险箱)
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor:
                secretsKeySource === 'env' ? 'var(--color-general)' :
                secretsKeySource === 'secrets' ? 'var(--color-ai)' :
                'var(--bg-hover)',
              color:
                secretsKeySource === 'none' ? 'var(--text-muted)' : 'var(--text-on-color)',
            }}
            title={`key_source: ${secretsKeySource}`}
          >
            {secretsKeySource}
          </span>
        </span>
        <span style={{ color: 'var(--text-muted)' }}>{secretsOpen ? '−' : '+'}</span>
      </button>
      {secretsOpen && (
        <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
          {!secretsUnlocked && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>
                保险箱状态: 未解锁
              </span>
              <button
                onClick={() => { setMasterKeyInput(''); setMasterKeyPrompt({ target: 'unlock' }); }}
                className="px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{ backgroundColor: 'var(--color-general)', color: 'var(--text-on-color)' }}
              >
                解锁
              </button>
            </div>
          )}
          {secretsUnlocked && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>
                保险箱已解锁 (30 分钟自动失效)
              </span>
              <button
                onClick={handleLock}
                className="px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
              >
                立即锁定
              </button>
            </div>
          )}
          {secretsList.length === 0 && secretsUnlocked && !secretsLoading && (
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              暂无密钥 — 点下方"新增"录入第一条
            </p>
          )}
          {secretsList.map(s => (
            <div key={s.id} className="flex items-center gap-2 p-2 rounded-[var(--radius-sm)]"
                 style={{ backgroundColor: 'var(--bg-hover)' }}>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
                  {s.name || '(无名)'} · {s.provider || '(无 provider)'}
                </div>
                <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>
                  {s.model} · {s.base_url}
                </div>
              </div>
              <button
                onClick={async () => {
                  setMasterKeyInput('');
                  setMasterKeyPrompt({ target: 'reveal', secretId: s.id });
                }}
                className="text-[10px] px-1.5 py-0.5"
                style={{ color: 'var(--text-secondary)' }}
                title="显明文 10s 自动隐藏"
              >
                显明文
              </button>
              <button
                onClick={async () => {
                  const r = await handleTestConnection(s.id);
                  setSecretsMessage({ type: r.ok ? 'ok' : 'error', text: r.ok ? '连接 OK' : (r.error || '失败') });
                }}
                className="text-[10px] px-1.5 py-0.5"
                style={{ color: 'var(--text-secondary)' }}
              >
                测连
              </button>
              <button
                onClick={() => setUpsertModal({
                  id: s.id, provider: s.provider || '', name: s.name || '',
                  model: s.model || '', base_url: s.base_url || '',
                  api_key: '', master_key: '',
                })}
                className="text-[10px] px-1.5 py-0.5"
                style={{ color: 'var(--text-secondary)' }}
              >
                编辑
              </button>
              <button
                onClick={async () => {
                  if (!confirm(`删除密钥 "${s.name}"?`)) return;
                  await handleDeleteSecret(s.id);
                }}
                className="text-[10px] px-1.5 py-0.5"
                style={{ color: 'var(--color-error)' }}
              >
                删
              </button>
            </div>
          ))}
          <button
            onClick={() => setUpsertModal({
              provider: providerOptions[0] || 'sensenova',
              name: '', model: '', base_url: '',
              api_key: '', master_key: '',
            })}
            className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: secretsUnlocked ? 'var(--color-ai)' : 'var(--bg-hover)',
              color: secretsUnlocked ? 'var(--text-on-color)' : 'var(--text-muted)',
              border: 'none',
            }}
            disabled={!secretsUnlocked}
            title={secretsUnlocked ? '新增密钥' : '请先解锁保险箱'}
          >
            + 新增密钥
          </button>
          {secretsMessage && (
            <p className="text-[10px]" style={{ color: secretsMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
              {secretsMessage.text}
            </p>
          )}
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            密钥 Fernet 加密 (PBKDF2 600k 派生主密钥); reveal/test 写 audit_log;
            进程内 30min unlock 窗口,过期需重新输入主密钥。
          </p>
        </div>
      )}

      {/* v0.7.4-image: 三场景模型选择 — 与 secrets 面板并列, 默认折叠 */}
      <button
        onClick={() => setScenarioOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs"
        style={{ color: 'var(--text-primary)', borderTop: '1px solid var(--border-color)' }}
      >
        <span className="font-medium">🎯 场景模型选择 (深度 / 轻度 / 图片)</span>
        <span style={{ color: 'var(--text-muted)' }}>{scenarioOpen ? '−' : '+'}</span>
      </button>
      {scenarioOpen && (
        <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
          {(['deep', 'light', 'image'] as const).map(scenario => {
            const current = scenarioModels[scenario] || '';
            const isSaving = savingScenario === scenario;
            const isDirty = current !== '';
            return (
              <div key={scenario} className="flex items-center gap-2">
                <span className="text-[11px] font-mono w-12" style={{ color: 'var(--text-secondary)' }}>
                  {scenario}
                </span>
                <input
                  value={current}
                  onChange={e => setScenarioModels(m => ({ ...m, [scenario]: e.target.value }))}
                  placeholder="留空走 yaml router 默认"
                  className="flex-1 px-2 py-1 text-xs font-mono rounded-[var(--radius-sm)] focus-ring"
                  style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
                />
                <button
                  onClick={() => saveScenarioModel(scenario, current.trim())}
                  disabled={isSaving || !isDirty}
                  className="px-2 py-1 text-[10px] rounded-[var(--radius-sm)]"
                  style={{
                    backgroundColor: isDirty ? 'var(--color-general)' : 'var(--bg-hover)',
                    color: isDirty ? 'var(--text-on-color)' : 'var(--text-muted)',
                    opacity: isSaving ? 0.6 : 1,
                  }}
                >
                  {isSaving ? '保存中...' : '保存'}
                </button>
              </div>
            );
          })}
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            优先级: env HOTSPOT_SCENARIO_*_MODEL &gt; 本设置 (settings.kv) &gt; yaml task_overrides &gt; 兜底。
            模型选择 = 路由选择, 密钥仍走下方加密保险箱 (Batch ⑥)。
          </p>
          {scenarioMessage && (
            <p className="text-[10px]" style={{ color: scenarioMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
              {scenarioMessage.text}
            </p>
          )}
        </div>
      )}

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

      {/* v0.7.x Batch ⑥: secrets 主密钥 prompt modal (unlock / reveal / upsert 共用) */}
      {masterKeyPrompt && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setMasterKeyPrompt(null)}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--bg-elevated)', padding: 20, borderRadius: 8,
              minWidth: 320, border: '1px solid var(--border-color)',
            }}
          >
            <h4 className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              {masterKeyPrompt.target === 'unlock' ? '解锁保险箱' :
               masterKeyPrompt.target === 'reveal' ? '显明文需验证主密钥' :
               '新增/更新密钥需主密钥'}
            </h4>
            <input
              type="password" value={masterKeyInput}
              onChange={e => setMasterKeyInput(e.target.value)}
              placeholder="主密钥 (12+ 字符)"
              autoFocus
              className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)] focus-ring mb-2"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            />
            <div className="flex gap-2">
              <button
                onClick={() => setMasterKeyPrompt(null)}
                className="flex-1 px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
              >
                取消
              </button>
              <button
                onClick={async () => {
                  try {
                    if (masterKeyPrompt.target === 'unlock') {
                      await handleUnlock(masterKeyInput);
                      setSecretsMessage({ type: 'ok', text: '保险箱已解锁' });
                    } else if (masterKeyPrompt.target === 'reveal' && masterKeyPrompt.secretId) {
                      const k = await handleReveal(masterKeyPrompt.secretId, masterKeyInput);
                      setRevealModal({ id: masterKeyPrompt.secretId, apiKey: k, ts: Date.now() });
                      setTimeout(() => setRevealModal(null), 10_000);
                    }
                    setMasterKeyPrompt(null);
                    setMasterKeyInput('');
                  } catch (e: any) {
                    setSecretsMessage({ type: 'error', text: `失败: ${e.message}` });
                  }
                }}
                disabled={masterKeyInput.length < 12}
                className="flex-1 px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{
                  backgroundColor: 'var(--color-general)', color: 'var(--text-on-color)',
                  opacity: masterKeyInput.length < 12 ? 0.5 : 1,
                }}
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}

      {/* v0.7.x Batch ⑥: reveal 明文 modal (10s 自动隐藏) */}
      {revealModal && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setRevealModal(null)}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--bg-elevated)', padding: 20, borderRadius: 8,
              minWidth: 360, border: '1px solid var(--border-color)',
            }}
          >
            <h4 className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              明文密钥 (10s 自动隐藏)
            </h4>
            <code
              className="block p-2 text-xs rounded-[var(--radius-sm)] mb-2 break-all"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
            >
              {revealModal.apiKey}
            </code>
            <button
              onClick={() => navigator.clipboard.writeText(revealModal.apiKey)}
              className="w-full px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)' }}
            >
              复制
            </button>
          </div>
        </div>
      )}

      {/* v0.7.x Batch ⑥: 新增/编辑密钥 modal */}
      {upsertModal && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setUpsertModal(null)}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: 'var(--bg-elevated)', padding: 20, borderRadius: 8,
              minWidth: 360, border: '1px solid var(--border-color)',
            }}
          >
            <h4 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
              {upsertModal.id ? `编辑密钥 #${upsertModal.id}` : '新增密钥'}
            </h4>
            <div className="space-y-2">
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>Provider</label>
              <select
                value={upsertModal.provider}
                onChange={e => setUpsertModal({ ...upsertModal, provider: e.target.value })}
                className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
              >
                {providerOptions.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>名称</label>
              <input value={upsertModal.name}
                     onChange={e => setUpsertModal({ ...upsertModal, name: e.target.value })}
                     className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                     style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>Model</label>
              <input value={upsertModal.model}
                     onChange={e => setUpsertModal({ ...upsertModal, model: e.target.value })}
                     className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                     style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>Base URL</label>
              <input value={upsertModal.base_url}
                     onChange={e => setUpsertModal({ ...upsertModal, base_url: e.target.value })}
                     className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                     style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>
                API Key {upsertModal.id && <span className="opacity-60">(留空保留旧值)</span>}
              </label>
              <input type="password" value={upsertModal.api_key}
                     onChange={e => setUpsertModal({ ...upsertModal, api_key: e.target.value })}
                     className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                     style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
              <label className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>主密钥 (验证身份)</label>
              <input type="password" value={upsertModal.master_key}
                     onChange={e => setUpsertModal({ ...upsertModal, master_key: e.target.value })}
                     className="w-full px-2 py-1 text-xs rounded-[var(--radius-sm)]"
                     style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
            </div>
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => setUpsertModal(null)}
                className="flex-1 px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
              >取消</button>
              <button
                onClick={async () => {
                  try {
                    const body: Record<string, any> = {
                      name: upsertModal.name,
                      model: upsertModal.model,
                      base_url: upsertModal.base_url,
                      provider: upsertModal.provider,
                      master_key: upsertModal.master_key,
                    };
                    if (upsertModal.api_key) body.api_key = upsertModal.api_key;
                    await handleUpsertSecret(upsertModal.id ? { ...body, id: upsertModal.id } : body);
                    setSecretsMessage({ type: 'ok', text: upsertModal.id ? '已更新' : '已新增' });
                    setUpsertModal(null);
                  } catch (e: any) {
                    setSecretsMessage({ type: 'error', text: `失败: ${e.message}` });
                  }
                }}
                disabled={
                  !upsertModal.name || !upsertModal.model || !upsertModal.base_url ||
                  (!upsertModal.id && !upsertModal.api_key) ||
                  upsertModal.master_key.length < 12
                }
                className="flex-1 px-2 py-1 text-[11px] rounded-[var(--radius-sm)]"
                style={{
                  backgroundColor: 'var(--color-ai)', color: 'var(--text-on-color)',
                }}
              >保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
