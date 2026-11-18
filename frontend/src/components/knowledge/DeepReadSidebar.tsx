/**
 * DeepReadSidebar — 深度阅读 右侧侧栏 (B5 续拆自 DeepReadMode)
 *
 * 纯展示: LifecycleProgress + 相关概念 + 推荐阅读; JSX 逐字搬运,
 * 跳转动作由容器注入 onOpen (URL 拼接保持原模板不变)。
 */
import { LifecycleProgress } from './LifecycleProgress';
import type { DeepReadItem, RecommendResult } from './deepReadModeModel';

export function DeepReadSidebar({
  item,
  recommendations,
  recommendLoading,
  onOpen,
}: {
  item: DeepReadItem;
  recommendations: RecommendResult[];
  recommendLoading: boolean;
  onOpen: (id: string) => void;
}) {
  return (
    <div
      className="w-64 shrink-0 space-y-3"
      style={{ position: 'sticky', top: 'var(--space-3, 12px)' }}
    >
      {/* LifecycleProgress */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3
          className="text-[10px] font-bold uppercase tracking-wide mb-2"
          style={{ color: 'var(--text-muted)' }}
        >
          学习进度
        </h3>
        <LifecycleProgress currentStage={item.lifecycle || 'kl:raw'} />
      </section>

      {/* 相关概念 */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3
          className="text-[10px] font-bold uppercase tracking-wide mb-2"
          style={{ color: 'var(--text-muted)' }}
        >
          相关概念
        </h3>
        {item.concepts && item.concepts.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {item.concepts.map(c => (
              <span
                key={c}
                className="px-2 py-0.5 rounded text-[10px]"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-startup) 12%, transparent)',
                  color: 'var(--color-startup)',
                }}
              >
                {c}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            暂无关联概念
          </p>
        )}
      </section>

      {/* 推荐条目 */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3
          className="text-[10px] font-bold uppercase tracking-wide mb-2"
          style={{ color: 'var(--text-muted)' }}
        >
          推荐阅读
        </h3>
        {recommendLoading ? (
          <div className="flex items-center gap-1.5 py-2">
            <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</span>
          </div>
        ) : recommendations.length > 0 ? (
          <ul className="space-y-2">
            {recommendations.map((rec, i) => (
              <li key={rec.item.id}>
                <button
                  type="button"
                  className="w-full text-left text-xs leading-relaxed px-2 py-1.5 rounded-[var(--radius-sm)] transition-colors"
                  style={{ color: 'var(--text-primary)' }}
                  onClick={() => onOpen(rec.item.id)}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.backgroundColor = 'var(--bg-hover)';
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent';
                  }}
                >
                  <span className="block truncate" title={rec.item.title}>
                    {rec.item.title}
                  </span>
                  <span className="block text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    共享标签: {rec.shared_tags.join(', ')}
                  </span>
                </button>
                {i < recommendations.length - 1 && (
                  <div style={{ borderBottom: '1px solid var(--border-color)', margin: '4px 0' }} />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            暂无推荐
          </p>
        )}
      </section>
    </div>
  );
}
