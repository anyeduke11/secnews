/**
 * FeedMustRead — 今日必读区块 (头条 story-top + 次级重点), B4 从 SentinelHomePage 抽出。
 * 纯展示: 取数 / 收藏 / 赞踩均由页容器经 binding 注入。
 *
 * D7 收口: 热度格改用 HeatCells 原子, 实践域标签改用 PracticeTag 原子,
 * 静态描边样式下沉 CSS 类 (行内 style 只保留动态色值)。
 */
import { useNavigate } from 'react-router-dom';
import { HotspotItem, plainSummary } from '../../../types';
import { trackInterest } from '../../../lib/interest';
import { ReactionButtons } from '../ReactionButtons';
import { DeepReadChip, HeatCells, PracticeTag, StarButton, type FeedRowBinding } from './FeedAtoms';
import { heatOf, ICON_ARROW_D, labelOf, relTime, safeHref, tagColorOf } from './feedModel';

export function FeedMustRead({ lead, secondaries, itemsCount, binding }: {
  lead: HotspotItem | null;
  secondaries: HotspotItem[];
  itemsCount: number;
  binding: FeedRowBinding;
}) {
  const navigate = useNavigate();
  const leadHref = lead ? safeHref(lead.url) : null;
  const leadHeat = lead ? heatOf(lead) : 0;
  return (
    <section aria-label="今日必读" data-testid="feed-must-read">
      <div className="flash-head">
        <h2>今日必读</h2>
        <span className="flash-count num">TOP {Math.min(itemsCount, 3)} · 评分优先</span>
      </div>
      {/* 头条 */}
      {lead && leadHref && (
        <article className="story-top">
          <div className="meta-row">
            <span className="tag" style={{ '--sn-tag-c': tagColorOf(lead.category) } as React.CSSProperties}><i aria-hidden="true" />{labelOf(lead.category)}</span>
            <DeepReadChip id={lead.id} label="进入深度阅读" itemTitle={lead.title} />
            <span className="src">{lead.source}</span>
            <span className="time num">{relTime(lead.published_at)}</span>
            <span className="time num">评分 {Math.round(lead.score ?? lead.quality_score ?? 0)}</span>
          </div>
          <h1 className="headline">
            <a href={leadHref} target="_blank" rel="noopener noreferrer" onClick={() => trackInterest(lead.id, 'view')}>{lead.title}</a>
          </h1>
          {(() => { const s = plainSummary(lead.summary); return s ? <p className="standfirst">{s}</p> : null; })()}
          <div className="head-foot">
            <div className="heatbox" aria-label={`当前热度 ${leadHeat} / 5`}>
              <span className="heat-cells" aria-hidden="true">
                <HeatCells n={leadHeat} />
              </span>
              <span className="heat-num">{leadHeat}/5</span>
            </div>
            {binding.showReactions && <ReactionButtons item={lead} current={binding.reactionOf(lead.id)} onReact={binding.onReact} />}
            <StarButton item={lead} fav={binding.isFavorite(lead.id)} onToggle={binding.onStar} />
            <button className="readmore" onClick={() => navigate(`/deep/hotspot/${lead.id}`)}>
              进入深度阅读
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d={ICON_ARROW_D} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </div>
        </article>
      )}

      {/* 次级重点 */}
      {secondaries.length > 0 && (
        <section className="secondary" aria-label="次级重点">
          {secondaries.map((item, idx) => {
            const href = safeHref(item.url);
            return (
              <div className="sub-item" key={item.id}>
                <span className="sub-index num">{String(idx + 2).padStart(2, '0')}</span>
                <div className="sub-body">
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" onClick={() => trackInterest(item.id, 'view')}><div className="sub-title">{item.title}</div></a>
                  ) : (
                    <div className="sub-title">{item.title}</div>
                  )}
                  <div className="sub-meta">
                    <span className="src">{item.source}</span>
                    <span className="time num">{relTime(item.published_at)}</span>
                    <span className="mini-heat" aria-hidden="true">
                      <HeatCells n={heatOf(item)} />
                    </span>
                    <span className="ftag ftag-outline" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span>
                    {item.practice_domain && (
                      <PracticeTag
                        domain={item.practice_domain}
                        hit={binding.interestDomains.includes(item.practice_domain)}
                        outlined
                      />
                    )}
                    <DeepReadChip id={item.id} itemTitle={item.title} />
                    {binding.showReactions && <ReactionButtons item={item} current={binding.reactionOf(item.id)} onReact={binding.onReact} />}
                    <StarButton item={item} fav={binding.isFavorite(item.id)} onToggle={binding.onStar} />
                  </div>
                </div>
              </div>
            );
          })}
        </section>
      )}
    </section>
  );
}
