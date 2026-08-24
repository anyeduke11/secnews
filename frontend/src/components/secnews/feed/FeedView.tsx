/**
 * FeedView — 报纸风 Feed 视图
 *
 * 展示安全资讯流，按 ingested_at DESC 排序。
 * 支持分类筛选 + 关键词搜索。
 */
import { useState, useEffect } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';
import { FeedCard } from './FeedCard';
import { FeedFilters } from './FeedFilters';

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
  const [items, setItems] = useState<FeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('');
  const [keyword, setKeyword] = useState('');

  const fetchFeed = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (keyword) params.set('keyword', keyword);
      params.set('limit', '30');
      const res = await fetch(`/api/secnews/feed?${params}`);
      const data = await res.json();
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchFeed(); }, [category, keyword]);

  return (
    <div>
      <SecNewsHeader title="安全资讯" onRefresh={fetchFeed} refreshing={loading} />
      <FeedFilters category={category} keyword={keyword} onCategoryChange={setCategory} onKeywordChange={setKeyword} />
      <div className="mt-4 text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
        共 {total} 条 · 显示 {items.length} 条
      </div>
      <div className="flex flex-col gap-2">
        {loading && items.length === 0 && (
          <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
        )}
        {items.map(item => <FeedCard key={item.id} item={item} />)}
        {!loading && items.length === 0 && (
          <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>暂无资讯</div>
        )}
      </div>
    </div>
  );
}
