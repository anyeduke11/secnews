/**
 * FeedFilters — 分类/时间/关键词筛选
 * v0.7 Batch ⑨ B9-1: 接入 i18n (feed.filter.* / feed.search_placeholder)
 */
import { useI18n } from '../../../contexts/I18nContext';

interface FeedFiltersProps {
  category: string;
  keyword: string;
  onCategoryChange: (v: string) => void;
  onKeywordChange: (v: string) => void;
}

const CATEGORY_KEYS = [
  { value: '', i18n: 'feed.filter_all' },
  { value: 'security', i18n: 'feed.filter_security' },
  { value: 'general', i18n: 'feed.filter_general' },
  { value: 'finance', i18n: 'feed.filter_finance' },
  { value: 'ai', i18n: 'feed.filter_all' },       // 复用 All 占位 — 实际可加 feed.filter_ai
  { value: 'bid', i18n: 'feed.filter_bidding' },
];

export function FeedFilters({ category, keyword, onCategoryChange, onKeywordChange }: FeedFiltersProps) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1">
        {CATEGORY_KEYS.map(c => (
          <button
            key={c.value}
            onClick={() => onCategoryChange(c.value)}
            className="px-2 py-1 text-[11px] font-mono rounded-[var(--radius-sm)] transition-colors"
            style={{
              color: category === c.value ? 'var(--accent)' : 'var(--text-muted)',
              backgroundColor: category === c.value ? 'var(--accent-soft)' : 'transparent',
            }}
            aria-pressed={category === c.value}
          >
            {t(c.i18n)}
          </button>
        ))}
      </div>
      <input
        type="text"
        value={keyword}
        onChange={e => onKeywordChange(e.target.value)}
        placeholder={t('feed.search_placeholder')}
        aria-label={t('common.search')}
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
