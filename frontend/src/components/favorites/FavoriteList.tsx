/**
 * FavoriteList — 收藏列表区（loading / empty / items 三态）。
 *
 * Phase 1B: 拆自原 FavoritesPanel.tsx 列表段。
 * props-only: 接收 items + 各种回调, 渲染 FavoriteItem 列表。
 */
import React from 'react';
import { FavoriteItem as FavoriteItemType } from '../../types';
import { FavoriteItem } from './FavoriteItem';

interface TodoPayload {
  important: boolean;
  deadline: string | null;
  note: string;
}

interface FavoriteListProps {
  items: FavoriteItemType[];
  loading: boolean;
  popoverForId: string | null;
  isFavoriteInTodo: (hotspotId: string) => boolean;
  onTogglePopover: (hotspotId: string) => void;
  onAddToTodo: (hotspotId: string, payload: TodoPayload) => void;
  onRemove: (hotspotId: string) => void;
}

export function FavoriteList({
  items, loading, popoverForId,
  isFavoriteInTodo, onTogglePopover, onAddToTodo, onRemove,
}: FavoriteListProps) {
  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto">
        <div className="px-4 py-8 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          加载中...
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <div className="px-4 py-12 text-center">
          <div className="mb-2 flex justify-center">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4 }}>
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无收藏</p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
            在首页卡片上点击右上角 ☆ 即可收藏
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <ul className="px-3 py-2 space-y-1">
        {items.map(it => (
          <FavoriteItem
            key={it.hotspot_id}
            item={it}
            inTodo={isFavoriteInTodo(it.hotspot_id)}
            isPopoverOpen={popoverForId === it.hotspot_id}
            onTogglePopover={() => onTogglePopover(it.hotspot_id)}
            onAddToTodo={(payload) => onAddToTodo(it.hotspot_id, payload)}
            onRemove={() => onRemove(it.hotspot_id)}
          />
        ))}
      </ul>
    </div>
  );
}
