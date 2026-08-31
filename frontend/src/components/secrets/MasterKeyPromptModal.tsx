/**
 * secrets/MasterKeyPromptModal — 主密钥单输入模态 (替换 window.prompt)。
 *
 * 用于: 导入 / 导出 / reveal 这三处仅需一次性输入主密钥的场景。
 * 与 UnlockModal 区别: 无 status 检查 / 无 session TTL 副作用, 纯返回 mk 字符串。
 */
import React, { useState } from 'react';
import { Icon } from '../Icon';
import { Modal } from './Modal';

export function MasterKeyPromptModal({
  title,
  hint,
  submitLabel,
  onSubmit,
  onClose,
}: {
  title: string;
  hint?: string;
  submitLabel?: string;
  onSubmit: (mk: string) => void;
  onClose: () => void;
}) {
  const [mk, setMk] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!mk) return;
    onSubmit(mk);
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Icon size={14}>
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
          </Icon>
          {title}
        </h3>
        {hint && (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {hint}
          </p>
        )}
        <input
          type="password"
          value={mk}
          onChange={e => setMk(e.target.value)}
          autoFocus
          autoComplete="new-password"
          placeholder="主密钥"
          className="tech-input px-2 py-1.5 text-xs font-mono w-full"
        />
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={!mk}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              backgroundColor: 'var(--text-primary)',
              color: 'var(--bg-primary)',
              borderColor: 'var(--text-primary)',
              opacity: !mk ? 0.6 : 1,
            }}
          >
            {submitLabel ?? '确定'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        </div>
      </form>
    </Modal>
  );
}
