/**
 * NoteEditorList — 笔记编辑器「笔记列表」展示区块 (含编辑态切换)
 * (B5.6 拆分: 从 NoteEditor 抽出)
 *
 * DOM 结构 / 内联 style / 按钮文案逐字保留; 编辑态与动作由容器传入。
 */
import type { Annotation } from '../../hooks/useAnnotations';
import {
  actionBtnStyle,
  cancelBtnStyle,
  editBtnRowStyle,
  editRowStyle,
  listStyle,
  mutedStyle,
  noteActionsStyle,
  noteContentStyle,
  noteItemStyle,
  noteMetaStyle,
  saveBtnStyle,
  textareaStyle,
} from './noteEditorModel';

export function NoteEditorList({
  items,
  loading,
  busy,
  editingId,
  editingContent,
  onEditingContentChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onRemove,
}: {
  items: Annotation[];
  loading: boolean;
  busy: boolean;
  editingId: string | null;
  editingContent: string;
  onEditingContentChange: (value: string) => void;
  onStartEdit: (a: Annotation) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div style={listStyle}>
      {items.map((a) => (
        <div key={a.id} style={noteItemStyle}>
          {editingId === a.id ? (
            <div style={editRowStyle}>
              <textarea
                style={textareaStyle}
                value={editingContent}
                onChange={(e) => onEditingContentChange(e.target.value)}
                rows={2}
                disabled={busy}
              />
              <div style={editBtnRowStyle}>
                <button type="button" style={saveBtnStyle} onClick={onSaveEdit} disabled={busy}>
                  保存
                </button>
                <button type="button" style={cancelBtnStyle} onClick={onCancelEdit} disabled={busy}>
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
                    onClick={() => onStartEdit(a)}
                    disabled={busy}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    style={{ ...actionBtnStyle, color: 'var(--color-error)' }}
                    onClick={() => onRemove(a.id)}
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
  );
}
