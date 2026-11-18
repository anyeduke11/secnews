/**
 * CompoundingStates — 复利仪表盘 加载/错误/空 三态展示区块 (B5 续拆自 KnowledgeCompoundingDashboard)
 *
 * 纯展示, JSX 逐字搬运; DOM 结构与原容器一致。
 */
import { Icon } from '../Icon';

/* ── Loading state ──────────────────────────────────────────── */

export function CompoundingSkeleton() {
  return (
    <div className="space-y-3" data-compounding-dashboard="loading">
      {[1, 2, 3, 4].map(i => (
        <div
          key={i}
          className="rounded-[var(--radius-md)] p-3.5 animate-shimmer"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="h-3 w-24 mb-3" style={{ backgroundColor: 'var(--border-color)', borderRadius: 'var(--radius-sm)' }} />
          <div className="h-28" style={{ backgroundColor: 'var(--border-subtle)', borderRadius: 'var(--radius-sm)' }} />
        </div>
      ))}
    </div>
  );
}

/* ── Error state ────────────────────────────────────────────── */

export function CompoundingError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-4 text-center"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      data-compounding-dashboard="error"
    >
      <div className="flex items-center justify-center gap-2 mb-2" style={{ color: '#ef4444' }}>
        <Icon size={16}>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </Icon>
        <span className="text-sm font-semibold">加载失败</span>
      </div>
      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>{error}</p>
      <button
        className="px-3 py-1.5 text-xs rounded-[var(--radius-sm)] font-medium"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--area-accent, var(--color-success)) 10%, transparent)',
          color: 'var(--area-accent, var(--color-success))',
          border: '1px solid color-mix(in srgb, var(--area-accent, var(--color-success)) 30%, transparent)',
        }}
        onClick={onRetry}
      >
        重试
      </button>
    </div>
  );
}

/* ── Empty state ────────────────────────────────────────────── */

export function CompoundingEmpty() {
  return (
    <div
      className="rounded-[var(--radius-md)] p-6 text-center"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      data-compounding-dashboard="empty"
    >
      <div className="flex items-center justify-center gap-2 mb-2" style={{ color: 'var(--text-muted)' }}>
        <Icon size={20}>
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </Icon>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>暂无复利数据</span>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        当天有知识条目被处理时，复利仪表盘将自动填充。
      </p>
    </div>
  );
}
