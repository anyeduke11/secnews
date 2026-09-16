/**
 * IconButton — 编辑部图标按钮 (原型 .ibtn)
 */
import React from 'react';

interface IconButtonProps {
  onClick?: () => void;
  active?: boolean;
  title?: string;
  ariaLabel?: string;
  children?: React.ReactNode;
}

export const IconButton: React.FC<IconButtonProps> = ({
  onClick,
  active = false,
  title,
  ariaLabel,
  children,
}) => {
  const base: React.CSSProperties = {
    width: 34,
    height: 34,
    borderRadius: 'var(--radius-sm)',
    display: 'inline-grid',
    placeItems: 'center',
    color: 'var(--ink-2)',
    background: active ? 'var(--accent-soft)' : 'transparent',
    border: `1px solid ${active ? 'var(--accent)' : 'transparent'}`,
    cursor: 'pointer',
    transition: 'background 120ms ease, color 120ms ease, border-color 120ms ease',
    padding: 0,
  };

  return (
    <button
      type="button"
      className={`ibtn${active ? ' on' : ''}`}
      style={base}
      onClick={onClick}
      title={title}
      aria-label={ariaLabel || title}
    >
      {children}
    </button>
  );
};
