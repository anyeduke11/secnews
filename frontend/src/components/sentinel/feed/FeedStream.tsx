/**
 * FeedStream — 资讯流域块: 精选视图 / 深度视图 / 待读(告警) / 已读。
 * B4 从 SentinelHomePage 抽出; 取数与模式判定留在页容器, 这里只做分支渲染。
 *
 * D7 收口:
 *   - NewsAlertList 改为按需加载 (alert 模式才需要), 不再常驻首屏 chunk;
 *   - 空态收敛到 FeedPanel 原子 (不再各带一份圆环 SVG)。
 */
import { lazy, Suspense } from 'react';
import { HotspotItem } from '../../../types';
import { trackInterest } from '../../../lib/interest';
import type { PickedItem } from '../../../api/secnews';
import type { QueryState } from '../../../hooks/useQuery';
import { ReactionButtons } from '../ReactionButtons';
import { FeedPanel, FeedSkeleton } from './FeedStates';
import { FlashRow, type FeedRowBinding } from './FeedAtoms';
import { labelOf, relTime, safeHref, tagColorOf } from './feedModel';

/**
 * 告警列表按需加载: 只有 alert 模式会渲染它, 常驻首屏 chunk 纯属浪费带宽。
 * 挂载期回退与组件自身的载入态 DOM 一致 (news-alert-list > na-empty)。
 */
const NewsAlertList = lazy(() =>
  import('../NewsAlertList').then(m => ({ default: m.NewsAlertList }))
);

/** 精选视图 (P2 2026-09-27): 独立数据源, 不混排常规快讯流 */
export function FeedPicked({ state, items, binding }: {
  state: QueryState;
  items: PickedItem[] | undefined;
  binding: FeedRowBinding;
}) {
  if (state === 'loading') return <FeedSkeleton />;
  if (!items || items.length === 0) {
    return <FeedPanel icon="star" title="暂无精选" desc="下一轮采集后生成 — pick_score 由采集尾部落列。" />;
  }
  return (
    <section aria-label="精选资讯">
      <div className="flash-head">
        <h2>精选资讯</h2>
        <span className="flash-count num">{items.length} ITEMS · PICK SCORE DESC</span>
      </div>
      <ul className="flash-list">
        {items.map(item => {
          const href = safeHref(item.url);
          return (
            <li className="flash-item" key={item.id}>
              <span className="flash-time num">{relTime(item.published_at)}</span>
              <div className="flash-body">
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" onClick={() => trackInterest(item.id, 'view')}><span className="flash-title">{item.title}</span></a>
                ) : (
                  <span className="flash-title">{item.title}</span>
                )}
                <span className="flash-tags">
                  <span className="badge b-ok">精选</span>
                  <span className="pick-score num" title="pick_score = 质量 + 关注域 + 收藏源 + 时效">{item.pick_score}</span>
                  <span className="tag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span>
                </span>
              </div>
              <div className="flash-side">
                <span className="flash-src">{item.source}</span>
              </div>
              {binding.showReactions && <ReactionButtons item={item} current={binding.reactionOf(item.id)} onReact={binding.onReact} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** 深度视图 (P2 2026-09-27): 长文候选过滤, 纯前端 */
export function FeedDeep({ items, binding }: { items: HotspotItem[]; binding: FeedRowBinding }) {
  if (items.length === 0) {
    return <FeedPanel icon="clock" title="当前无深读候选" desc="在条目上收藏后归入深读。" />;
  }
  return (
    <section aria-label="深度阅读">
      <div className="flash-head">
        <h2>深度阅读</h2>
        <span className="flash-count num">{items.length} ITEMS · 长文候选</span>
      </div>
      <ul className="flash-list">
        {items.map(item => (
          <FlashRow key={item.id} item={item} binding={binding} />
        ))}
      </ul>
    </section>
  );
}

/** 待读 / 告警 (2026-09-27: alert 接真告警列表) + 游标分页 */
export function FeedQueue({ mode, toRead, binding, onOpen, page, totalPages, total, hasMore, loadingPage, itemsCount, latestIngestionCount, latestIngestionAt, onPrev, onNext }: {
  mode: string;
  toRead: HotspotItem[];
  binding: FeedRowBinding;
  onOpen: (id: string) => void;
  page: number;
  totalPages: number;
  total: number;
  hasMore: boolean;
  loadingPage: boolean;
  itemsCount: number;
  latestIngestionCount: number;
  latestIngestionAt: string | null;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <section aria-label={mode === 'alert' ? '资讯告警' : '待读'} data-testid={mode === 'alert' ? undefined : 'feed-to-read'}>
      {mode === 'alert' ? (
        <Suspense fallback={<div className="news-alert-list"><p className="na-empty">载入中…</p></div>}>
          <NewsAlertList />
        </Suspense>
      ) : (
        <>
          <div className="flash-head">
            <h2>待读</h2>
            <span className="flash-count num">
              PAGE {page} · {itemsCount} ITEMS
              {latestIngestionCount ? ` · 最近一轮 +${latestIngestionCount}` : ''}
              {latestIngestionAt ? ` · ${relTime(latestIngestionAt)}` : ''}
            </span>
          </div>
          {toRead.length > 0 ? (
            <ul className="flash-list">
              {toRead.map(item => (
                <FlashRow key={item.id} item={item} binding={binding} onOpen={onOpen} />
              ))}
            </ul>
          ) : (
            <div className="empty-panel" data-testid="feed-to-read-empty">
              <p>本页条目均已打开</p>
              <p className="sub">翻到下一页继续，或在上方「已读」回看</p>
            </div>
          )}

          {/* 游标分页控件 */}
          <div className="pagination-row">
            <button
              type="button"
              className="pagination-btn"
              aria-label="上一页"
              disabled={page <= 1 || loadingPage}
              onClick={onPrev}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
              <span>上一页</span>
            </button>
            <span className="page-indicator" aria-live="polite">
              第 <strong>{page}</strong> / {totalPages} 页 · 共 {total} 篇
            </span>
            <button
              type="button"
              className="pagination-btn"
              aria-label="下一页"
              disabled={!hasMore || loadingPage}
              onClick={onNext}
            >
              <span>下一页</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/** 已读 — 仅本次会话真实打开过的条目, 无数据时整段不渲染 */
export function FeedRead({ items, binding, onOpen }: {
  items: HotspotItem[];
  binding: FeedRowBinding;
  onOpen: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section aria-label="已读" data-testid="feed-read">
      <div className="flash-head">
        <h2>已读</h2>
        <span className="flash-count num">{items.length} ITEMS · 本次会话</span>
      </div>
      <ul className="flash-list">
        {items.map(item => (
          <FlashRow key={item.id} item={item} binding={binding} onOpen={onOpen} />
        ))}
      </ul>
    </section>
  );
}
