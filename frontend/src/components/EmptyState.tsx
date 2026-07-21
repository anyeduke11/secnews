/**
 * EmptyState — Phase 1A 设计系统原子
 *
 * 统一"空数据"占位展示。所有列表/详情页缺数据时使用。
 *
 * Usage:
 *   <EmptyState
 *     title="暂无热点"
 *     description="5 分钟自动刷新，可手动触发采集"
 *     actionLabel="立即刷新"
 *     onAction={refresh}
 *     icon={<Icon><path d="..." /></Icon>}
 *   />
 */
import React from 'react';

export interface EmptyStateProps {
  /** 主标题，必填 */
  title: string;
  /** 描述文字，可选 */
  description?: string;
  /** CTA 按钮标签 */
  actionLabel?: string;
  /** CTA 点击 */
  onAction?: () => void;
  /** 顶部图标 (24x24 viewBox) */
  icon?: React.ReactNode;
  /** 紧凑模式（用于卡片/抽屉） */
  compact?: boolean;
}

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  icon,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={
        compact
          ? 'flex flex-col items-center justify-center gap-2 py-6 text-center'
          : 'flex flex-col items-center justify-center gap-3 py-12 px-4 text-center animate-fade-in'
      }
      style={{ color: 'var(--text-muted)' }}
      role="status"
      aria-live="polite"
    >
      {icon && (
        <div
          className={compact ? 'opacity-50' : 'opacity-60 mb-1'}
          style={{ color: 'var(--text-secondary)' }}
        >
          {icon}
        </div>
      )}
      <p
        className={compact ? 'text-xs' : 'text-sm font-medium'}
        style={{ color: 'var(--text-secondary)' }}
      >
        {title}
      </p>
      {description && !compact && (
        <p className="text-xs max-w-md" style={{ color: 'var(--text-muted)' }}>
          {description}
        </p>
      )}
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="btn-ghost focus-ring text-xs px-3 py-1.5 mt-1"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
