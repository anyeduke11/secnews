import React, { Suspense, useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';
import { PageLayout } from './components/PageLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Header } from './components/Header';
import { CategoryNav } from './components/CategoryNav';
import { SearchBar } from './components/SearchBar';
import { StatsPanel } from './components/StatsPanel';
import { TrendChart } from './components/TrendChart';
import { HotspotGrid } from './components/HotspotGrid';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { RegionFilter } from './components/RegionFilter';
// Lazy-loaded page components — split into separate chunks to reduce initial bundle size.
const SettingsPanel = React.lazy(() =>
  import('./components/settings').then(m => ({ default: m.SettingsPanel }))
);
const FavoritesPanel = React.lazy(() =>
  import('./components/favorites').then(m => ({ default: m.FavoritesPanel }))
);
const HistoryPage = React.lazy(() =>
  import('./components/HistoryPage').then(m => ({ default: m.HistoryPage }))
);
const TodosPage = React.lazy(() =>
  import('./components/TodosPage').then(m => ({ default: m.TodosPage }))
);
const SkillsPage = React.lazy(() =>
  import('./components/SkillsPage').then(m => ({ default: m.SkillsPage }))
);
const SecretsPage = React.lazy(() =>
  import('./components/SecretsPage').then(m => ({ default: m.SecretsPage }))
);
const SyncPage = React.lazy(() =>
  import('./components/sync').then(m => ({ default: m.SyncPage }))
);
const WeeklyReportPage = React.lazy(() =>
  import('./components/WeeklyReportPage').then(m => ({ default: m.WeeklyReportPage }))
);
const KnowledgePage = React.lazy(() =>
  import('./components/KnowledgePage').then(m => ({ default: m.KnowledgePage }))
);
const CodegardenPage = React.lazy(() =>
  import('./components/CodegardenPage').then(m => ({ default: m.CodegardenPage }))
);
const CodegardenPhase2bPage = React.lazy(() =>
  import('./components/CodegardenPhase2bPage').then(m => ({ default: m.CodegardenPhase2bPage }))
);
const ReviewPage = React.lazy(() =>
  import('./components/ReviewPage').then(m => ({ default: m.ReviewPage }))
);
const DeepReadView = React.lazy(() =>
  import('./components/DeepReadView').then(m => ({ default: m.DeepReadView }))
);
const BriefModeView = React.lazy(() =>
  import('./components/BriefModeView').then(m => ({ default: m.BriefModeView }))
);
import { useHotspotData } from './hooks/useHotspotData';
import { useRefreshInterval } from './hooks/useRefreshInterval';
import { useTodos } from './hooks/useTodos';
import { useSSE } from './hooks/useSSE';
import { ConsistencyDrift, StatsResponse, HotspotItem } from './types';

/** Minimal loading fallback for Suspense-wrapped routes. */
function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
        <span style={{ color: 'var(--color-ai)', marginRight: 8 }}>&gt;</span>
        加载中 ...
      </div>
    </div>
  );
}


interface ThemeContextValue {
  theme: 'dark' | 'light';
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  toggleTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

function getInitialTheme(): 'dark' | 'light' {
  try {
    const saved = localStorage.getItem('hotspot-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {}
  return 'dark';
}

function formatRefreshLabel(minutes: number): string {
  if (minutes < 60) return `每${minutes}分钟自动刷新`;
  if (minutes < 720) {
    const hours = Math.round(minutes / 60);
    return `每${hours}小时自动刷新`;
  }
  if (minutes < 1440) {
    const hours = Math.round(minutes / 60);
    return `每${hours}小时自动刷新`;
  }
  return `每约${Math.round(minutes / 60 / 24)}天自动刷新`;
}

function HomePage() {
  const { cat } = useParams<{ cat?: string }>();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const category = cat || 'all';

  const [timeRange, setTimeRange] = useState('7d');
  const [keyword, setKeyword] = useState('');
  const [region, setRegion] = useState('');  // Phase 8: 标讯地区筛选
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [favoritesCount, setFavoritesCount] = useState(0);
  const [favoritedIds, setFavoritedIds] = useState<Set<string>>(new Set());
  const [consistencyDrift, setConsistencyDrift] = useState<ConsistencyDrift[]>([]);
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const { interval: refreshInterval, setInterval: setRefreshInterval, refreshFromServer } = useRefreshInterval();
  const lastAutoRefreshAtRef = useRef<number>(Date.now());

  const {
    items, total, categoryCounts, loading, loadingPage, error, lastUpdated,
    hasMore, page, pageSize, totalPages, setPage, setPageSize, refresh,
    latestIngestionCount, latestIngestionAt,
  } = useHotspotData(category, timeRange, keyword, region);

  const todos = useTodos();

  // Phase 6: SSE 实时推送 — 连接后禁用轮询，断开时恢复
  const { connected: sseConnected } = useSSE({
    onEvent: (type, data) => {
      if (type === 'collect_done') {
        refresh();
      }
    },
  });

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/favorites?limit=1000');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        setFavoritesCount(data.total || 0);
        setFavoritedIds(new Set((data.items || []).map((it: any) => it.hotspot_id)));
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { refreshFromServer(); }, []);

  useEffect(() => {
    let cancelled = false;
    const fetchStats = async () => {
      try {
        const resp = await fetch('/api/stats');
        if (!resp.ok) return;
        const data: StatsResponse = await resp.json();
        if (!cancelled && data.consistency_check?.drift) {
          setConsistencyDrift(data.consistency_check.drift);
        }
      } catch {}
    };
    fetchStats();
    const t = window.setInterval(fetchStats, 5 * 60 * 1000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, []);

  useEffect(() => {
    if (sseConnected) return; // SSE 推送已连接，无需轮询
    const ms = Math.max(refreshInterval, 1) * 60 * 1000;
    lastAutoRefreshAtRef.current = Date.now();
    const timer = window.setInterval(() => {
      lastAutoRefreshAtRef.current = Date.now();
      refresh();
    }, ms);
    return () => window.clearInterval(timer);
  }, [refreshInterval, refresh, sseConnected]);

  const handleManualRefresh = useCallback(() => {
    lastAutoRefreshAtRef.current = Date.now();
    setManualRefreshing(true);
    refresh();
  }, [refresh]);

  const handleToggleFavorite = useCallback(async (item: HotspotItem) => {
    const wasFavorited = favoritedIds.has(item.id);
    setFavoritedIds(prev => {
      const next = new Set(prev);
      if (wasFavorited) next.delete(item.id); else next.add(item.id);
      return next;
    });
    setFavoritesCount(prev => Math.max(0, prev + (wasFavorited ? -1 : 1)));
    try {
      if (wasFavorited) {
        const r = await fetch(`/api/favorites/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
      } else {
        const r = await fetch('/api/favorites', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hotspot_id: item.id, category: item.category, title: item.title, source: item.source, url: item.url }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
      }
    } catch {
      setFavoritedIds(prev => {
        const next = new Set(prev);
        if (wasFavorited) next.add(item.id); else next.delete(item.id);
        return next;
      });
      setFavoritesCount(prev => Math.max(0, prev + (wasFavorited ? 1 : -1)));
    }
  }, [favoritedIds]);

  const handleFavoritesChange = useCallback((ids: Set<string>) => {
    setFavoritedIds(ids);
    setFavoritesCount(ids.size);
  }, []);

  const handleCategoryChange = useCallback((cat: string) => {
    if (cat === 'all') navigate('/');
    else navigate(`/category/${cat}`);
  }, [navigate]);

  return (
    <>
      <Header
        latestIngestionCount={latestIngestionCount}
        latestIngestionAt={latestIngestionAt}
        lastUpdated={lastUpdated}
        onRefresh={handleManualRefresh}
        theme={theme}
        onThemeToggle={toggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenFavorites={() => setFavoritesOpen(true)}
        favoritesCount={favoritesCount}
        refreshIntervalMinutes={refreshInterval}
        lastAutoRefreshAtRef={lastAutoRefreshAtRef}
        todosOpenCount={todos.count?.by_status.open ?? 0}
        refreshing={manualRefreshing}
      />

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onRefreshIntervalChange={setRefreshInterval}
      />

      <FavoritesPanel
        open={favoritesOpen}
        onClose={() => setFavoritesOpen(false)}
        onCountChange={setFavoritesCount}
        onFavoritesChange={handleFavoritesChange}
      />

      <CategoryNav
        active={category}
        onChange={handleCategoryChange}
        counts={categoryCounts}
        consistencyDrift={consistencyDrift}
      />

      <SearchBar
        keyword={keyword}
        timeRange={timeRange}
        onKeywordChange={setKeyword}
        onTimeRangeChange={setTimeRange}
      />

      {/* Phase 8: 标讯地区筛选 — 仅 category=bid 时显示 */}
      {category === 'bid' && (
        <div className="mb-3">
          <RegionFilter value={region} onChange={setRegion} />
        </div>
      )}

      {!loading && items.length > 0 && (
        <StatsPanel
          categoryCounts={categoryCounts}
          total={Object.values(categoryCounts).reduce((a, b) => a + b, 0)}
        />
      )}

      {!loading && category === 'all' && <TrendChart />}

      {loading ? (
        <LoadingSkeleton />
      ) : (
        <HotspotGrid
          items={items}
          loading={loading}
          error={error}
          favoritedIds={favoritedIds}
          onToggleFavorite={handleToggleFavorite}
          page={page}
          pageSize={pageSize}
          totalPages={totalPages}
          total={total}
          hasMore={hasMore}
          loadingPage={loadingPage}
          onSetPage={setPage}
          onSetPageSize={setPageSize}
        />
      )}

      <div className="tech-divider mt-6" />
      <footer className="text-center pb-3">
        <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--color-ai)', marginRight: 4 }}>{'>'}</span>
          SecNews 热点地图 | 数据源: 安全客 / Krebs / PortSwigger / SANS / FreeBuf / 奇安信 / AVD / CNNVD / CNVD / 新浪财经 / 东方财富 / Hacker News / aihot / GitHub Trending / 中国政府采购网
        </p>
        <p className="text-xs mt-1.5 font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
          [i] 点击卡片查看原文 · {formatRefreshLabel(refreshInterval)}
        </p>
        <p className="text-xs mt-2 font-mono">
          <a
            href="/api/export"
            target="_blank"
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border transition-colors hover:bg-[var(--bg-hover)]"
            style={{ color: 'var(--color-ai)', borderColor: 'color-mix(in srgb, var(--color-ai) 30%, transparent)' }}
            rel="noreferrer"
          >
            <span>[</span>
            <span>export</span>
            <span>]</span>
            <span>静态 HTML</span>
          </a>
        </p>
      </footer>
    </>
  );
}

export default function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme);
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('hotspot-theme', theme); } catch {}
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  const goHome = useCallback(() => navigate('/'), [navigate]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <Routes>
        {/* Phase 1A: 嵌套 Layout (PageLayout 含 ToastProvider + 外层容器) */}
        <Route element={<PageLayout />}>
          <Route path="/" element={
            <ErrorBoundary onReset={goHome}>
              <HomePage />
            </ErrorBoundary>
          } />
          <Route path="/category/:cat" element={
            <ErrorBoundary onReset={goHome}>
              <HomePage />
            </ErrorBoundary>
          } />
          {/* Phase 5A: Lazy-loaded with Suspense boundary */}
          <Route path="/todos" element={<Suspense fallback={<PageFallback />}><TodosPage /></Suspense>} />
          <Route path="/history" element={<Suspense fallback={<PageFallback />}><HistoryPage favoritedIds={new Set()} onToggleFavorite={() => {}} /></Suspense>} />
          <Route path="/skills" element={<Suspense fallback={<PageFallback />}><SkillsPage onBack={goHome} /></Suspense>} />
          <Route path="/secrets" element={<Suspense fallback={<PageFallback />}><SecretsPage onBack={goHome} /></Suspense>} />
          <Route path="/sync" element={<Suspense fallback={<PageFallback />}><SyncPage onBack={goHome} /></Suspense>} />
          <Route path="/weekly-report" element={<Suspense fallback={<PageFallback />}><WeeklyReportPage onBack={goHome} /></Suspense>} />
          <Route path="/knowledge" element={<Suspense fallback={<PageFallback />}><KnowledgePage onBack={goHome} /></Suspense>} />
          <Route path="/codegarden" element={<Suspense fallback={<PageFallback />}><CodegardenPage onBack={goHome} /></Suspense>} />
          <Route path="/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><CodegardenPhase2bPage onBack={goHome} /></Suspense>} />
          <Route path="/reviews" element={<Suspense fallback={<PageFallback />}><ReviewPage /></Suspense>} />
          <Route path="/deep/:type/:id" element={<Suspense fallback={<PageFallback />}><DeepReadView /></Suspense>} />
          <Route path="/brief" element={<Suspense fallback={<PageFallback />}><BriefModeView /></Suspense>} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  );
}
