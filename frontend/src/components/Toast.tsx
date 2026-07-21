/**
 * Toast — Phase 1A 设计系统原子
 *
 * 全局轻量通知。自动消失，可配置类型/时长。
 *
 * Usage:
 *   import { useToast } from './hooks/useToast';
 *   const toast = useToast();
 *   toast.show({ type: 'success', message: '已保存' });
 *   toast.show({ type: 'error', message: '保存失败', action: { label: '重试', onClick: retry } });
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Icon } from './Icon';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  /** 自动消失 ms，默认 4000 */
  duration?: number;
  /** 行动按钮（可选） */
  action?: { label: string; onClick: () => void };
}

interface ToastContextValue {
  show: (item: Omit<ToastItem, 'id'>) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // 兜底：在没有 Provider 时不抛错，避免阻塞
    // eslint-disable-next-line no-console
    console.warn('[useToast] outside ToastProvider, no-op');
    return {
      show: () => '',
      dismiss: () => {},
      clear: () => {},
    };
  }
  return ctx;
}

const TYPE_COLOR: Record<ToastType, string> = {
  success: 'var(--color-success)',
  error:   'var(--color-error)',
  warning: 'var(--color-warning)',
  info:    'var(--color-info)',
};

const TYPE_ICON: Record<ToastType, React.ReactNode> = {
  success: <Icon size={14}><polyline points="20 6 9 17 4 12" /></Icon>,
  error:   <Icon size={14}><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></Icon>,
  warning: <Icon size={14}><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></Icon>,
  info:    <Icon size={14}><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></Icon>,
};

interface ToastProviderProps {
  children: React.ReactNode;
  /** 同时显示上限，默认 5 */
  max?: number;
}

export function ToastProvider({ children, max = 5 }: ToastProviderProps) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems(prev => prev.filter(t => t.id !== id));
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (item: Omit<ToastItem, 'id'>): string => {
      const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const fullItem: ToastItem = { id, duration: 4000, ...item };
      setItems(prev => {
        const next = [...prev, fullItem];
        return next.length > max ? next.slice(next.length - max) : next;
      });
      if (fullItem.duration && fullItem.duration > 0) {
        const t = setTimeout(() => dismiss(id), fullItem.duration);
        timers.current.set(id, t);
      }
      return id;
    },
    [dismiss, max]
  );

  const clear = useCallback(() => {
    timers.current.forEach(t => clearTimeout(t));
    timers.current.clear();
    setItems([]);
  }, []);

  useEffect(() => {
    return () => {
      timers.current.forEach(t => clearTimeout(t));
      timers.current.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ show, dismiss, clear }}>
      {children}
      <div
        className="fixed bottom-4 right-4 flex flex-col gap-2 pointer-events-none"
        style={{ zIndex: 'var(--z-toast)' }}
        aria-live="polite"
        aria-atomic="false"
      >
        {items.map(t => (
          <ToastCard key={t.id} item={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const color = TYPE_COLOR[item.type];
  const icon = TYPE_ICON[item.type];
  return (
    <div
      className="card-base animate-slide-up pointer-events-auto flex items-start gap-2.5 min-w-[260px] max-w-[400px] px-3 py-2.5"
      style={{ borderLeft: `3px solid ${color}` }}
      role="status"
    >
      <span className="mt-0.5 shrink-0" style={{ color }}>{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs leading-relaxed" style={{ color: 'var(--text-primary)' }}>
          {item.message}
        </p>
        {item.action && (
          <button
            onClick={() => {
              item.action!.onClick();
              onDismiss();
            }}
            className="text-[10px] mt-1 underline focus-ring"
            style={{ color }}
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="shrink-0 opacity-50 hover:opacity-100 focus-ring rounded-sm p-0.5"
        style={{ color: 'var(--text-muted)' }}
        aria-label="关闭"
      >
        <Icon size={12}>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </Icon>
      </button>
    </div>
  );
}
