// 拆分自 ItemDetailDialog.tsx: 弹窗顶部标题栏 (图标 + 标题 + 关闭按钮), 纯展示件。
import { Icon } from '../primitives/Icon';

type ItemDetailDialogHeaderProps = {
  onClose: () => void;
};

export function ItemDetailDialogHeader({ onClose }: ItemDetailDialogHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
        <Icon size={16}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </Icon>
        条目详情
      </h3>
      <button
        onClick={onClose}
        className="btn-ghost px-2 py-0.5 text-xs"
        aria-label="关闭"
      >
        <Icon size={14}>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </Icon>
      </button>
    </div>
  );
}