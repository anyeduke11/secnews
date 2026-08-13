/**
 * secrets/SetupModal — 首次设置主密钥模态。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 SetupModal (~684-774 行)。
 * 纯结构拆分: 表单状态与校验逻辑逐字迁移。
 */
import React, { useState } from 'react';
import { Icon } from '../Icon';
import { Modal } from './Modal';

export function SetupModal({
  onSubmit, onClose,
}: {
  onSubmit: (mk: string) => Promise<void>;
  onClose: () => void;
}) {
  const [mk, setMk] = useState('');
  const [mk2, setMk2] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (mk.length < 8) {
      setErr('主密钥至少 8 字符');
      return;
    }
    if (mk !== mk2) {
      setErr('两次输入不一致');
      return;
    }
    setBusy(true);
    try {
      await onSubmit(mk);
    } catch (e: any) {
      setErr(e?.message || '设置失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
          <Icon size={14}>
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </Icon>
          首次设置主密钥
        </h3>
        <p className="text-xs" style={{ color: 'var(--color-error)' }}>
          ⚠️ <b>主密钥不存数据库, 一旦丢失, 该主密钥下所有 secret 永久不可解密, 且禁止重置</b>。
          请使用密码管理器保存或选一段你能记住的强密码。
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
          placeholder="主密钥 (>= 8 字符)"
          className="tech-input px-2 py-1.5 text-xs font-mono w-full"
        />
        <input
          type="password"
          value={mk2}
          onChange={e => setMk2(e.target.value)}
          autoComplete="new-password"
          placeholder="再次输入主密钥"
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
            {busy ? '设置中…' : '确认设置'}
          </button>
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">
            取消
          </button>
        </div>
      </form>
    </Modal>
  );
}
