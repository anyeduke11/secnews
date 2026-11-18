/**
 * LayerCard — 三层架构统一卡片容器 (v2)
 *
 * Phase 5: 设计治理
 * 提供变体样式（default / compact / highlight / ghost / pipeline），
 * 一致的间距、标题区域和操作按钮位置。
 * 消除各层页面重复的 {bg-elevated, border, radius} 内联样式。
 *
 * B6-a 拆分: 行项目/网格/告警/管线 → ./LayerCardParts, 链接/空态/骨架 → ./LayerCardStates;
 * 本文件末尾按原名 re-export, 导出面与调用方保持不变。
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

export { LayerCardRow, LayerCardGrid, LayerCardAlert, PipelineFlow } from './LayerCardParts';
export { ViewMoreLink, LayerEmptyState, LayerSkeleton } from './LayerCardStates';