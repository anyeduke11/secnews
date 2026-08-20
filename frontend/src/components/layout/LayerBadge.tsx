/**
 * LayerBadge — 统一徽标组件 (v1)
 *
 * Phase 5 设计治理: 消除散落的 editorial-badge / status-icon / 自建 badge。
 *
 * 变体:
 * - solid:  实色背景 (用于状态: success/warning/danger)
 * - soft:   半透明背景 (用于分类标签, 与 HotspotCard 一致)
 * - outline: 仅边框 (用于中性元信息)
 *
 * 颜色: 优先用 layerColor (CSS var) 或显式 color; 不传则用 var(--text-muted)
 */
import React from 'react';

type BadgeVariant = 'solid' | 'soft' | 'outline';
type BadgeSize = 'sm' | 'md';

interface LayerBadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  color?: string;
  /** 用作 title/aria-label */
  title?: string;
  className?: string;
}

export function LayerBadge({
  children,
  variant = 'soft',
  size = 'md',
  color,
  title,
  className = '',
}: LayerBadgeProps) {
  const baseColor = color || 'var(--text-muted)';
  const padding = size === 'sm' ? '1px 6px' : '2px 8px';
  const fontSize = size === 'sm' ? '10px' : '11px';

  let style: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize,
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    padding,
    borderRadius: 'var(--radius-full)',
    letterSpacing: '0.06em',
    lineHeight: '1.5',
    textTransform: 'uppercase',
  };

  if (variant === 'solid') {
    style = { ...style, backgroundColor: baseColor, color: 'var(--text-on-light)', border: 'none' };
  } else if (variant === 'soft') {
    style = {
      ...style,
      backgroundColor: `color-mix(in srgb, ${baseColor} 9%, transparent)`,
      color: baseColor,
      border: 'none',
    };
  } else {
    // outline
    style = { ...style, backgroundColor: 'transparent', color: baseColor, border: `1px solid ${baseColor}` };
  }

  return (
    <span className={`layer-badge ${className}`} style={style} title={title}>
      {children}
    </span>
  );
}
