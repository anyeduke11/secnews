/**
 * LayerCard — 三层架构统一卡片容器 (v2)
 *
 * Phase 5: 设计治理
 * 提供变体样式（default / compact / highlight / ghost / pipeline），
 * 一致的间距、标题区域和操作按钮位置。
 * 消除各层页面重复的 {bg-elevated, border, radius} 内联样式。
 */
import React from 'react';

type CardVariant = 'default' | 'compact' | 'highlight' | 'ghost' | 'pipeline';

type TitleStyle = 'eyebrow' | 'plain' | 'none';

interface LayerCardProps {
  /** 卡片标题 */
  title?: string;
  /** 标题样式: eyebrow (大写 tracking) | plain (正常) | none (不显示标题头) */
  titleStyle?: TitleStyle;
  /** 标题右侧的标签/元信息 */
  badge?: React.ReactNode;
  /** 右上角操作按钮 */
  actions?: React.ReactNode;
  /** 卡片主体内容 */
  children: React.ReactNode;
  /** 额外的容器类名 */
  className?: string;
  /** 点击卡片跳转（整卡可点击） */
  onClick?: () => void;
  /** 底部操作区 */
  footer?: React.ReactNode;
  /** 卡片变体 */
  variant?: CardVariant;
  /** 层色 — 用于 pipeline 和 highlight 变体的着色 */
  layerColor?: string;
}

const CARD_VARIANTS: Record<CardVariant, {
  bg: string;
  border: string;
  hoverBg: string;
  hoverBorder: string;
  padding: string;
}> = {
  default: {
    bg: 'var(--bg-elevated)',
    border: '1px solid var(--border-color)',
    hoverBg: 'var(--bg-hover)',
    hoverBorder: '1px solid var(--border-color)',
    padding: 'p-4',
  },
  compact: {
    bg: 'var(--bg-elevated)',
    border: '1px solid var(--border-color)',
    hoverBg: 'var(--bg-hover)',
    hoverBorder: '1px solid var(--border-color)',
    padding: 'p-3',
  },
  highlight: {
    bg: 'var(--accent-highlight)',
    border: '1px solid var(--accent-glow)',
    hoverBg: 'color-mix(in srgb, var(--accent-soft) 50%, var(--bg-elevated))',
    hoverBorder: '1px solid var(--accent-dim)',
    padding: 'p-4',
  },
  ghost: {
    bg: 'transparent',
    border: 'none',
    hoverBg: 'var(--bg-hover)',
    hoverBorder: 'none',
    padding: 'p-0',
  },
  pipeline: {
    bg: 'var(--bg-elevated)',
    border: '1px solid var(--border-color)',
    hoverBg: 'var(--bg-hover)',
    hoverBorder: '1px solid var(--border-color)',
    padding: 'p-3',
  },
};

export function LayerCard({
  title, titleStyle, badge, actions, children, className = '', onClick, footer,
  variant = 'default', layerColor,
}: LayerCardProps) {
  const Container = onClick ? 'button' : 'div';
  const styles = CARD_VARIANTS[variant];

  // 判断是否显示左边界线 accent
  const showAccent = variant === 'highlight' || variant === 'pipeline';

  return (
    <Container
      onClick={onClick}
      className={`layer-card rounded-[var(--radius-md)] ${styles.padding} transition-all duration-[var(--duration-normal)] ${
        onClick ? 'text-left w-full focus-ring cursor-pointer' : ''
      } ${showAccent && layerColor ? 'layer-accent-visible' : ''} ${className}`}
      style={{
        backgroundColor: styles.bg,
        border: styles.border,
        ...(styles.hoverBorder !== styles.border ? {
          '--hover-bg': styles.hoverBg,
          '--hover-border': styles.hoverBorder.replace('1px solid ', ''),
        } : {}),
        ...(layerColor ? { '--layer-color': layerColor } as React.CSSProperties : {}),
        ...(showAccent && layerColor ? { '--layer-accent': layerColor } as React.CSSProperties : {}),
      }}
    >
      {(title || badge || actions) && titleStyle !== 'none' && (
        <div className={`flex items-center justify-between ${
          variant === 'compact' || variant === 'pipeline' ? 'mb-2' : 'mb-3'
        }`}>
          {title && (
            <h3 className={titleStyle === 'plain' ? 'text-xs font-semibold' : 'text-xs font-bold tracking-[0.12em] uppercase'} style={{ color: 'var(--text-primary)' }}>
              {title}
            </h3>
          )}
          {badge && (
            <span className="text-[10px] font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
              {badge}
            </span>
          )}
          {actions && (
            <div className="ml-auto flex items-center gap-2">{actions}</div>
          )}
        </div>
      )}
      {children}
      {footer && (
        <div className="mt-2.5 flex items-center gap-2">{footer}</div>
      )}
    </Container>
  );
}

/**
 * LayerCardRow — 卡片内的行项目（统一 hover 状态）
 */
export function LayerCardRow({
  label, value, onClick, color, children,
}: {
  label?: string;
  value?: string | number;
  onClick?: () => void;
  color?: string;
  children?: React.ReactNode;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] transition-colors ${
        onClick ? 'w-full text-left focus-ring hover:bg-[var(--bg-hover)]' : ''
      }`}
      style={{ border: '1px solid var(--border-color)' }}
    >
      {color && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />}
      {label && (
        <span className="text-[11px] flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
      )}
      {children}
      {value !== undefined && (
        <span className="text-[11px] font-mono font-bold tabular-nums" style={{ color: color || 'var(--text-primary)' }}>
          {value}
        </span>
      )}
    </Tag>
  );
}

/**
 * LayerCardGrid — 卡片内的按钮网格
 */
export function LayerCardGrid({
  items,
}: {
  items: { key: string; label: string; desc?: string; onClick: () => void }[];
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map(item => (
        <button
          key={item.key}
          onClick={item.onClick}
          className="text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)] focus-ring"
          style={{ border: '1px solid var(--border-color)' }}
        >
          <div className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
            {item.label}
          </div>
          {item.desc && (
            <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {item.desc}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}

/**
 * LayerCardAlert — 卡片内的告警横幅（高亮背景）
 */
export function LayerCardAlert({
  label, value, color, children,
}: {
  label: string;
  value: string | number;
  color: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-sm)]"
      style={{ backgroundColor: `color-mix(in srgb, ${color} 8%, transparent)` }}
    >
      <span className="text-[10px] font-bold" style={{ color }}>{label}</span>
      <span className="text-[11px] font-mono font-bold" style={{ color }}>{value}</span>
      {children}
    </div>
  );
}

/**
 * PipelineFlow — 管线流转视觉组件 (v3)
 *
 * 在跨层流转卡片中显示 data → judge → action 之间的流动状态。
 * v3 改进:
 * - 箭头使用下一层色，视觉上连贯
 * - 箭头加粗，使用层色渐变
 * - 当前层使用更醒目的边框和背景
 * - 非活跃层保持视觉连续
 */
export function PipelineFlow({
  steps,
}: {
  steps: {
    key: string;
    label: string;
    count: number;
    color: string;
    active?: boolean;
  }[];
}) {
  return (
    <div className="flex items-center gap-1">
      {steps.map((step, i) => {
        const isActive = step.active;
        const isLast = i === steps.length - 1;
        /* 箭头使用下一层色，让视觉流向更连贯 */
        const arrowColor = i < steps.length - 1 ? steps[i + 1].color : step.color;
        return (
          <React.Fragment key={step.key}>
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 transition-all"
              style={{
                backgroundColor: isActive
                  ? `color-mix(in srgb, ${step.color} 10%, transparent)`
                  : 'color-mix(in srgb, var(--bg-hover) 40%, transparent)',
                border: isActive
                  ? `1px solid color-mix(in srgb, ${step.color} 30%, transparent)`
                  : '1px solid transparent',
                borderRadius: 'var(--radius-sm)',
                opacity: 1,
              }}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  backgroundColor: step.color,
                  boxShadow: isActive ? `0 0 0 2px color-mix(in srgb, ${step.color} 25%, transparent)` : 'none',
                }}
              />
              <span className="text-[11px] font-mono font-semibold" style={{ color: isActive ? step.color : 'var(--text-secondary)' }}>
                {step.label}
              </span>
              {step.count > 0 && (
                <span className="text-[11px] font-mono tabular-nums font-bold" style={{ color: step.color }}>
                  {step.count}
                </span>
              )}
            </div>
            {!isLast && (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true" className="shrink-0 mx-1">
                <path
                  d="M7.5 5l5 5-5 5"
                  stroke={arrowColor}
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity="0.6"
                />
              </svg>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

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