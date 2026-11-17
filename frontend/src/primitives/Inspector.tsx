/**
 * Inspector — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 右侧详情抽屉。Esc 关闭, 关闭按钮常驻, 不锁焦点 (单机工具型交互)。
 */
import React from 'react';

export interface InspectorProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
  /** 抽屉内容区无障碍名称, 默认取 title */
  label?: string;
}

export function Inspector({ open, onClose, title, children, footer, width = 420, label }: InspectorProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-label={label ?? (typeof title === 'string' ? title : '详情')}
      className="fixed right-0 top-0 z-[var(--z-overlay)] flex h-full flex-col border-l"
      style={{
        width,
        maxWidth: '100vw',
        borderColor: 'var(--line)',
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-modal)',
      }}
    >
      <header
        className="flex items-center justify-between gap-3 border-b px-3 py-2"
        style={{ borderColor: 'var(--line)' }}
      >
        <h2 className="truncate text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="focus-ring shrink-0 rounded-[3px] px-1.5 py-0.5 text-[11px]"
          style={{ color: 'var(--text-muted)' }}
        >
          关闭
        </button>
      </header>

      <div className="min-w-0 flex-1 overflow-auto p-3">{children}</div>

      {footer && (
        <footer
          className="flex items-center justify-end gap-1.5 border-t px-3 py-2"
          style={{ borderColor: 'var(--line)' }}
        >
          {footer}
        </footer>
      )}
    </aside>
  );
}