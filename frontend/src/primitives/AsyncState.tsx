/**
 * AsyncState — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 统一 loading 骨架 / empty / error / stale 四态, 替换 54 处手写三态。
 * 状态文案固定, 不接收业务词条 (业务方传 emptyTitle/errorMessage)。
 */
import React from 'react';

export type AsyncStatus = 'loading' | 'empty' | 'error' | 'ready';

export interface AsyncStateProps {
  status: AsyncStatus;
  children?: React.ReactNode;
  /** ready 但数据已过期: 顶部提示条 */
  stale?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  skeletonRows?: number;
  className?: string;
}

export function AsyncState({
  status,
  children,
  stale = false,
  errorMessage = '请求失败',
  onRetry,
  emptyTitle = '暂无数据',
  emptyDescription,
  skeletonRows = 3,
  className = '',
}: AsyncStateProps) {
  if (status === 'loading') {
    return (
      <div role="status" aria-busy="true" aria-live="polite" className={`flex flex-col gap-1.5 py-2 ${className}`}>
        <span className="sr-only">加载中</span>
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <div
            key={i}
            aria-hidden="true"
            className="h-7 rounded-[3px]"
            style={{ backgroundColor: 'var(--bg-hover)', opacity: 0.7 - i * 0.12 }}
          />
        ))}
      </div>
    );
  }

  if (status === 'empty') {
    return (
      <div role="status" className={`flex flex-col items-center gap-1 py-8 text-center ${className}`}>
        <p className="text-[13px]" style={{ color: 'var(--text-secondary)' }}>
          {emptyTitle}
        </p>
        {emptyDescription && (
          <p className="max-w-md text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {emptyDescription}
          </p>
        )}
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div role="alert" className={`flex flex-col items-center gap-2 py-8 text-center ${className}`}>
        <p className="text-[13px]" style={{ color: 'var(--red)' }}>
          {errorMessage}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="focus-ring rounded-[3px] border px-2 py-1 text-[11px]"
            style={{ borderColor: 'var(--line)', color: 'var(--text-primary)' }}
          >
            重试
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={className}>
      {stale && (
        <p
          role="status"
          className="mb-2 rounded-[3px] border px-2 py-1 text-[11px]"
          style={{
            borderColor: 'var(--line)',
            color: 'var(--amber)',
            backgroundColor: 'var(--bg-card)',
          }}
        >
          数据已过期, 正在刷新
        </p>
      )}
      {children}
    </div>
  );
}