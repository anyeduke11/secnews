/**
 * BriefingView — 工作台简报视图 (Phase 4 v0.6.1)
 *
 * 展示今日官方简报 + 已发布知识条目 + 源健康概览。
 * 数据源: GET /api/digests/latest · GET /api/knowledge/items · GET /api/sources/health
 */
import { useEffect, useState } from 'react';
import { useDigest } from '../../hooks/useDigest';

interface BriefingItem {
  id: string;
  title: string;
  source: string;
  lifecycle: string;
  updated_at: string;
  topic?: string;
}

interface SourceHealth {
  category: string;
  source_name: string;
  status: string;
  total_items: number;
}

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

export function BriefingView() {
  const { digest, loading: digestLoading, generate: generateDigest, markRead: markDigestRead } = useDigest();

  const [items, setItems] = useState<BriefingItem[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [itemsLoading, setItemsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/api/knowledge/items?limit=20').then(r => r.ok ? r.json() : { items: [] }),
      fetch('/api/sources/health').then(r => r.ok ? r.json() : { sources: [] }),
    ]).then(([kb, hs]) => {
      if (cancelled) return;
      setItems((kb.items || []).filter((i: BriefingItem) => i.lifecycle === 'kl:publish'));
      setHealth(hs.sources || []);
      setItemsLoading(false);
    }).catch(() => { if (!cancelled) setItemsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const handleGenerate = async () => {
    await generateDigest();
    await markDigestRead();
  };

  const todayItems = items.filter(i => isToday(i.updated_at));
  const activeCount = health.filter(h => h.status === 'active').length;
  const staleCount = health.filter(h => h.status === 'stale').length;

  return (
    <div className="space-y-3 max-w-4xl">
      {/* 官方每日简报 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', borderLeft: '3px solid var(--accent)' }}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
            官方每日简报
          </h3>
          <button onClick={handleGenerate} className="btn-secondary text-[10px] px-2 py-0.5">
            生成
          </button>
        </div>
        {digestLoading && <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>}
        {!digestLoading && digest && (
          <div className="text-[11px] font-mono space-y-1">
            <div style={{ color: 'var(--text-muted)' }}>{digest.period} · {digest.created_at}</div>
            <pre className="whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>{digest.summary}</pre>
            <div style={{ color: 'var(--text-muted)' }}>关联条目: {digest.item_ids?.length ?? digest.count ?? 0}</div>
          </div>
        )}
        {!digestLoading && !digest && (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无简报，点击「生成」</p>
        )}
      </section>

      {/* 今日已发布条目 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          今日已发布 · <span style={{ color: 'var(--accent)' }}>{todayItems.length}</span>
        </h3>
        {itemsLoading ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
        ) : todayItems.length === 0 ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>今日无新发布</p>
        ) : (
          <ul className="text-[11px] space-y-1">
            {todayItems.slice(0, 10).map(item => (
              <li key={item.id} className="flex items-center justify-between gap-2">
                <span style={{ color: 'var(--text-primary)' }} className="truncate flex-1">{item.title}</span>
                <span style={{ color: 'var(--text-muted)' }} className="shrink-0">{item.topic || item.source}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 源健康 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          源健康 · <span style={{ color: 'var(--color-success)' }}>{activeCount} active</span>
            {staleCount > 0 && <span style={{ color: 'var(--color-warning)' }}> / {staleCount} stale</span>}
        </h3>
        {health.length === 0 ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无源健康数据</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1">
            {health.slice(0, 12).map(s => (
              <div key={`${s.category}-${s.source_name}`} className="text-[10px] font-mono flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full inline-block" style={{
                  backgroundColor: s.status === 'active' ? 'var(--color-success)' :
                    s.status === 'stale' ? 'var(--color-warning)' : 'var(--color-error)',
                }} />
                <span style={{ color: 'var(--text-secondary)' }} className="truncate">{s.source_name}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}