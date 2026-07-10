import React, { useState } from 'react';
import { FavoriteItem } from '../types';

interface FavoriteToTodoPopoverProps {
  favorite: FavoriteItem;
  /** Phase 46: 紧急由 deadline 派生, 不再传 urgent。 */
  onConfirm: (req: { important: boolean; deadline: string | null; note: string }) => Promise<void>;
  onCancel: () => void;
}

/**
 * Phase 36 Task 5: 收藏 → 待办 popover
 *
 * Phase 46: 取消「紧急」checkbox, 改为「截止日期」input。
 * - 紧急由 deadline 自动派生 (≤1 业务日=紧急, 过滤周末)
 * - 重要仍是用户主动决定
 * - 备注不变
 */
export function FavoriteToTodoPopover({ favorite, onConfirm, onCancel }: FavoriteToTodoPopoverProps) {
  const [important, setImportant] = useState(false);
  const [deadline, setDeadline] = useState('');  // 'YYYY-MM-DD' or ''
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        important,
        deadline: deadline.trim() || null,
        note: note.trim(),
      });
      // 父级处理成功后调用 onCancel 关闭
    } catch (e) {
      setError((e as Error).message || '添加失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-1.5 mx-1 rounded-[var(--radius-md)] p-2.5 animate-fade-in"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        boxShadow: 'var(--shadow-elevated)',
      }}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h5
            className="text-[11px] font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            添加为待办
          </h5>
          <span
            className="text-[10px] truncate max-w-[180px]"
            style={{ color: 'var(--text-muted)' }}
            title={favorite.title}
          >
            {favorite.title}
          </span>
        </div>

        <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-secondary)' }}>
          {/* Phase 46: 紧急 checkbox → 截止日期 input */}
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <span>截止日期</span>
            <input
              type="date"
              value={deadline}
              onChange={e => setDeadline(e.target.value)}
              disabled={submitting}
              className="px-1.5 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                colorScheme: 'light dark',
              }}
            />
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={important}
              onChange={e => setImportant(e.target.checked)}
              disabled={submitting}
              className="focus-ring"
            />
            <span
              className="dot-indicator"
              style={{ backgroundColor: important ? '#3b82f6' : 'transparent', border: '1px solid #3b82f6' }}
              aria-hidden="true"
            />
            重要
          </label>
          {deadline && (
            <span
              className="text-[10px]"
              style={{ color: 'var(--text-muted)' }}
              title="紧急由截止日期自动判断: ≤ 1 业务日(过滤周末) = 紧急"
            >
              (紧急自动)
            </span>
          )}
        </div>

        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="备注 (可选)"
          rows={1}
          maxLength={500}
          disabled={submitting}
          className="px-2 py-1 text-[11px] rounded-[var(--radius-sm)] focus-ring resize-none"
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            fontFamily: 'inherit',
          }}
        />

        {error && (
          <p className="text-[11px]" style={{ color: '#e85d5d' }}>
            {error}
          </p>
        )}

        <div className="flex items-center gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="btn-ghost px-2.5 py-1 text-[11px]"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-2.5 py-1 text-[11px] rounded-[var(--radius-sm)] font-medium transition-colors duration-150"
            style={{
              backgroundColor: submitting ? 'var(--text-muted)' : 'var(--color-ai)',
              color: '#0a1f15',
              opacity: submitting ? 0.7 : 1,
              cursor: submitting ? 'not-allowed' : 'pointer',
              border: 'none',
            }}
          >
            {submitting ? '添加中…' : '确认'}
          </button>
        </div>
      </div>
    </form>
  );
}
