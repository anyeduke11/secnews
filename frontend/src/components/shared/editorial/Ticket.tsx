/**
 * Ticket — 稿签卡 (原型 .ticket)
 *
 * 语义变体: hot / lead / 默认
 * 子区: kick (状态栏) / title / summary / meta / side (侧边信息)
 */
import React from 'react';

interface TicketProps {
  kick?: React.ReactNode;
  title?: React.ReactNode;
  summary?: React.ReactNode;
  meta?: React.ReactNode;
  side?: React.ReactNode;
  hot?: boolean;
  lead?: boolean;
  className?: string;
  onClick?: () => void;
  children?: React.ReactNode;
}

export const Ticket: React.FC<TicketProps> = ({
  kick,
  title,
  summary,
  meta,
  side,
  hot = false,
  lead = false,
  className = '',
  onClick,
  children,
}) => {
  const base: React.CSSProperties = {
    position: 'relative',
    display: 'flex',
    gap: 12,
    padding: '14px 16px',
    borderBottom: '1px solid var(--line)',
    background: 'transparent',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background 120ms ease',
    fontFamily: 'var(--ff-sans)',
  };

  const kickStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-mono)',
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--ink-2)',
    marginBottom: 4,
  };

  const titleStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-serif)',
    fontSize: 15,
    fontWeight: 700,
    color: 'var(--ink)',
    lineHeight: 1.35,
    marginBottom: summary ? 4 : 0,
  };

  const summaryStyle: React.CSSProperties = {
    fontSize: 13,
    color: 'var(--ink-2)',
    lineHeight: 1.55,
    flex: 1,
  };

  const metaStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-mono)',
    fontSize: 11,
    color: 'var(--ink-3)',
    marginTop: 6,
  };

  const sideStyle: React.CSSProperties = {
    fontFamily: 'var(--ff-mono)',
    fontSize: 11,
    color: 'var(--ink-3)',
    textAlign: 'right',
    whiteSpace: 'nowrap',
    flexShrink: 0,
  };

  return (
    <div
      className={`ticket${hot ? ' hot' : ''}${lead ? ' lead' : ''} ${className}`}
      style={base}
      onClick={onClick}
      onMouseEnter={e => { if (onClick) (e.currentTarget as HTMLDivElement).style.background = 'var(--paper-2)'; }}
      onMouseLeave={e => { if (onClick) (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        {kick && <div style={kickStyle}>{kick}</div>}
        {title && <div style={titleStyle}>{title}</div>}
        {summary && <div style={summaryStyle}>{summary}</div>}
        {meta && <div style={metaStyle}>{meta}</div>}
        {children}
      </div>
      {side && <div style={sideStyle}>{side}</div>}
    </div>
  );
};
