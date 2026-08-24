/**
 * SecNewsHeader — 看板页头组件
 *
 * 显示标题 + 当前日期 + 刷新按钮。
 */
interface SecNewsHeaderProps {
  title?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function SecNewsHeader({ title = '安全看板', onRefresh, refreshing }: SecNewsHeaderProps) {
  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  return (
    <header className="flex items-center justify-between mb-4">
      <div>
        <h1 className="text-lg font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{today}</p>
      </div>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
        >
          {refreshing ? '刷新中...' : '刷新'}
        </button>
      )}
    </header>
  );
}
