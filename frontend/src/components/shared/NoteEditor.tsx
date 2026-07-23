import { useState, useEffect } from 'react';
import type { Annotation } from '../../hooks/useAnnotations';

/**
 * v1.7 Phase 2 — NoteEditor 笔记编辑器
 *
 * Props:
 *  - entityType / entityId:  当前实体 (笔记归属)
 *  - items:                  该实体的笔记列表
 *  - onAdd:     (content, rangeStart?, rangeEnd?) => Promise<Annotation>
 *  - onUpdate:  (annotationId, content) => Promise<Annotation>
 *  - onRemove:  (annotationId) => Promise<void>
 *
 * 行为:
 *  - 顶部输入框 + 添加按钮 (验收 3: 笔记 CRUD 正常)
 *  - 列表显示已有笔记, 每条可编辑/删除
 *  - 编辑模式: 点击编辑 → 文本框 + 保存/取消
 */

export interface NoteEditorProps {
  entityType: string;
  entityId: string;
  items: Annotation[];
  loading?: boolean;
  onAdd: (content: string, rangeStart?: number, rangeEnd?: number) => Promise<Annotation>;
  onUpdate: (annotationId: string, content: string) => Promise<Annotation>;
  onRemove: (annotationId: string) => Promise<void>;
}

export function NoteEditor({
  entityType,
  entityId,
  items,
  loading,
  onAdd,
  onUpdate,
  onRemove,
}: NoteEditorProps) {
  const [draft, setDraft] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 切换实体时清空草稿
  useEffect(() => {
    setDraft('');
    setEditingId(null);
    setError(null);
  }, [entityType, entityId]);

  const handleAdd = async () => {
    const content = draft.trim();
    if (!content) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(content);
      setDraft('');
    } catch (e: any) {
      setError(e?.message || '添加笔记失败');
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (a: Annotation) => {
    setEditingId(a.id);
    setEditingContent(a.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingContent('');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    const content = editingContent.trim();
    if (!content) return;
    setBusy(true);
    setError(null);
    try {
      await onUpdate(editingId, content);
      cancelEdit();
    } catch (e: any) {
      setError(e?.message || '更新笔记失败');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await onRemove(id);
    } catch (e: any) {
      setError(e?.message || '删除笔记失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="note-editor" style={wrapperStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>笔记</span>
        <span style={countStyle}>{items.length} 条</span>
      </div>

      {/* 新建输入 */}
      <div style={addRowStyle}>
        <textarea
          style={textareaStyle}
          placeholder={`为 ${entityType}/${entityId} 添加笔记…`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          disabled={busy}
        />
        <button
          type="button"
          style={addBtnStyle}
          onClick={handleAdd}
          disabled={busy || !draft.trim()}
        >
          添加
        </button>
      </div>

      {error && <div style={errorStyle}>{error}</div>}
      {loading && <div style={mutedStyle}>加载中…</div>}

      {/* 笔记列表 */}
      <div style={listStyle}>
        {items.map((a) => (
          <div key={a.id} style={noteItemStyle}>
            {editingId === a.id ? (
              <div style={editRowStyle}>
                <textarea
                  style={textareaStyle}
                  value={editingContent}
                  onChange={(e) => setEditingContent(e.target.value)}
                  rows={2}
                  disabled={busy}
                />
                <div style={editBtnRowStyle}>
                  <button type="button" style={saveBtnStyle} onClick={saveEdit} disabled={busy}>
                    保存
                  </button>
                  <button type="button" style={cancelBtnStyle} onClick={cancelEdit} disabled={busy}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div style={noteContentStyle}>{a.content}</div>
                <div style={noteMetaStyle}>
                  <span>{new Date(a.created_at).toLocaleString('zh-CN')}</span>
                  <div style={noteActionsStyle}>
                    <button
                      type="button"
                      style={actionBtnStyle}
                      onClick={() => startEdit(a)}
                      disabled={busy}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      style={{ ...actionBtnStyle, color: 'var(--color-error, #ef4444)' }}
                      onClick={() => handleRemove(a.id)}
                      disabled={busy}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        ))}
        {!loading && items.length === 0 && (
          <div style={mutedStyle}>暂无笔记</div>
        )}
      </div>
    </div>
  );
}

// ── styles (tech-style: 青色主调, 透明卡片) ───────────────────────
const wrapperStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2, 8px)',
  padding: 'var(--space-3, 12px)',
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-md, 8px)',
  background: 'var(--bg-card, #0d0d14)',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2, 8px)',
};

const titleStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--color-ai, #00d4e0)',
  fontFamily: 'monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const countStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

const addRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2, 8px)',
  alignItems: 'flex-end',
};

const textareaStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 8px',
  fontSize: 13,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'var(--bg-secondary, #09090f)',
  color: 'var(--text-primary, #f0f0f7)',
  fontFamily: 'inherit',
  resize: 'vertical',
  outline: 'none',
};

const addBtnStyle: React.CSSProperties = {
  padding: '6px 14px',
  fontSize: 12,
  border: '1px solid var(--color-ai, #00d4e0)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'rgba(0, 212, 224, 0.12)',
  color: 'var(--color-ai, #00d4e0)',
  cursor: 'pointer',
};

const errorStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--color-error, #ef4444)',
};

const mutedStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted, #5b5b72)',
  padding: 'var(--space-1, 4px)',
};

const listStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2, 8px)',
  maxHeight: 320,
  overflowY: 'auto',
};

const noteItemStyle: React.CSSProperties = {
  padding: 'var(--space-2, 8px)',
  border: '1px solid var(--border-subtle, rgba(255,255,255,0.04))',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'var(--surface-raised, rgba(255,255,255,0.03))',
};

const noteContentStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-primary, #f0f0f7)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  lineHeight: 1.5,
};

const noteMetaStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginTop: 'var(--space-1, 4px)',
  fontSize: 10,
  color: 'var(--text-muted, #5b5b72)',
  fontFamily: 'monospace',
};

const noteActionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-1, 4px)',
};

const actionBtnStyle: React.CSSProperties = {
  padding: '2px 6px',
  fontSize: 10,
  border: '1px solid var(--border-color, #1c1c2e)',
  borderRadius: 'var(--radius-sm, 4px)',
  background: 'transparent',
  color: 'var(--text-secondary, #9a9ab2)',
  cursor: 'pointer',
};

const editRowStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-1, 4px)',
};

const editBtnRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-1, 4px)',
  justifyContent: 'flex-end',
};

const saveBtnStyle: React.CSSProperties = {
  ...addBtnStyle,
  padding: '2px 10px',
};

const cancelBtnStyle: React.CSSProperties = {
  ...actionBtnStyle,
  padding: '2px 10px',
};

export default NoteEditor;
