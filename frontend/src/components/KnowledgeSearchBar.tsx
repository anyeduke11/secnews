import { useCallback, useEffect, useRef, useState } from 'react';

interface SearchResult {
  id: string;
  title: string;
  source: 'hotspot' | 'local';
  url: string;
  score: number;
}

interface KnowledgeSearchBarProps {
  /** 选中结果时的回调 */
  onSelect?: (result: SearchResult) => void;
}

/**
 * Phase 1j Task 10.6: 联邦搜索栏
 *
 * 调用 GET /api/knowledge/search?q=&limit=20 跨 hotspot + local wiki 搜索。
 * 结果按 source 区分颜色（hotspot=蓝 / local=紫）。
 * 300ms debounce + 最小 2 字符触发 + Escape 清除。
 */
export default function KnowledgeSearchBar({ onSelect }: KnowledgeSearchBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced search
  const doSearch = useCallback((q: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setShowResults(false);
      return;
    }
    setLoading(true);
    const url = new URL('/api/knowledge/search', window.location.origin);
    url.searchParams.set('q', q.trim());
    url.searchParams.set('limit', '20');
    fetch(url.toString())
      .then(r => r.json())
      .then(data => {
        setResults(Array.isArray(data?.results) ? data.results : []);
        setShowResults(true);
      })
      .catch(() => {
        setResults([]);
        setShowResults(false);
      })
      .finally(() => setLoading(false));
  }, []);

  // Input change handler with 300ms debounce
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 300);
  };

  // Keyboard: Escape to clear
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setQuery('');
      setResults([]);
      setShowResults(false);
    }
  };

  // Click outside to close results
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSelect = (result: SearchResult) => {
    onSelect?.(result);
    setShowResults(false);
    // If result has a URL, open in new tab
    if (result.url) {
      window.open(result.url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div ref={containerRef} className="relative flex-1 max-w-md">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="搜索知识库（hotspot + local）..."
          className="w-full rounded-[var(--radius-md)] px-3 py-1.5 pl-8 text-xs"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
          }}
          aria-label="联邦搜索"
        />
        <span
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          {loading ? '⋯' : '🔍'}
        </span>
      </div>

      {showResults && results.length > 0 && (
        <div
          className="absolute z-50 mt-1 w-full rounded-[var(--radius-md)] shadow-lg max-h-80 overflow-y-auto"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
          }}
        >
          <div className="px-2.5 py-1.5 text-[10px] border-b" style={{ borderColor: 'var(--border-color)', color: 'var(--text-muted)' }}>
            {results.length} 条结果
          </div>
          <ul>
            {results.map(r => (
              <li key={`${r.source}-${r.id}`}>
                <button
                  onClick={() => handleSelect(r)}
                  className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-[var(--bg-hover)] flex items-center gap-2"
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <span
                    className="inline-block px-1.5 py-0.5 rounded text-[9px] font-medium flex-shrink-0"
                    style={{
                      backgroundColor: r.source === 'local' ? 'rgba(149, 117, 205, 0.15)' : 'rgba(92, 159, 224, 0.15)',
                      color: r.source === 'local' ? '#9575cd' : '#5c9fe0',
                    }}
                  >
                    {r.source === 'local' ? 'LOCAL' : 'HOTSPOT'}
                  </span>
                  <span
                    className="flex-1 truncate"
                    style={{ color: 'var(--text-primary)' }}
                    title={r.title}
                  >
                    {r.title}
                  </span>
                  <span className="flex-shrink-0 text-[9px]" style={{ color: 'var(--text-muted)' }}>
                    ★{r.score}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showResults && results.length === 0 && !loading && (
        <div
          className="absolute z-50 mt-1 w-full rounded-[var(--radius-md)] px-2.5 py-2 text-xs"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-muted)',
          }}
        >
          无匹配结果
        </div>
      )}
    </div>
  );
}
