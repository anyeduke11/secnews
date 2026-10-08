/**
 * UnifiedSearchPage — 统一跨层搜索 (找回丢失前端入口 v1.7 Phase 3)
 *
 * 跨 hotspots + knowledge_items (+ wiki FTS5 旁路) 统一搜索, 分组渲染。
 * 数据源: GET /api/search?q=&sources=&limit=
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { ApiError, getJSON, postJSON } from '../../lib/api';

interface SearchItem {
  entity_type: string;
  entity_id: string;
  title: string;
  summary?: string;
  category?: string;
  ingested_at?: string;
  url?: string;
  fts_snippet?: string;
}

const SOURCE_LABELS: Record<string, string> = {
  hotspot: '热点',
  knowledge: '知识条目',
  wiki: 'Wiki (FTS)',
  chunks: 'Wiki 正文',
  wiki_chunk: 'Wiki 正文',
};

/** P4-1: 结果 → 证据锚点 (检索闭环最后一环)。
 *  hotspot 命中带原文 url → 新开原文; knowledge/wiki → 深读视图。 */
function itemHref(it: SearchItem): string | null {
  if (it.entity_type === 'hotspot') return it.url || null;
  if (it.entity_type === 'knowledge') return `/deep/knowledge/${it.entity_id}`;
  if (it.entity_type === 'wiki') return `/deep/knowledge/${it.entity_id}`;
  if (it.entity_type === 'wiki_chunk') return `/deep/knowledge/${it.entity_id.split('#')[0]}`;
  return null;
}

// 来源 chips 只渲染真实来源键 (wiki_chunk 是分组标签, 不是可选来源)
const SOURCE_CHIP_KEYS = ['hotspot', 'knowledge', 'wiki', 'chunks'];

interface ChunkResult {
  item_id: string;
  chunk_index: number;
  snippet: string;
  wiki_path?: string;
}

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
      // 'chunks' = wiki 正文段落检索 (POST /api/wiki/search, FTS5 trigram);
      // 其余来源走 /api/search。未选来源时两者都查。
      const wantChunks = srcs.length === 0 || srcs.includes('chunks');
      const apiSrcs = srcs.filter(s => s !== 'chunks');
      const wantMain = srcs.length === 0 || apiSrcs.length > 0;

      const [mainRes, chunkRes] = await Promise.all([
        wantMain
          ? getJSON<{ result?: { items?: SearchItem[]; grouped?: Record<string, SearchItem[]> } }>(`/api/search?q=${encodeURIComponent(trimmed)}${apiSrcs.length > 0 ? `&sources=${apiSrcs.join(',')}` : ''}&limit=50`)
          : Promise.resolve(null),
        wantChunks
          ? postJSON<{ results: ChunkResult[] }>('/api/wiki/search', { q: trimmed, limit: 20 })
          : Promise.resolve(null),
      ]);

      const mainGrouped = mainRes?.result?.grouped ?? {};
      const mainItems = mainRes?.result?.items ?? [];
      const chunkItems: SearchItem[] = (chunkRes?.results ?? []).map(c => ({
        entity_type: 'wiki_chunk',
        entity_id: `${c.item_id}#${c.chunk_index}`,
        title: `${c.wiki_path ?? `items/${c.item_id}.md`}`,
        summary: c.snippet,
      }));
      setGrouped(
        chunkItems.length > 0
          ? { ...mainGrouped, wiki_chunk: chunkItems }
          : mainGrouped
      );
      setItems([...mainItems, ...chunkItems]);
    } catch (e) {
      setError(e instanceof ApiError
        ? `搜索失败 (${e.status})`
        : '搜索失败: 网络或后端不可达');
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
        <button onClick={goBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回">
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回</span>
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
        {SOURCE_CHIP_KEYS.map(s => {
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
            {list.map(item => {
              const href = itemHref(item);
              const titleEl = (
                <span className="flex-1 truncate font-medium" style={{ color: href ? 'var(--color-info)' : 'var(--text-primary)' }}>{item.title || item.entity_id}</span>
              );
              return (
                <li key={`${item.entity_type}-${item.entity_id}`} className="py-1.5">
                  <div className="flex items-center gap-2 text-[11px]">
                    {href ? (
                      href.startsWith('http')
                        ? <a href={href} target="_blank" rel="noopener noreferrer" className="flex-1 min-w-0 truncate hover:underline">{titleEl}</a>
                        : <a href={href} className="flex-1 min-w-0 truncate hover:underline" title="打开深度阅读">{titleEl}</a>
                    ) : titleEl}
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
                  {(item.summary || item.fts_snippet) && (
                    <p className="text-[10px] line-clamp-2 mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {item.summary || item.fts_snippet}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {loading && (
        <div className="text-sm py-12 text-center animate-pulse" style={{ color: 'var(--text-muted)' }}>搜索中…</div>
      )}
    </div>
  );
}
