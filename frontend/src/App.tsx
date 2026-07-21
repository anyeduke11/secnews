import React, { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
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
import { SettingsPanel } from './components/settings';
import { FavoritesPanel } from './components/favorites';
import { HistoryPage } from './components/HistoryPage';
import { TodosPage } from './components/TodosPage';
import { SkillsPage } from './components/SkillsPage';
import { SecretsPage } from './components/SecretsPage';
import { SyncPage } from './components/sync';
import { WeeklyReportPage } from './components/WeeklyReportPage';
import { KnowledgePage } from './components/KnowledgePage';
import { CodegardenPage } from './components/CodegardenPage';
import { CodegardenPhase2bPage } from './components/CodegardenPhase2bPage';
import { useHotspotData } from './hooks/useHotspotData';
import { useRefreshInterval } from './hooks/useRefreshInterval';
import { useTodos } from './hooks/useTodos';
import { useSSE } from './hooks/useSSE';
import { ConsistencyDrift, StatsResponse, HotspotItem } from './types';

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

      <footer
        className="mt-10 pt-5 text-center"
        style={{
          borderTop: '1px solid var(--border-color)',
          position: 'relative',
        }}
      >
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: -1,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 60,
            height: 1,
            background: 'var(--color-ai)',
            opacity: 0.6,
          }}
        />
        <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--color-ai)', marginRight: 4 }}>{'>'}</span>
          热点地图 | 数据源: 安全客 / Krebs / PortSwigger / SANS / FreeBuf / 奇安信 / AVD / CNNVD / CNVD / 新浪财经 / 东方财富 / Hacker News / aihot / GitHub Trending / 中国政府采购网
        </p>
        <p className="text-xs mt-1.5 font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
          [i] 点击卡片查看原文 · {formatRefreshLabel(refreshInterval)}
        </p>
        <p className="text-xs mt-1.5 font-mono">
          <a
            href="/api/export"
            target="_blank"
            className="hover:underline"
            style={{ color: 'var(--color-ai)' }}
            rel="noreferrer"
          >
            {'[ export ]'} 静态 HTML
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
          {/* Phase 5A: HealthDashboard/HistoryPage/TodosPage 已迁移到 useGoHome (移除 onBack prop) */}
          <Route path="/todos" element={<TodosPage />} />
          <Route path="/history" element={<HistoryPage favoritedIds={new Set()} onToggleFavorite={() => {}} />} />
          <Route path="/skills" element={<SkillsPage onBack={goHome} />} />
          <Route path="/secrets" element={<SecretsPage onBack={goHome} />} />
          <Route path="/sync" element={<SyncPage onBack={goHome} />} />
          <Route path="/weekly-report" element={<WeeklyReportPage onBack={goHome} />} />
          <Route path="/knowledge" element={<KnowledgePage onBack={goHome} />} />
          <Route path="/codegarden" element={<CodegardenPage onBack={goHome} />} />
          <Route path="/codegarden/phase2b" element={<CodegardenPhase2bPage onBack={goHome} />} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  );
}
