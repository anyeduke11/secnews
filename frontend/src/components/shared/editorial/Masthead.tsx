/**
 * Masthead — 报头 (原型 .masthead)
 *
 * 用途: 品牌区 + 主标题 + 副标题 + 右侧操作
 */
import React from 'react';

interface MastheadProps {
  brand?: React.ReactNode;
  title?: React.ReactNode;
  sub?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}

export const Masthead: React.FC<MastheadProps> = ({ brand, title, sub, right, className = '' }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    padding: '16px 20px',
    borderBottom: '1px solid var(--line)',
    background: 'var(--paper)',
  };

  const leftStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'baseline',
    gap: 12,
    minWidth: 0,
  };

  const brandStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-mono)',
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--accent)',
  };

  const titleStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-serif)',
    fontSize: 22,
    fontWeight: 700,
    color: 'var(--ink)',
    lineHeight: 1.2,
  };

  const subStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-mono)',
    fontSize: 11,
    color: 'var(--ink-3)',
    letterSpacing: '0.04em',
  };

  return (
    <header className={`masthead ${className}`} style={base}>
      <div style={leftStyle}>
        {brand && <span style={brandStyle}>{brand}</span>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          {title && <span style={titleStyle}>{title}</span>}
          {sub && <span style={subStyle}>{sub}</span>}
        </div>
      </div>
      {right && <div style={{ flexShrink: 0 }}>{right}</div>}
    </header>
  );
};
