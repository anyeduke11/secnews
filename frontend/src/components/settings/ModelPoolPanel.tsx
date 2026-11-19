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
import {
  createSecret,
  getLlmPool,
  getLlmPoolPlatform,
  getLlmPoolRouting,
  getSecretsStatus,
  putLlmPoolRoute,
} from '../../api/settings';
import type { PoolPlatform, PoolRouting, PoolSnapshot } from '../../api/settings';
import { PoolPlatformRow } from './ModelPoolPanelParts';
import { StatusBadge } from '../../primitives/StatusBadge';

export function ModelPoolPanel() {
  const [snap, setSnap] = useState<PoolSnapshot | null>(null);
  const [probing, setProbing] = useState(false);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [vaultUnlocked, setVaultUnlocked] = useState<boolean | null>(null);
  const [msg, setMsg] = useState<{ name: string; type: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [routing, setRouting] = useState<PoolRouting['routing']>({});
  const [routeOpen, setRouteOpen] = useState<Record<string, boolean>>({});
  const [routeDrafts, setRouteDrafts] = useState<Record<string, { tier: string; model: string }>>({});
  const [writing, setWriting] = useState<string | null>(null);

  const loadRouting = useCallback(async () => {
    try {
      const d = await getLlmPoolRouting();
      setRouting(d.routing ?? {});
    } catch {
      /* 路由展示失败不阻塞池面板 */
    }
  }, []);

  const load = useCallback(async (probe: boolean) => {
    setProbing(probe);
    try {
      const d = await getLlmPool(probe);
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
    getSecretsStatus()
      .then(d => setVaultUnlocked(Boolean(d?.unlocked)))
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
      await createSecret({
        provider: p.name, name: p.label, model: '', base_url: p.base_url,
        api_key: key, master_key: '',
      });
      setKeyDrafts(prev => ({ ...prev, [p.name]: '' }));
    } catch (e) {
      setMsg({ name: p.name, type: 'error', text: e instanceof Error && e.message ? e.message : '密钥保存失败 (保险箱未解锁?)' });
      return;
    }
    setMsg({ name: p.name, type: 'ok', text: '密钥已入保险箱, 探测中…' });
    try {
      const d = await getLlmPoolPlatform(p.name);
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
      const d = await putLlmPoolRoute(
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
            <PoolPlatformRow
              key={p.name}
              p={p}
              keyDraft={keyDrafts[p.name] ?? ''}
              routeOpen={Boolean(routeOpen[p.name])}
              routeDraft={routeDrafts[p.name]}
              isWriting={writing === p.name}
              onKeyDraftChange={v => setKeyDrafts(prev => ({ ...prev, [p.name]: v }))}
              onToggleRoute={() => {
                setRouteOpen(prev => ({ ...prev, [p.name]: !prev[p.name] }));
                setRouteDrafts(prev => ({
                  ...prev,
                  [p.name]: prev[p.name] ?? { tier: 't1_score', model: p.models[0] ?? '' },
                }));
              }}
              onTierChange={tier => setRouteDrafts(prev => ({
                ...prev,
                [p.name]: { ...(prev[p.name] ?? { model: p.models[0] ?? '' }), tier },
              }))}
              onModelChange={model => setRouteDrafts(prev => ({
                ...prev,
                [p.name]: { ...(prev[p.name] ?? { tier: 't1_score' }), model },
              }))}
              onSave={() => saveAndDetect(p)}
              onWriteRoute={(tier, model) => writeRoute(p.name, tier, model)}
            />
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
                  <StatusBadge tone="ok" dot>{r.provider ?? '—'} / {r.model ?? '—'}</StatusBadge>
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
                  <StatusBadge tone="warn" dot blink>Agent 通道</StatusBadge>
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
