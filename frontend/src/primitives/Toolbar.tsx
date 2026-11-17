/**
 * Toolbar — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 筛选/搜索/视图切换的等距栏。§3 密度: 工具栏高 40px, 间距 8px。
 */
import React from 'react';

export interface ToolbarProps {
  children?: React.ReactNode;
  /** 右对齐区 (视图切换/次要操作) */
  trailing?: React.ReactNode;
  /** 吸顶 (长列表页) */
  sticky?: boolean;
  'aria-label'?: string;
  className?: string;
}

export function Toolbar({ children, trailing, sticky = false, className = '', ...rest }: ToolbarProps) {
  return (
    <div
      role="toolbar"
      aria-label={rest['aria-label'] ?? '工具栏'}
      className={`flex min-w-0 flex-wrap items-center gap-2 border-b px-2 py-1 ${sticky ? 'sticky top-0' : ''} ${className}`}
      style={{
        height: 40,
        borderColor: 'var(--line)',
        backgroundColor: 'var(--bg-card)',
        zIndex: sticky ? 'var(--z-sticky)' : undefined,
      }}
    >
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{children}</div>
      {trailing && <div className="flex shrink-0 items-center gap-1.5">{trailing}</div>}
    </div>
  );
}