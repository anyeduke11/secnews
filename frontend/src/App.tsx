import React, { Suspense, useState, useEffect, useCallback, createContext, useContext } from 'react';
import { Routes, Route, Navigate, useNavigate, useParams } from 'react-router-dom';
import { PageLayout } from './components/PageLayout';
import { useFavorites } from './hooks/useFavorites';
// Lazy-loaded page components — split into separate chunks to reduce initial bundle size.
const SettingsPage = React.lazy(() =>
  import('./components/settings/SettingsPage').then(m => ({ default: m.SettingsPage }))
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
  import('./components/secrets/SecretsPage').then(m => ({ default: m.SecretsPage }))
);
const SyncPage = React.lazy(() =>
  import('./components/sync').then(m => ({ default: m.SyncPage }))
);
const ReportPage = React.lazy(() =>
  import('./components/report/ReportPage').then(m => ({ default: m.ReportPage }))
);
const KnowledgePage = React.lazy(() =>
  import('./components/KnowledgePage').then(m => ({ default: m.KnowledgePage }))
);
const KnowledgeImport = React.lazy(() =>
  import('./components/knowledge/KnowledgeImport').then(m => ({ default: m.KnowledgeImport }))
);
const KnowledgeProcess = React.lazy(() =>
  import('./components/knowledge/KnowledgeProcess').then(m => ({ default: m.KnowledgeProcess }))
);
const KnowledgeCompile = React.lazy(() =>
  import('./components/knowledge/KnowledgeCompile').then(m => ({ default: m.KnowledgeCompile }))
);
const KnowledgeCompound = React.lazy(() =>
  import('./components/knowledge/KnowledgeCompound').then(m => ({ default: m.KnowledgeCompound }))
);
const KnowledgeFavoritesView = React.lazy(() =>
  import('./components/knowledge/KnowledgeFavoritesView')
);
const BriefingMode = React.lazy(() =>
  import('./components/knowledge/BriefingMode').then(m => ({ default: m.BriefingMode }))
);
const ScanMode = React.lazy(() =>
  import('./components/knowledge/ScanMode').then(m => ({ default: m.ScanMode }))
);
const DeepReadMode = React.lazy(() =>
  import('./components/knowledge/DeepReadMode').then(m => ({ default: m.DeepReadMode }))
);
const AlertMode = React.lazy(() =>
  import('./components/knowledge/AlertMode').then(m => ({ default: m.AlertMode }))
);
const OutboxMode = React.lazy(() =>
  import('./components/knowledge/OutboxMode').then(m => ({ default: m.OutboxMode }))
);
const ReviewMode = React.lazy(() =>
  import('./components/knowledge/ReviewMode').then(m => ({ default: m.ReviewMode }))
);
const AttentionHeatmap = React.lazy(() =>
  import('./components/knowledge/AttentionHeatmap').then(m => ({ default: m.AttentionHeatmap }))
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
const QualityRejectionPage = React.lazy(() =>
  import('./components/QualityRejectionPage').then(m => ({ default: m.default }))
);

// Phase 1: 三层架构页面
const DataLayerPage = React.lazy(() =>
  import('./components/data/DataLayerPage').then(m => ({ default: m.DataLayerPage }))
);
const JudgeLayerPage = React.lazy(() =>
  import('./components/judge/JudgeLayerPage').then(m => ({ default: m.JudgeLayerPage }))
);
const ActionLayerPage = React.lazy(() =>
  import('./components/action/ActionLayerPage').then(m => ({ default: m.ActionLayerPage }))
);
// Phase 2: 资料层子页面
const DataImportPage = React.lazy(() =>
  import('./components/data/DataImportPage').then(m => ({ default: m.DataImportPage }))
);
const DataFavoritesPage = React.lazy(() =>
  import('./components/data/DataFavoritesPage').then(m => ({ default: m.DataFavoritesPage }))
);
// Phase 3: 判断层子页面
const JudgeTrendsPage = React.lazy(() =>
  import('./components/judge/JudgeTrendsPage').then(m => ({ default: m.JudgeTrendsPage }))
);
const JudgeBidAnalysisPage = React.lazy(() =>
  import('./components/judge/JudgeBidAnalysisPage').then(m => ({ default: m.JudgeBidAnalysisPage }))
);

// Phase 4: 行动层子页面（包装现有组件，添加行动层导航头）
const ActionReportPage = React.lazy(() =>
  import('./components/action/ActionReportPage').then(m => ({ default: m.ActionReportPage }))
);
const ActionCompoundPage = React.lazy(() =>
  import('./components/action/ActionCompoundPage').then(m => ({ default: m.ActionCompoundPage }))
);
const ActionTodosPage = React.lazy(() =>
  import('./components/action/ActionTodosPage').then(m => ({ default: m.ActionTodosPage }))
);
const ActionOutboxPage = React.lazy(() =>
  import('./components/action/ActionOutboxPage').then(m => ({ default: m.ActionOutboxPage }))
);
const ActionReviewPage = React.lazy(() =>
  import('./components/action/ActionReviewPage').then(m => ({ default: m.ActionReviewPage }))
);
const ActionCodegardenPage = React.lazy(() =>
  import('./components/action/ActionCodegardenPage').then(m => ({ default: m.ActionCodegardenPage }))
);
const ActionCodegardenPhase2bPage = React.lazy(() =>
  import('./components/action/ActionCodegardenPhase2bPage').then(m => ({ default: m.ActionCodegardenPhase2bPage }))
);
const ActionSkillsPage = React.lazy(() =>
  import('./components/action/ActionSkillsPage').then(m => ({ default: m.ActionSkillsPage }))
);
const ActionBidAlertPage = React.lazy(() =>
  import('./components/action/ActionBidAlertPage').then(m => ({ default: m.ActionBidAlertPage }))
);

/** 旧路由 /category/:cat 重定向到资料层，带上 category 参数 */
function CategoryRedirect() {
  const { cat } = useParams<{ cat: string }>();
  return <Navigate to={`/data?category=${cat}`} replace />;
}

/** Minimal loading fallback for Suspense-wrapped routes. */
function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
        正在排版…
      </div>
    </div>
  );
}


interface ThemeContextValue {
  theme: 'dark' | 'light';
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
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
  // v1.9 Editorial: 日报版 (light) 为新默认, 夜读版 (dark) 可切换
  return 'light';
}

// v1.8: /history 独立路由的收藏状态壳 —— 改用 useFavorites 共享 store
// (之前是本地空 Set + 手动 fetch + 乐观更新, 与 DataLayerPage 各持一份导致不同步)
function HistoryPageRoute() {
  const { favorites: favoritedIds, toggleFavorite } = useFavorites();
  return <HistoryPage favoritedIds={favoritedIds} onToggleFavorite={toggleFavorite} />;
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
          {/* ── 三层架构新路由 ── */}
          <Route path="/data" element={<Suspense fallback={<PageFallback />}><DataLayerPage /></Suspense>} />
          <Route path="/data/import" element={<Suspense fallback={<PageFallback />}><DataImportPage /></Suspense>} />
          <Route path="/data/favorites" element={<Suspense fallback={<PageFallback />}><DataFavoritesPage /></Suspense>} />
          <Route path="/data/history" element={<HistoryPageRoute />} />
          <Route path="/judge" element={<Suspense fallback={<PageFallback />}><JudgeLayerPage /></Suspense>} />
          <Route path="/action" element={<Suspense fallback={<PageFallback />}><ActionLayerPage /></Suspense>} />

          {/* ── 旧路由兼容: Navigate 到新路由 ── */}
          <Route path="/" element={<Navigate to="/data" replace />} />
          <Route path="/category/:cat" element={<CategoryRedirect />} />
          <Route path="/weekly-report" element={<Navigate to="/report" replace />} />

          {/* ── 行动层子路由 (Phase 4: 实际包装页面，替换旧重定向) ── */}
          <Route path="/action/report" element={<Suspense fallback={<PageFallback />}><ActionReportPage /></Suspense>} />
          <Route path="/action/compound" element={<Suspense fallback={<PageFallback />}><ActionCompoundPage /></Suspense>} />
          <Route path="/action/todos" element={<Suspense fallback={<PageFallback />}><ActionTodosPage /></Suspense>} />
          <Route path="/action/outbox" element={<Suspense fallback={<PageFallback />}><ActionOutboxPage /></Suspense>} />
          <Route path="/action/review" element={<Suspense fallback={<PageFallback />}><ActionReviewPage /></Suspense>} />
          <Route path="/action/skills" element={<Suspense fallback={<PageFallback />}><ActionSkillsPage /></Suspense>} />
          <Route path="/action/codegarden" element={<Suspense fallback={<PageFallback />}><ActionCodegardenPage /></Suspense>} />
          <Route path="/action/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><ActionCodegardenPhase2bPage /></Suspense>} />
          <Route path="/action/bid-alert" element={<Suspense fallback={<PageFallback />}><ActionBidAlertPage /></Suspense>} />

          {/* ── 判断层子路由（Phase 3: 趋势/标讯分析独立页面，其余保留跳转） ── */}
          <Route path="/judge/trends" element={<Suspense fallback={<PageFallback />}><JudgeTrendsPage /></Suspense>} />
          <Route path="/judge/bid-analysis" element={<Suspense fallback={<PageFallback />}><JudgeBidAnalysisPage /></Suspense>} />
          <Route path="/judge/quality" element={<Navigate to="/quality/rejection" replace />} />
          <Route path="/judge/heatmap" element={<Navigate to="/knowledge/heatmap" replace />} />
          <Route path="/judge/graph" element={<Navigate to="/knowledge/process" replace />} />
          <Route path="/judge/compile" element={<Navigate to="/knowledge/compile" replace />} />
          <Route path="/judge/read" element={<Navigate to="/knowledge/briefing" replace />} />

          {/* ── 保留的旧路由 (内容尚未迁移) ── */}
          <Route path="/todos" element={<Suspense fallback={<PageFallback />}><TodosPage /></Suspense>} />
          <Route path="/history" element={<Suspense fallback={<PageFallback />}><HistoryPageRoute /></Suspense>} />
          <Route path="/skills" element={<Suspense fallback={<PageFallback />}><SkillsPage onBack={goHome} /></Suspense>} />
          <Route path="/secrets" element={<Suspense fallback={<PageFallback />}><SecretsPage onBack={goHome} /></Suspense>} />
          <Route path="/sync" element={<Suspense fallback={<PageFallback />}><SyncPage onBack={goHome} /></Suspense>} />
          <Route path="/settings" element={<Suspense fallback={<PageFallback />}><SettingsPage /></Suspense>} />
          <Route path="/report" element={<Suspense fallback={<PageFallback />}><ReportPage onBack={goHome} /></Suspense>} />
          {/* 知识管理: 4 大领域 (信息导入 / 处理数据 / 知识库编译 / 知识复利) */}
          <Route path="/knowledge" element={<Suspense fallback={<PageFallback />}><KnowledgePage onBack={goHome} /></Suspense>}>
            <Route index element={<Navigate to="import" replace />} />
            <Route path="import" element={<Suspense fallback={<PageFallback />}><KnowledgeImport /></Suspense>} />
            <Route path="process" element={<Suspense fallback={<PageFallback />}><KnowledgeProcess /></Suspense>} />
            <Route path="compile" element={<Suspense fallback={<PageFallback />}><KnowledgeCompile /></Suspense>} />
            <Route path="compound" element={<Suspense fallback={<PageFallback />}><KnowledgeCompound /></Suspense>} />
            <Route path="imported" element={<Suspense fallback={<PageFallback />}><KnowledgeFavoritesView /></Suspense>} />
            <Route path="briefing" element={<Suspense fallback={<PageFallback />}><BriefingMode /></Suspense>} />
            <Route path="scan" element={<Suspense fallback={<PageFallback />}><ScanMode /></Suspense>} />
            <Route path="deep-read/:id" element={<Suspense fallback={<PageFallback />}><DeepReadMode /></Suspense>} />
            <Route path="alert" element={<Suspense fallback={<PageFallback />}><AlertMode /></Suspense>} />
            <Route path="outbox" element={<Suspense fallback={<PageFallback />}><OutboxMode /></Suspense>} />
            <Route path="review" element={<Suspense fallback={<PageFallback />}><ReviewMode /></Suspense>} />
            <Route path="heatmap" element={<Suspense fallback={<PageFallback />}><AttentionHeatmap /></Suspense>} />
          </Route>
          <Route path="/codegarden" element={<Suspense fallback={<PageFallback />}><CodegardenPage onBack={goHome} /></Suspense>} />
          <Route path="/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><CodegardenPhase2bPage onBack={goHome} /></Suspense>} />
          <Route path="/reviews" element={<Suspense fallback={<PageFallback />}><ReviewPage /></Suspense>} />
          <Route path="/deep/:type/:id" element={<Suspense fallback={<PageFallback />}><DeepReadView /></Suspense>} />
          <Route path="/brief" element={<Suspense fallback={<PageFallback />}><BriefModeView /></Suspense>} />
          <Route path="/quality/rejection" element={<Suspense fallback={<PageFallback />}><QualityRejectionPage /></Suspense>} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  );
}
