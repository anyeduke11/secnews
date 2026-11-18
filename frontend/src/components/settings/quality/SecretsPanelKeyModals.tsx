/**
 * quality/SecretsPanelKeyModals — 主密钥 prompt / 明文 reveal 两个 modal (拆分自 SecretsPanel.tsx)
 *
 * 纯渲染: 可见性由 SecretsPanel 的条件渲染控制, 本组件不持有状态。
 */
import type { SecretsPanelKeyPrompt } from './SecretsPanel.types';

interface SecretsPanelMasterKeyModalProps {
  prompt: SecretsPanelKeyPrompt;
  masterKeyInput: string;
  onInput: (v: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export function SecretsPanelMasterKeyModal({
  prompt, masterKeyInput, onInput, onClose, onConfirm,
}: SecretsPanelMasterKeyModalProps) {
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
        style={{ minWidth: 360, background: 'var(--sn-bg-panel)' }}
      >
        <h3>
          {prompt.target === 'unlock' ? '解锁保险箱' : '显明文需验证主密钥'}
        </h3>
        <input
          type="password" value={masterKeyInput}
          onChange={e => onInput(e.target.value)}
          placeholder="主密钥 (12+ 字符)"
          autoFocus
          className="st-input"
          data-testid="master-key-input"
        />
        <div className="st-actionbar">
          <button type="button" className="st-btn ghost" onClick={onClose}>取消</button>
          <button
            type="button"
            className="st-btn primary"
            disabled={masterKeyInput.length < 12}
            onClick={onConfirm}
          >确认</button>
        </div>
      </div>
    </div>
  );
}

interface SecretsPanelRevealModalProps {
  apiKey: string;
  onClose: () => void;
}

export function SecretsPanelRevealModal({ apiKey, onClose }: SecretsPanelRevealModalProps) {
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
        style={{ minWidth: 360, background: 'var(--sn-bg-panel)' }}
      >
        <h3>明文密钥 (10s 自动隐藏)</h3>
        <code
          className="st-info"
          style={{ display: 'block', wordBreak: 'break-all', fontFamily: 'var(--sn-mono)' }}
          data-testid="reveal-key"
        >
          {apiKey}
        </code>
        <div className="st-actionbar">
          <button
            type="button"
            className="st-btn primary"
            onClick={() => navigator.clipboard.writeText(apiKey)}
          >复制</button>
        </div>
      </div>
    </div>
  );
}