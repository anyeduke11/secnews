/**
 * FeedView — 报纸风 Feed 完整视图 (S3-1)
 *
 * 头版头条 (hero) + 分类标签 + 网格卡片 + 关键词搜索。
 * 视觉: 报纸编辑风 — 头版大标题 + 栏线分隔 + 卡片网格。
 * v0.7 Batch ⑨ B9-1: 接入 i18n (feed.* namespace)
 */
import { useState, useEffect, useCallback } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';
import { DigestCard } from './DigestCard';
import { FeedCard } from './FeedCard';
import { FeedFilters } from './FeedFilters';
import { useI18n } from '../../../contexts/I18nContext';

interface FeedItem {
  id: string;
  title: string;
  url: string;
  source: string;
  category: string;
  summary?: string;
  published_at?: string;
}

export function FeedView() {
  const { locale, t } = useI18n();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState('');
  const [keyword, setKeyword] = useState('');

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (keyword) params.set('keyword', keyword);
      params.set('limit', '30');
      const res = await fetch(`/api/secnews/feed?${params}`);
      if (!res.ok) {
        setError(`${t('feed.load_failed_status', { status: res.status })}`);
        return;
      }
      const data = await res.json();
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setError(t('feed.load_failed_network'));
    } finally {
      setLoading(false);
    }
  }, [category, keyword, t]);

  useEffect(() => { fetchFeed(); }, [fetchFeed]);

  const hero = !category && !keyword && items.length > 0 ? items[0] : null;
  const rest = hero ? items.slice(1) : items;
  const dateLocale = locale === 'en-US' ? 'en-US' : 'zh-CN';

  return (
    <div>
      <SecNewsHeader title={t('feed.security_news')} onRefresh={fetchFeed} refreshing={loading} />

      {/* 官方每日简报 (workbench BriefingView 并入) */}
      <div className="mb-4">
        <DigestCard />
      </div>

      <FeedFilters category={category} keyword={keyword} onCategoryChange={setCategory} onKeywordChange={setKeyword} />

      {/* 统计行 */}
      <div className="flex items-center justify-between mt-3 mb-2 text-[10px] font-mono"
        style={{ color: 'var(--text-muted)', borderBottom: '2px solid var(--text-primary)', paddingBottom: '4px' }}>
        <span>{t('feed.total_count', { total: total.toLocaleString(), shown: items.length })}</span>
        <span>{new Date().toLocaleDateString(dateLocale, { month: 'long', day: 'numeric', weekday: 'long' })}</span>
      </div>

      {loading && items.length === 0 && (
        <div className="text-sm py-12 text-center animate-pulse" style={{ color: 'var(--text-muted)' }}
          role="status" aria-live="polite">
          {t('feed.laying_out')}
        </div>
      )}

      {error && !loading && items.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-sm" style={{ color: 'var(--color-error)' }} role="alert">{error}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)', opacity: 0.6 }}>
            {t('feed.check_backend')}
          </p>
        </div>
      )}

      {!error && !loading && items.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{t('feed.empty_title')}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)', opacity: 0.6 }}>
            {t('feed.empty_hint')}
          </p>
        </div>
      )}

      {/* 头版头条 */}
      {hero && (
        <div className="mb-4 pb-4" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: 'var(--accent)' }}>
            {t('feed.headlines')}
          </div>
          <a href={hero.url} target="_blank" rel="noopener noreferrer" className="block group">
            <h2 className="text-xl font-bold leading-tight mb-1.5 group-hover:underline"
              style={{ color: 'var(--text-primary)' }}>
              {hero.title}
            </h2>
            {hero.summary && (
              <p className="text-sm leading-relaxed line-clamp-3" style={{ color: 'var(--text-secondary)' }}>
                {hero.summary}
              </p>
            )}
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                style={{ backgroundColor: 'color-mix(in srgb, var(--accent) 10%, transparent)', color: 'var(--accent)' }}>
                {hero.source}
              </span>
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{hero.category}</span>
            </div>
          </a>
        </div>
      )}

      {/* 网格卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {rest.map(item => <FeedCard key={item.id} item={item} />)}
      </div>
    </div>
  );
}
