/**
 * NoteEditorComposer — 笔记编辑器「新建输入」展示区块
 * (B5.6 拆分: 从 NoteEditor 抽出)
 *
 * DOM 结构 / 内联 style / placeholder 文案逐字保留; 状态与动作由容器传入。
 */
import { addBtnStyle, addRowStyle, textareaStyle } from './noteEditorModel';

export function NoteEditorComposer({
  entityType,
  entityId,
  draft,
  busy,
  onDraftChange,
  onAdd,
}: {
  entityType: string;
  entityId: string;
  draft: string;
  busy: boolean;
  onDraftChange: (value: string) => void;
  onAdd: () => void;
}) {
  return (
    <div style={addRowStyle}>
      <textarea
        style={textareaStyle}
        placeholder={`为 ${entityType}/${entityId} 添加笔记…`}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        rows={2}
        disabled={busy}
      />
      <button
        type="button"
        style={addBtnStyle}
        onClick={onAdd}
        disabled={busy || !draft.trim()}
      >
        添加
      </button>
    </div>
  );
}
