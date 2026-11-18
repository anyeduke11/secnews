/**
 * quality/SecretsPanelForm — 新增/编辑密钥 modal (拆分自 SecretsPanel.tsx)
 *
 * 纯渲染: 表单状态由 SecretsPanel 持有, 本组件只负责字段编排与回写。
 */
import type { SecretsPanelUpsertState } from './SecretsPanel.types';

interface SecretsPanelFormProps {
  modal: SecretsPanelUpsertState;
  providerOptions: string[];
  onChange: (next: SecretsPanelUpsertState) => void;
  onClose: () => void;
  onSave: () => void;
}

export function SecretsPanelForm({ modal, providerOptions, onChange, onClose, onSave }: SecretsPanelFormProps) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        onClick={e => e.stopPropagation()}
        className="st-card"
        style={{ minWidth: 380, background: 'var(--sn-bg-panel)' }}
      >
        <h3>{modal.id ? `编辑密钥 #${modal.id}` : '新增密钥'}</h3>
        <div className="st-section-body">
          <label className="st-rule">
            <div><p className="st-label">Provider</p></div>
            <div className="st-ctrl">
              <select
                value={modal.provider}
                onChange={e => onChange({ ...modal, provider: e.target.value })}
                className="st-select"
              >
                {providerOptions.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </label>
          <label className="st-rule">
            <div><p className="st-label">名称</p></div>
            <div className="st-ctrl">
              <input className="st-input" value={modal.name}
                     onChange={e => onChange({ ...modal, name: e.target.value })} />
            </div>
          </label>
          <label className="st-rule">
            <div><p className="st-label">Model</p></div>
            <div className="st-ctrl">
              <input className="st-input" value={modal.model}
                     onChange={e => onChange({ ...modal, model: e.target.value })} />
            </div>
          </label>
          <label className="st-rule">
            <div><p className="st-label">Base URL</p></div>
            <div className="st-ctrl">
              <input className="st-input" value={modal.base_url}
                     onChange={e => onChange({ ...modal, base_url: e.target.value })} />
            </div>
          </label>
          <label className="st-rule">
            <div>
              <p className="st-label">API Key</p>
              {modal.id && <p className="st-key">(留空保留旧值)</p>}
            </div>
            <div className="st-ctrl">
              <input type="password" className="st-input" value={modal.api_key}
                     onChange={e => onChange({ ...modal, api_key: e.target.value })} />
            </div>
          </label>
          <label className="st-rule">
            <div><p className="st-label">主密钥</p><p className="st-key">(验证身份)</p></div>
            <div className="st-ctrl">
              <input type="password" className="st-input" value={modal.master_key}
                     onChange={e => onChange({ ...modal, master_key: e.target.value })}
                     data-testid="upsert-master-key" />
            </div>
          </label>
        </div>
        <div className="st-actionbar">
          <button type="button" className="st-btn ghost" onClick={onClose}>取消</button>
          <button
            type="button"
            className="st-btn primary"
            disabled={
              !modal.name || !modal.model || !modal.base_url ||
              (!modal.id && !modal.api_key) ||
              modal.master_key.length < 12
            }
            onClick={onSave}
          >保存</button>
        </div>
      </div>
    </div>
  );
}