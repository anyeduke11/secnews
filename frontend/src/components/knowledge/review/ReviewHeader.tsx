/**
 * ReviewHeader — 间隔复习标题条 (B5 从 ReviewMode 抽出, 五种状态共用)
 */
import { Icon } from '../../Icon';

export function ReviewHeader({ desc }: { desc?: string }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-2">
        <Icon size={16}>
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </Icon>
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          间隔复习
        </h3>
      </div>
      {desc && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          {desc}
        </p>
      )}
    </div>
  );
}
