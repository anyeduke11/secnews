/**
 * PageHeader — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4)
 *
 * 标题 + 面包屑 + 主操作 + 元信息行。§3 纪律: 不做巨幅标题/欢迎区,
 * 标题 18px, 元信息 11px 等宽。
 */
import React from 'react';

export interface PageHeaderBreadcrumb {
  label: string;
  href?: string;
}

export interface PageHeaderProps {
  title: React.ReactNode;
  breadcrumb?: PageHeaderBreadcrumb[];
  actions?: React.ReactNode;
  /** 元信息行: 时间/统计/状态等 */
  meta?: React.ReactNode;
  description?: React.ReactNode;
}

export function PageHeader({ title, breadcrumb, actions, meta, description }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav aria-label="面包屑" className="mb-1 flex items-center gap-1 text-[11px]">
            {breadcrumb.map((b, i) => (
              <React.Fragment key={`${b.label}-${i}`}>
                {i > 0 && (
                  <span aria-hidden="true" style={{ color: 'var(--text-muted)' }}>
                    /
                  </span>
                )}
                {b.href ? (
                  <a href={b.href} style={{ color: 'var(--text-secondary)' }}>
                    {b.label}
                  </a>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>{b.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
        )}

        <div className="flex items-center gap-2">
          <h1 className="truncate text-[18px] font-semibold leading-[1.3]" style={{ color: 'var(--text-primary)' }}>
            {title}
          </h1>
          {meta && (
            <span
              className="flex items-center gap-2 text-[11px]"
              style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}
            >
              {meta}
            </span>
          )}
        </div>

        {description && (
          <p className="mt-1 text-[12px] leading-[1.55]" style={{ color: 'var(--text-secondary)' }}>
            {description}
          </p>
        )}
      </div>

      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </header>
  );
}