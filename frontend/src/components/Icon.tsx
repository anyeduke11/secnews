/**
 * Shared Icon component — 14×14 SVG wrapper with consistent stroke style.
 *
 * Usage:
 *   <Icon size={14}>
 *     <line x1="19" y1="12" x2="5" y2="12" />
 *     <polyline points="12 19 5 12 12 5" />
 *   </Icon>
 *
 * The default size is 14×14, matching the project-wide convention.
 * Pass children as SVG elements (<path>, <line>, <circle>, etc.).
 */
import React from 'react';

interface IconProps {
  children: React.ReactNode;
  size?: number;
}

export function Icon({ children, size = 14 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}