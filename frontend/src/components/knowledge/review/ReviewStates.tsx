/**
 * ReviewStates — 间隔复习的标题条与三种前置状态 (加载 / 错误 / 空队列),
 * B5 从 ReviewMode 原样抽出, DOM 与文案未改。
 */
import { Icon } from '../../Icon';
import { ReviewHeader } from './ReviewHeader';

/** 加载状态 */
export function ReviewLoading() {
  return (
    <div className="space-y-3">
      <ReviewHeader desc="SM-2 抽认卡复习，巩固长期记忆。" />
      <div className="flex items-center justify-center py-16">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          加载复习队列…
        </div>
      </div>
    </div>
  );
}

/** 错误状态 */
export function ReviewError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="space-y-3">
      <ReviewHeader />
      <div
        className="rounded-[var(--radius-md)] p-3 text-xs"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
          border: '1px solid var(--color-error)',
          color: 'var(--color-error)',
        }}
      >
        <div className="flex items-center gap-2">
          <Icon size={14}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </Icon>
          {error}
          <button
            type="button"
            className="ml-auto underline hover:no-underline"
            onClick={onRetry}
          >
            重试
          </button>
        </div>
      </div>
    </div>
  );
}

/** 空状态 (无到期复习) */
export function ReviewEmpty({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="space-y-3">
      <ReviewHeader />
      <div
        className="rounded-[var(--radius-md)] p-6 text-center"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-3"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-info) 10%, transparent)',
            color: 'var(--color-info)',
          }}
        >
          <Icon size={20}>
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </Icon>
        </div>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
          暂无到期复习
        </p>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          当前没有到期的复习条目。在「深度阅读」中打开知识条目（或收藏）后，
          它们会自动进入复习队列（1 天后到期）。
        </p>
        <button
          type="button"
          className="mt-3 px-3 py-1.5 text-xs rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-info) 12%, transparent)',
            color: 'var(--color-info)',
            border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)',
          }}
          onClick={onRefresh}
        >
          刷新
        </button>
      </div>
    </div>
  );
}
