/**
 * secrets/StatusBar — 密钥解锁状态条 (未初始化 / 已锁定 / 已解锁)。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 StatusBar (~278-367 行) + formatRemaining。
 * 纯结构拆分, 渲染逻辑逐字迁移。
 */
import { useSecrets } from '../../hooks/useSecrets';

function formatRemaining(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function StatusBar({
  status, remaining, onSetupClick, onUnlockClick, onLockClick,
}: {
  status: ReturnType<typeof useSecrets>['status'];
  remaining: number;
  onSetupClick: () => void;
  onUnlockClick: () => void;
  onLockClick: () => void;
}) {
  if (!status) {
    return (
      <div className="rounded-[var(--radius-md)] p-3 mb-3 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
        状态加载中…
      </div>
    );
  }

  if (!status.setup) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
        style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-error) 40%, transparent)' }}
      >
        <div>
          <p style={{ color: 'var(--text-primary)' }}>🔒 主密钥未初始化</p>
          <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
            请先设置主密钥 (master key, &gt;= 12 字符)。<b>主密钥不存数据库</b>, 丢失后该密钥下所有 secret 永久不可解密。
          </p>
        </div>
        <button
          onClick={onSetupClick}
          className="btn-ghost px-3 py-1.5 text-xs shrink-0"
          style={{ backgroundColor: 'var(--color-ai)', color: 'var(--text-on-light)', borderColor: 'var(--color-ai)' }}
        >
          首次设置主密钥
        </button>
      </div>
    );
  }

  if (!status.unlocked) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
        style={{ backgroundColor: 'color-mix(in srgb, var(--color-warning) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-warning) 40%, transparent)' }}
      >
        <div>
          <p style={{ color: 'var(--text-primary)' }}>🔒 已锁定</p>
          <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
            输入主密钥可解锁 30 分钟, 期间可一键复制明文 API key。
            {status.keychain_persisted && (
              <span style={{ color: 'var(--color-success)' }}> · 密钥已持久化, 重启后自动恢复</span>
            )}
          </p>
        </div>
        <button
          onClick={onUnlockClick}
          className="btn-ghost px-3 py-1.5 text-xs shrink-0"
          style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
        >
          🔑 解锁
        </button>
      </div>
    );
  }

  return (
    <div
      className="rounded-[var(--radius-md)] p-3 mb-3 text-xs flex items-center justify-between gap-2"
      style={{ backgroundColor: 'color-mix(in srgb, var(--color-success) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--color-success) 40%, transparent)' }}
    >
      <div>
        <p style={{ color: 'var(--text-primary)' }}>
          🔓 已解锁 <span className="font-mono tabular-nums" style={{ color: 'var(--color-ai)' }}>{formatRemaining(remaining)}</span>
          <span style={{ color: 'var(--text-muted)' }}> 后过期</span>
        </p>
        <p style={{ color: 'var(--text-muted)', marginTop: 2 }}>
          到期后清空内存中的明文, 重新输入主密钥可继续使用。
        </p>
      </div>
      <button
        onClick={onLockClick}
        className="btn-ghost px-3 py-1.5 text-xs shrink-0"
        style={{ color: 'var(--color-error)', borderColor: 'var(--color-error)' }}
      >
        立即锁定
      </button>
    </div>
  );
}
