/**
 * DeepReaderComposer — 选区批注表单展示区块 (B5.6 拆分: 从 DeepReaderPage 抽出)
 *
 * DOM 结构 / 内联 style / aria 文案逐字保留; 状态与提交动作由容器传入。
 */
export function DeepReaderComposer({
  selQuote,
  formOpen,
  noteText,
  posting,
  onNoteTextChange,
  onSubmit,
  onCancel,
  onOpenForm,
}: {
  selQuote: string;
  formOpen: boolean;
  noteText: string;
  posting: boolean;
  onNoteTextChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  onOpenForm: () => void;
}) {
  return (
    <div style={{ maxWidth: 820, margin: '18px auto 0' }} data-testid="ann-composer">
      <div className="pgx-quote-box" style={{ border: '1px solid var(--line-strong)', borderRadius: 'var(--radius-md)', padding: 12, background: 'var(--bg-card)' }}>
        <div className="pgx-quote-text" style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>
          批注引用:「{selQuote}」
        </div>
        {formOpen ? (
          <div style={{ display: 'flex', gap: 8, flexDirection: 'column' }}>
            <textarea
              className="editorial-input"
              aria-label="批注内容"
              rows={3}
              value={noteText}
              onChange={e => onNoteTextChange(e.target.value)}
              placeholder="写下你的批注…"
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="ed-btn primary" disabled={posting || !noteText.trim()} onClick={onSubmit}>
                {posting ? '保存中…' : '保存批注'}
              </button>
              <button type="button" className="ed-btn" onClick={onCancel}>
                取消
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="ed-btn" onClick={onOpenForm}>
            批注选中内容
          </button>
        )}
      </div>
    </div>
  );
}
