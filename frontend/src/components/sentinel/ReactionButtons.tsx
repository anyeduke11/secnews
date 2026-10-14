/**
 * ReactionButtons — 资讯赞/踩按钮组 (DEV-0311)。
 *
 * 视觉: 复用 .agihunt-card-star 按钮壳 (与 StarButton 同语言 — 圆形小按钮);
 * like 高亮用 --sn-mint (同收藏激活色), dislike 高亮用 --sn-cat-sec (降调警示色)。
 * 交互: 同键=取消 / 异键=切换 (语义由 useReactions + 后端互斥保证);
 * 点击不冒泡 (卡片可能整体可点)。
 */
import { useReactions, type ReactionTarget, type ReactionType } from '../../hooks/useReactions';

/**
 * useReactionAction — 赞/踩点击处理器 (DEV-0326)。
 *
 * 4 个资讯面 (首页精选/告警/报纸流/历史) 共用的调用壳; 赞/踩对全部条目放行
 * 并由后端持久化 (含非安全领域/未归类, 存哨兵域 weight 0), 无"丢弃"分支。
 */
export function useReactionAction(): (item: ReactionTarget, type: ReactionType) => Promise<void> {
  return useReactions().react;
}

function ThumbIcon({ down = false, filled = false }: { down?: boolean; filled?: boolean }) {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {down ? (
        <>
          <path d="M17 14V2" />
          <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
        </>
      ) : (
        <>
          <path d="M7 10v12" />
          <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
        </>
      )}
    </svg>
  );
}

export function ReactionButtons<T extends ReactionTarget>({
  item,
  current,
  onReact,
}: {
  item: T;
  current: ReactionType | undefined;
  onReact: (item: T, type: ReactionType) => void;
}) {
  const liked = current === 'like';
  const disliked = current === 'dislike';
  return (
    <span className="sn-reactions" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
      <button
        type="button"
        className="agihunt-card-star"
        style={{ color: liked ? 'var(--sn-mint)' : 'var(--sn-ink-3)' }}
        title={liked ? '取消点赞' : '点赞'}
        aria-label={`${liked ? '取消点赞' : '点赞'}：${item.title}`}
        aria-pressed={liked}
        onClick={e => {
          e.stopPropagation();
          onReact(item, 'like');
        }}
      >
        <ThumbIcon filled={liked} />
      </button>
      <button
        type="button"
        className="agihunt-card-star"
        style={{ color: disliked ? 'var(--sn-cat-sec, #d4574e)' : 'var(--sn-ink-3)' }}
        title={disliked ? '取消点踩' : '点踩'}
        aria-label={`${disliked ? '取消点踩' : '点踩'}：${item.title}`}
        aria-pressed={disliked}
        onClick={e => {
          e.stopPropagation();
          onReact(item, 'dislike');
        }}
      >
        <ThumbIcon down filled={disliked} />
      </button>
    </span>
  );
}