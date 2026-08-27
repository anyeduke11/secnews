/**
 * KnowledgeView — 工作台知识视图 (Phase 4 v0.6.1)
 *
 * 展示 wiki items 列表 + 概念标签 + 复习到期。
 * 数据源: GET /api/knowledge/items · GET /api/knowledge/concepts · GET /api/knowledge/health
 */
import { useEffect, useMemo, useState } from 'react';

interface KnowledgeItem {
  id: string;
  title: string;
  source: string;
  lifecycle: string;
  topic?: string;
  mastery?: number;
  concepts?: string[];
  ingested_at?: string;
}

interface Concept {
  slug: string;
  name: string;
  item_count: number;
}

export function KnowledgeView() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/api/knowledge/items?limit=50').then(r => r.ok ? r.json() : { items: [] }),
      fetch('/api/knowledge/concepts').then(r => r.ok ? r.json() : { concepts: [] }),
    ]).then(([kb, cs]) => {
      if (cancelled) return;
      setItems(kb.items || []);
      setConcepts(cs.concepts || []);
      setLoading(false);
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter(i =>
      i.title.toLowerCase().includes(q) ||
      (i.topic ?? '').toLowerCase().includes(q) ||
      (i.concepts ?? []).some(c => c.toLowerCase().includes(q))
    );
  }, [items, search]);

  const reviewDue = useMemo(
    () => items.filter(i => (i.mastery ?? 0) < 0.5).slice(0, 10),
    [items],
  );

  return (
    <div className="space-y-3 max-w-5xl">
      {/* 搜索 + 概念 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <div className="flex items-center gap-2 mb-2">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索 wiki items..."
            className="flex-1 px-2 py-1 text-xs font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            {filtered.length}/{items.length}
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {concepts.slice(0, 20).map(c => (
            <span key={c.slug} className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}>
              {c.name} <span style={{ color: 'var(--text-muted)' }}>×{c.item_count}</span>
            </span>
          ))}
        </div>
      </section>

      {/* 复习到期 */}
      {reviewDue.length > 0 && (
        <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', borderLeft: '3px solid var(--color-warning)' }}>
          <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
            复习到期 · {reviewDue.length}
          </h3>
          <ul className="text-[11px] space-y-1">
            {reviewDue.map(i => (
              <li key={i.id} className="flex items-center gap-2">
                <span style={{ color: 'var(--text-primary)' }} className="flex-1 truncate">{i.title}</span>
                <span style={{ color: 'var(--color-warning)' }} className="font-mono shrink-0">
                  mastery {(i.mastery ?? 0).toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 全部条目 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          全部 wiki items
        </h3>
        {loading ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
        ) : filtered.length === 0 ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{search ? '无匹配项' : '暂无条目'}</p>
        ) : (
          <ul className="text-[11px] divide-y" style={{ borderColor: 'var(--border-light)' }}>
            {filtered.map(i => (
              <li key={i.id} className="py-1.5 flex items-center gap-2">
                <span style={{ color: 'var(--text-primary)' }} className="flex-1 truncate">{i.title}</span>
                <span style={{ color: 'var(--text-muted)' }} className="text-[10px] font-mono shrink-0">{i.lifecycle}</span>
                {i.topic && (
                  <span style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
                    className="text-[10px] font-mono px-1 rounded shrink-0">
                    {i.topic}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}