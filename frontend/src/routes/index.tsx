import { Suspense, useCallback } from 'react';
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

// P1-3: 跨 7 个子模块的路由速查表见 ./ROUTE_REGISTRY.md (真源 = 本文件,
// 表漂移时以本文件为准回改; 此前声称的 "CI 校验" 从未存在, 勿再依赖)。

/** 旧路由 /category/:cat 兼容 (v0.6.3: workbench 已并入 SecNews, 跳哨兵首页) */
function CategoryRedirect() {
  const { cat } = useParams<{ cat: string }>();
  void cat;
  return <Navigate to="/" replace />;
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

// v0.8 Phase B (B6): /skill-store 路由包装 — 导航回调在此收敛, 页面组件保持 router-free
function SkillStoreRoute() {
  const navigate = useNavigate();
  return (
    <P.SkillStore
      onBack={() => navigate('/')}
      onDetail={id => navigate(`/skill-store/${encodeURIComponent(id)}`)}
      onHistory={id => navigate(`/skill-store/${encodeURIComponent(id)}?focus=history`)}
    />
  );
}

// v0.8 Phase B (B6): /skill-store/:skillId 详情页包装 — 路由参数注入 + 返回商店
// skillId 从 useParams 注入已不需要, SkillDetail 自己 fallback 到路由
function SkillDetailRoute() {
  const navigate = useNavigate();
  return <P.SkillDetail onBack={() => navigate('/skill-store')} />;
}

// v0.8 Phase C (C4): /skill-store/new 包装 — 4 步创建向导
function SkillBuilderRoute() {
  const navigate = useNavigate();
  return (
    <P.SkillBuilder
      onBack={() => navigate('/skill-store')}
      onCreated={id => navigate(`/skill-store/${encodeURIComponent(id)}`)}
    />
  );
}

// v0.8 Phase D (D2): /dashboard 包装 — 技能看板
function DashboardRoute() {
  const navigate = useNavigate();
  return <P.Dashboard onBack={() => navigate('/skill-store')} />;
}

export function AppRoutes() {
  const navigate = useNavigate();
  // v0.4.3: 扩展路由按 feature flag 条件渲染 (core 路由永远注册)
  const features = useFeatureFlags();
  const goHome = useCallback(() => navigate('/'), [navigate]);

  return (
    <Routes>
      {/* v4.3 报纸版式已移除 (v0.7.1) — 保留入口重定向, 老书签与外链不 404 */}
      <Route path="/editorial" element={<Navigate to="/" replace />} />

      {/* v0.7.1: 哨兵终端 (V2 设计稿还原) — 独立全屏, 不走 PageLayout, 壳由 SentinelShell 提供 */}
      <Route path="/" element={<Suspense fallback={<PageFallback />}><P.SentinelHomePage /></Suspense>} />
      <Route path="/judge" element={<Suspense fallback={<PageFallback />}><P.SentinelJudgePage /></Suspense>} />
      <Route path="/judge/graph" element={<Suspense fallback={<PageFallback />}><P.SentinelGraphPage /></Suspense>} />
      <Route path="/action" element={<Suspense fallback={<PageFallback />}><P.SentinelActionPage /></Suspense>} />
      <Route path="/garden" element={<Suspense fallback={<PageFallback />}><P.SentinelGardenPage /></Suspense>} />
      {/* v0.7.x SettingsHub: /sentinel/settings 已并入 /settings?sentinel=, 永久 redirect (外部书签不失效) */}
      <Route path="/sentinel/settings" element={<Navigate to="/settings?cat=sentinel" replace />} />

      {/* Phase 1A: 嵌套 Layout (PageLayout 含 ToastProvider + 外层容器) */}
      <Route element={<PageLayout />}>
        {/* v0.7.0 (D.8-D.10): 三层架构 (data/judge/action) 物理删除 — v0.6.3 起 SecNews 为统一工作台 */}
        {/* ── 旧路由兼容 (v0.7 Step 1: workbench_legacy=false 关闭老路由) ── */}
        <Route path="/category/:cat" element={<CategoryRedirect />} />
        <Route path="/weekly-report" element={<Navigate to="/report" replace />} />

        {/* ── 保留的旧路由 (内容尚未迁移) ── */}
        <Route path="/todos" element={<Suspense fallback={<PageFallback />}><P.TodosPage /></Suspense>} />
        <Route path="/history" element={<Suspense fallback={<PageFallback />}><HistoryPageRoute /></Suspense>} />
        <Route path="/skills" element={<Suspense fallback={<PageFallback />}><P.SkillsPage onBack={goHome} /></Suspense>} />
        {/* v0.8 Phase A (A4): 技能商店 (/skill-registry) — /skills 已被 Phase 41 技能库占用, 故用 /skill-store */}
        <Route path="/skill-store" element={<Suspense fallback={<PageFallback />}><SkillStoreRoute /></Suspense>} />
        {/* v0.8 Phase B (B6): 详情页 + 运行历史回放 + 反馈打分 */}
        <Route path="/skill-store/:skillId" element={<Suspense fallback={<PageFallback />}><SkillDetailRoute /></Suspense>} />
        {/* v0.8 Phase C (C4): Skill Builder 4 步向导 */}
        <Route path="/skill-store/new" element={<Suspense fallback={<PageFallback />}><SkillBuilderRoute /></Suspense>} />
        {/* v0.8 Phase D (D2): 技能看板 */}
        <Route path="/dashboard" element={<Suspense fallback={<PageFallback />}><DashboardRoute /></Suspense>} />
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
          {/* v0.7.0 (D.9): 4 cognitive mode 物理删除 — 删 briefing/scan/alert/outbox 4 路由 */}
          {/* 保留: deep-read/:id (主路径), review (主路径 SM-2), heatmap (知识图谱) */}
          <Route path="deep-read/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadMode /></Suspense>} />
          <Route path="review" element={<Suspense fallback={<PageFallback />}><P.ReviewMode /></Suspense>} />
          <Route path="heatmap" element={<Suspense fallback={<PageFallback />}><P.AttentionHeatmap /></Suspense>} />
        </Route>

        <Route path="/reviews" element={<Suspense fallback={<PageFallback />}><P.ReviewPage /></Suspense>} />
        {/* /deep/:type/:id 跨实体深读视图, 与知识库 /knowledge/deep-read/:id 并存 (不同组件) */}
        <Route path="/deep/:type/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadView /></Suspense>} />
        {/* P1.4: /brief (官方每日简报) 已合并进 /knowledge/briefing, 旧路径重定向 */}
        <Route path="/quality/rejection" element={<Suspense fallback={<PageFallback />}><P.QualityRejectionPage /></Suspense>} />
        {features.codegarden && (
          <>
            <Route path="/codegarden" element={<Suspense fallback={<PageFallback />}><P.CodegardenPage onBack={goHome} /></Suspense>} />
            {features.codegardenPhase2b && (
              <Route path="/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><P.CodegardenPhase2bPage onBack={goHome} /></Suspense>} />
            )}
          </>
        )}
        {/* SecNews 安全看板 (S0-8) — v0.6.3 workbench 5 视图并入 (研判 tab + 状态栏) */}
        <Route path="/secnews" element={<Suspense fallback={<PageFallback />}><P.SecNewsShell /></Suspense>}>
          <Route index element={<Navigate to="feed" replace />} />
          <Route path="feed" element={<Suspense fallback={<PageFallback />}><P.SecNewsFeed /></Suspense>} />
          <Route path="pipeline" element={<Suspense fallback={<PageFallback />}><P.SecNewsPipeline /></Suspense>} />
          <Route path="knowledge" element={<Suspense fallback={<PageFallback />}><P.SecNewsKnowledge /></Suspense>} />
          <Route path="analyze" element={<Suspense fallback={<PageFallback />}><P.SecNewsAnalyze /></Suspense>} />
          {/* v0.7.x SettingsHub: /secnews/image 与 /secnews/settings 已并入 /settings, 永久 redirect */}
          <Route path="image" element={<Navigate to="/settings?cat=image_models" replace />} />
          <Route path="analytics" element={<Suspense fallback={<PageFallback />}><P.SecNewsAnalytics /></Suspense>} />
          <Route path="observability" element={<Suspense fallback={<PageFallback />}><P.SecNewsObservability /></Suspense>} />
          <Route path="settings" element={<Navigate to="/settings?cat=pipeline" replace />} />
        </Route>

        {/* CRM 业绩座舱 (v0.6 security-cockpit 方案 C, feature gate: crm) */}
        {features.crm && (
          <Route path="/crm" element={<Suspense fallback={<PageFallback />}><P.CrmPage onBack={goHome} /></Suspense>} />
        )}

        {/* 找回丢失前端入口 (v0.6.3): 后端路由已存在, 前端从未接入的 4 域 */}
        <Route path="/bid-alert" element={<Suspense fallback={<PageFallback />}><P.BidAlertPage onBack={goHome} /></Suspense>} />
        <Route path="/tags" element={<Suspense fallback={<PageFallback />}><P.TagsPage onBack={goHome} /></Suspense>} />
        <Route path="/extract" element={<Suspense fallback={<PageFallback />}><P.ExtractPage onBack={goHome} /></Suspense>} />
        <Route path="/search" element={<Suspense fallback={<PageFallback />}><P.UnifiedSearchPage onBack={goHome} /></Suspense>} />

        {/* D1 (Batch ⑧): OAuth 授权回调页 (无 PageLayout, 全屏显示状态) */}
        <Route path="/oauth-callback" element={<Suspense fallback={<PageFallback />}><P.OAuthCallbackPage /></Suspense>} />

        {/* v0.7.1: 未匹配路径回落到哨兵首页 (扩展关闭时旧深链不白屏) */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
