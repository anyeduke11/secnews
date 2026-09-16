/**
 * Stamp — 编辑部印章徽章 (原型 .st)
 *
 * 语义色: ok / warn / err / info
 * 变体: solid (实底) / hollow (描边) / italic (斜体) / lg (大号) / pad (加内距)
 */
import React from 'react';

type StampColor = 'ok' | 'warn' | 'err' | 'info';
type StampVariant = 'solid' | 'hollow' | 'italic';
type StampSize = 'sm' | 'md' | 'lg';

interface StampProps {
  color?: StampColor;
  variant?: StampVariant;
  size?: StampSize;
  className?: string;
  children?: React.ReactNode;
}

const COLOR_MAP: Record<StampColor, { bg: string; text: string; border: string }> = {
  ok: { bg: 'var(--ok)', text: '#fff', border: 'var(--ok)' },
  warn: { bg: 'var(--warn)', text: '#fff', border: 'var(--warn)' },
  err: { bg: 'var(--err)', text: '#fff', border: 'var(--err)' },
  info: { bg: 'var(--info)', text: '#fff', border: 'var(--info)' },
};

export const Stamp: React.FC<StampProps> = ({
  color = 'info',
  variant = 'solid',
  size = 'md',
  className = '',
  children,
}) => {
  const c = COLOR_MAP[color];
  const isHollow = variant === 'hollow';
  const isItalic = variant === 'italic';
  const isLg = size === 'lg';

  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontFamily: 'var(--ff-mono)',
    fontSize: isLg ? '13px' : '11px',
    fontWeight: 600,
    lineHeight: 1.5,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    padding: isLg ? '4px 12px' : '2px 8px',
    borderRadius: 'var(--radius-full)',
    border: `1px solid ${isHollow ? c.border : 'currentColor'}`,
    color: isHollow ? c.border : c.text,
    background: isHollow ? 'transparent' : c.bg,
    fontStyle: isItalic ? 'italic' : 'normal',
    whiteSpace: 'nowrap',
  };

  return <span className={`st st-${color} st-${variant}${isLg ? ' st-lg' : ''} ${className}`} style={base}>{children}</span>;
};
