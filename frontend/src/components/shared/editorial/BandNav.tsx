/**
 * BandNav — 版面条 / 二级导航 (原型 .bandnav)
 *
 * 语义: 页面内二级分区导航 (chip list)
 */
import React from 'react';

interface BandNavProps {
  items: { label: string; href?: string; active?: boolean; onClick?: () => void }[];
  className?: string;
}

export const BandNav: React.FC<BandNavProps> = ({ items, className = '' }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '10px 16px',
    borderBottom: '1px solid var(--line)',
    background: 'var(--paper)',
    overflowX: 'auto',
  };

  const chipBase: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '5px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid transparent',
    background: 'transparent',
    color: 'var(--ink-2)',
    fontFamily: 'var(--ff-mono)',
    fontSize: 12,
    fontWeight: 500,
    lineHeight: 1.3,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 120ms ease',
    textDecoration: 'none',
  };

  const chipActive: React.CSSProperties = {
    background: 'var(--accent-soft)',
    borderColor: 'var(--accent)',
    color: 'var(--accent)',
    fontWeight: 700,
  };

  return (
    <nav className={`bandnav ${className}`} style={base} aria-label="版面条">
      {items.map((item, idx) => {
        if (item.onClick) {
          return (
            <button key={idx} type="button" style={item.active ? chipActive : chipBase} onClick={item.onClick}>
              {item.label}
            </button>
          );
        }
        return (
          <a key={idx} href={item.href || '#'} style={item.active ? chipActive : chipBase}>
            {item.label}
          </a>
        );
      })}
    </nav>
  );
};
