/**
 * noteEditorModel — NoteEditor 笔记编辑器的内联 style 常量
 * (B5.6 拆分: 从 NoteEditor 抽出)
 *
 * 纯常量, 无 React 依赖; 渲染结果与 style 对象的值逐字不变 (仍以内联 style 落到 DOM,
 * 不改写为 className)。
 */

// ── styles (tech-style: 青色主调, 透明卡片) ───────────────────────
export const wrapperStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2, 8px)',
  padding: 'var(--space-3, 12px)',
  border: '1px solid var(--border-color)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card)',
};

export const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
};

export const titleStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--color-ai)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

export const countStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted)',
  fontFamily: 'monospace',
};

export const addRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2, 8px)',
  alignItems: 'flex-end',
};

export const textareaStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 8px',
  fontSize: 13,
  border: '1px solid var(--border-color)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
  resize: 'vertical',
  outline: 'none',
};

export const addBtnStyle: React.CSSProperties = {
  padding: '6px 14px',
  fontSize: 12,
  border: '1px solid var(--accent)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'color-mix(in srgb, var(--accent) 8%, transparent)',
  color: 'var(--accent)',
  cursor: 'pointer',
};

export const errorStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--color-error)',
};

export const mutedStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted)',
  padding: 'var(--space-1, 4px)',
};

export const listStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2, 8px)',
  maxHeight: 320,
  overflowY: 'auto',
};

export const noteItemStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px)',
  border: '1px solid var(--border-subtle, rgba(255,255,255,0.04))',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'var(--surface-raised, rgba(255,255,255,0.03))',
};

export const noteContentStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-primary)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  lineHeight: 1.5,
};

export const noteMetaStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginTop: 'var(--space-1, 4px)',
  fontSize: 10,
  color: 'var(--text-muted)',
  fontFamily: 'monospace',
};

export const noteActionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-1, 4px)',
};

export const actionBtnStyle: React.CSSProperties = {
  padding: '2px 6px',
  fontSize: 10,
  border: '1px solid var(--border-color)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
};

export const editRowStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-1, 4px)',
};

export const editBtnRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-1, 4px)',
  justifyContent: 'flex-end',
};

export const saveBtnStyle: React.CSSProperties = {
  ...addBtnStyle,
  padding: '2px 10px',
};

export const cancelBtnStyle: React.CSSProperties = {
  ...actionBtnStyle,
  padding: '2px 10px',
};
