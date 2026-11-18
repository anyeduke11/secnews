/**
 * ReviewStackPanel — 行动层「复习栈 · SM-2」区块 (B5 从 SentinelActionPage 抽出)
 *
 * 纯展示 + props 回调: 取数 (GET /api/reviews/due?enrich=1 · /api/reviews/stats) 与
 * 评分写操作 (POST /api/reviews/{type}/{id}/grade · undo) 仍由容器编排, 本文件只渲染
 * loading / 空态 / 卡片层叠 + 反馈条 + 扩展入口。DOM 与 class 与拆分前逐字一致。
 */
import type { RvView } from '../review/ReviewOverlay';
import {
  GRADE_DEFS, relTime, reviewTitle, safeHref, stamp,
  type JustGraded, type ReviewRow, type ReviewStats, type WriteState,
} from './actionModel';

interface ReviewStackPanelProps {
  loading: boolean;
  reviewStats: ReviewStats | null;
  /** 视觉层数内的到期卡片 (顶层可操作, 其后为后续卡) */
  stack: ReviewRow[];
  top: ReviewRow | null;
  /** 本次会话已评分张数 */
  graded: number;
  /** 行级写入态: key = review id */
  reviewState: Record<string, WriteState>;
  justGraded: JustGraded | null;
  onGrade: (row: ReviewRow, grade: number) => void;
  onUndo: () => void;
  onOpenOverlay: (view: RvView) => void;
  onGoNews: () => void;
}

export function ReviewStackPanel({
  loading,
  reviewStats,
  stack,
  top,
  graded,
  reviewState,
  justGraded,
  onGrade,
  onUndo,
  onOpenOverlay,
  onGoNews,
}: ReviewStackPanelProps) {
  return (
    <section className="ac-panel ac-review" aria-labelledby="ac-h-review">
      <header className="ac-ph">
        <h2 id="ac-h-review">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 4.5L6.5 2 11 4.5 6.5 7z" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /><path d="M2 7.5L6.5 10 11 7.5" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /></svg>
          复习栈
        </h2>
        <span className="ac-phn num">{reviewStats ? `${reviewStats.due} DUE` : '…'}</span>
      </header>

      {loading ? (
        <div className="ac-load" aria-busy="true"><div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" /></div>
      ) : !top ? (
        <div className="ac-empty">
          <div className="ac-empty-ring" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.5" /><path d="M9 5.6V9l2.3 1.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          </div>
          <h3>今日复习栈已清空</h3>
          <p>到期队列为空。SM-2 会在下一次到期时把卡片排回来。</p>
        </div>
      ) : (
        <>
          <div className="ac-stack" aria-label={`复习栈 ${stack.length} 张到期卡片，最上层为当前待评分卡片`}>
            {/* 绝对定位层序: 后续卡先入 DOM, 顶层卡最后渲染才压在上方 */}
            {stack.slice(1).map((row, i) => {
              const depth = stack.length - 1 - i; // 队列里往后第几张
              return (
                <article key={row.id} className={`ac-card ${depth >= 2 ? 'c2' : 'c1'}`} aria-hidden="true">
                  <div className="ac-cmeta">
                    <span className="ac-cdeck">{row.entity_type.toUpperCase()}</span>
                    <span>往后第 {depth} 张</span>
                  </div>
                  <p className="ac-ct" title={reviewTitle(row)}>{reviewTitle(row)}</p>
                </article>
              );
            })}
            {top && (() => {
              const state = reviewState[top.id];
              const href = safeHref(top.url);
              return (
                <article className="ac-card top">
                  <div className="ac-cmeta">
                    <span className="ac-cdeck">{top.entity_type.toUpperCase()}</span>
                    <span>本次已评 {graded} 张</span>
                  </div>
                  <p className="ac-ct" title={reviewTitle(top)}>{reviewTitle(top)}</p>
                  {top.title && <p className="ac-chint num" title={top.entity_id}>{top.entity_id}</p>}
                  <p className="ac-chint">
                    {relTime(top.last_reviewed_at)}评过一次。
                    {href && (
                      <> <a href={href} target="_blank" rel="noopener noreferrer">查看原文</a></>
                    )}
                  </p>
                  <div className="ac-sm2">
                    <span>EF <b className="num">{Number(top.easiness).toFixed(2)}</b></span>
                    <span>间隔 <b className="num">{top.interval}d</b></span>
                    <span>重复 <b className="num">{top.repetitions}</b></span>
                    <span>到期 <b className="num">{stamp(top.due_at)}</b></span>
                  </div>
                  <div className="ac-grade">
                    {GRADE_DEFS.map(g => (
                      <button
                        key={g.label}
                        type="button"
                        className="ac-gbtn"
                        title={`${g.label} → grade ${g.grade}：${g.hint}`}
                        disabled={state === 'saving'}
                        onClick={() => onGrade(top, g.grade)}
                      >
                        {state === 'saving' ? '提交中' : g.label}
                        <span className="g num">g{g.grade}</span>
                      </button>
                    ))}
                  </div>
                  {state === 'fail' && <p className="ac-note is-fail" role="status">评分未写入成功，卡片仍在今日队列中。</p>}
                </article>
              );
            })()}
          </div>
          <div className="ac-sched">
            <span className="num ac-now">今日 {reviewStats?.due ?? stack.length}</span>
            <i aria-hidden="true" />
            <span className="num">在册 {reviewStats?.total ?? '--'}</span>
            <i aria-hidden="true" />
            <span className="num">平均 EF {reviewStats ? Number(reviewStats.avg_easiness).toFixed(2) : '--'}</span>
          </div>
          <p className="ac-self">自评机制：记得牢，间隔拉长；模糊，近日再见；忘光，回资讯页重读原文。</p>
          <a className="ac-link" href="/" onClick={e => { e.preventDefault(); onGoNews(); }}>
            去资讯页重读原文
            <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </a>
        </>
      )}
      {justGraded && (
        <div className="ac-gfeedback" role="status">
          <span>
            已评「{justGraded.title}」
            {justGraded.interval != null && (
              <> · <b className="is-next num">下次 {justGraded.interval} 天后见</b></>
            )}
          </span>
          <button type="button" className="ac-undobtn" onClick={() => { void onUndo(); }}>
            撤销
          </button>
        </div>
      )}
      <div className="ac-rentry" aria-label="复习栈扩展入口">
        <button type="button" className="ac-dbtn" onClick={() => onOpenOverlay('session')}>
          专注复习
        </button>
        <button type="button" className="ac-dbtn" onClick={() => onOpenOverlay('manage')}>
          卡片管理
        </button>
      </div>
    </section>
  );
}
