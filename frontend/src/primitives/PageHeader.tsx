/**
 * PageHeader — L1 原子 (FRONTEND_REWRITE_V1_PLAN §4 / redesign-v1 R-2)
 *
 * 标题 + 面包屑 + 主操作 + 元信息行。§3 纪律: 不做巨幅标题/欢迎区。
 * 视觉直接复用仓库既有编辑部词汇 `.ed-head / .ed-h1 / .ed-sub`
 * (components/shared/editorial/pages.css), 不新造平行样式 (DESIGN.md §5 R-2)。
 */
import React from 'react';
// 编辑部词汇 (.ed-*) 由本原子自带, 与 6 个既有页面同款引入方式 (仓内约定)
import '../components/shared/editorial/pages.css';

export interface PageHeaderBreadcrumb {
  label: string;
  href?: string;
}

export interface PageHeaderProps {
  title: React.ReactNode;
  /** 眉标 (.ed-kicker): 全大写英文馆室名, 如 CATALOG ROOM */
  kicker?: string;
  breadcrumb?: PageHeaderBreadcrumb[];
  actions?: React.ReactNode;
  /** 元信息行: 时间/统计/状态等 */
  meta?: React.ReactNode;
  description?: React.ReactNode;
  /** 标题区尾注: 数据源印章 / 提示等 (渲染在描述之下) */
  footer?: React.ReactNode;
}

export function PageHeader({ title, kicker, breadcrumb, actions, meta, description, footer }: PageHeaderProps) {
  const hasTopRow = (breadcrumb && breadcrumb.length > 0) || meta != null;

  return (
    <header className="ed-head">
      {kicker && <span className="ed-kicker">{kicker}</span>}

      {hasTopRow && (
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 text-[11px]">
          {breadcrumb && breadcrumb.length > 0 ? (
            <nav aria-label="面包屑" className="flex items-center gap-1">
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
          ) : (
            <span />
          )}
          {meta != null && (
            <div className="num shrink-0" style={{ color: 'var(--text-muted)' }}>
              {meta}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <h1 className="ed-h1 min-w-0">{title}</h1>
        {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
      </div>

      {description != null && <p className="ed-sub">{description}</p>}
      {footer != null && <div style={{ marginTop: 10 }}>{footer}</div>}
    </header>
  );
}