/**
 * FeedFilters — 分类/时间/关键词筛选
 */
interface FeedFiltersProps {
  category: string;
  keyword: string;
  onCategoryChange: (v: string) => void;
  onKeywordChange: (v: string) => void;
}

const CATEGORIES = [
  { value: '', label: '全部' },
  { value: 'security', label: '安全' },
  { value: 'general', label: '综合' },
  { value: 'finance', label: '金融' },
  { value: 'ai', label: 'AI' },
  { value: 'bid', label: '标讯' },
];

export function FeedFilters({ category, keyword, onCategoryChange, onKeywordChange }: FeedFiltersProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1">
        {CATEGORIES.map(c => (
          <button
            key={c.value}
            onClick={() => onCategoryChange(c.value)}
            className="px-2 py-1 text-[11px] font-mono rounded-[var(--radius-sm)] transition-colors"
            style={{
              color: category === c.value ? 'var(--accent)' : 'var(--text-muted)',
              backgroundColor: category === c.value ? 'var(--accent-soft)' : 'transparent',
            }}
          >
            {c.label}
          </button>
        ))}
      </div>
      <input
        type="text"
        value={keyword}
        onChange={e => onKeywordChange(e.target.value)}
        placeholder="搜索关键词..."
        className="px-2 py-1 text-xs font-mono rounded-[var(--radius-sm)] w-40"
        style={{
          border: '1px solid var(--border-color)',
          color: 'var(--text-primary)',
          backgroundColor: 'var(--bg-primary)',
        }}
      />
    </div>
  );
}
