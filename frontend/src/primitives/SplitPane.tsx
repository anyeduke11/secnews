/**
 * SplitPane — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 主从两栏, 辅助栏可折叠; 窄屏 (<=1080) 降级为单栏堆叠。
 * 断点取 §3 的 1080px (Tailwind 任意变体), 不引 JS 监听。
 */
import React from 'react';

export interface SplitPaneProps {
  main: React.ReactNode;
  aside: React.ReactNode;
  /** 辅助栏无障碍名称 (必填, 窄屏折叠后仍可被读屏识别) */
  asideLabel: string;
  asideWidth?: number;
  collapsed?: boolean;
  onToggleAside?: () => void;
  className?: string;
}

export function SplitPane({
  main,
  aside,
  asideLabel,
  asideWidth = 360,
  collapsed = false,
  onToggleAside,
  className = '',
}: SplitPaneProps) {
  return (
    <div
      className={`grid min-h-0 min-w-0 max-[1080px]:grid-cols-1 ${
        collapsed ? 'grid-cols-1' : 'grid-cols-[minmax(0,1fr)_var(--split-aside)]'
      } ${className}`}
      style={{ '--split-aside': `${asideWidth}px` } as React.CSSProperties}
    >
      <div className="min-w-0 min-h-0">{main}</div>

      {!collapsed && (
        <aside
          aria-label={asideLabel}
          className="min-w-0 min-h-0 border-l max-[1080px]:border-l-0 max-[1080px]:border-t"
          style={{ borderColor: 'var(--line)' }}
        >
          <div className="flex items-center justify-end px-2 py-1">
            {onToggleAside && (
              <button
                type="button"
                onClick={onToggleAside}
                aria-expanded={!collapsed}
                aria-label={`收起${asideLabel}`}
                className="focus-ring rounded-[3px] px-1.5 py-0.5 text-[11px]"
                style={{ color: 'var(--text-muted)' }}
              >
                收起
              </button>
            )}
          </div>
          {aside}
        </aside>
      )}

      {collapsed && onToggleAside && (
        <button
          type="button"
          onClick={onToggleAside}
          aria-expanded={false}
          aria-label={`展开${asideLabel}`}
          className="focus-ring m-2 self-start rounded-[3px] border px-2 py-1 text-[11px]"
          style={{ borderColor: 'var(--line)', color: 'var(--text-secondary)' }}
        >
          展开{asideLabel}
        </button>
      )}
    </div>
  );
}