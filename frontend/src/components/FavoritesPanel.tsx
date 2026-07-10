import React, { useState, useEffect, useCallback } from 'react';
import {
  FavoriteItem,
  FavoritesListResponse,
  FavoritesCountResponse,
  CATEGORIES,
  getCategoryColor,
  getCategoryLabel,
} from '../types';
import { useTodos } from '../hooks/useTodos';
import { FavoriteToTodoPopover } from './FavoriteToTodoPopover';

interface FavoritesPanelProps {
  open: boolean;
  onClose: () => void;
  /** 列表变化时通知父组件(用于更新 Header 徽标) */
  onCountChange?: (count: number) => void;
  /** 列表内容变化(用于同步刷新卡片上的星标) */
  onFavoritesChange?: (favoritedIds: Set<string>) => void;
}

const CATEGORY_CHIPS = [
  { id: 'all', label: '全部' },
  ...CATEGORIES.filter(c => c.id !== 'all'),
];

/** Phase 10 收藏面板 — 右侧抽屉,6 大分类筛选 + 列表 + 批量导出 xlsx */
export function FavoritesPanel({ open, onClose, onCountChange, onFavoritesChange }: FavoritesPanelProps) {
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [activeCat, setActiveCat] = useState('all');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);
  const [popoverForId, setPopoverForId] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  // Phase 36 Task 5: 收藏 → 待办 hook
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

  // 打开时拉一次,分类变化时重拉
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
      // 重新拉 count
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

  // Phase 36 Task 5: 把 favorite 提升为 todo
  // Phase 46: 紧急由 deadline 派生, 不再传 urgent
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

        {/* 分类筛选 chip + 导出按钮 */}
        <div
          className="px-4 py-2.5 shrink-0 flex items-center gap-2 flex-wrap"
          style={{ borderBottom: '1px solid var(--border-color)' }}
        >
          {CATEGORY_CHIPS.map(c => {
            const cCount = c.id === 'all' ? total : (counts[c.id] || 0);
            const isActive = activeCat === c.id;
            const catColor = c.id === 'all' ? '#f0c929' : getCategoryColor(c.id);
            return (
              <button
                key={c.id}
                onClick={() => setActiveCat(c.id)}
                className="text-[11px] px-2.5 py-1 rounded-full transition-colors duration-150 flex items-center gap-1"
                style={{
                  backgroundColor: isActive ? `${catColor}24` : 'var(--bg-hover)',
                  color: isActive ? catColor : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? catColor : 'transparent'}`,
                }}
              >
                <span>{c.label}</span>
                <span
                  className="text-[10px] font-mono"
                  style={{ color: isActive ? catColor : 'var(--text-muted)' }}
                >
                  {cCount}
                </span>
              </button>
            );
          })}
          {/* 导出按钮 — 紧贴 chip 右侧 */}
          <button
            onClick={handleExport}
            disabled={total === 0}
            className="ml-auto text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors duration-150 disabled:opacity-50"
            style={{
              backgroundColor: '#00c96a',
              color: '#0a1f15',
            }}
            title="导出当前筛选为 .xlsx"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="inline-block mr-1" style={{ verticalAlign: '-1px' }}>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            导出 .xlsx
          </button>
        </div>

        {/* Phase 36 Task 5: 添加待办错误条 — 优先级高于普通 message */}
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
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="px-4 py-8 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
              加载中...
            </div>
          ) : items.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <div className="mb-2 flex justify-center">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4 }}>
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                暂无收藏
              </p>
              <p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
                在首页卡片上点击右上角 ☆ 即可收藏
              </p>
            </div>
          ) : (
            <ul className="px-3 py-2 space-y-1">
              {items.map(it => {
                const catColor = getCategoryColor(it.category);
                const inTodo = todos.isFavoriteInTodo(it.hotspot_id);
                const isPopoverOpen = popoverForId === it.hotspot_id;
                return (
                  <li
                    key={it.hotspot_id}
                    className="group px-3 py-2.5 rounded transition-colors"
                    style={{ borderLeft: `2px solid ${catColor}80` }}
                  >
                    <div className="flex items-start gap-2">
                      <a
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 min-w-0"
                        title={it.url}
                      >
                        <div className="flex items-center gap-1.5 mb-1">
                          <span
                            className="text-[10px] px-1.5 py-0.5 rounded"
                            style={{
                              backgroundColor: `${catColor}14`,
                              color: catColor,
                            }}
                          >
                            {getCategoryLabel(it.category)}
                          </span>
                          <span
                            className="text-[10px] truncate"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            {it.source}
                          </span>
                        </div>
                        <h4
                          className="text-[12px] font-medium leading-snug line-clamp-2"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {it.title}
                        </h4>
                      </a>
                      {/* Phase 36 Task 5: → 待办 按钮 (always visible, 取消收藏按钮左侧) */}
                      <button
                        onClick={() => {
                          if (inTodo) return;
                          setPopoverForId(prev => (prev === it.hotspot_id ? null : it.hotspot_id));
                        }}
                        disabled={inTodo}
                        className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors duration-150"
                        style={{
                          color: inTodo ? '#00c96a' : 'var(--text-muted)',
                          opacity: inTodo ? 0.6 : 1,
                          cursor: inTodo ? 'not-allowed' : 'pointer',
                          border: `1px solid ${inTodo ? '#00c96a66' : 'var(--border-color)'}`,
                        }}
                        title={inTodo ? '已加入待办' : '添加为待办'}
                        aria-label={inTodo ? '已加入待办' : '添加为待办'}
                      >
                        {inTodo ? '✓ 已加入' : '→ 待办'}
                      </button>
                      {/* 取消收藏按钮 */}
                      <button
                        onClick={() => handleRemove(it.hotspot_id)}
                        className="shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ color: '#e85d5d' }}
                        title="取消收藏"
                        aria-label="取消收藏"
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                          <path d="M10 11v6" />
                          <path d="M14 11v6" />
                        </svg>
                      </button>
                    </div>
                    {/* Phase 36 Task 5: popover — 紧贴 li 下方, 仅在 popoverForId 匹配时渲染 */}
                    {isPopoverOpen && (
                      <FavoriteToTodoPopover
                        favorite={it}
                        onCancel={() => setPopoverForId(null)}
                        onConfirm={(payload) => handleAddToTodo(it.hotspot_id, payload)}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

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
