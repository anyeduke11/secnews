/**
 * ActionLayerPage — 行动层首页
 *
 * Phase 5: 设计治理
 * 使用 LayerCard + LayerHeader 统一组件，增加跨层流转指示。
 * 左栏: 报告生成 + 知识复利 + CodeGarden
 * 右栏: 今日待办 + 投标提醒 + 跨层回溯
 */
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import { Header } from '../Header';
import { CategoryNav } from '../CategoryNav';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useRefreshInterval } from '../../hooks/useRefreshInterval';
import { useSSE } from '../../hooks/useSSE';
import { LayerCard, LayerCardRow, LayerCardGrid, LayerCardAlert, PipelineFlow, ViewMoreLink, LayerSkeleton, LayerEmptyState } from '../layout/LayerCard';
import { useState, useEffect, useCallback, useMemo } from 'react';
import type { StatsResponse, ConsistencyDrift, TodoCountResponse } from '../../types';

/* ─── 类型 ─── */

interface CodeGardenProject {
  id: number;
  name: string;
  type: string;
  lifecycle_stage: string;
  status: string;
  description?: string;
  repo_url?: string;
  created_at: string;
}

interface BidAlertSummary {
  new_today: number;
  total_open: number;
  loaded: boolean;
}

/* ─── 常量 ─── */

const REPORT_TYPES = [
  { key: 'daily',   label: '日报', path: '/report?type=daily',   desc: '今日摘要' },
  { key: 'weekly',  label: '周报', path: '/report?type=weekly',  desc: '本周回顾' },
  { key: 'monthly', label: '月报', path: '/report?type=monthly', desc: '本月总结' },
];

/* ─── 主组件 ─── */

export function ActionLayerPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') || 'all';
  const { theme, toggleTheme } = useTheme();
  const { refreshFromServer } = useRefreshInterval();
  const [consistencyDrift, setConsistencyDrift] = useState<ConsistencyDrift[]>([]);
  const [manualRefreshing, setManualRefreshing] = useState(false);

  const {
    categoryCounts, lastUpdated,
    latestIngestionCount, latestIngestionAt, refresh,
  } = useHotspotData(category, '7d', '', '', '');

  useSSE({
    onEvent: (type, _data) => {
      if (type === 'collect_done') refresh();
    },
  });

  /* 待办统计 */
  const [todoCounts, setTodoCounts] = useState<TodoCountResponse | null>(null);
  const [todoLoaded, setTodoLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/todos/count');
        if (!r.ok) return;
        const data: TodoCountResponse = await r.json();
        if (cancelled) return;
        setTodoCounts(data);
        setTodoLoaded(true);
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const openCount = todoCounts?.by_status?.open ?? 0;
  const importantCount = (todoCounts?.by_priority?.urgent_important ?? 0) + (todoCounts?.by_priority?.important_only ?? 0);

  /* 管线摘要 */
  const pipelineSummary = useMemo(() => ({
    data: 0,
    judge: 0,
    action: openCount + importantCount,
  }), [openCount, importantCount]);

  /* CodeGarden 项目统计 */
  const [codeGardenProjects, setCodeGardenProjects] = useState<CodeGardenProject[]>([]);
  const [cgLoaded, setCgLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/codegarden/projects?limit=100');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        setCodeGardenProjects(data.items || []);
        setCgLoaded(true);
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  /* 标讯提醒摘要 */
  const [bidAlert, setBidAlert] = useState<BidAlertSummary>({ new_today: 0, total_open: 0, loaded: false });

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/hotspots?category=bid&limit=1000');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        const items = data.items || [];
        const today = new Date().toISOString().slice(0, 10);
        const newToday = items.filter((it: any) => {
          const pub = it.published_at || it.created_at || '';
          return pub.startsWith(today);
        }).length;
        setBidAlert({ new_today: newToday, total_open: items.length, loaded: true });
      } catch {}
    };
    load();
    return () => { cancelled = true; };
  }, []);

  /* 一致性漂移 */
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

  const handleManualRefresh = useCallback(() => {
    setManualRefreshing(true);
    refresh();
  }, [refresh]);

  const handleCategoryChange = useCallback((cat: string) => {
    if (cat === 'all') navigate('/action');
    else navigate(`/action?category=${cat}`);
  }, [navigate]);

  const cgActive = codeGardenProjects.filter(p => p.status === 'active' || p.status === 'in_progress');
  const cgCount = cgActive.length > 0 ? `${cgActive.length} 个活跃` : `${codeGardenProjects.length} 个项目`;

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
        layerName="行动层"
        layerSubtitle="我下一步做什么 · 计划、学习、创作、项目管理"
      />

      <CategoryNav
        active={category}
        onChange={handleCategoryChange}
        counts={categoryCounts}
        consistencyDrift={consistencyDrift}
      />

      {/* 双栏仪表盘布局 — 标准侧栏宽度 280px */}
      <div className="xl:grid xl:grid-cols-[1fr_280px] xl:gap-6">
        {/* ── 左栏: 报告生成 + 知识复利 + CodeGarden ── */}
        <div className="min-w-0 layer-section-gap">
          <ReportSection navigate={navigate} />
          <CompoundSection navigate={navigate} />
          <CodeGardenSection
            projects={codeGardenProjects}
            loaded={cgLoaded}
            summary={cgCount}
            navigate={navigate}
          />
        </div>

        {/* ── 右栏: 今日待办 + 投标提醒 + 跨层回溯 ── */}
        <aside className="min-w-0 layer-section-gap">
          <TodoSection
            openCount={openCount}
            importantCount={importantCount}
            loaded={todoLoaded}
            navigate={navigate}
          />

          <BidAlertSection
            alert={bidAlert}
            navigate={navigate}
          />

          {/* 跨层回溯：回溯到判断层 */}
          <LayerCard
            title="跨层回溯"
            titleStyle="plain"
            badge="action ← judge"
            variant="pipeline"
            layerColor="var(--color-general)"
          >
            <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
              回溯判断层的分析结果和洞察
            </p>
            <PipelineFlow
              steps={[
                { key: 'data', label: '资料层', count: 0, color: 'var(--color-info)' },
                { key: 'judge', label: '判断层', count: 0, color: 'var(--color-warning)', active: true },
                { key: 'action', label: '行动层', count: 0, color: 'var(--color-general)' },
              ]}
            />
            <div className="mt-2 flex flex-col gap-1.5">
              <LayerCardRow
                label="趋势分析"
                value="←"
                onClick={() => navigate('/judge/trends')}
                color="var(--color-ai)"
              />
              <LayerCardRow
                label="质量门禁"
                value="←"
                onClick={() => navigate('/quality/rejection')}
                color="var(--color-error)"
              />
              <LayerCardRow
                label="标讯分析"
                value="←"
                onClick={() => navigate('/judge/bid-analysis')}
                color="var(--color-bid)"
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

/* ─── 报告生成 ─── */

function ReportSection({ navigate }: { navigate: (path: string) => void }) {
  return (
    <LayerCard title="报告生成" titleStyle="plain" badge="AIHot 风格简报">
      <LayerCardGrid
        items={REPORT_TYPES.map(rt => ({
          key: rt.key,
          label: rt.label,
          desc: rt.desc,
          onClick: () => navigate(rt.path),
        }))}
      />
    </LayerCard>
  );
}

/* ─── 知识复利 ─── */

function CompoundSection({ navigate }: { navigate: (path: string) => void }) {
  const shortcuts = [
    { key: 'learning', label: '学习路径', path: '/action/compound' },
    { key: 'mastery',  label: '掌握度',   path: '/action/compound' },
    { key: 'calendar', label: '创作日历', path: '/action/compound' },
    { key: 'drafts',   label: '草稿箱',   path: '/action/compound' },
  ];

  return (
    <LayerCard
      title="知识复利"
      titleStyle="plain"
      actions={
        <ViewMoreLink label="进入复利空间 →" onClick={() => navigate('/action/compound')} />
      }
    >
      <LayerCardGrid
        items={shortcuts.map(sc => ({
          key: sc.key,
          label: sc.label,
          onClick: () => navigate(sc.path),
        }))}
      />
    </LayerCard>
  );
}

/* ─── CodeGarden ─── */

function CodeGardenSection({
  projects, loaded, summary, navigate,
}: {
  projects: CodeGardenProject[];
  loaded: boolean;
  summary: string;
  navigate: (path: string) => void;
}) {
  const activeProjects = projects
    .filter(p => p.status === 'active' || p.status === 'in_progress')
    .slice(0, 3);

  return (
    <LayerCard
      title="CodeGarden"
      badge={loaded ? summary : '加载中...'}
      footer={
        <>
          <ViewMoreLink label="项目管理 →" onClick={() => navigate('/action/codegarden')} />
          <ViewMoreLink label="服务网格 →" onClick={() => navigate('/action/codegarden/phase2b')} />
        </>
      }
    >
      {!loaded ? (
        <LayerSkeleton variant="text" />
      ) : activeProjects.length === 0 ? (
        <LayerEmptyState
          message="暂无活跃项目"
          action={{ label: '创建新项目 →', onClick: () => navigate('/action/codegarden') }}
        />
      ) : (
        <div className="space-y-1.5">
          {activeProjects.map(p => (
            <LayerCardRow
              key={p.id}
              label={p.name}
              value={p.lifecycle_stage || p.status}
            />
          ))}
        </div>
      )}
    </LayerCard>
  );
}

/* ─── 今日待办 ─── */

function TodoSection({
  openCount, importantCount, loaded, navigate,
}: {
  openCount: number;
  importantCount: number;
  loaded: boolean;
  navigate: (path: string) => void;
}) {
  const items = [
    { label: '待办任务', count: openCount, path: '/action/todos', color: 'var(--accent)' },
    { label: '待复习',   count: 0,         path: '/action/review', color: 'var(--color-finance)' },
    { label: '待整理',   count: 0,         path: '/action/outbox', color: 'var(--color-startup)' },
  ];

  return (
    <LayerCard
      title="今日待办"
      badge={loaded ? `${openCount} 条待办` : undefined}
      footer={
        <ViewMoreLink label="查看全部待办 →" onClick={() => navigate('/action/todos')} />
      }
    >
      {!loaded ? (
        <LayerSkeleton variant="row" lines={3} />
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <LayerCardRow
              key={item.label}
              label={item.label}
              value={item.count > 0 ? item.count : '—'}
              onClick={() => navigate(item.path)}
              color={item.color}
            />
          ))}
          {importantCount > 0 && (
            <LayerCardAlert
              label="重要"
              value={`${importantCount} 条待办标记为重要`}
              color="var(--color-error, #e53e3e)"
            />
          )}
        </div>
      )}
    </LayerCard>
  );
}

/* ─── 投标提醒 ─── */

function BidAlertSection({
  alert, navigate,
}: {
  alert: BidAlertSummary;
  navigate: (path: string) => void;
}) {
  return (
    <LayerCard
      title="投标提醒"
      titleStyle="plain"
      actions={
        <ViewMoreLink label="分析 →" onClick={() => navigate('/judge/bid-analysis')} />
      }
    >
      {!alert.loaded ? (
        <LayerSkeleton variant="row" lines={2} />
      ) : (
        <div className="space-y-2">
          <LayerCardRow
            label="标讯总数"
            value={alert.total_open}
            color="var(--accent)"
          />
          {alert.new_today > 0 && (
            <LayerCardAlert
              label="今日新增"
              value={`${alert.new_today} 条`}
              color="var(--color-bid, #d69e2e)"
            />
          )}
        </div>
      )}
    </LayerCard>
  );
}