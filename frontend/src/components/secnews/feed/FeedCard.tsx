/**
 * FeedCard — 单条资讯卡片
 *
 * 报纸风格的单条安全资讯展示。
 * DEV-0176 T0.4: 显示实践域徽标 (命中兴趣域时高亮, 高亮名单由接口 interest_domains 回传)。
 */
import { PRACTICE_DOMAIN_LABELS } from '../../../types';
import { useReactions } from '../../../hooks/useReactions';
import { ReactionButtons, useReactionAction } from '../../sentinel/ReactionButtons';

interface FeedCardProps {
  item: {
    id: string;
    title: string;
    url: string;
    source: string;
    category: string;
    summary?: string;
    published_at?: string;
    practice_domain?: string | null;
  };
  /** 本次请求的兴趣域 (来自响应 interest_domains); 命中时徽标高亮 */
  interestDomains?: string[];
}

export function FeedCard({ item, interestDomains }: FeedCardProps) {
  const practiceLabel = item.practice_domain
    ? PRACTICE_DOMAIN_LABELS[item.practice_domain] || item.practice_domain
    : null;
  const interestHit = !!practiceLabel && !!interestDomains?.includes(item.practice_domain!);
  // DEV-0326: 赞/踩覆盖报纸流 — 卡片根由 <a> 改为 <div> (内层 <a> 承载跳转, 避免 button 嵌 a 非法)
  const { reactionOf, available: reactionsAvailable } = useReactions();
  const doReact = useReactionAction();

  return (
    <div
      className="p-3 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
      style={{
        border: '1px solid var(--border-color)',
        ...(interestHit ? { borderColor: 'var(--accent, #00bcd4)' } : {}),
      }}
    >
      <a href={item.url} target="_blank" rel="noopener noreferrer" className="block">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium leading-snug line-clamp-2" style={{ color: 'var(--text-primary)' }}>
              {item.title}
            </h3>
            {item.summary && (
              <p className="text-xs mt-1 line-clamp-2 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {item.summary}
              </p>
            )}
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                {item.source}
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                {item.category}
              </span>
              {practiceLabel && (
                <span
                  data-testid="practice-domain-badge"
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={
                    interestHit
                      ? { backgroundColor: 'var(--accent-soft, rgba(0,188,212,0.15))', color: 'var(--accent, #00bcd4)' }
                      : { backgroundColor: 'var(--bg-secondary)', color: 'var(--text-muted)' }
                  }
                  title={interestHit ? '命中你的兴趣方向, 已优先展示' : '实践域'}
                >
                  {practiceLabel}
                </span>
              )}
            </div>
          </div>
        </div>
      </a>
      {reactionsAvailable && (
        <div className="mt-1.5">
          <ReactionButtons item={item} current={reactionOf(item.id)} onReact={doReact} />
        </div>
      )}
    </div>
  );
}
