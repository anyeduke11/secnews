/**
 * PressBar — 编辑出版条 (原型 .pressbar)
 *
 * 语义: 管道路由 / 发行统计 / 状态条
 */
import React from 'react';

interface PressBarProps {
  children?: React.ReactNode;
  className?: string;
}

export const PressBar: React.FC<PressBarProps> = ({ children, className = '' }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 18,
    padding: '8px 16px',
    borderBottom: '1px solid var(--line)',
    background: 'var(--paper-2)',
    fontFamily: 'var(--ff-mono)',
    fontSize: 11,
    color: 'var(--ink-2)',
    lineHeight: 1.4,
    overflowX: 'auto',
  };

  return (
    <div className={`pressbar ${className}`} style={base}>
      {children}
    </div>
  );
};

/** 键值对单元 */
interface PressItemProps {
  label: React.ReactNode;
  value: React.ReactNode;
}

export const PressItem: React.FC<PressItemProps> = ({ label, value }) => {
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'baseline',
    gap: 6,
    whiteSpace: 'nowrap',
  };

  return (
    <span style={base}>
      <span style={{ color: 'var(--ink-3)', fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ color: 'var(--ink)', fontWeight: 600 }}>{value}</span>
    </span>
  );
};
