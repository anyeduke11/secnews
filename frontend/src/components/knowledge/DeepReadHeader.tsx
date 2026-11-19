/**
 * DeepReadHeader — 深度阅读 引导提示 + 顶部导航栏 (B5 续拆自 DeepReadMode)
 *
 * 纯展示: JSX 逐字搬运, DOM 结构与原容器一致 (Fragment 不产生元素)。
 */
import { Icon } from '../../primitives/Icon';
import { OnboardingHint } from '../layout/OnboardingHint';
import type { DeepReadItem } from './deepReadModeModel';

export function DeepReadHeader({ item, onBack }: { item: DeepReadItem | null; onBack: () => void }) {
  return (
    <>
      <OnboardingHint storageKey="kb-deepread" title="深度阅读模式">
        <p>对单个知识条目做深度阅读，查看完整内容与摘要。</p>
      </OnboardingHint>

      {/* 顶部导航栏 */}
      <div
        className="flex items-center gap-3 rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 text-xs flex items-center gap-1.5"
          style={{ color: 'var(--text-secondary)' }}
          onClick={onBack}
          aria-label="返回知识库"
        >
          <Icon size={12}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h1 className="text-sm font-bold flex-1" style={{ color: 'var(--text-primary)' }}>
          深度阅读
        </h1>
        {item && (
          <span
            className="text-[10px] px-2 py-0.5 rounded font-mono"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-ai) 12%, transparent)',
              color: 'var(--color-ai)',
            }}
          >
            {item.domain || 'unknown'}
          </span>
        )}
      </div>
    </>
  );
}
