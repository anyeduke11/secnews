/**
 * quality/SecretsPanel — LLM 密钥管理 (加密保险箱) — Batch ⑥
 *
 * 数据源: GET /api/secrets / /api/secrets/status / /api/llm/status (key_source)
 * 写入: POST/DELETE /api/secrets, PATCH /api/secrets/{id},
 *       POST /api/secrets/unlock /lock /{id}/reveal /{id}/test
 *
 * 设计: 沿用 settings-shell.css 的 st-section / st-table / st-chip / st-btn;
 *       key_source 徽章三档: env / secrets / none (灰);
 *       密钥表格见 SecretsPanelTable, 主密钥 prompt / reveal / upsert 三个 modal
 *       见 SecretsPanelKeyModals / SecretsPanelForm。
 */
import { useState, useCallback, useEffect } from 'react';
import {
  createSecret,
  deleteSecret,
  getSecrets,
  getSecretsStatus,
  lockSecrets,
  revealSecret,
  testSecret,
  unlockSecrets,
  updateSecret,
} from '../../../api/settings';
import { SecretsPanelTable } from './SecretsPanelTable';
import { SecretsPanelMasterKeyModal, SecretsPanelRevealModal } from './SecretsPanelKeyModals';
import { SecretsPanelForm } from './SecretsPanelForm';
import type { SecretsPanelKeyPrompt, SecretsPanelMsg, SecretsPanelUpsertState } from './SecretsPanel.types';

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
  const [msg, setMsg] = useState<SecretsPanelMsg | null>(null);
  const [keySource, setKeySource] = useState<string>(initialKeySource);
  const [revealModal, setRevealModal] = useState<{ id: number; apiKey: string; ts: number } | null>(null);
  const [upsertModal, setUpsertModal] = useState<SecretsPanelUpsertState | null>(null);
  const [masterKeyPrompt, setMasterKeyPrompt] = useState<SecretsPanelKeyPrompt | null>(null);
  const [masterKeyInput, setMasterKeyInput] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      try {
        // apiFetch 非 ok 抛错 → 置 null 跳过 (原实现为 json 解析失败走 catch)
        const [lr, sr] = await Promise.all([
          getSecrets<{ items?: Array<Record<string, any>> }>().catch(() => null),
          getSecretsStatus().catch(() => null),
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
    // apiFetch 非 ok 抛错 (message 为后端 detail / HTTP 状态; 原实现抛 INVALID_MASTER_KEY 字面量)
    await unlockSecrets(mk);
    setUnlocked(true);
    await load();
  }, [load]);

  const lock = useCallback(async () => {
    try {
      await lockSecrets();
    } catch {
      // 原实现对非 ok 响应静默继续
    }
    setUnlocked(false);
  }, []);

  const reveal = useCallback(async (id: number, mk: string) => {
    const d = await revealSecret(id, mk);
    return d.api_key;
  }, []);

  const testConn = useCallback(async (id: number) => {
    try {
      return await testSecret(id);
    } catch (e: any) {
      // 原 testConn 不看 r.ok, 消费方读 r.ok / r.error — 保持该契约
      return { ok: false, error: e?.message || '失败' };
    }
  }, []);

  const upsert = useCallback(async (body: Record<string, any>) => {
    const isUpd = Boolean(body.id);
    // apiFetch 非 ok 抛错 (message 为后端 detail; 原实现抛 UPSERT_FAILED 字面量)
    if (isUpd) {
      await updateSecret(body.id, body);
    } else {
      await createSecret(body);
    }
    await load();
  }, [load]);

  const remove = useCallback(async (id: number) => {
    // DELETE 204 时 apiFetch 返回 undefined; 非 ok 抛错 (原实现抛 DELETE_FAILED 字面量)
    await deleteSecret(id);
    await load();
  }, [load]);

  // 主密钥 prompt 确认 (unlock / reveal 共用)
  const confirmMasterKey = useCallback(async () => {
    if (!masterKeyPrompt) return;
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
  }, [masterKeyPrompt, masterKeyInput, unlock, reveal]);

  const saveUpsert = useCallback(async () => {
    if (!upsertModal) return;
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
  }, [upsertModal, upsert]);

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
          <SecretsPanelTable
            list={list}
            onReveal={id => {
              setMasterKeyInput('');
              setMasterKeyPrompt({ target: 'reveal', secretId: id });
            }}
            onTest={async id => {
              const r = await testConn(id);
              setMsg({ type: r.ok ? 'ok' : 'error', text: r.ok ? '连接 OK' : (r.error || '失败') });
            }}
            onEdit={s => setUpsertModal({
              id: s.id, provider: s.provider || '', name: s.name || '',
              model: s.model || '', base_url: s.base_url || '',
              api_key: '', master_key: '',
            })}
            onRemove={async s => {
              if (!confirm(`删除密钥 "${s.name}"?`)) return;
              await remove(s.id);
            }}
          />
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
        <SecretsPanelMasterKeyModal
          prompt={masterKeyPrompt}
          masterKeyInput={masterKeyInput}
          onInput={setMasterKeyInput}
          onClose={() => setMasterKeyPrompt(null)}
          onConfirm={confirmMasterKey}
        />
      )}

      {/* reveal 明文 modal (10s 自动隐藏) */}
      {revealModal && (
        <SecretsPanelRevealModal
          apiKey={revealModal.apiKey}
          onClose={() => setRevealModal(null)}
        />
      )}

      {/* 新增/编辑密钥 modal */}
      {upsertModal && (
        <SecretsPanelForm
          modal={upsertModal}
          providerOptions={providerOptions}
          onChange={setUpsertModal}
          onClose={() => setUpsertModal(null)}
          onSave={saveUpsert}
        />
      )}
    </section>
  );
}

export default SecretsPanel;