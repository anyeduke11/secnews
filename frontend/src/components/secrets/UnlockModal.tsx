/**
 * secrets/UnlockModal — 解锁主密钥模态。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 UnlockModal (~607-682 行)。
 * 纯结构拆分: 表单状态与校验逻辑逐字迁移。
 */
import React, { useState } from 'react';
import { Icon } from '../Icon';
import { Modal } from './Modal';

export function UnlockModal({
  onSubmit, onClose,
}: {
  onSubmit: (mk: string) => Promise<void>;
  onClose: () => void;
}) {
  const [mk, setMk] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (mk.length < 8) {
      setErr('主密钥至少 8 字符');
      return;
    }
    setBusy(true);
    try {
      await onSubmit(mk);
    } catch (e: any) {
      setErr(e?.message || '解锁失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Icon size={14}>
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
          </Icon>
          解锁密钥
        </h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          输入主密钥, 解锁 30 分钟。期间可一键复制明文 API key, 过期自动锁定。
        </p>
        {err && (
          <p className="text-xs px-2 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 9%, transparent)', color: 'var(--color-error)' }}>
            {err}
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
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              backgroundColor: 'var(--text-primary)',
              color: 'var(--bg-primary)',
              borderColor: 'var(--text-primary)',
              opacity: busy ? 0.6 : 1,
              cursor: busy ? 'wait' : 'pointer',
            }}
          >
            {busy ? '验证中…' : '解锁'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        </div>
      </form>
    </Modal>
  );
}
