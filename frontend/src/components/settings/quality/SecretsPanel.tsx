/**
 * quality/SecretsPanel — LLM 密钥管理 (加密保险箱) — Batch ⑥
 *
 * 数据源: GET /api/secrets / /api/secrets/status / /api/llm/status (key_source)
 * 写入: POST/DELETE /api/secrets, PATCH /api/secrets/{id},
 *       POST /api/secrets/unlock /lock /{id}/reveal /{id}/test
 *
 * 设计: 沿用 settings-shell.css 的 st-section / st-table / st-chip / st-btn;
 *       key_source 徽章三档: env / secrets / none (灰);
 *       主密钥 prompt / reveal / upsert 三个 modal 集中在本组件内。
 */
import { useState, useCallback, useEffect } from 'react';

export interface SecretsPanelProps {
  providerOptions: string[];
  /**
   * 从父组件 QualitySettings 注入的 key_source (避免本组件自己拉 /api/llm/status,
   * 防止父级 open=false 门控失效)。
   */
  initialKeySource?: string;
}

export function SecretsPanel({ providerOptions, initialKeySource = 'none' }: SecretsPanelProps) {
  const [list, setList] = useState<Array<Record<string, any>>>([]);
  const [unlocked, setUnlocked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);
  const [keySource, setKeySource] = useState<string>(initialKeySource);
  const [revealModal, setRevealModal] = useState<{ id: number; apiKey: string; ts: number } | null>(null);
  const [upsertModal, setUpsertModal] = useState<{
    id?: number; provider: string; name: string; model: string; base_url: string; api_key: string; master_key: string;
  } | null>(null);
  const [masterKeyPrompt, setMasterKeyPrompt] = useState<{ target: 'unlock' | 'reveal'; secretId?: number } | null>(null);
  const [masterKeyInput, setMasterKeyInput] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      try {
        const [lr, sr] = await Promise.all([
          fetch('/api/secrets').then(r => r.json()),
          fetch('/api/secrets/status').then(r => r.json()),
        ]);
        setList(Array.isArray(lr?.items) ? lr.items : []);
        setUnlocked(Boolean(sr?.unlocked));
      } catch {
        setList([]);
      }
      // key_source 由父组件 QualitySettings 通过 initialKeySource 注入,
      // 避免本组件另起 /api/llm/status 调用破坏父级 open 门控。
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 父组件 key_source 更新 → 同步本地 state (ProviderPanel 切换后会重拉 /api/llm/status)
  useEffect(() => {
    setKeySource(initialKeySource);
  }, [initialKeySource]);

  const unlock = useCallback(async (mk: string) => {
    const r = await fetch('/api/secrets/unlock', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ master_key: mk }),
    });
    if (!r.ok) throw new Error('INVALID_MASTER_KEY');
    setUnlocked(true);
    await load();
  }, [load]);

  const lock = useCallback(async () => {
    await fetch('/api/secrets/lock', { method: 'POST' });
    setUnlocked(false);
  }, []);

  const reveal = useCallback(async (id: number, mk: string) => {
    const r = await fetch(`/api/secrets/${id}/reveal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ master_key: mk }),
    });
    if (!r.ok) throw new Error('REVEAL_FAILED');
    const d = await r.json();
    return d.api_key as string;
  }, []);

  const testConn = useCallback(async (id: number) => {
    const r = await fetch(`/api/secrets/${id}/test`, { method: 'POST' });
    return await r.json();
  }, []);

  const upsert = useCallback(async (body: Record<string, any>) => {
    const isUpd = Boolean(body.id);
    const url = isUpd ? `/api/secrets/${body.id}` : '/api/secrets';
    const r = await fetch(url, {
      method: isUpd ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error('UPSERT_FAILED');
    await load();
  }, [load]);

  const remove = useCallback(async (id: number) => {
    const r = await fetch(`/api/secrets/${id}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('DELETE_FAILED');
    await load();
  }, [load]);

  const keySourceChip = keySource === 'env' ? 'st-chip ok'
    : keySource === 'secrets' ? 'st-chip ok'
    : 'st-chip mute';

  return (
    <section className="st-section" aria-label="LLM 密钥管理" data-testid="secrets-panel">
      <h3>
        🔐 LLM 密钥管理 (加密保险箱)
        <span className={keySourceChip} title={`key_source: ${keySource}`}>
          <i aria-hidden />{keySource}
        </span>
      </h3>
      <p className="st-section-desc">
        密钥 Fernet 加密 (PBKDF2 600k 派生主密钥); reveal/test 写 audit_log;
        进程内 30min unlock 窗口, 过期需重新输入主密钥。
      </p>

      <div className="st-section-body">
        {!unlocked && (
          <div className="st-info warn">保险箱状态: 未解锁 — 点下方"解锁"按钮</div>
        )}
        {unlocked && (
          <div className="st-rule">
            <div>
              <p className="st-label">保险箱已解锁</p>
              <p className="st-key">session 30min auto-lock</p>
            </div>
            <div className="st-ctrl">
              <button type="button" className="st-btn ghost" onClick={lock} aria-label="立即锁定">
                立即锁定
              </button>
            </div>
          </div>
        )}

        {unlocked && list.length === 0 && !loading && (
          <p className="st-cellnote">暂无密钥 — 点下方"新增"录入第一条</p>
        )}

        {list.length > 0 && (
          <table className="st-table" aria-label="密钥列表">
            <thead>
              <tr>
                <th>名称</th>
                <th>Provider</th>
                <th>Model · Base URL</th>
                <th style={{ width: 200 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {list.map(s => (
                <tr key={s.id} data-testid={`secrets-row-${s.id}`}>
                  <td><span className="st-nm">{s.name || '(无名)'}</span></td>
                  <td>{s.provider || '(无)'}</td>
                  <td>
                    <span className="st-sub">{s.model}</span>
                    <span className="st-sub">{s.base_url}</span>
                  </td>
                  <td>
                    <div className="st-ctrlrow">
                      <button type="button" className="st-btn ghost" onClick={() => {
                        setMasterKeyInput('');
                        setMasterKeyPrompt({ target: 'reveal', secretId: s.id });
                      }} title="显明文 10s 自动隐藏">显明文</button>
                      <button type="button" className="st-btn ghost" onClick={async () => {
                        const r = await testConn(s.id);
                        setMsg({ type: r.ok ? 'ok' : 'error', text: r.ok ? '连接 OK' : (r.error || '失败') });
                      }}>测连</button>
                      <button type="button" className="st-btn ghost" onClick={() => setUpsertModal({
                        id: s.id, provider: s.provider || '', name: s.name || '',
                        model: s.model || '', base_url: s.base_url || '',
                        api_key: '', master_key: '',
                      })}>编辑</button>
                      <button type="button" className="st-btn danger" onClick={async () => {
                        if (!confirm(`删除密钥 "${s.name}"?`)) return;
                        await remove(s.id);
                      }}>删</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="st-actionbar">
          {msg && <span className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`}>{msg.text}</span>}
          <button
            type="button"
            className="st-btn primary"
            onClick={() => {
              if (!unlocked) {
                setMasterKeyInput('');
                setMasterKeyPrompt({ target: 'unlock' });
              } else {
                setUpsertModal({
                  provider: providerOptions[0] || 'sensenova',
                  name: '', model: '', base_url: '',
                  api_key: '', master_key: '',
                });
              }
            }}
            disabled={false}
            data-testid="secrets-add-btn"
          >
            {unlocked ? '+ 新增密钥' : '解锁保险箱'}
          </button>
        </div>
      </div>

      {/* 主密钥 prompt modal (unlock / reveal 共用) */}
      {masterKeyPrompt && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setMasterKeyPrompt(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="st-card"
            style={{ minWidth: 360, background: 'var(--sn-bg-panel)' }}
          >
            <h3>
              {masterKeyPrompt.target === 'unlock' ? '解锁保险箱' : '显明文需验证主密钥'}
            </h3>
            <input
              type="password" value={masterKeyInput}
              onChange={e => setMasterKeyInput(e.target.value)}
              placeholder="主密钥 (12+ 字符)"
              autoFocus
              className="st-input"
              data-testid="master-key-input"
            />
            <div className="st-actionbar">
              <button type="button" className="st-btn ghost" onClick={() => setMasterKeyPrompt(null)}>取消</button>
              <button
                type="button"
                className="st-btn primary"
                disabled={masterKeyInput.length < 12}
                onClick={async () => {
                  try {
                    if (masterKeyPrompt.target === 'unlock') {
                      await unlock(masterKeyInput);
                      setMsg({ type: 'ok', text: '保险箱已解锁' });
                    } else if (masterKeyPrompt.target === 'reveal' && masterKeyPrompt.secretId) {
                      const k = await reveal(masterKeyPrompt.secretId, masterKeyInput);
                      setRevealModal({ id: masterKeyPrompt.secretId, apiKey: k, ts: Date.now() });
                      setTimeout(() => setRevealModal(null), 10_000);
                    }
                    setMasterKeyPrompt(null);
                    setMasterKeyInput('');
                  } catch (e: any) {
                    setMsg({ type: 'error', text: `失败: ${e.message}` });
                  }
                }}
              >确认</button>
            </div>
          </div>
        </div>
      )}

      {/* reveal 明文 modal (10s 自动隐藏) */}
      {revealModal && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setRevealModal(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="st-card"
            style={{ minWidth: 360, background: 'var(--sn-bg-panel)' }}
          >
            <h3>明文密钥 (10s 自动隐藏)</h3>
            <code
              className="st-info"
              style={{ display: 'block', wordBreak: 'break-all', fontFamily: 'var(--sn-mono)' }}
              data-testid="reveal-key"
            >
              {revealModal.apiKey}
            </code>
            <div className="st-actionbar">
              <button
                type="button"
                className="st-btn primary"
                onClick={() => navigator.clipboard.writeText(revealModal.apiKey)}
              >复制</button>
            </div>
          </div>
        </div>
      )}

      {/* 新增/编辑密钥 modal */}
      {upsertModal && (
        <div
          style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          onClick={() => setUpsertModal(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="st-card"
            style={{ minWidth: 380, background: 'var(--sn-bg-panel)' }}
          >
            <h3>{upsertModal.id ? `编辑密钥 #${upsertModal.id}` : '新增密钥'}</h3>
            <div className="st-section-body">
              <label className="st-rule">
                <div><p className="st-label">Provider</p></div>
                <div className="st-ctrl">
                  <select
                    value={upsertModal.provider}
                    onChange={e => setUpsertModal({ ...upsertModal, provider: e.target.value })}
                    className="st-select"
                  >
                    {providerOptions.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </label>
              <label className="st-rule">
                <div><p className="st-label">名称</p></div>
                <div className="st-ctrl">
                  <input className="st-input" value={upsertModal.name}
                         onChange={e => setUpsertModal({ ...upsertModal, name: e.target.value })} />
                </div>
              </label>
              <label className="st-rule">
                <div><p className="st-label">Model</p></div>
                <div className="st-ctrl">
                  <input className="st-input" value={upsertModal.model}
                         onChange={e => setUpsertModal({ ...upsertModal, model: e.target.value })} />
                </div>
              </label>
              <label className="st-rule">
                <div><p className="st-label">Base URL</p></div>
                <div className="st-ctrl">
                  <input className="st-input" value={upsertModal.base_url}
                         onChange={e => setUpsertModal({ ...upsertModal, base_url: e.target.value })} />
                </div>
              </label>
              <label className="st-rule">
                <div>
                  <p className="st-label">API Key</p>
                  {upsertModal.id && <p className="st-key">(留空保留旧值)</p>}
                </div>
                <div className="st-ctrl">
                  <input type="password" className="st-input" value={upsertModal.api_key}
                         onChange={e => setUpsertModal({ ...upsertModal, api_key: e.target.value })} />
                </div>
              </label>
              <label className="st-rule">
                <div><p className="st-label">主密钥</p><p className="st-key">(验证身份)</p></div>
                <div className="st-ctrl">
                  <input type="password" className="st-input" value={upsertModal.master_key}
                         onChange={e => setUpsertModal({ ...upsertModal, master_key: e.target.value })}
                         data-testid="upsert-master-key" />
                </div>
              </label>
            </div>
            <div className="st-actionbar">
              <button type="button" className="st-btn ghost" onClick={() => setUpsertModal(null)}>取消</button>
              <button
                type="button"
                className="st-btn primary"
                disabled={
                  !upsertModal.name || !upsertModal.model || !upsertModal.base_url ||
                  (!upsertModal.id && !upsertModal.api_key) ||
                  upsertModal.master_key.length < 12
                }
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
                    await upsert(upsertModal.id ? { ...body, id: upsertModal.id } : body);
                    setMsg({ type: 'ok', text: upsertModal.id ? '已更新' : '已新增' });
                    setUpsertModal(null);
                  } catch (e: any) {
                    setMsg({ type: 'error', text: `失败: ${e.message}` });
                  }
                }}
              >保存</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default SecretsPanel;