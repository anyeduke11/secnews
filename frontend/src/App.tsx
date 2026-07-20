import React, { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { CategoryNav } from './components/CategoryNav';
import { SearchBar } from './components/SearchBar';
import { StatsPanel } from './components/StatsPanel';
import { TrendChart } from './components/TrendChart';
import { HotspotGrid } from './components/HotspotGrid';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { SettingsPanel } from './components/SettingsPanel';
import { FavoritesPanel } from './components/FavoritesPanel';
import { HistoryPage } from './components/HistoryPage';
import { TodosPage } from './components/TodosPage';
import { SkillsPage } from './components/SkillsPage';
import { SecretsPage } from './components/SecretsPage';
import { SyncPage } from './components/SyncPage';
import { WeeklyReportPage } from './components/WeeklyReportPage';
import { KnowledgePage } from './components/KnowledgePage';
import { CodegardenPage } from './components/CodegardenPage';
import { useHotspotData } from './hooks/useHotspotData';
import { useRefreshInterval } from './hooks/useRefreshInterval';
import { useTodos } from './hooks/useTodos';
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
  } = useHotspotData(category, timeRange, keyword);

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
    const ms = Math.max(refreshInterval, 1) * 60 * 1000;
    lastAutoRefreshAtRef.current = Date.now();
    const timer = window.setInterval(() => {
      lastAutoRefreshAtRef.current = Date.now();
      refresh();
    }, ms);
    return () => window.clearInterval(timer);
  }, [refreshInterval, refresh]);

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

  const handleOpenSidebar = useCallback(() => {
    window.dispatchEvent(new CustomEvent('hotspot:open-sidebar'));
  }, []);

  // 当前分类的人类可读标题
  const currentCatLabel = (() => {
    if (category === 'all') return '全部热点';
    const map: Record<string, string> = {
      ai: '科技 / AI',
      security: '网络安全',
      finance: '金融 / 投资',
      startup: '独立开发 / 创业',
      bid: '招标资讯',
      github: 'GitHub 项目',
    };
    return map[category] || '全部热点';
  })();

  return (
    <div className="home-main">
      <TopBar
        pageTitle={currentCatLabel}
        pageSubtitle="七大领域热点实时聚合"
        latestIngestionCount={latestIngestionCount}
        lastUpdated={lastUpdated}
        refreshIntervalMinutes={refreshInterval}
        lastAutoRefreshAtRef={lastAutoRefreshAtRef}
        onOpenSidebar={handleOpenSidebar}
        onRefresh={handleManualRefresh}
        refreshing={manualRefreshing}
        theme={theme}
        onThemeToggle={toggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenFavorites={() => setFavoritesOpen(true)}
        favoritesCount={favoritesCount}
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

      <footer className="mt-8 pt-4 text-center" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {category === 'all' ? (
          <div className="datasource-block">
            <div className="source-section-label">数据源 · 7 大类聚合</div>
            <ul className="source-list">
              <li>aihot.virxact.com</li>
              <li>安全客 · Krebs · PortSwigger</li>
              <li>FreeBuf · SANS ISC</li>
              <li>奇安信 · AVD · CNNVD</li>
              <li>新浪财经 · 东方财富</li>
              <li>Hacker News · GitHub</li>
              <li>中国政府采购网</li>
            </ul>
          </div>
        ) : (
          <p className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
            热点地图 · 16 数据源聚合 · v1.4
          </p>
        )}
      </footer>

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
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const todos = useTodos();
  const [secretTTL, setSecretTTL] = useState<number | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('hotspot-theme', theme); } catch {}
  }, [theme]);

  useEffect(() => {
    const handler = () => setSidebarOpen(true);
    window.addEventListener('hotspot:open-sidebar', handler);
    return () => window.removeEventListener('hotspot:open-sidebar', handler);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch('/api/secrets/status');
        if (!cancelled && r.ok) {
          const data = await r.json();
          if (data.setup && data.unlocked) {
            setSecretTTL(data.remaining_seconds);
          } else {
            setSecretTTL(null);
          }
        }
      } catch {}
    };
    poll();
    const t = window.setInterval(poll, 15000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  const goHome = useCallback(() => navigate('/'), [navigate]);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <div className="app-shell">
        <div className="app-grid">
          <Sidebar
            open={sidebarOpen}
            onClose={closeSidebar}
            todosOpenCount={todos.count?.by_status.open ?? 0}
            secretTTL={secretTTL}
          />
          <div className="app-main-col">
            <div className="app-container">
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/category/:cat" element={<HomePage />} />
                <Route path="/todos" element={<TodosPage />} />
                <Route path="/history" element={<HistoryPage favoritedIds={new Set()} onToggleFavorite={() => {}} />} />
                <Route path="/skills" element={<SkillsPage />} />
                <Route path="/secrets" element={<SecretsPage />} />
                <Route path="/sync" element={<SyncPage />} />
                <Route path="/weekly-report" element={<WeeklyReportPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/codegarden" element={<CodegardenPage />} />
              </Routes>
            </div>
          </div>
        </div>
      </div>
    </ThemeContext.Provider>
  );
}
