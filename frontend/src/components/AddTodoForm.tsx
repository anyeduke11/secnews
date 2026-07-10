import React, { useState } from 'react';
import { TodoCreateRequest } from '../types';

interface AddTodoFormProps {
  onAdd: (req: TodoCreateRequest) => Promise<void>;
}

function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
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

/**
 * Phase 46: 添加手动待办。
 *
 * - 取消「紧急」checkbox — 紧急由 deadline 自动派生 (≤1 业务日=紧急, 过滤周末)。
 * - 保留「重要」checkbox — 用户主动决定。
 * - 新增「截止日期」date input — 可选, 留空表示无截止日期 (永远不紧急)。
 * - 备注 textarea 不变。
 */
export function AddTodoForm({ onAdd }: AddTodoFormProps) {
  const [expanded, setExpanded] = useState(false);
  const [title, setTitle] = useState('');
  const [important, setImportant] = useState(false);
  const [deadline, setDeadline] = useState('');  // 'YYYY-MM-DD' or ''
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle('');
    setImportant(false);
    setDeadline('');
    setNote('');
    setError(null);
  };

  const handleCancel = () => {
    reset();
    setExpanded(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setError('标题不能为空');
      return;
    }
    if (trimmed.length > 500) {
      setError('标题长度不能超过 500 字符');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onAdd({
        source_type: 'manual',
        title: trimmed,
        important,
        deadline: deadline.trim() || null,
        note: note.trim() || undefined,
      });
      reset();
      setExpanded(false);
    } catch (e: any) {
      setError(e?.message || '添加失败');
    } finally {
      setSubmitting(false);
    }
  };

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="btn-ghost w-full py-2 text-xs"
        style={{
          borderStyle: 'dashed',
          color: 'var(--text-secondary)',
        }}
      >
        <Icon>
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </Icon>
        添加手动待办
      </button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[var(--radius-md)] p-3 animate-fade-in"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
      }}
    >
      <div className="flex flex-col gap-2">
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="待办标题 (必填)"
          maxLength={500}
          autoFocus
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
          }}
        />

        <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-secondary)' }}>
          {/* Phase 46: 紧急 checkbox 移除, 改为截止日期 input */}
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <Icon size={12}>
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </Icon>
            <span>截止日期</span>
            <input
              type="date"
              value={deadline}
              onChange={e => setDeadline(e.target.value)}
              className="px-1.5 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                colorScheme: 'light dark',
              }}
            />
            {deadline && (
              <button
                type="button"
                onClick={() => setDeadline('')}
                className="text-[10px] underline"
                style={{ color: 'var(--text-muted)' }}
                title="清空截止日期"
              >
                清空
              </button>
            )}
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={important}
              onChange={e => setImportant(e.target.checked)}
              className="focus-ring"
            />
            重要
          </label>
          {/* 紧急说明 */}
          {deadline && (
            <span
              className="text-[10px]"
              style={{ color: 'var(--text-muted)' }}
              title="紧急由截止日期自动判断: ≤ 1 业务日(过滤周末) = 紧急"
            >
              (紧急自动判断)
            </span>
          )}
        </div>

        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="备注 (可选)"
          rows={1}
          className="px-2 py-1.5 text-xs rounded-[var(--radius-sm)] focus-ring resize-none"
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
            onClick={handleCancel}
            disabled={submitting}
            className="btn-ghost px-3 py-1 text-xs"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={submitting || !title.trim()}
            className="btn-ghost px-3 py-1 text-xs"
            style={{
              color: submitting || !title.trim() ? 'var(--text-muted)' : 'var(--color-general)',
              borderColor: submitting || !title.trim() ? 'var(--border-color)' : 'var(--color-general)',
              opacity: submitting ? 0.7 : 1,
              cursor: submitting || !title.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? '添加中…' : '添加'}
          </button>
        </div>
      </div>
    </form>
  );
}
