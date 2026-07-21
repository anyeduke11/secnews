/**
 * FavoritesPanel — 收藏面板主壳（Phase 1B 拆分后）。
 *
 * Phase 1B: 拆自原 FavoritesPanel.tsx (16KB / 402 行)。
 * 当前负责：抽屉壳 + 状态管理 + 副作用（拉取/计数）+ 渲染 3 个子区段。
 * 公开 API 完全保留（<FavoritesPanel open onClose onCountChange onFavoritesChange />）。
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  FavoriteItem as FavoriteItemType,
  FavoritesListResponse,
  FavoritesCountResponse,
} from '../../types';
import { useTodos } from '../../hooks/useTodos';
import { FavoriteToolbar } from './FavoriteToolbar';
import { FavoriteList } from './FavoriteList';

interface FavoritesPanelProps {
  open: boolean;
  onClose: () => void;
  /** 列表变化时通知父组件(用于更新 Header 徽标) */
  onCountChange?: (count: number) => void;
  /** 列表内容变化(用于同步刷新卡片上的星标) */
  onFavoritesChange?: (favoritedIds: Set<string>) => void;
}

type PanelMessage = { type: 'ok' | 'error'; text: string } | null;

export function FavoritesPanel({
  open, onClose, onCountChange, onFavoritesChange,
}: FavoritesPanelProps) {
  const [items, setItems] = useState<FavoriteItemType[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [activeCat, setActiveCat] = useState('all');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<PanelMessage>(null);
  const [popoverForId, setPopoverForId] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const todos = useTodos();

  const loadFavorites = useCallback(async (cat: string) => {
    setLoading(true);
    try {
      const url = cat === 'all' ? '/api/favorites' : `/api/favorites?category=${cat}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: FavoritesListResponse = await r.json();
      setItems(data.items || []);
      setTotal(data.total);
      onFavoritesChange?.(new Set((data.items || []).map(it => it.hotspot_id)));
    } catch (e) {
      setMessage({ type: 'error', text: `加载收藏失败: ${(e as Error).message}` });
    } finally {
      setLoading(false);
    }
  }, [onFavoritesChange]);

  const loadCounts = useCallback(async () => {
    try {
      const r = await fetch('/api/favorites/count');
      if (!r.ok) return;
      const data: FavoritesCountResponse = await r.json();
      setCounts(data.by_category);
      setTotal(data.total);
      onCountChange?.(data.total);
    } catch {
      // 静默
    }
  }, [onCountChange]);

  useEffect(() => {
    if (open) {
      loadCounts();
      loadFavorites(activeCat);
    }
  }, [open, activeCat, loadCounts, loadFavorites]);

  // 初次挂载也拉一次 counts(用于 Header 徽标)
  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  const handleRemove = useCallback(async (hotspotId: string) => {
    setMessage(null);
    try {
      const r = await fetch(`/api/favorites/${encodeURIComponent(hotspotId)}`, {
        method: 'DELETE',
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      // 乐观更新: 从列表移除
      setItems(prev => prev.filter(it => it.hotspot_id !== hotspotId));
      setTotal(prev => Math.max(0, prev - 1));
      setCounts(prev => {
        const it = items.find(x => x.hotspot_id === hotspotId);
        if (!it) return prev;
        return { ...prev, [it.category]: Math.max(0, (prev[it.category] || 1) - 1) };
      });
      setMessage({ type: 'ok', text: '已取消收藏' });
      onFavoritesChange?.(new Set(items.filter(it => it.hotspot_id !== hotspotId).map(it => it.hotspot_id)));
      loadCounts();
    } catch (e) {
      setMessage({ type: 'error', text: `取消收藏失败: ${(e as Error).message}` });
    }
  }, [items, loadCounts, onFavoritesChange]);

  const handleExport = useCallback(() => {
    const url = activeCat === 'all'
      ? '/api/favorites/export'
      : `/api/favorites/export?category=${activeCat}`;
    window.open(url, '_blank');
  }, [activeCat]);

  const handleAddToTodo = useCallback(
    async (hotspotId: string, payload: { important: boolean; deadline: string | null; note: string }) => {
      setAddError(null);
      const fav = items.find(x => x.hotspot_id === hotspotId);
      if (!fav) {
        setAddError('找不到对应的收藏');
        return;
      }
      try {
        await todos.add({
          source_type: 'favorite',
          source_id: hotspotId,
          title: fav.title,
          url: fav.url,
          source: fav.source,
          category: fav.category,
          important: payload.important,
          deadline: payload.deadline,
          note: payload.note || undefined,
        });
        setPopoverForId(null);
        setMessage({ type: 'ok', text: '已加入待办' });
      } catch (e) {
        setAddError((e as Error).message || '添加失败');
      }
    },
    [todos, items]
  );

  const handleTogglePopover = useCallback((hotspotId: string) => {
    setPopoverForId(prev => (prev === hotspotId ? null : hotspotId));
  }, []);

  if (!open) return null;

  return (
    <>
      {/* 背景遮罩 */}
      <div
        className="fixed inset-0 z-40"
        style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
        onClick={onClose}
      />

      {/* 右侧抽屉 */}
      <div
        className="fixed top-0 right-0 h-full w-full max-w-md z-50 flex flex-col shadow-2xl"
        style={{ backgroundColor: 'var(--bg-primary)', borderLeft: '1px solid var(--border-color)' }}
      >
        {/* 标题栏 */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: '1px solid var(--border-color)' }}
        >
          <div className="flex items-center gap-2">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="#f0c929" stroke="#f0c929" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              收藏
            </h2>
            <span
              className="text-[11px] px-1.5 py-0.5 rounded-full"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
            >
              共 {total} 条
            </span>
          </div>
          <button
            onClick={onClose}
            className="btn-ghost px-2 py-1 text-xs"
            title="关闭"
            aria-label="关闭"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* 工具栏: 分类 chips + 导出按钮 */}
        <FavoriteToolbar
          counts={counts}
          total={total}
          activeCat={activeCat}
          onCategoryChange={setActiveCat}
          onExport={handleExport}
        />

        {/* 添加待办错误条 — 优先级高于普通 message */}
        {addError && (
          <div
            className="px-4 py-2 text-[11px] shrink-0"
            style={{
              backgroundColor: '#e85d5d14',
              color: '#e85d5d',
              borderBottom: '1px solid var(--border-color)',
            }}
            onClick={() => setAddError(null)}
          >
            添加待办失败: {addError}
          </div>
        )}

        {/* 提示条 */}
        {message && (
          <div
            className="px-4 py-2 text-[11px] shrink-0"
            style={{
              backgroundColor: message.type === 'ok' ? '#00c96a14' : '#e85d5d14',
              color: message.type === 'ok' ? '#00c96a' : '#e85d5d',
              borderBottom: '1px solid var(--border-color)',
            }}
            onClick={() => setMessage(null)}
          >
            {message.text}
          </div>
        )}

        {/* 列表区 */}
        <FavoriteList
          items={items}
          loading={loading}
          popoverForId={popoverForId}
          isFavoriteInTodo={todos.isFavoriteInTodo}
          onTogglePopover={handleTogglePopover}
          onAddToTodo={handleAddToTodo}
          onRemove={handleRemove}
        />

        {/* 底部 footer */}
        <div
          className="px-4 py-2.5 text-[10px] shrink-0 flex items-center justify-between"
          style={{
            borderTop: '1px solid var(--border-color)',
            color: 'var(--text-muted)',
          }}
        >
          <span>点击标题查看原文</span>
          <span>导出 .xlsx 含 3 列: 信息类型 / 标题 / 原文链接</span>
        </div>
      </div>
    </>
  );
}
