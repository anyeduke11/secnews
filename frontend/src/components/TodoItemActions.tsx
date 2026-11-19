/**
 * TodoItemActions — 从 components/TodoItem.tsx 拆出的右侧操作簇 (B6-a 纯搬迁, 无行为变更)。
 * 职责: 重要切换 / 截止日期编辑 / 4 象限 chip / 打开原文 / 删除; 事件回调由 TodoItem 传入。
 */
import React from 'react';
import { TodoItem as TodoItemModel } from '../types';
import { Icon } from '../primitives/Icon';

interface TodoItemActionsProps {
  item: TodoItemModel;
  isArchived: boolean;
  quadrant: 'P0' | 'P1' | 'P2' | 'P3';
  qInfo: { color: string; bg: string; label: string };
  onImportantClick: () => void;
  onDeadlineEdit: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDeleteClick: () => void;
}

export function TodoItemActions({
  item,
  isArchived,
  quadrant,
  qInfo,
  onImportantClick,
  onDeadlineEdit,
  onDeleteClick,
}: TodoItemActionsProps) {
  return (
    <div className="shrink-0 flex items-center gap-1.5">
      {/* Phase 46: 重要切换按钮 (替代旧的 4 象限循环) */}
      <button
        type="button"
        onClick={onImportantClick}
        disabled={isArchived}
        className="px-1.5 py-0.5 rounded-[var(--radius-sm)] text-[10px] focus-ring flex items-center gap-1"
        style={{
          border: `1px solid ${item.important ? 'var(--color-info)' : 'var(--border-color)'}`,
          backgroundColor: item.important ? 'color-mix(in srgb, var(--color-info) 8%, transparent)' : 'transparent',
          color: item.important ? 'var(--color-info)' : 'var(--text-muted)',
          cursor: isArchived ? 'not-allowed' : 'pointer',
        }}
        title={item.important ? '取消重要' : '标记为重要'}
        aria-label={item.important ? '取消重要' : '标记为重要'}
      >
        <Icon size={10}>
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </Icon>
        <span>{item.important ? '重要' : '标为重要'}</span>
      </button>

      {/* Phase 46: 截止日期快速编辑 (input type=date, 仅图标) */}
      <label
        className="btn-ghost p-1.5"
        style={{
          minHeight: 0,
          cursor: isArchived ? 'not-allowed' : 'pointer',
          opacity: isArchived ? 0.4 : 1,
          position: 'relative',  // input 绝对定位的参照
        }}
        title={item.deadline ? `截止: ${item.deadline}` : '设置截止日期'}
      >
        <Icon>
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </Icon>
        <input
          type="date"
          value={item.deadline || ''}
          onChange={onDeadlineEdit}
          disabled={isArchived}
          // 覆盖整个 label 区域: 点击图标实际是点击 input, 浏览器自动弹 date picker
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            opacity: 0,
            cursor: isArchived ? 'not-allowed' : 'pointer',
            border: 'none',
            background: 'transparent',
            padding: 0,
            margin: 0,
          }}
        />
      </label>

      {/* 4 象限 chip (read-only, 反映 effective_urgent × important) */}
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          backgroundColor: qInfo.bg,
          border: quadrant === 'P3' ? '2px solid var(--text-muted)' : 'none',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          opacity: isArchived ? 0.6 : 1,
        }}
        title={`${qInfo.label} (紧急由截止日期自动判断)`}
        aria-label={`象限: ${qInfo.label}`}
      >
        {quadrant === 'P3' && (
          <span
            style={{
              width: 5,
              height: 5,
              borderRadius: '50%',
              backgroundColor: 'var(--text-muted)',
            }}
          />
        )}
      </div>

      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-ghost p-1.5"
          style={{ minHeight: 0 }}
          title="打开原文"
          aria-label="打开原文"
        >
          <Icon>
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </Icon>
        </a>
      )}

      <button
        type="button"
        onClick={onDeleteClick}
        className="btn-ghost p-1.5 transition-colors"
        style={{ minHeight: 0, color: 'var(--text-muted)' }}
        title="删除"
        aria-label="删除"
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.color = 'var(--color-error)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-error)';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-muted)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-color)';
        }}
      >
        <Icon>
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
        </Icon>
      </button>
    </div>
  );
}