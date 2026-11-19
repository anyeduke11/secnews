/**
 * ToolPageHeader — L1 原子 (前端重构 V1 · B9-b, 2026-11-19)
 *
 * 工具页页头。收口两种合法体例 (B7 §17.7 的"两种合法页头体例"在此扩展为可复用原子):
 *
 * - `compact` — 紧凑工具头 (`/tags` `/search` `/extract`): 2px 下边线 + 右对齐 ghost 返回钮
 *   + `text-sm` 标题 + 等宽前缀 (TAG / FIND / EXT)。
 * - `bar` — 横条头 (skills 三页): 左侧 bordered 返回钮 + `text-lg` 标题 + 尾部计数/徽标槽。
 *
 * DOM 与类名逐字复刻各页原实现 (**零视觉变更**); 本原子只做重复块收敛, 不改版式。
 * 编辑部大标题体例走 `PageHeader` (`.ed-*` 词汇), 与本原子互斥, 禁止混用。
 */
import React from 'react';
import { Icon } from './Icon';

export interface ToolPageHeaderProps {
  /** 页头标题 */
  title: React.ReactNode;
  /** 标题前的等宽前缀 (compact 体例: TAG / FIND / EXT) */
  prefix?: string;
  /** 返回回调; 不传则不渲染返回钮 */
  onBack?: () => void;
  /** 返回钮无障碍名 (bar 体例默认「返回」) */
  backLabel?: string;
  /** 体例: compact = 紧凑工具头; bar = 横条头 (默认) */
  variant?: 'compact' | 'bar';
  /** bar 体例的尾部计数/徽标槽 */
  trailing?: React.ReactNode;
  /** bar 体例标题截断 (长技能名) */
  truncate?: boolean;
  className?: string;
}

export function ToolPageHeader({
  title,
  prefix,
  onBack,
  backLabel,
  variant = 'bar',
  trailing,
  truncate = false,
  className = '',
}: ToolPageHeaderProps) {
  if (variant === 'compact') {
    return (
      <div
        className={`flex items-center justify-between pb-2 mb-1 ${className}`.trim()}
        style={{ borderBottom: '2px solid var(--text-primary)' }}
      >
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          {prefix && <span className="font-mono mr-2">{prefix}</span>}
          {title}
        </h1>
        {onBack && (
          <button onClick={onBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回">
            <Icon size={11}>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            <span className="hidden sm:inline">返回</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <header className={`flex items-center gap-3 ${className}`.trim()}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          aria-label={backLabel ?? '返回'}
          className="h-8 px-2.5 rounded-md text-sm border"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
        >
          ←
        </button>
      )}
      <h1
        className={`text-lg font-bold${truncate ? ' truncate' : ''}`}
        style={{ color: 'var(--ink)' }}
      >
        {title}
      </h1>
      {trailing}
    </header>
  );
}
