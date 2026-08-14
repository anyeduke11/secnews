/**
 * DataLayerPage — 资料层首页
 *
 * Phase 5: 设计治理
 * 使用 LayerCard + LayerHeader 统一组件，增加跨层流转指示。
 * 左栏: 资讯流/标讯列表
 * 右栏: 快捷入口 + 跨层流转 + 统计 + 趋势
 */
import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useRefreshInterval } from '../../hooks/useRefreshInterval';
import { useTodos } from '../../hooks/useTodos';
import { useFavorites, syncFavorites } from '../../hooks/useFavorites';
import { useSSE } from '../../hooks/useSSE';
import { Header } from '../Header';
import { CategoryNav } from '../CategoryNav';
import { SearchBar } from '../SearchBar';
import { StatsPanel } from '../StatsPanel';
import { TrendChart } from '../TrendChart';
import { HotspotGrid } from '../HotspotGrid';
import { LoadingSkeleton } from '../LoadingSkeleton';
import { RegionFilter } from '../RegionFilter';
import { FavoritesPanel } from '../favorites';
import { LayerCard, LayerCardRow, PipelineFlow, ViewMoreLink } from '../layout/LayerCard';
import { useTheme } from '../../App';
import type { ConsistencyDrift, StatsResponse } from '../../types';
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';

export function DataLayerPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') || 'all';
  const { theme, toggleTheme } = useTheme();

  const [timeRange, setTimeRange] = useState('7d');
  const [keyword, setKeyword] = useState('');
  const [region, setRegion] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [consistencyDrift, setConsistencyDrift] = useState<ConsistencyDrift[]>([]);
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const { interval: refreshInterval, setInterval: setRefreshInterval, refreshFromServer } = useRefreshInterval();
  const lastAutoRefreshAtRef = useRef<number>(Date.now());

  // 收藏状态统一走 useFavorites 共享 store (ids + 总数 + 乐观更新/回滚)
  const { favorites: favoritedIds, count: favoritesCount, toggleFavorite } = useFavorites();

  const {
    items, total, categoryCounts, loading, loadingPage, error, lastUpdated,
    hasMore, page, pageSize, totalPages, setPage, setPageSize, refresh,
    latestIngestionCount, latestIngestionAt,
  } = useHotspotData(category, timeRange, keyword, region, sourceFilter);

  const todos = useTodos();

  const { connected: sseConnected } = useSSE({
    onEvent: (type, _data) => {
      if (type === 'collect_done') refresh();
    },
  });

  /* 管线摘要 — 各层数据量 */
  const pipelineSummary = useMemo(() => ({
    data: total,
    judge: 0,
    action: 0,
  }), [total]);

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
    if (sseConnected) return;
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

  // FavoritesPanel 桥接: 面板内部仍是独立列表, 通过回调把 ids/count 同步进共享 store
  const handleFavoritesChange = useCallback((ids: Set<string>) => {
    syncFavorites(ids, ids.size);
  }, []);

  const handleCategoryChange = useCallback((cat: string) => {
    if (cat === 'all') navigate('/data');
    else navigate(`/data?category=${cat}`);
  }, [navigate]);

  const handleItemCategoryClick = useCallback((cat: string) => {
    handleCategoryChange(cat === 'tech' ? 'ai' : cat);
  }, [handleCategoryChange]);

  const handleItemSourceClick = useCallback((source: string) => {
    setSourceFilter(prev => (prev === source ? '' : source));
  }, []);

  return (
    <>
      <Header
        latestIngestionCount={latestIngestionCount}
        latestIngestionAt={latestIngestionAt}
        lastUpdated={lastUpdated}
        onRefresh={handleManualRefresh}
        theme={theme}
        onThemeToggle={toggleTheme}
        onOpenFavorites={() => setFavoritesOpen(true)}
        favoritesCount={favoritesCount}
        refreshIntervalMinutes={refreshInterval}
        lastAutoRefreshAtRef={lastAutoRefreshAtRef}
        todosOpenCount={todos.count?.by_status.open ?? 0}
        refreshing={manualRefreshing}
        pipelineSummary={pipelineSummary}
        layerName="资料层"
        layerSubtitle="我有什么 · 信息采集与组织"
      />

      <FavoritesPanel
        open={favoritesOpen}
        onClose={() => setFavoritesOpen(false)}
        onCountChange={(count) => syncFavorites(undefined, count)}
        onFavoritesChange={handleFavoritesChange}
      />

      {/* 层内领域筛选器 */}
      <CategoryNav
        active={category}
        onChange={handleCategoryChange}
        counts={categoryCounts}
        consistencyDrift={consistencyDrift}
      />

      {/* 主内容区 — 标准侧栏宽度 280px */}
      <div className="xl:grid xl:grid-cols-[1fr_280px] xl:gap-6">
        <main className="min-w-0">
          <SearchBar
            keyword={keyword}
            timeRange={timeRange}
            onKeywordChange={setKeyword}
            onTimeRangeChange={setTimeRange}
          />

          {category === 'bid' && (
            <div className="mb-3">
              <RegionFilter value={region} onChange={setRegion} />
            </div>
          )}

          {sourceFilter && (
            <div className="mb-3 flex items-center gap-2 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
              <span>来源筛选</span>
              <button
                type="button"
                onClick={() => setSourceFilter('')}
                className="ink-chip active focus-ring transition-colors"
                style={{ padding: '3px 9px' }}
              >
                {sourceFilter}
                <span aria-hidden="true" style={{ fontWeight: 400 }}>×</span>
              </button>
            </div>
          )}

          {loading ? (
            <LoadingSkeleton />
          ) : (
            <HotspotGrid
              items={items}
              loading={loading}
              error={error}
              favoritedIds={favoritedIds}
              onToggleFavorite={toggleFavorite}
              page={page}
              pageSize={pageSize}
              totalPages={totalPages}
              total={total}
              hasMore={hasMore}
              loadingPage={loadingPage}
              onSetPage={setPage}
              onSetPageSize={setPageSize}
              onCategoryClick={handleItemCategoryClick}
              onSourceClick={handleItemSourceClick}
            />
          )}
        </main>

        <aside className="min-w-0 layer-section-gap">
          {/* 快捷入口组 */}
          <LayerCard title="快捷入口" titleStyle="plain">
            <div className="flex flex-col gap-1.5">
              <LayerCardRow
                label="知识导入"
                value="Cubox / 书签"
                onClick={() => navigate('/data/import')}
                color="var(--accent)"
              />
              <LayerCardRow
                label="收藏夹"
                value={favoritesCount > 0 ? `${favoritesCount} 条` : '0 条'}
                onClick={() => navigate('/data/favorites')}
                color="var(--color-general)"
              />
              <LayerCardRow
                label="历史记录"
                value="按周浏览"
                onClick={() => navigate('/data/history')}
                color="var(--color-finance)"
              />
            </div>
          </LayerCard>

          {/* 跨层流转：发送到判断层 */}
          {!loading && items.length > 0 && (
            <LayerCard
              title="跨层流转"
              titleStyle="plain"
              badge={`${items.length} 条待分析`}
              variant="pipeline"
              layerColor="var(--color-info)"
            >
              <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
                将采集到的信息送入判断层进行分析
              </p>
              <PipelineFlow
                steps={[
                  { key: 'data', label: '资料层', count: items.length, color: 'var(--color-info)', active: true },
                  { key: 'judge', label: '判断层', count: 0, color: 'var(--color-warning)' },
                  { key: 'action', label: '行动层', count: 0, color: 'var(--color-general)' },
                ]}
              />
              <div className="mt-3 flow-action-btn-grid">
                <button
                  onClick={() => navigate(`/judge/trends?category=${category}`)}
                  className="text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)] focus-ring"
                  style={{ border: '1px solid var(--border-color)' }}
                >
                  <div className="text-[11px] font-medium" style={{ color: 'var(--color-ai)' }}>趋势分析</div>
                  <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>查看数据趋势</div>
                </button>
                {category === 'bid' && (
                  <button
                    onClick={() => navigate('/judge/bid-analysis')}
                    className="text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)] focus-ring"
                    style={{ border: '1px solid var(--border-color)' }}
                  >
                    <div className="text-[11px] font-medium" style={{ color: 'var(--color-bid)' }}>标讯分析</div>
                    <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>竞争态势研判</div>
                  </button>
                )}
                <button
                  onClick={() => navigate('/quality/rejection')}
                  className="text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)] focus-ring"
                  style={{ border: '1px solid var(--border-color)' }}
                >
                  <div className="text-[11px] font-medium" style={{ color: 'var(--color-error)' }}>质量门禁</div>
                  <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>审查拒稿记录</div>
                </button>
              </div>
            </LayerCard>
          )}

          {/* 统计面板 */}
          {!loading && items.length > 0 && (
            <StatsPanel
              categoryCounts={categoryCounts}
              total={Object.values(categoryCounts).reduce((a, b) => a + b, 0)}
            />
          )}

          {/* 趋势图 */}
          {!loading && category === 'all' && <TrendChart />}
        </aside>
      </div>

      {/* 页脚 */}
      <div className="editorial-divider mt-6" />
      <footer className="text-center pb-4">
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          SecNews 热点地图 · 数据源: 安全客 / Krebs / PortSwigger / SANS / FreeBuf / 奇安信 / AVD / CNNVD / CNVD / 新浪财经 / 东方财富 / Hacker News / aihot / GitHub Trending / 中国政府采购网
        </p>
        <p className="text-xs mt-2 font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
          <a href="/api/export" target="_blank" className="inline-flex items-center gap-1 px-2.5 py-1 rounded-sm border transition-colors hover:bg-[var(--bg-hover)]" style={{ color: 'var(--accent)', borderColor: 'color-mix(in srgb, var(--accent) 40%, transparent)' }} rel="noreferrer">export</a>
        </p>
      </footer>
    </>
  );
}