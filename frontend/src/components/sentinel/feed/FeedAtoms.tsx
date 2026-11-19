/**
 * FeedAtoms — 资讯行级原子 (加星 / 深读入口 / 快讯行), B4 从 SentinelHomePage 抽出。
 *
 * 只做展示与回调转发, 数据与状态由页容器 (SentinelHomePage) 持有。
 *
 * D7 收口: 热度格与实践域标签此前在三处各写一遍 (行内 map / 重复 style 对象),
 * 收敛为 HeatCells / PracticeTag 两个原子, 顺带省下重复的 SVG 与样式字面量。
 */
import { useNavigate } from 'react-router-dom';
import { HotspotItem, PRACTICE_DOMAIN_LABELS } from '../../../types';
import { trackInterest } from '../../../lib/interest';
import { ReactionButtons } from '../ReactionButtons';
import type { ReactionTarget, ReactionType } from '../../../hooks/useReactions';
import { heatCells, heatOf, ICON_ARROW_D, labelOf, relTime, safeHref, tagColorOf } from './feedModel';

/** 页面统一的"每行"绑定: 收藏 / 赞踩 / 兴趣域高亮, 避免每个区块重复 8 个 prop */
export interface FeedRowBinding {
  interestDomains: string[];
  isFavorite: (id: string) => boolean;
  onStar: (item: HotspotItem) => void;
  reactionOf: (id: string) => ReactionType | undefined;
  onReact: (item: ReactionTarget, type: ReactionType) => void;
  showReactions: boolean;
}

/** 热度格 (0–5 格): 头条 / 次级 / 快讯行共用同一结构 */
export function HeatCells({ n }: { n: number }) {
  return <>{heatCells(n).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}</>;
}

/**
 * 实践域标签: 命中兴趣方向时高亮。
 * outlined=true 为次级重点区的描边变体 (常态描边, 未命中走 dim 色)。
 */
export function PracticeTag({ domain, hit, outlined }: { domain: string; hit: boolean; outlined?: boolean }) {
  const label = PRACTICE_DOMAIN_LABELS[domain] || domain;
  const title = hit ? '命中你的兴趣方向, 已优先展示' : '实践域';
  if (outlined) {
    return (
      <span className="tag" title={title} style={hit
        ? { color: 'var(--sn-mint, #00e5a0)', background: 'transparent', border: '1px solid var(--sn-mint, #00e5a0)' }
        : { color: 'var(--sn-text-dim)', background: 'transparent', border: '1px solid var(--sn-line)' }}>{label}</span>
    );
  }
  return (
    <span className="tag" title={title} style={hit
      ? { color: 'var(--sn-mint, #00e5a0)', border: '1px solid var(--sn-mint, #00e5a0)' }
      : undefined}>{label}</span>
  );
}

/** 加星按钮: 样式类复用 index.css 的 .agihunt-card-star, 颜色走 --sn-* token */
export function StarButton({ item, fav, onToggle }: { item: HotspotItem; fav: boolean; onToggle: (item: HotspotItem) => void }) {
  return (
    <button
      type="button"
      className="agihunt-card-star"
      style={{ color: fav ? 'var(--sn-mint)' : 'var(--sn-ink-3)' }}
      title={fav ? '取消收藏' : '收藏'}
      aria-label={`${fav ? '取消收藏' : '收藏'}：${item.title}`}
      aria-pressed={fav}
      onClick={e => { e.stopPropagation(); onToggle(item); }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill={fav ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    </button>
  );
}

/** tag 右侧的"进入深度阅读"金黄入口, 跳转后由 DeepReadPage 自动开始分析 */
export function DeepReadChip({ id, label = '深读', itemTitle }: { id: string; label?: string; itemTitle?: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="dr-link"
      title="进入深度阅读"
      aria-label={itemTitle ? `对「${itemTitle}」进入深度阅读` : undefined}
      onClick={e => { e.stopPropagation(); navigate(`/deep/hotspot/${id}`); }}
    >
      {label}
      <svg width="12" height="12" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d={ICON_ARROW_D} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
  );
}

/** 快讯行: brief 快讯流与 deep 深度视图共用同一行结构 (P2 2026-09-27 抽取) */
export function FlashRow({ item, binding, onOpen }: {
  item: HotspotItem;
  binding: FeedRowBinding;
  /** R-15: 打开原文即记为已读 (会话内), 驱动「待读 → 已读」递进 */
  onOpen?: (id: string) => void;
}) {
  const href = safeHref(item.url);
  const fav = binding.isFavorite(item.id);
  const heat = heatOf(item);
  return (
    <li className="flash-item">
      <span className="flash-time num">{relTime(item.published_at)}</span>
      <div className="flash-body">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" onClick={() => { trackInterest(item.id, 'view'); onOpen?.(item.id); }}><span className="flash-title">{item.title}</span></a>
        ) : (
          <span className="flash-title">{item.title}</span>
        )}
        <span className="flash-tags">
          <span className="tag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span>
          {item.practice_domain && (
            <PracticeTag domain={item.practice_domain} hit={binding.interestDomains.includes(item.practice_domain)} />
          )}
          <DeepReadChip id={item.id} itemTitle={item.title} />
        </span>
      </div>
      <div className="flash-side">
        <span className="flash-src">{item.source}</span>
        <span className="mini-heat" aria-hidden="true">
          <HeatCells n={heat} />
        </span>
      </div>
      {binding.showReactions && <ReactionButtons item={item} current={binding.reactionOf(item.id)} onReact={binding.onReact} />}
      <StarButton item={item} fav={fav} onToggle={binding.onStar} />
    </li>
  );
}
