/**
 * WireList — 快讯列 (原型 .wire)
 */
import React from 'react';

interface WireListProps {
  children?: React.ReactNode;
  className?: string;
}

export const WireList: React.FC<WireListProps> = ({ children, className = '' }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
    fontFamily: 'var(--ff-sans)',
    fontSize: 13,
    color: 'var(--ink)',
  };

  return (
    <div className={`wire ${className}`} style={base}>
      {children}
    </div>
  );
};

/** 单条快讯 */
interface WireRowProps {
  title: React.ReactNode;
  sc?: React.ReactNode;
  done?: boolean;
  onClick?: () => void;
}

export const WireRow: React.FC<WireRowProps> = ({ title, sc, done = false, onClick }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'baseline',
    gap: 10,
    padding: '8px 0',
    borderBottom: '1px solid var(--line)',
    cursor: onClick ? 'pointer' : 'default',
    opacity: done ? 0.55 : 1,
    transition: 'opacity 120ms ease',
    textDecoration: done ? 'line-through' : 'none',
  };

  return (
    <div className={`wire-row${done ? ' done' : ''}`} style={base} onClick={onClick}>
      {sc && <span className="wire-sc" style={{ fontFamily: 'var(--ff-mono)', fontSize: 11, color: 'var(--ink-3)', flexShrink: 0 }}>{sc}</span>}
      <span className="wire-title" style={{ flex: 1, lineHeight: 1.5 }}>{title}</span>
    </div>
  );
};
