import type { MouseEvent } from 'react';

/**
 * v1.7 Phase 3 — 告警徽章 (未读计数)
 *
 * Props:
 *  - count:     未读告警数
 *  - onClick:   点击回调 (打开 AlertCenter)
 *
 * 行为:
 *  - count=0 时不显示
 *  - count>99 显示 "99+"
 *  - count>0 显示红色圆点 + 数字
 *
 * 验收 3: 告警 SSE 推送到达前端 — 徽章实时更新未读计数。
 */

export interface AlertBadgeProps {
  count: number;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
}

export function AlertBadge({ count, onClick }: AlertBadgeProps) {
  if (count <= 0) return null;
  const display = count > 99 ? '99+' : String(count);
  return (
    <button
      className="alert-badge"
      onClick={onClick}
      aria-label={`${count} 条未读告警`}
      title={`${count} 条未读告警`}
      style={{
        position: 'relative',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
      }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      <span
        style={{
          position: 'absolute',
          top: '-4px',
          right: '-4px',
          background: '#e53e3e',
          color: '#fff',
          fontSize: '10px',
          fontWeight: 'bold',
          minWidth: '16px',
          height: '16px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 4px',
          lineHeight: 1,
        }}
      >
        {display}
      </span>
    </button>
  );
}
