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
import { apiFetch, getJSON, postJSON } from '../../lib/api';

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

const TIER_OPTIONS: Array<{ key: string; label: string }> = [
  { key: 't1_score', label: 'STANDARD 档 (评分/NER/评测)' },
  { key: 't3_summary', label: 'HEAVY 档 (深度阅读/报告)' },
  { key: 't3_chunk_summary', label: 'FLASH 档 (摘要/轻量高频)' },
];

interface CurrentRouting {
  routing?: Record<string, { label: string; provider: string | null; model: string | null }>;
  error?: string | null;
}

export function ModelPoolPanel() {
  const [snap, setSnap] = useState<PoolSnapshot | null>(null);
  const [probing, setProbing] = useState(false);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [vaultUnlocked, setVaultUnlocked] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<{ name: string; type: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [routing, setRouting] = useState<CurrentRouting['routing']>({});
  const [routeOpen, setRouteOpen] = useState<Record<string, boolean>>({});
  const [routeDrafts, setRouteDrafts] = useState<Record<string, { tier: string; model: string }>>({});
  const [writing, setWriting] = useState<string | null>(null);

  const loadRouting = useCallback(async () => {
    try {
      const d = await getJSON<CurrentRouting>('/api/llm/pool/routing');
      setRouting(d.routing ?? {});
    } catch {
      /* 路由展示失败不阻塞池面板 */
    }
  }, []);

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
    loadRouting();
    getJSON<SecretsStatus>('/api/secrets/status')
      .then((d: SecretsStatus) => setVaultUnlocked(Boolean(d?.unlocked)))
      .catch(() => setVaultUnlocked(null));
  }, [load, loadRouting]);

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

  const writeRoute = useCallback(async (platform: string, overrideKey: string, model: string, force = false) => {
    setWriting(platform);
    setMsg(null);
    try {
      const d = await postJSON<{ status?: string; message?: string }>(
        '/api/llm/pool/route',
        { override_key: overrideKey, provider: platform, model, force },
      );
      if (d.status === 'ok') {
        // force 写入 = 成功但未经验证 — 用 warn 色而非 ok, 避免"未经验证"淹没在成功色里
        const isForce = (d.message ?? '').includes('已跳过在线探测');
        setMsg({ name: platform, type: isForce ? 'warn' : 'ok', text: d.message ?? '路由已写入' });
        setRouteOpen(prev => ({ ...prev, [platform]: false }));
        loadRouting();
      } else {
        setMsg({ name: platform, type: 'error', text: d.message ?? '写入失败' });
      }
    } catch (e) {
      setMsg({ name: platform, type: 'error', text: e instanceof Error && e.message ? e.message : '写入失败 (网络错误)' });
    } finally {
      setWriting(null);
    }
  }, [loadRouting]);

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
                {(p.available === true || p.configured) && (
                  <button
                    type="button"
                    className="st-btn"
                    onClick={() => {
                      setRouteOpen(prev => ({ ...prev, [p.name]: !prev[p.name] }));
                      setRouteDrafts(prev => ({
                        ...prev,
                        [p.name]: prev[p.name] ?? { tier: 't1_score', model: p.models[0] ?? '' },
                      }));
                    }}
                    aria-expanded={Boolean(routeOpen[p.name])}
                    aria-label={`写入路由 ${p.label}`}
                  >
                    写入路由
                  </button>
                )}
              </div>
              {routeOpen[p.name] && (p.available === true || p.configured) && (
                <div className="st-ctrlrow" style={{ width: '100%', marginTop: 6 }} data-testid={`route-${p.name}`}>
                  <select
                    className="st-select"
                    style={{ maxWidth: 230 }}
                    aria-label={`${p.label} 路由档位`}
                    value={routeDrafts[p.name]?.tier ?? 't1_score'}
                    onChange={e => setRouteDrafts(prev => ({
                      ...prev,
                      [p.name]: { ...(prev[p.name] ?? { model: p.models[0] ?? '' }), tier: e.target.value },
                    }))}
                  >
                    {TIER_OPTIONS.map(t => (
                      <option key={t.key} value={t.key}>{t.label}</option>
                    ))}
                  </select>
                  {p.available === true && p.models.length > 0 ? (
                    <select
                      className="st-select"
                      style={{ maxWidth: 230 }}
                      aria-label={`${p.label} 路由模型`}
                      value={routeDrafts[p.name]?.model ?? p.models[0]}
                      onChange={e => setRouteDrafts(prev => ({
                        ...prev,
                        [p.name]: { ...(prev[p.name] ?? { tier: 't1_score' }), model: e.target.value },
                      }))}
                    >
                      {p.models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input
                      type="text"
                      className="st-input"
                      style={{ maxWidth: 230 }}
                      placeholder="模型名 (可先「重新探测」自动获取)"
                      aria-label={`${p.label} 路由模型 (手输)`}
                      value={routeDrafts[p.name]?.model ?? ''}
                      onChange={e => setRouteDrafts(prev => ({
                        ...prev,
                        [p.name]: { ...(prev[p.name] ?? { tier: 't1_score' }), model: e.target.value },
                      }))}
                    />
                  )}
                  <button
                    type="button"
                    className="st-btn primary"
                    disabled={writing === p.name || !(routeDrafts[p.name]?.model ?? '').trim()}
                    onClick={() => writeRoute(p.name, routeDrafts[p.name]?.tier ?? 't1_score', (routeDrafts[p.name]?.model ?? '').trim())}
                    aria-label={`确认写入 ${p.label} 路由`}
                  >
                    {writing === p.name ? '写入中…' : '确认写入'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {msg && (
        <p className={`st-ab-msg ${msg.type}`} data-testid="pool-msg">
          [{msg.name}] {msg.text}
          {/* 探测未通过类错误 → 提供 force 重试出口 (跳过在线探测直接写入; 无 key 仍会被后端拒绝) */}
          {msg.type === 'error' && msg.text.includes('密钥探测未通过') && routeDrafts[msg.name] && (
            <button
              type="button"
              className="st-btn"
              style={{ marginLeft: 8 }}
              disabled={writing === msg.name}
              onClick={() => writeRoute(msg.name, routeDrafts[msg.name]!.tier, routeDrafts[msg.name]!.model, true)}
              aria-label={`跳过探测写入 ${msg.name}`}
            >
              确认模型无误? 跳过探测写入
            </button>
          )}
        </p>
      )}
      {vaultUnlocked === false && (
        <p className="st-cellnote">保险箱处于锁定状态 — 保存密钥需先在密钥管理解锁 (或填写主密钥)。</p>
      )}

      {routing && Object.keys(routing).length > 0 && (
        <>
          <h3 style={{ marginTop: 12 }}>当前路由 (llm.yaml task_overrides)</h3>
          <div className="st-rule-list" data-testid="current-routing">
            {Object.entries(routing).map(([key, r]) => (
              <div className="st-rule" key={key}>
                <div>
                  <p className="st-label">{r.label}</p>
                  <p className="st-key">{key}</p>
                </div>
                <div className="st-ctrl">
                  <span className="st-chip ok"><i aria-hidden />{r.provider ?? '—'} / {r.model ?? '—'}</span>
                </div>
              </div>
            ))}
          </div>
        </>
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
