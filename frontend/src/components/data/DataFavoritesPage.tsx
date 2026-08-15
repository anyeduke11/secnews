/**
 * DataFavoritesPage — 资料层收藏夹页面
 *
 * Phase 2: 将 FavoritesPanel 以全页形式展示在资料层。
 * 复用 FavoriteToolbar + FavoriteList 子组件，以页面模式渲染（非抽屉）。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { apiFetch, postJSON } from '../../lib/api';
import type { FavoriteItem, FavoritesListResponse, FavoritesCountResponse } from '../../types';
// P5-7: 真复用 favorites/ 共享组件 (此前内联重写 FavoriteToolbarInline/FavoriteListInline)
import { FavoriteToolbar } from '../favorites/FavoriteToolbar';
import { FavoriteList } from '../favorites/FavoriteList';

interface TodoPayload {
  important: boolean;
  deadline: string | null;
  note: string;
}

export function DataFavoritesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [activeCat, setActiveCat] = useState('all');
  const [loading, setLoading] = useState(false);
  const [popoverForId, setPopoverForId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 统一走 lib/api.ts; 任一失败不影响另一路 (catch 兜底为 null)
      const [listData, countData] = await Promise.all([
        apiFetch<FavoritesListResponse>(`/api/favorites?limit=1000&category=${activeCat}`).catch(() => null),
        apiFetch<FavoritesCountResponse>('/api/favorites/count').catch(() => null),
      ]);
      if (listData) {
        setItems(listData.items || []);
        setTotal(listData.total || 0);
      }
      if (countData) {
        setCounts(countData.by_category || {});
      }
    } catch { /* 静默 */ }
    setLoading(false);
  }, [activeCat]);

  useEffect(() => { load(); }, [load]);

  const handleRemove = useCallback(async (hotspotId: string) => {
    try {
      await apiFetch(`/api/favorites/${encodeURIComponent(hotspotId)}`, { method: 'DELETE' });
      setItems(prev => prev.filter(it => it.hotspot_id !== hotspotId));
      setTotal(prev => Math.max(0, prev - 1));
      setMessage({ type: 'ok', text: '已取消收藏' });
      setTimeout(() => setMessage(null), 3000);
    } catch {
      setMessage({ type: 'error', text: '取消收藏失败' });
      setTimeout(() => setMessage(null), 3000);
    }
  }, []);

  const handleAddToTodo = useCallback(async (hotspotId: string, payload: TodoPayload) => {
    try {
      const item = items.find(it => it.hotspot_id === hotspotId);
      await postJSON('/api/todos', {
        source_type: 'favorite',
        source_id: hotspotId,
        title: item ? `[收藏] ${item.title || hotspotId}` : hotspotId,
        category: item?.category || 'other',
        url: item?.url || '',
        important: payload.important,
        deadline: payload.deadline,
      });
      setMessage({ type: 'ok', text: '已添加到待办' });
      setTimeout(() => setMessage(null), 3000);
    } catch {
      setMessage({ type: 'error', text: '添加到待办失败' });
      setTimeout(() => setMessage(null), 3000);
    }
  }, [items]);

  const isFavoriteInTodo = useCallback((_hotspotId: string) => false, []);

  const handleExport = useCallback(async () => {
    try {
      const blob = await apiFetch<Blob>('/api/favorites/export', { parse: 'blob' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'favorites-export.xlsx';
      a.click();
      URL.revokeObjectURL(url);
      setMessage({ type: 'ok', text: '导出成功' });
      setTimeout(() => setMessage(null), 3000);
    } catch {
      setMessage({ type: 'error', text: '导出失败' });
      setTimeout(() => setMessage(null), 3000);
    }
  }, []);

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/data')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回资料层"
          aria-label="返回资料层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-mono text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          收藏夹
        </h2>
        {!loading && (
          <span className="text-xs font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
            {total} 条
          </span>
        )}
      </div>

      {/* Toast 消息 */}
      {message && (
        <div
          className="mb-3 px-3 py-2 rounded-sm text-xs font-medium"
          style={{
            backgroundColor: message.type === 'ok'
              ? 'color-mix(in srgb, var(--color-finance) 12%, transparent)'
              : 'color-mix(in srgb, var(--color-error, #e53e3e) 12%, transparent)',
            color: message.type === 'ok' ? 'var(--color-finance)' : 'var(--color-error, #e53e3e)',
          }}
        >
          {message.text}
        </div>
      )}

      {/* 分类筛选 (P5-7: 复用共享 FavoriteToolbar) */}
      <FavoriteToolbar
        activeCat={activeCat}
        counts={counts}
        total={total}
        onCategoryChange={setActiveCat}
        onExport={handleExport}
      />

      {/* 收藏列表 (P5-7: 复用共享 FavoriteList) */}
      <FavoriteList
        items={items}
        loading={loading}
        popoverForId={popoverForId}
        isFavoriteInTodo={isFavoriteInTodo}
        onTogglePopover={setPopoverForId}
        onAddToTodo={handleAddToTodo}
        onRemove={handleRemove}
      />
    </div>
  );
}

