import React, { Suspense, useCallback } from 'react';
import { Routes, Route, Navigate, useNavigate, useParams } from 'react-router-dom';
import { PageLayout } from '../components/PageLayout';
import { useFavorites } from '../hooks/useFavorites';
import { useFeatureFlags } from '../hooks/useFeatureFlags';
import * as P from './lazy-imports';

// Stage1 拆分: 路由声明 = 应用结构图, 所有 <Route> 集中于此, 与 lazy-imports.ts 1:1 映射。
// Stage1 批1 命名整理:
//  - 所有旧路由重定向统一标注 "v0.4 兼容性保留", Stage6 再按实测使用频率决定去留
//  - /deep/:type/:id (DeepReadView) vs /knowledge/deep-read/:id (DeepReadMode):
//    /deep 是跨实体深读视图, /knowledge/deep-read 属知识库阅读流, 并存不冲突
//  - P1.4: /brief (官方每日简报 digest) 已合并进 /knowledge/briefing, 旧路径重定向

/** 旧路由 /category/:cat 重定向到资料层，带上 category 参数 */
function CategoryRedirect() {
  const { cat } = useParams<{ cat: string }>();
  return <Navigate to={`/data?category=${cat}`} replace />;
}

/** Suspense 全局加载占位 (不进行白屏) */
function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[40vh]">
      <div className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
        正在排版…
      </div>
    </div>
  );
}

// v1.8: /history 独立路由的收藏状态壳 —— 改用 useFavorites 共享 store
// (之前是本地空 Set + 手动 fetch + 乐观更新, 与 DataLayerPage 各持一份导致不同步)
function HistoryPageRoute() {
  const { favorites: favoritedIds, toggleFavorite } = useFavorites();
  return <P.HistoryPage favoritedIds={favoritedIds} onToggleFavorite={toggleFavorite} />;
}

export function AppRoutes() {
  const navigate = useNavigate();
  // v0.4.3: 扩展路由按 feature flag 条件渲染 (core 路由永远注册)
  const features = useFeatureFlags();
  const goHome = useCallback(() => navigate('/'), [navigate]);

  return (
    <Routes>
      {/* v4.3: 报纸版式 (Editorial) — 独立全屏，不走 PageLayout */}
      <Route path="/editorial" element={<Suspense fallback={<PageFallback />}><P.EditorialView /></Suspense>} />

      {/* Phase 1A: 嵌套 Layout (PageLayout 含 ToastProvider + 外层容器) */}
      <Route element={<PageLayout />}>
        {/* ── 三层架构新路由 ── */}
        <Route path="/data" element={<Suspense fallback={<PageFallback />}><P.DataLayerPage /></Suspense>} />
        <Route path="/data/import" element={<Suspense fallback={<PageFallback />}><P.DataImportPage /></Suspense>} />
        <Route path="/data/favorites" element={<Suspense fallback={<PageFallback />}><P.DataFavoritesPage /></Suspense>} />
        <Route path="/data/history" element={<HistoryPageRoute />} />
        <Route path="/judge" element={<Suspense fallback={<PageFallback />}><P.JudgeLayerPage /></Suspense>} />
        <Route path="/action" element={<Suspense fallback={<PageFallback />}><P.ActionLayerPage /></Suspense>} />

        {/* ── 旧路由兼容 (v0.4 兼容性保留): Navigate 到新路由 ── */}
        <Route path="/" element={<Navigate to="/data" replace />} />
        <Route path="/category/:cat" element={<CategoryRedirect />} />
        <Route path="/weekly-report" element={<Navigate to="/report" replace />} />

        {/* ── 行动层子路由 (Phase 4: 实际包装页面，替换旧重定向) ── */}
        <Route path="/action/report" element={<Suspense fallback={<PageFallback />}><P.ActionReportPage /></Suspense>} />
        <Route path="/action/compound" element={<Suspense fallback={<PageFallback />}><P.ActionCompoundPage /></Suspense>} />
        <Route path="/action/todos" element={<Suspense fallback={<PageFallback />}><P.ActionTodosPage /></Suspense>} />
        <Route path="/action/outbox" element={<Suspense fallback={<PageFallback />}><P.ActionOutboxPage /></Suspense>} />
        <Route path="/action/review" element={<Suspense fallback={<PageFallback />}><P.ActionReviewPage /></Suspense>} />
        <Route path="/action/skills" element={<Suspense fallback={<PageFallback />}><P.ActionSkillsPage /></Suspense>} />
        {features.codegarden && (
          <>
            <Route path="/action/codegarden" element={<Suspense fallback={<PageFallback />}><P.ActionCodegardenPage /></Suspense>} />
            {features.codegardenPhase2b && (
              <Route path="/action/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><P.ActionCodegardenPhase2bPage /></Suspense>} />
            )}
          </>
        )}
        <Route path="/action/bid-alert" element={<Suspense fallback={<PageFallback />}><P.ActionBidAlertPage /></Suspense>} />

        {/* ── 判断层子路由 (Phase 3: 趋势/标讯分析独立页面, 其余 v0.4 兼容性保留跳转) ── */}
        <Route path="/judge/trends" element={<Suspense fallback={<PageFallback />}><P.JudgeTrendsPage /></Suspense>} />
        <Route path="/judge/bid-analysis" element={<Suspense fallback={<PageFallback />}><P.JudgeBidAnalysisPage /></Suspense>} />
        <Route path="/judge/quality" element={<Navigate to="/quality/rejection" replace />} />
        <Route path="/judge/heatmap" element={<Navigate to="/knowledge/heatmap" replace />} />
        <Route path="/judge/graph" element={<Navigate to="/knowledge/process" replace />} />
        <Route path="/judge/compile" element={<Navigate to="/knowledge/compile" replace />} />
        <Route path="/judge/read" element={<Navigate to="/knowledge/briefing" replace />} />

        {/* ── 保留的旧路由 (内容尚未迁移) ── */}
        <Route path="/todos" element={<Suspense fallback={<PageFallback />}><P.TodosPage /></Suspense>} />
        <Route path="/history" element={<Suspense fallback={<PageFallback />}><HistoryPageRoute /></Suspense>} />
        <Route path="/skills" element={<Suspense fallback={<PageFallback />}><P.SkillsPage onBack={goHome} /></Suspense>} />
        <Route path="/secrets" element={<Suspense fallback={<PageFallback />}><P.SecretsPage onBack={goHome} /></Suspense>} />
        {features.sync && (
          <Route path="/sync" element={<Suspense fallback={<PageFallback />}><P.SyncPage onBack={goHome} /></Suspense>} />
        )}
        <Route path="/settings" element={<Suspense fallback={<PageFallback />}><P.SettingsPage /></Suspense>} />
        <Route path="/report" element={<Suspense fallback={<PageFallback />}><P.ReportPage onBack={goHome} /></Suspense>} />

        {/* 知识管理: 4 大领域 (信息导入 / 处理数据 / 知识库编译 / 知识库复利) */}
        <Route path="/knowledge" element={<Suspense fallback={<PageFallback />}><P.KnowledgePage onBack={goHome} /></Suspense>}>
          <Route index element={<Navigate to="import" replace />} />
          <Route path="import" element={<Suspense fallback={<PageFallback />}><P.KnowledgeImport /></Suspense>} />
          <Route path="process" element={<Suspense fallback={<PageFallback />}><P.KnowledgeProcess /></Suspense>} />
          <Route path="compile" element={<Suspense fallback={<PageFallback />}><P.KnowledgeCompile /></Suspense>} />
          <Route path="compound" element={<Suspense fallback={<PageFallback />}><P.KnowledgeCompound /></Suspense>} />
          <Route path="imported" element={<Suspense fallback={<PageFallback />}><P.KnowledgeFavoritesView /></Suspense>} />
          <Route path="briefing" element={<Suspense fallback={<PageFallback />}><P.BriefingMode /></Suspense>} />
          <Route path="scan" element={<Suspense fallback={<PageFallback />}><P.ScanMode /></Suspense>} />
          <Route path="deep-read" element={<Navigate to="scan" replace />} />
          <Route path="deep-read/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadMode /></Suspense>} />
          <Route path="alert" element={<Suspense fallback={<PageFallback />}><P.AlertMode /></Suspense>} />
          <Route path="outbox" element={<Suspense fallback={<PageFallback />}><P.OutboxMode /></Suspense>} />
          <Route path="review" element={<Suspense fallback={<PageFallback />}><P.ReviewMode /></Suspense>} />
          <Route path="heatmap" element={<Suspense fallback={<PageFallback />}><P.AttentionHeatmap /></Suspense>} />
        </Route>

        <Route path="/reviews" element={<Suspense fallback={<PageFallback />}><P.ReviewPage /></Suspense>} />
        {/* /deep/:type/:id 跨实体深读视图, 与知识库 /knowledge/deep-read/:id 并存 (不同组件) */}
        <Route path="/deep/:type/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadView /></Suspense>} />
        {/* P1.4: /brief (官方每日简报) 已合并进 /knowledge/briefing, 旧路径重定向 */}
        <Route path="/brief" element={<Navigate to="/knowledge/briefing" replace />} />
        <Route path="/quality/rejection" element={<Suspense fallback={<PageFallback />}><P.QualityRejectionPage /></Suspense>} />
        {features.codegarden && (
          <>
            <Route path="/codegarden" element={<Suspense fallback={<PageFallback />}><P.CodegardenPage onBack={goHome} /></Suspense>} />
            {features.codegardenPhase2b && (
              <Route path="/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><P.CodegardenPhase2bPage onBack={goHome} /></Suspense>} />
            )}
          </>
        )}
        {/* SecNews 安全看板 (S0-8) */}
        <Route path="/secnews" element={<Suspense fallback={<PageFallback />}><P.SecNewsShell /></Suspense>}>
          <Route index element={<Navigate to="feed" replace />} />
          <Route path="feed" element={<Suspense fallback={<PageFallback />}><P.SecNewsFeed /></Suspense>} />
          <Route path="pipeline" element={<Suspense fallback={<PageFallback />}><P.SecNewsPipeline /></Suspense>} />
          <Route path="knowledge" element={<Suspense fallback={<PageFallback />}><P.SecNewsKnowledge /></Suspense>} />
          <Route path="inbox" element={<Suspense fallback={<PageFallback />}><P.SecNewsInbox /></Suspense>} />
          <Route path="ledger" element={<Suspense fallback={<PageFallback />}><P.SecNewsLedger /></Suspense>} />
        </Route>

        {/* v0.4.3: 未匹配路径回落到资料层首页 (扩展关闭时旧深链不白屏) */}
        <Route path="*" element={<Navigate to="/data" replace />} />
      </Route>
    </Routes>
  );
}
