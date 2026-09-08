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
  /**
   * v1.0.1 一致性重构: 装饰环模式 (附件同款仪式感).
   * 启用后顶部显示 56px dashed circle (用 CSS 变量 token + border-color,
   * 不写死颜色), 用于大块空态 (工作台首页 / 看板首页) 给用户"非错误,是空数据"
   * 的视觉缓冲; 紧凑模式与空态都不强制, 默认 false (零回归).
   */
  decorative?: boolean;
}

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  icon,
  compact = false,
  decorative = false,
}: EmptyStateProps) {
  return (
    <div
      className={
        compact
          ? 'flex flex-col items-center justify-center gap-2 py-6 text-center'
          : 'flex flex-col items-center justify-center gap-3 py-12 px-4 text-center animate-fade-in rounded-[var(--radius-md)]'
      }
      style={
        compact
          ? { color: 'var(--text-muted)' }
          : {
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-card)',
              border: '1px dashed var(--border-color)',
            }
      }
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
      {decorative && !compact && (
        <div
          aria-hidden="true"
          className="empty-ring"
          style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            border: '1.5px dashed var(--mint)',
            marginBottom: 4,
          }}
        />
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
