/**
 * FavoriteToolbar — 收藏面板工具栏（分类 chips + 导出按钮）。
 *
 * Phase 1B: 拆自原 FavoritesPanel.tsx 工具栏段。
 * props-only: 接收 counts/total/activeCat + 切换/导出回调。
 */
import React from 'react';
import { CATEGORIES, getCategoryColor } from '../../types';

const CATEGORY_CHIPS = [
  { id: 'all', label: '全部' },
  ...CATEGORIES.filter(c => c.id !== 'all'),
];

interface FavoriteToolbarProps {
  counts: Record<string, number>;
  total: number;
  activeCat: string;
  onCategoryChange: (cat: string) => void;
  onExport: () => void;
}

export function FavoriteToolbar({
  counts, total, activeCat, onCategoryChange, onExport,
}: FavoriteToolbarProps) {
  return (
    <div
      className="px-4 py-2.5 shrink-0 flex items-center gap-2 flex-wrap"
      style={{ borderBottom: '1px solid var(--border-color)' }}
    >
      {CATEGORY_CHIPS.map(c => {
        const cCount = c.id === 'all' ? total : (counts[c.id] || 0);
        const isActive = activeCat === c.id;
        const catColor = c.id === 'all' ? 'var(--color-warning)' : getCategoryColor(c.id);
        return (
          <button
            key={c.id}
            onClick={() => onCategoryChange(c.id)}
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
        onClick={onExport}
        disabled={total === 0}
        className="ml-auto text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors duration-150 disabled:opacity-50"
        style={{ backgroundColor: 'var(--color-success)', color: 'var(--text-on-light)' }}
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
  );
}
