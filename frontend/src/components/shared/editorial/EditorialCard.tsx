/**
 * EditorialCard — 通用卡片容器 (原型 .card)
 */
import React from 'react';

interface EditorialCardProps {
  children?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

export const EditorialCard: React.FC<EditorialCardProps> = ({
  children,
  className = '',
  style,
  onClick,
}) => {
  const base: React.CSSProperties = {
    background: 'var(--card)',
    border: '1px solid var(--line)',
    borderRadius: 'var(--radius-md)',
    padding: 16,
    boxShadow: 'var(--shadow-pop)',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'border-color 200ms var(--ease-out), background 200ms var(--ease-out)',
    ...style,
  };

  return (
    <div
      className={`card ${className}`}
      style={base}
      onClick={onClick}
      onMouseEnter={e => {
        if (onClick) {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--accent)';
          (e.currentTarget as HTMLDivElement).style.background = 'var(--paper-2)';
        }
      }}
      onMouseLeave={e => {
        if (onClick) {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--line)';
          (e.currentTarget as HTMLDivElement).style.background = 'var(--card)';
        }
      }}
    >
      {children}
    </div>
  );
};
