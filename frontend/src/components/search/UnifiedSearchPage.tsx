/**
 * UnifiedSearchPage — 统一跨层搜索 (找回丢失前端入口 v1.7 Phase 3)
 *
 * 跨 hotspots + knowledge_items (+ wiki FTS5 旁路) 统一搜索, 分组渲染。
 * 数据源: GET /api/search?q=&sources=&limit=
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

interface SearchItem {
  entity_type: string;
  entity_id: string;
  title: string;
  summary?: string;
  category?: string;
  ingested_at?: string;
}

const SOURCE_LABELS: Record<string, string> = {
  hotspot: '热点',
  knowledge: '知识条目',
  wiki: 'Wiki (FTS)',
};

export function UnifiedSearchPage({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate();
  const goBack = onBack ?? (() => navigate('/'));

  const [q, setQ] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [items, setItems] = useState<SearchItem[]>([]);
  const [grouped, setGrouped] = useState<Record<string, SearchItem[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const doSearch = useCallback(async (query: string, srcs: string[]) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const params = new URLSearchParams();
      params.set('q', trimmed);
      if (srcs.length > 0) params.set('sources', srcs.join(','));
      params.set('limit', '50');
      const r = await fetch(`/api/search?${params}`);
      if (!r.ok) {
        setError(`搜索失败 (${r.status})`);
        return;
      }
      const d = await r.json();
      setItems(d.result?.items ?? []);
      setGrouped(d.result?.grouped ?? {});
    } catch {
      setError('搜索失败: 网络或后端不可达');
    } finally {
      setLoading(false);
    }
  }, []);

  // 回车触发
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && document.activeElement?.tagName === 'INPUT') {
        doSearch(q, sources);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [q, sources, doSearch]);

  const toggleSource = (s: string) => {
    setSources(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  };

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between pb-2 mb-1" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-mono mr-2">FIND</span>统一搜索
        </h1>
        <button onClick={goBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回首页">
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回首页</span>
        </button>
      </div>

      {/* 搜索框 + 来源过滤 */}
      <div className="flex items-center gap-2">
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="搜索热点与知识库... (回车执行)"
          autoFocus
          className="flex-1 px-3 py-1.5 text-sm font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <button onClick={() => doSearch(q, sources)} disabled={loading || !q.trim()}
          className="btn-secondary text-[10px] px-3 py-1.5">
          {loading ? '搜索中...' : '搜索'}
        </button>
      </div>
      <div className="flex items-center gap-1.5">
        {Object.keys(SOURCE_LABELS).map(s => {
          const active = sources.includes(s);
          return (
            <button key={s} onClick={() => toggleSource(s)}
              className="text-[10px] font-mono px-2 py-0.5 rounded transition-colors"
              style={{
                color: active ? 'var(--accent)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--accent-soft)' : 'var(--bg-hover)',
                border: '1px solid var(--border-color)',
              }}>
              {SOURCE_LABELS[s]}
            </button>
          );
        })}
        {sources.length > 0 && (
          <button onClick={() => setSources([])} className="text-[10px] font-mono px-1.5 py-0.5"
            style={{ color: 'var(--text-muted)' }}>
            清除
          </button>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-[var(--radius-sm)] text-xs font-mono"
          style={{ color: 'var(--color-error)', border: '1px solid var(--color-error)' }}>
          {error}
        </div>
      )}

      {/* 结果 */}
      {searched && !loading && !error && items.length === 0 && (
        <p className="text-xs py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          无匹配结果 — 尝试其他关键词或放宽来源过滤
        </p>
      )}

      {Object.entries(grouped).map(([type, list]) => (
        <section key={type} className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
          <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
            {SOURCE_LABELS[type] ?? type} · {list.length}
          </h3>
          <ul className="divide-y" style={{ borderColor: 'var(--border-light)' }}>
            {list.map(item => (
              <li key={`${item.entity_type}-${item.entity_id}`} className="py-1.5">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="flex-1 truncate font-medium" style={{ color: 'var(--text-primary)' }}>{item.title}</span>
                  {item.category && (
                    <span className="text-[10px] font-mono px-1 rounded shrink-0"
                      style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                      {item.category}
                    </span>
                  )}
                  {item.ingested_at && (
                    <span className="text-[10px] font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>
                      {String(item.ingested_at).slice(0, 10)}
                    </span>
                  )}
                </div>
                {item.summary && (
                  <p className="text-[10px] line-clamp-2 mt-0.5" style={{ color: 'var(--text-muted)' }}>{item.summary}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      {loading && (
        <div className="text-sm py-12 text-center animate-pulse" style={{ color: 'var(--text-muted)' }}>搜索中…</div>
      )}
    </div>
  );
}
