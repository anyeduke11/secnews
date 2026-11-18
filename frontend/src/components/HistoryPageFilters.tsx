// HistoryPageFilters — 从 HistoryPage.tsx 拆出的分类 + 关键词筛选条 (纯搬迁, 行为不变).
// 职责: 全部/分类按钮组 + 本批次关键词输入框 (FTS5).

import { CATEGORIES } from '../types';

interface HistoryPageFiltersProps {
  category: string;
  keyword: string;
  onCategoryChange: (category: string) => void;
  onKeywordChange: (keyword: string) => void;
}

export function HistoryPageFilters({
  category, keyword, onCategoryChange, onKeywordChange,
}: HistoryPageFiltersProps) {
  return (
    <div className="flex items-center gap-2 mb-3 flex-wrap">
      <button
        onClick={() => onCategoryChange('all')}
        className="btn-ghost px-2.5 py-1 text-xs"
        style={{
          color: category === 'all' ? 'var(--color-ai)' : undefined,
          borderBottom: category === 'all' ? '2px solid var(--color-ai)' : '2px solid transparent',
        }}
      >
        全部
      </button>
      {CATEGORIES.filter(c => c.id !== 'all').map(c => (
        <button
          key={c.id}
          onClick={() => onCategoryChange(c.id)}
          className="btn-ghost px-2.5 py-1 text-xs"
          style={{
            color: category === c.id ? c.color : undefined,
            borderBottom: category === c.id ? `2px solid ${c.color}` : '2px solid transparent',
          }}
        >
          {c.label}
        </button>
      ))}
      <input
        type="text"
        value={keyword}
        onChange={e => onKeywordChange(e.target.value)}
        placeholder="搜索本批次内关键词 (FTS5)…"
        className="ml-auto px-2 py-1 text-xs rounded-[var(--radius-sm)]"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          color: 'var(--text-primary)',
          width: 240,
        }}
      />
    </div>
  );
}