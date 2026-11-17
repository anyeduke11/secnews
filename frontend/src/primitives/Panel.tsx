/**
 * Panel — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 带标题 / 操作区 / 空态插槽的容器。替代各页面自拼卡片。
 * §3 纪律: hairline 分区, 不用阴影分层; 不嵌套卡片。
 */
import React from 'react';

export interface PanelProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** 标题右侧操作区 */
  actions?: React.ReactNode;
  /** 无 children 时展示的空态插槽 */
  empty?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  /** 紧凑模式: 内容区零内边距 (表格/列表用自己的内边距) */
  dense?: boolean;
  className?: string;
  id?: string;
}

export function Panel({
  title,
  description,
  actions,
  empty,
  children,
  footer,
  dense = false,
  className = '',
  id,
}: PanelProps) {
  const hasBody = children !== undefined && children !== null && children !== false;
  const showEmpty = !hasBody && empty !== undefined;

  return (
    <section
      id={id}
      className={`flex min-w-0 flex-col rounded-[5px] border ${className}`}
      style={{ borderColor: 'var(--line)', backgroundColor: 'var(--bg-card)' }}
    >
      {(title || actions) && (
        <header
          className="flex items-center justify-between gap-3 border-b px-3 py-2"
          style={{ borderColor: 'var(--line)' }}
        >
          <div className="min-w-0">
            {title && (
              <h2 className="truncate text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-0.5 text-[11px] leading-[1.45]" style={{ color: 'var(--text-muted)' }}>
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}

      <div className={dense ? 'min-w-0 flex-1' : 'min-w-0 flex-1 p-3'}>
        {hasBody ? children : showEmpty ? empty : null}
      </div>

      {footer && (
        <footer
          className="border-t px-3 py-1.5 text-[11px]"
          style={{ borderColor: 'var(--line)', color: 'var(--text-muted)' }}
        >
          {footer}
        </footer>
      )}
    </section>
  );
}