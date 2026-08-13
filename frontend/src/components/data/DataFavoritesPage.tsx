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
        <h2 className="font-serif text-base font-bold" style={{ color: 'var(--text-primary)' }}>
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

      {/* 分类筛选 */}
      <FavoriteToolbarInline
        activeCat={activeCat}
        counts={counts}
        total={total}
        onCategoryChange={setActiveCat}
        onExport={handleExport}
      />

      {/* 收藏列表 */}
      <FavoriteListInline
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

/* ─── 内联版 FavoriteToolbar ─── */

const CATEGORY_CHIPS = [
  { id: 'all', label: '全部' },
  { id: 'ai', label: 'AI' },
  { id: 'security', label: '安全' },
  { id: 'finance', label: '金融' },
  { id: 'startup', label: '创业' },
  { id: 'bid', label: '标讯' },
  { id: 'github', label: 'GitHub' },
  { id: 'tech', label: '科技' },
];

function FavoriteToolbarInline({
  activeCat, counts, total,
  onCategoryChange, onExport,
}: {
  activeCat: string;
  counts: Record<string, number>;
  total: number;
  onCategoryChange: (cat: string) => void;
  onExport: () => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap mb-3 pb-2.5" style={{ borderBottom: '1px solid var(--border-color)' }}>
      {CATEGORY_CHIPS.map(chip => {
        const active = chip.id === activeCat;
        const count = chip.id === 'all' ? total : (counts[chip.id] ?? 0);
        return (
          <button
            key={chip.id}
            onClick={() => onCategoryChange(chip.id)}
            className="ink-chip focus-ring transition-colors"
            style={{
              padding: '3px 9px',
              color: active ? 'var(--text-on-light)' : 'var(--text-secondary)',
              backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
              borderColor: active ? 'var(--accent)' : 'var(--border-color)',
              fontWeight: active ? 600 : 400,
            }}
            aria-current={active ? 'page' : undefined}
          >
            {chip.label}
            {count > 0 && (
              <span className="ml-1.5 font-mono tabular-nums text-[10px]" style={{ opacity: 0.7 }}>
                {count}
              </span>
            )}
          </button>
        );
      })}
      <div className="ml-auto">
        <button
          onClick={onExport}
          className="ink-chip focus-ring transition-colors"
          style={{ padding: '3px 9px', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-hover)', borderColor: 'var(--border-color)' }}
          title="导出收藏"
        >
          导出
        </button>
      </div>
    </div>
  );
}

/* ─── 内联版 FavoriteList ─── */

function FavoriteListInline({
  items, loading, popoverForId,
  isFavoriteInTodo, onTogglePopover, onAddToTodo, onRemove,
}: {
  items: FavoriteItem[];
  loading: boolean;
  popoverForId: string | null;
  isFavoriteInTodo: (hotspotId: string) => boolean;
  onTogglePopover: (hotspotId: string) => void;
  onAddToTodo: (hotspotId: string, payload: TodoPayload) => void;
  onRemove: (hotspotId: string) => void;
}) {
  if (loading) {
    return (
      <div className="py-8 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        加载中...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无收藏</p>
        <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
          在资料层点击卡片上的星标即可收藏
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {items.map(item => (
        <div
          key={item.id}
          className="flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] transition-colors hover:bg-[var(--bg-hover)]"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div className="min-w-0 flex-1">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11.5px] font-medium hover:underline block truncate"
              style={{ color: 'var(--text-primary)' }}
            >
              {item.title || item.hotspot_id}
            </a>
            <div className="flex items-center gap-2 mt-1">
              {item.category && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                  {item.category}
                </span>
              )}
              {item.source && (
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.source}</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {popoverForId === item.hotspot_id ? (
              <TodoPopover
                hotspotId={item.hotspot_id}
                onConfirm={onAddToTodo}
                onClose={() => onTogglePopover('')}
              />
            ) : (
              <button
                onClick={() => onTogglePopover(item.hotspot_id)}
                className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-hover)] focus-ring"
                title="添加到待办"
                aria-label="添加到待办"
              >
                <Icon size={12}>
                  <polyline points="9 11 12 14 22 4" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </Icon>
              </button>
            )}
            <button
              onClick={() => onRemove(item.hotspot_id)}
              className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-hover)] focus-ring"
              title="取消收藏"
              aria-label="取消收藏"
            >
              <Icon size={12}>
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </Icon>
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── 内联版 TodoPopover ─── */

function TodoPopover({
  hotspotId, onConfirm, onClose,
}: {
  hotspotId: string;
  onConfirm: (hotspotId: string, payload: TodoPayload) => void;
  onClose: () => void;
}) {
  const [important, setImportant] = useState(false);
  const [deadline, setDeadline] = useState('');

  return (
    <div className="flex items-center gap-1.5">
      <label className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={important} onChange={e => setImportant(e.target.checked)} className="w-3 h-3" />
        重要
      </label>
      <input
        type="date"
        value={deadline}
        onChange={e => setDeadline(e.target.value)}
        className="w-20 text-[10px] px-1 py-0.5 rounded-sm"
        style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        placeholder="截止"
      />
      <button
        onClick={() => { onConfirm(hotspotId, { important, deadline: deadline || null, note: '' }); onClose(); }}
        className="px-1.5 py-0.5 rounded-sm text-[10px] font-medium"
        style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}
      >
        确定
      </button>
      <button
        onClick={onClose}
        className="px-1.5 py-0.5 rounded-sm text-[10px]"
        style={{ color: 'var(--text-muted)' }}
      >
        取消
      </button>
    </div>
  );
}