// HistoryPageItem — 从 HistoryPage.tsx 拆出的历史条目卡 (纯搬迁, 行为不变).
// 职责: HotspotCard + 归档到知识库按钮 + 赞/踩按钮叠加层.

import type { HotspotItem } from '../types';
import type { ReactionType } from '../hooks/useReactions';
import { HotspotCard } from './HotspotCard';
import { ReactionButtons } from './sentinel/ReactionButtons';

interface HistoryPageItemProps {
  item: HotspotItem;
  index: number;
  isFavorited: boolean;
  onToggleFavorite: (item: HotspotItem) => void;
  isArchived: boolean;
  isArchiving: boolean;
  onArchive: (item: HotspotItem) => void;
  reactionsAvailable: boolean;
  currentReaction: ReactionType | undefined;
  onReact: (item: HotspotItem, type: ReactionType) => void;
}

export function HistoryPageItem({
  item, index, isFavorited, onToggleFavorite,
  isArchived, isArchiving, onArchive, reactionsAvailable, currentReaction, onReact,
}: HistoryPageItemProps) {
  return (
    <div className="relative">
      <HotspotCard
        item={item}
        index={index}
        isFavorited={isFavorited}
        onToggleFavorite={onToggleFavorite}
      />
      <div className="absolute bottom-2 left-2 z-10 flex items-center gap-1.5">
        <button
          type="button"
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onArchive(item); }}
          disabled={isArchived || isArchiving}
          className="btn-ghost px-1.5 py-0.5 text-[10px]"
          style={{
            backgroundColor: isArchived ? 'var(--bg-hover)' : 'var(--bg-elevated)',
            color: isArchived ? 'var(--text-muted)' : 'var(--text-secondary)',
            border: '1px solid var(--border-color)',
            opacity: isArchiving ? 0.6 : 1,
            cursor: (isArchived || isArchiving) ? 'default' : 'pointer',
          }}
          title={isArchived ? '已归档到知识库' : '归档到知识库'}
        >
          {isArchiving ? '📚 归档中…' : isArchived ? '✓ 已归档' : '📚 归档'}
        </button>
        {reactionsAvailable && (
          <ReactionButtons item={item} current={currentReaction} onReact={onReact} />
        )}
      </div>
    </div>
  );
}