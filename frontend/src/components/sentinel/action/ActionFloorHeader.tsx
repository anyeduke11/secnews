/**
 * ActionFloorHeader — 行动层页头 + 数据源降级提示条 (B5 从 SentinelActionPage 抽出)
 *
 * 纯展示: kicker / 标题 / 副标题为静态文案; notice 由容器 load() 的失败计数驱动。
 * 两个兄弟节点用 Fragment 返回, DOM 结构与拆分前一致。
 */

interface ActionFloorHeaderProps {
  /** 有 N 个数据源本次未返回时的提示文案 (null = 不渲染提示条) */
  notice: string | null;
}

export function ActionFloorHeader({ notice }: ActionFloorHeaderProps) {
  return (
    <>
      <header className="ac-head">
        <div>
          <span className="ac-kicker">ACTION FLOOR</span>
          <h1 className="ac-h1">今日<b>行动</b><span> / 04</span></h1>
          <p className="ac-sub">案件从主张到产物的执行闭环在上方指挥台推进；复习栈与判读队列在其下同步维护。</p>
        </div>
      </header>

      {notice && (
        <p className="ac-banner" role="status">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M6.5 1.8l5 9H1.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M6.5 5.2v2.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="6.5" cy="9.2" r=".7" fill="currentColor" /></svg>
          {notice}
        </p>
      )}
    </>
  );
}
