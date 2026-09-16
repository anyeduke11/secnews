/**
 * SectionHead — 区块标题 (原型 .sec-head)
 *
 * 变体: slim (紧凑，无下划线)
 */
import React from 'react';

interface SectionHeadProps {
  title: string;
  slim?: boolean;
  right?: React.ReactNode;
}

export const SectionHead: React.FC<SectionHeadProps> = ({ title, slim = false, right }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 12,
    fontFamily: 'var(--ff-serif)',
    fontSize: '16px',
    fontWeight: 700,
    color: 'var(--ink)',
    lineHeight: 1.3,
    paddingBottom: slim ? 0 : 8,
    borderBottom: slim ? 'none' : '1px solid var(--line)',
    marginBottom: 12,
  };

  return (
    <div className={`sec-head${slim ? ' slim' : ''}`} style={base}>
      <span>{title}</span>
      {right && <span style={{ fontFamily: 'var(--ff-mono)', fontSize: 12, fontWeight: 400 }}>{right}</span>}
    </div>
  );
};
