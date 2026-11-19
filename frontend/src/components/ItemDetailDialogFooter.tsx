// 拆分自 ItemDetailDialog.tsx: 底部动作栏 (保存 / 删除 + toast)
// 与删除确认块; 回调与状态仍由主组件持有。

type ItemDetailDialogFooterProps = {
  saving: boolean;
  deleting: boolean;
  confirmDelete: boolean;
  toast: string | null;
  onSave: () => void;
  onRequestDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
};

export function ItemDetailDialogFooter({
  saving,
  deleting,
  confirmDelete,
  toast,
  onSave,
  onRequestDelete,
  onCancelDelete,
  onDelete,
}: ItemDetailDialogFooterProps) {
  return (
    <>
      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={onSave}
          disabled={saving}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ color: 'var(--color-ai)', opacity: saving ? 0.6 : 1 }}
        >
          {saving ? '保存中…' : '保存修改'}
        </button>
        <button
          onClick={onRequestDelete}
          disabled={deleting}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ color: 'var(--color-error)', opacity: deleting ? 0.6 : 1 }}
        >
          删除
        </button>
        {toast && (
          <span className="text-[10px] ml-auto" style={{
            color: toast.startsWith('✓') ? 'var(--color-ai)' : 'var(--color-error)',
          }}>
            {toast}
          </span>
        )}
      </div>

      {/* 删除确认弹窗 */}
      {confirmDelete && (
        <div
          className="rounded-[var(--radius-sm)] p-3"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--color-error)' }}
        >
          <p className="text-xs mb-2" style={{ color: 'var(--text-primary)' }}>
            确认删除此条目? 此操作不可撤销。
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onDelete}
              disabled={deleting}
              className="btn-ghost px-3 py-1 text-xs"
              style={{ color: 'var(--color-error)', opacity: deleting ? 0.6 : 1 }}
            >
              {deleting ? '删除中…' : '确认删除'}
            </button>
            <button
              onClick={onCancelDelete}
              className="btn-ghost px-3 py-1 text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </>
  );
}