/**
 * LayerCardStates — 从 layout/LayerCard.tsx 拆出的链接/空态/骨架态 (B6-a 纯搬迁, 无行为变更)。
 * 职责: ViewMoreLink / LayerEmptyState / LayerSkeleton。
 * 导出面仍由 ./LayerCard 按原名 re-export, 调用方无需改动。
 */
import React from 'react';

/**
 * ViewMoreLink — 统一的"查看详情/跳转"链接
 *
 * 消除各层页面重复的 inline 样式。
 */
export function ViewMoreLink({
  label = '查看详情 →',
  onClick,
}: {
  label?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="view-more-link"
    >
      {label}
    </button>
  );
}

/**
 * LayerEmptyState — 统一的空状态占位
 *
 * 在所有层页面中一致显示空状态，消除重复的 inline 样式。
 */
export function LayerEmptyState({
  message = '暂无数据',
  action,
  icon,
}: {
  message?: string;
  action?: { label: string; onClick: () => void };
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-2">
      {icon && (
        <div className="mb-1" style={{ color: 'var(--text-muted)' }}>
          {icon}
        </div>
      )}
      <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
        {message}
      </p>
      {action && (
        <ViewMoreLink label={action.label} onClick={action.onClick} />
      )}
    </div>
  );
}

/**
 * LayerSkeleton — 统一的骨架屏加载态
 *
 * 替代各层页面重复的 skeleton-block div。
 * variant: 'card' | 'row' | 'text'
 */
export function LayerSkeleton({
  variant = 'card',
  lines = 3,
}: {
  variant?: 'card' | 'row' | 'text';
  lines?: number;
}) {
  if (variant === 'row') {
    return (
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="skeleton-block h-4 w-full" style={{ width: `${70 + Math.random() * 30}%` }} />
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-6">
      <div className="skeleton-block w-3/4 h-4" />
    </div>
  );
}