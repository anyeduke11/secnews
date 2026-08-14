/**
 * JudgeLayerPage — 判断层首页
 *
 * Phase 5: 设计治理
 * 使用 LayerCard + LayerHeader 统一组件，增加跨层流转指示。
 * 左栏: 质量门禁 + 趋势分析 + 标讯分析
 * 右栏: 阅读模式 + 热力图 + SOUL + 跨层行动
 */
import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTheme } from '../../App';
import { Header } from '../Header';
import { CategoryNav } from '../CategoryNav';
import { TrendChart } from '../TrendChart';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useRefreshInterval } from '../../hooks/useRefreshInterval';
import { useSSE } from '../../hooks/useSSE';
import { LayerCard, LayerCardRow, LayerCardGrid, PipelineFlow, ViewMoreLink, LayerSkeleton } from '../layout/LayerCard';
import { useState, useEffect, useCallback, useMemo } from 'react';
import type { StatsResponse, ConsistencyDrift } from '../../types';

/* ─── 阅读模式入口配置 ─── */

const READING_MODES = [
  { key: 'briefing', label: '简报',   path: '/knowledge/briefing', desc: '每日摘要' },
  { key: 'scan',     label: '扫描',   path: '/knowledge/scan',     desc: '快速浏览' },
  { key: 'deep',     label: '深度',   path: '/knowledge/briefing', desc: '沉浸阅读' },
  { key: 'alert',    label: '告警',   path: '/knowledge/alert',    desc: '异常通知' },
];

/* ─── 质量门禁摘要数据 ─── */

interface RejectionStats {
  total: number;
  by_gate: { gate_name: string; count: number }[];
  today_count: number;
  loaded: boolean;
}

/* ─── 标讯分析摘要数据 ─── */

interface BidSummary {
  region_dist: Record<string, number>;
  status_dist: Record<string, number>;
  total: number;
  loaded: boolean;
}

/* ─── SOUL画像数据 ─── */

interface SoulProfile {
  expertise: Record<string, number>;
  loaded: boolean;
}

/* ─── 主组件 ─── */

export function JudgeLayerPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') || 'all';
  const { theme, toggleTheme } = useTheme();
  const { refreshFromServer } = useRefreshInterval();
  const [manualRefreshing, setManualRefreshing] = useState(false);

  const {
    items, categoryCounts, loading, lastUpdated,
    latestIngestionCount, latestIngestionAt, refresh,
  } = useHotspotData(category, '7d', '', '', '');

  const { connected: sseConnected } = useSSE({
    onEvent: (type, _data) => {
      if (type === 'collect_done') refresh();
    },
  });

  const [rejectionStats, setRejectionStats] = useState<RejectionStats>({ total: 0, by_gate: [], today_count: 0, loaded: false });
  const [bidSummary, setBidSummary] = useState<BidSummary>({ region_dist: {}, status_dist: {}, total: 0, loaded: false });
  const [soulProfile, setSoulProfile] = useState<SoulProfile>({ expertise: {}, loaded: false });

  /* 管线摘要 */
  const pipelineSummary = useMemo(() => ({
    data: 0,
    judge: items.length,
    action: 0,
  }), [items.length]);

  useEffect(() => { refreshFromServer(); }, []);

  /* 加载质量门禁统计 */
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/quality/rejection-stats');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        const today = new Date().toISOString().slice(0, 10);
        const todayCount = (data.trend || []).find((t: any) => t.day === today)?.count ?? 0;
        setRejectionStats({ total: data.total ?? 0, by_gate: data.by_gate ?? [], today_count: todayCount, loaded: true });
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  /* 加载标讯分析摘要 */
  useEffect(() => {
    if (category !== 'bid') return;
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/hotspots?category=bid&limit=1000');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        const bidItems = data.items || [];
        const regionDist: Record<string, number> = {};
        const statusDist: Record<string, number> = {};
        for (const item of bidItems) {
          const region = (item as any).region || '未知';
          regionDist[region] = (regionDist[region] || 0) + 1;
          const status = (item as any).bid_status || '未知';
          statusDist[status] = (statusDist[status] || 0) + 1;
        }
        setBidSummary({ region_dist: regionDist, status_dist: statusDist, total: bidItems.length, loaded: true });
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, [category]);

  /* 加载 SOUL 画像 */
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/soul');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        setSoulProfile({ expertise: data.expertise ?? {}, loaded: true });
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  /* 加载一致性漂移 */
  const [consistencyDrift, setConsistencyDrift] = useState<ConsistencyDrift[]>([]);
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

  const handleManualRefresh = useCallback(() => {
    setManualRefreshing(true);
    refresh();
  }, [refresh]);

  const handleCategoryChange = useCallback((cat: string) => {
    if (cat === 'all') navigate('/judge');
    else navigate(`/judge?category=${cat}`);
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
        refreshing={manualRefreshing}
        pipelineSummary={pipelineSummary}
        layerName="判断层"
        layerSubtitle="我怎么看 · 筛选、分析、关联、提炼洞察"
      />

      <CategoryNav
        active={category}
        onChange={handleCategoryChange}
        counts={categoryCounts}
        consistencyDrift={consistencyDrift}
      />

      {/* 双栏仪表盘布局 — 标准侧栏宽度 280px */}
      <div className="xl:grid xl:grid-cols-[1fr_280px] xl:gap-6">
        {/* ── 左栏：质量门禁 + 趋势 + 标讯分析 ── */}
        <div className="min-w-0 layer-section-gap">
          <QualityGateCard stats={rejectionStats} onViewDetail={() => navigate('/quality/rejection')} />

          {/* 趋势分析 */}
          <LayerCard
            title="趋势分析"
            actions={
              <ViewMoreLink label="查看完整分析 →" onClick={() => navigate('/judge/trends')} />
            }
          >
            <TrendChart />
          </LayerCard>

          {/* 标讯分析摘要（仅筛选标讯时显示） */}
          {category === 'bid' && <BidAnalysisCard summary={bidSummary} onViewDetail={() => navigate('/judge/bid-analysis')} />}
        </div>

        {/* ── 右栏：阅读模式 + 热力图 + SOUL + 跨层行动 ── */}
        <aside className="min-w-0 layer-section-gap">
          <ReadingModeSection navigate={navigate} />
          <AttentionHeatmapSection navigate={navigate} />
          <SoulSection profile={soulProfile} />

          {/* 跨层流转：生成行动 */}
          <LayerCard
            title="生成行动"
            titleStyle="plain"
            badge="judge → action"
            variant="pipeline"
            layerColor="var(--color-warning)"
          >
            <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
              将判断层洞察转化为可执行的动作
            </p>
            <PipelineFlow
              steps={[
                { key: 'data', label: '资料层', count: 0, color: 'var(--color-info)' },
                { key: 'judge', label: '判断层', count: items.length, color: 'var(--color-warning)', active: true },
                { key: 'action', label: '行动层', count: 0, color: 'var(--color-general)' },
              ]}
            />
            <div className="mt-2 flex flex-col gap-1.5">
              <LayerCardRow
                label="生成报告"
                value="→"
                onClick={() => navigate('/action/report')}
                color="var(--accent)"
              />
              <LayerCardRow
                label="创建待办"
                value="→"
                onClick={() => navigate('/action/todos')}
                color="var(--color-general)"
              />
              <LayerCardRow
                label="知识复利"
                value="→"
                onClick={() => navigate('/action/compound')}
                color="var(--color-ai)"
              />
            </div>
          </LayerCard>
        </aside>
      </div>
    </>
  );
}

/* ══════════════════════════════════════════════
   子组件
   ══════════════════════════════════════════════ */

/* ─── 质量门禁卡片 ─── */

function QualityGateCard({ stats, onViewDetail }: { stats: RejectionStats; onViewDetail: () => void }) {
  return (
    <LayerCard
      title="质量门禁"
      badge={stats.loaded ? `${stats.by_gate.length} 道规则` : undefined}
      footer={
        <ViewMoreLink label="查看详情 →" onClick={onViewDetail} />
      }
    >
      <div className="flex items-center gap-3 mb-2">
        <span className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>
          {stats.loaded ? stats.total : '—'}
        </span>
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>累计拒稿</span>
        {stats.loaded && stats.today_count > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-sm ml-auto" style={{ backgroundColor: 'color-mix(in srgb, var(--color-error, #e53e3e) 12%, transparent)', color: 'var(--color-error, #e53e3e)' }}>
            今日 {stats.today_count} 条
          </span>
        )}
      </div>

      {stats.loaded && stats.by_gate.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {stats.by_gate.slice(0, 5).map(g => (
            <span key={g.gate_name} className="text-[10px] px-1.5 py-0.5 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
              {g.gate_name}: {g.count}
            </span>
          ))}
        </div>
      )}
    </LayerCard>
  );
}

/* ─── 标讯分析摘要卡片 ─── */

function BidAnalysisCard({ summary, onViewDetail }: { summary: BidSummary; onViewDetail: () => void }) {
  const topRegions = Object.entries(summary.region_dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const topStatuses = Object.entries(summary.status_dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <LayerCard
      title="标讯分析"
      badge={summary.loaded ? `${summary.total} 条` : undefined}
      footer={
        <ViewMoreLink label="查看完整分析 →" onClick={onViewDetail} />
      }
    >
      {!summary.loaded ? (
        <LayerSkeleton variant="text" />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-bold mb-1.5" style={{ color: 'var(--text-muted)' }}>地区分布</p>
            {topRegions.map(([region, count]) => (
              <div key={region} className="flex items-center justify-between text-[11px] py-0.5">
                <span style={{ color: 'var(--text-secondary)' }}>{region}</span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
            ))}
          </div>
          <div>
            <p className="text-[10px] font-bold mb-1.5" style={{ color: 'var(--text-muted)' }}>状态分布</p>
            {topStatuses.map(([status, count]) => (
              <div key={status} className="flex items-center justify-between text-[11px] py-0.5">
                <span style={{ color: 'var(--text-secondary)' }}>{status}</span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </LayerCard>
  );
}

/* ─── 阅读模式 ─── */

function ReadingModeSection({ navigate }: { navigate: (path: string) => void }) {
  return (
    <LayerCard title="阅读模式" titleStyle="plain">
      <LayerCardGrid
        items={READING_MODES.map(mode => ({
          key: mode.key,
          label: mode.label,
          desc: mode.desc,
          onClick: () => navigate(mode.path),
        }))}
      />
    </LayerCard>
  );
}

/* ─── 注意力热力图（紧凑版） ─── */

function AttentionHeatmapSection({ navigate }: { navigate: (path: string) => void }) {
  return (
    <LayerCard
      title="注意力热力图"
      titleStyle="plain"
      actions={
        <ViewMoreLink label="详情 →" onClick={() => navigate('/judge/heatmap')} />
      }
    >
      <div className="flex items-center justify-center h-20 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
        <a
          href="/judge/heatmap"
          onClick={e => { e.preventDefault(); navigate('/judge/heatmap'); }}
          className="text-[10px] focus-ring transition-colors hover:underline"
          style={{ color: 'var(--text-muted)' }}
        >
          点击查看完整热力图
        </a>
      </div>
    </LayerCard>
  );
}

/* ─── SOUL 画像 ─── */

function SoulSection({ profile }: { profile: SoulProfile }) {
  const topExpertise = Object.entries(profile.expertise)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <LayerCard title="SOUL 画像">
      {!profile.loaded || topExpertise.length === 0 ? (
        <LayerSkeleton variant="row" lines={4} />
      ) : (
        <div className="space-y-2">
          {topExpertise.map(([domain, score]) => (
            <div key={domain} className="flex items-center gap-2">
              <span className="text-[10px] w-12 shrink-0" style={{ color: 'var(--text-secondary)' }}>{domain}</span>
              <div className="flex-1 h-2 rounded-full" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(score * 20, 100)}%`,
                    backgroundColor: 'var(--accent)',
                    opacity: 0.7,
                  }}
                />
              </div>
              <span className="text-[10px] font-mono tabular-nums w-4 text-right" style={{ color: 'var(--text-muted)' }}>
                {score}
              </span>
            </div>
          ))}
        </div>
      )}
    </LayerCard>
  );
}