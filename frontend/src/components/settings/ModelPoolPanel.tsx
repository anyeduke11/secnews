/**
 * ModelPoolPanel — 模型池 (DEV-0244)
 *
 * owner 裁决: pi 是 Agent 不是模型; 模型池内置国产主流平台接口信息
 * (base_url 等), 用户提供 key 即可, 自动识别有哪些模型可用。
 *
 * 数据源: GET /api/llm/pool[?probe=1] (backend/services/ai_hub/pool.py)
 * 密钥写入: POST /api/secrets (provider=<平台名>, 与 SecretsPanel 同保险箱)
 * pi 在 agent_channels 单列 — 本面板模型表格永不出现 pi。
 */
import { useCallback, useEffect, useState } from 'react';
import { apiFetch, getJSON } from '../../lib/api';

interface PoolPlatform {
  name: string;
  label: string;
  base_url: string;
  key_env: string;
  configured: boolean;
  key_source: string;
  available: boolean | null;
  models: string[];
  model_count: number;
  latency_ms: number | null;
  error: string | null;
}

interface PoolSnapshot {
  platforms: PoolPlatform[];
  agent_channels: Array<{ name: string; kind: string; desc: string }>;
  probed: boolean;
}

interface SecretsStatus {
  unlocked?: boolean;
}

function PlatformChip({ p }: { p: PoolPlatform }) {
  if (!p.configured) {
    return <span className="st-chip mute"><i aria-hidden />未配置</span>;
  }
  if (p.available === true) {
    return <span className="st-chip ok"><i aria-hidden />可用 {p.model_count} 款模型</span>;
  }
  if (p.available === false && p.error === 'no_key') {
    return <span className="st-chip mute"><i aria-hidden />未配置</span>;
  }
  if (p.available === false) {
    return <span className="st-chip bad"><i aria-hidden />{p.error?.startsWith('HTTP 40') ? '密钥无效' : '不可达'}</span>;
  }
  return <span className="st-chip warn"><i aria-hidden />已配置 · 未知</span>;
}

export function ModelPoolPanel() {
  const [snap, setSnap] = useState<PoolSnapshot | null>(null);
  const [probing, setProbing] = useState(false);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [vaultUnlocked, setVaultUnlocked] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<{ name: string; type: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async (probe: boolean) => {
    setProbing(probe);
    try {
      const d = await getJSON<PoolSnapshot>(`/api/llm/pool${probe ? '?probe=1' : ''}`);
      setSnap(d ?? null);
    } catch {
      setSnap(null);
    } finally {
      setProbing(false);
    }
  }, []);

  useEffect(() => {
    load(false);
    getJSON<SecretsStatus>('/api/secrets/status')
      .then((d: SecretsStatus) => setVaultUnlocked(Boolean(d?.unlocked)))
      .catch(() => setVaultUnlocked(null));
  }, [load]);

  const saveAndDetect = useCallback(async (p: PoolPlatform) => {
    const key = (keyDrafts[p.name] ?? '').trim();
    setMsg(null);
    if (!key) {
      setMsg({ name: p.name, type: 'error', text: '请先粘贴 API Key' });
      return;
    }
    try {
      // 与 SecretsPanel 同一保险箱通道 (provider=<平台名> 即 pool 密钥解析键)
      await apiFetch('/api/secrets', {
        method: 'POST',
        body: JSON.stringify({
          provider: p.name, name: p.label, model: '', base_url: p.base_url,
          api_key: key, master_key: '',
        }),
      });
      setKeyDrafts(prev => ({ ...prev, [p.name]: '' }));
    } catch (e) {
      setMsg({ name: p.name, type: 'error', text: e instanceof Error && e.message ? e.message : '密钥保存失败 (保险箱未解锁?)' });
      return;
    }
    setMsg({ name: p.name, type: 'ok', text: '密钥已入保险箱, 探测中…' });
    try {
      const d = await getJSON<PoolSnapshot>(`/api/llm/pool?probe=1&only=${p.name}`);
      const updated = d.platforms?.[0];
      if (updated) {
        setSnap(prev => prev
          ? { ...prev, platforms: prev.platforms.map(x => (x.name === p.name ? updated : x)) }
          : prev);
        setMsg(updated.available === true
          ? { name: p.name, type: 'ok', text: `检测成功: ${updated.model_count} 款模型可用` }
          : { name: p.name, type: 'error', text: `检测未通过: ${updated.error ?? '未知'}` });
      }
    } catch {
      setMsg({ name: p.name, type: 'error', text: '探测失败 (网络/后端不可达)' });
    }
  }, [keyDrafts]);

  return (
    <div className="st-card" data-testid="model-pool-panel">
      <h3>
        模型池 — 内置平台
        <button
          type="button"
          className="st-btn"
          style={{ marginLeft: 'auto' }}
          onClick={() => load(true)}
          disabled={probing}
          aria-label="全量探测模型池"
        >
          {probing ? '探测中…' : '重新探测'}
        </button>
      </h3>
      <p className="st-section-desc">
        内置国产主流平台接口信息 — 粘贴对应平台 API Key 即自动识别可用模型
        (密钥存入加密保险箱, 一次配置长期有效)。pi 是 Agent 通道, 不属于模型池 (见下方单列)。
      </p>

      {!snap && <p className="st-cellnote">模型池不可用 — 后端不可达。</p>}

      {snap && (
        <div className="st-rule-list">
          {snap.platforms.map(p => (
            <div className="st-rule" key={p.name} data-testid={`pool-${p.name}`}>
              <div>
                <p className="st-label">{p.label}</p>
                <p className="st-key">
                  {p.name} · {p.key_env}
                  {p.available === true && p.models.length > 0 && (
                    <span> · {p.models.slice(0, 3).join(' / ')}{p.model_count > 3 ? ` …` : ''}</span>
                  )}
                  {p.error && p.error !== 'no_key' && <span> · {p.error}</span>}
                </p>
              </div>
              <div className="st-ctrl">
                <PlatformChip p={p} />
                {!p.configured && (
                  <div className="st-ctrlrow">
                    <input
                      type="password"
                      className="st-input"
                      style={{ maxWidth: 180 }}
                      placeholder={`${p.label} API Key`}
                      aria-label={`${p.label} API Key`}
                      value={keyDrafts[p.name] ?? ''}
                      onChange={e => setKeyDrafts(prev => ({ ...prev, [p.name]: e.target.value }))}
                    />
                    <button
                      type="button"
                      className="st-btn primary"
                      onClick={() => saveAndDetect(p)}
                      aria-label={`保存并检测 ${p.label}`}
                    >
                      保存并检测
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {msg && (
        <p className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`} data-testid="pool-msg">
          [{msg.name}] {msg.text}
        </p>
      )}
      {vaultUnlocked === false && (
        <p className="st-cellnote">保险箱处于锁定状态 — 保存密钥需先在密钥管理解锁 (或填写主密钥)。</p>
      )}

      {snap && snap.agent_channels.length > 0 && (
        <>
          <h3 style={{ marginTop: 12 }}>Agent 通道 (非模型)</h3>
          <div className="st-rule-list">
            {snap.agent_channels.map(a => (
              <div className="st-rule" key={a.name} data-testid={`agent-${a.name}`}>
                <div>
                  <p className="st-label">{a.name} — Agent</p>
                  <p className="st-key">{a.desc}</p>
                </div>
                <div className="st-ctrl">
                  <span className="st-chip warn"><i aria-hidden />Agent 通道</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default ModelPoolPanel;
