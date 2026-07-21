/**
 * FavoriteItem — 单条收藏项渲染（含 → 待办 popover 入口）。
 *
 * Phase 1B: 拆自原 FavoritesPanel.tsx 单条 li 段。
 * props-only: 接收 item + inTodo + isPopoverOpen + 3 个 handlers。
 */
import React from 'react';
import { FavoriteItem as FavoriteItemType, getCategoryColor, getCategoryLabel } from '../../types';
import { FavoriteToTodoPopover } from '../FavoriteToTodoPopover';

interface FavoriteItemProps {
  item: FavoriteItemType;
  inTodo: boolean;
  isPopoverOpen: boolean;
  onTogglePopover: () => void;
  onAddToTodo: (payload: { important: boolean; deadline: string | null; note: string }) => void | Promise<void>;
  onRemove: () => void;
}

export function FavoriteItem({
  item: it, inTodo, isPopoverOpen,
  onTogglePopover, onAddToTodo, onRemove,
}: FavoriteItemProps) {
  const catColor = getCategoryColor(it.category);
  return (
    <li
      className="group px-3 py-2.5 rounded transition-colors"
      style={{ borderLeft: `2px solid ${catColor}80` }}
    >
      <div className="flex items-start gap-2">
        <a
          href={it.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 min-w-0"
          title={it.url}
        >
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: `${catColor}14`, color: catColor }}
            >
              {getCategoryLabel(it.category)}
            </span>
            <span className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>
              {it.source}
            </span>
          </div>
          <h4
            className="text-[12px] font-medium leading-snug line-clamp-2"
            style={{ color: 'var(--text-primary)' }}
          >
            {it.title}
          </h4>
        </a>
        {/* → 待办 按钮 (always visible, 取消收藏按钮左侧) */}
        <button
          onClick={() => { if (!inTodo) onTogglePopover(); }}
          disabled={inTodo}
          className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors duration-150"
          style={{
            color: inTodo ? '#00c96a' : 'var(--text-muted)',
            opacity: inTodo ? 0.6 : 1,
            cursor: inTodo ? 'not-allowed' : 'pointer',
            border: `1px solid ${inTodo ? '#00c96a66' : 'var(--border-color)'}`,
          }}
          title={inTodo ? '已加入待办' : '添加为待办'}
          aria-label={inTodo ? '已加入待办' : '添加为待办'}
        >
          {inTodo ? '✓ 已加入' : '→ 待办'}
        </button>
        {/* 取消收藏按钮 */}
        <button
          onClick={onRemove}
          className="shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ color: '#e85d5d' }}
          title="取消收藏"
          aria-label="取消收藏"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6" />
            <path d="M14 11v6" />
          </svg>
        </button>
      </div>
      {isPopoverOpen && (
        <FavoriteToTodoPopover
          favorite={it}
          onCancel={onTogglePopover}
          onConfirm={async (payload) => { await onAddToTodo(payload); }}
        />
      )}
    </li>
  );
}
