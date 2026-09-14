import { Suspense } from 'react';
import { Routes, Route, Navigate, useNavigate, useParams, useLocation } from 'react-router-dom';
import { PageLayout, SentinelLayout } from '../components/PageLayout';
import { useFavorites } from '../hooks/useFavorites';
import { useFeatureFlags } from '../hooks/useFeatureFlags';
import { useGoBack } from '../hooks/useGoBack';
import * as P from './lazy-imports';

// Stage1 拆分: 路由声明 = 应用结构图, 所有 <Route> 集中于此, 与 lazy-imports.ts 1:1 映射。
// Stage1 批1 命名整理:
//  - 所有旧路由重定向统一标注 "v0.4 兼容性保留", Stage6 再按实测使用频率决定去留
//  - /deep/:type/:id (DeepReadView) vs /knowledge/deep-read/:id (DeepReadMode):
//    /deep 是跨实体深读视图, /knowledge/deep-read 属知识库阅读流, 并存不冲突
//  - P1.4: /brief (官方每日简报 digest) 已合并进 /knowledge/briefing, 旧路径重定向

// P1-3: 跨 7 个子模块的路由速查表见 ./ROUTE_REGISTRY.md (真源 = 本文件,
// 表漂移时以本文件为准回改; 此前声称的 "CI 校验" 从未存在, 勿再依赖)。

// v0.8.5 反向收敛 (2026-09-08 裁决, spec = docs/v0.8.5/V0.8.5_PLAN.md §5):
//  - 三层 Sentinel 恢复为唯一壳: / (资料层) → /judge (判断层) → /action (行动层),
//    走 SentinelLayout 全屏组 (无 AppNav), 壳由各页内嵌 SentinelShell 提供 (心跳条常驻)
//  - v1 四入口降级: /workbench /intel → /, /cases → /judge (QueryRedirect 透传 query)
//  - V1SentinelShell 物理删除; /garden 恢复 (gate codegarden, 更多菜单死链自愈)
//  - 守卫: routes/__tests__/v085_route_shell.test.tsx 锁定上述口径, 违反即 CI 红
// NAV4 (2026-09-13): 四菜单壳 — 资讯 / 知识 / 行动 / 设置
//  - /judge → / (透传 query); /cases → /action; /judge/graph → /knowledge/graph; /secnews → /secnews/feed
//  - SecNewsShell 已物理删除 (P2): 6 视图直挂 PageLayout, 由 menuOf() 按内容归属四菜单
//    (feed/pipeline/analytics→资讯, knowledge→知识, analyze→行动, observability→设置);
//    StatusBar 由 SentinelShell 心跳条接管
//  - 守卫: routes/__tests__/nav4_shell.test.tsx

/** 旧路由 /category/:cat 兼容 (v0.6.3: workbench 已并入 SecNews, 跳哨兵首页) */
function CategoryRedirect() {
  const { cat } = useParams<{ cat: string }>();
  void cat;
  return <Navigate to="/" replace />;
}

/** v0.8.5: 旧 v1 入口重定向 — 透传 query string (spec §5, FactCheck #5); 导出供守卫测试运行时断言 */
export function QueryRedirect({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
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
// 2026-09-10: onBack 统一为智能返回 (useGoBack: 有来路回上一页, 否则回 fallback), 壳已提供回首页
function SkillStoreRoute() {
  const navigate = useNavigate();
  const goBack = useGoBack();
  return (
    <P.SkillStore
      onBack={goBack}
      onDetail={id => navigate(`/skill-store/${encodeURIComponent(id)}`)}
      onHistory={id => navigate(`/skill-store/${encodeURIComponent(id)}?focus=history`)}
    />
  );
}

// v0.8 Phase B (B6): /skill-store/:skillId 详情页包装 — 路由参数注入 + 返回商店
// skillId 从 useParams 注入已不需要, SkillDetail 自己 fallback 到路由
function SkillDetailRoute() {
  const goBack = useGoBack('/skill-store');
  return <P.SkillDetail onBack={goBack} />;
}

// v0.8 Phase C (C4): /skill-store/new 包装 — 4 步创建向导
function SkillBuilderRoute() {
  const navigate = useNavigate();
  const goBack = useGoBack('/skill-store');
  return (
    <P.SkillBuilder
      onBack={goBack}
      onCreated={id => navigate(`/skill-store/${encodeURIComponent(id)}`)}
    />
  );
}

// v0.8 Phase D (D2): /dashboard 包装 — 技能看板
function DashboardRoute() {
  const goBack = useGoBack('/skill-store');
  return <P.Dashboard onBack={goBack} />;
}

export function AppRoutes() {
  // v0.4.3: 扩展路由按 feature flag 条件渲染 (core 路由永远注册)
  const features = useFeatureFlags();
  const goBack = useGoBack();

  return (
    <Routes>
      <Route path="/sentinel/settings" element={<Navigate to="/settings?cat=sentinel" replace />} />

      {/* ===== NAV4 旧路径重定向 (透传 query; 2026-09-13) ===== */}
      <Route path="/judge" element={<QueryRedirect to="/" />} />
      <Route path="/cases" element={<QueryRedirect to="/action" />} />
      <Route path="/judge/graph" element={<Navigate to="/knowledge/graph" replace />} />

      {/* ===== v0.8.5 三层 Sentinel 全屏壳 (唯一壳, 无 AppNav; 心跳条由页内 SentinelShell 提供) ===== */}
      <Route element={<SentinelLayout />}>
        {/* 资料层: 有什么新的、可信的变化影响我 */}
        <Route path="/" element={<Suspense fallback={<PageFallback />}><P.SentinelHomePage /></Suspense>} />
        {/* 判断层: 这些证据能形成什么结论, 还缺什么 */}
        <Route path="/judge" element={<Suspense fallback={<PageFallback />}><P.SentinelJudgePage /></Suspense>} />
        <Route path="/judge/graph" element={<Suspense fallback={<PageFallback />}><P.SentinelGraphPage /></Suspense>} />
        {/* 行动层: 已接受的结论要如何执行、验收和沉淀 */}
        <Route path="/action" element={<Suspense fallback={<PageFallback />}><P.SentinelActionPage /></Suspense>} />
        {/* 判断层深链接: Case 详情 (URL 真相源, ?section= 定位; spec §5/§6.3) */}
        <Route path="/cases/:caseId" element={<Suspense fallback={<PageFallback />}><P.CaseDetailPage /></Suspense>} />
        {features.codegarden && (
          <Route path="/garden" element={<Suspense fallback={<PageFallback />}><P.SentinelGardenPage /></Suspense>} />
        )}
      </Route>

      {/* ===== v0.8.5: 旧 v1 四入口重定向 (透传 query; /cases/:caseId 深链见下方 PageLayout 组) ===== */}
      <Route path="/workbench" element={<QueryRedirect to="/" />} />
      <Route path="/intel" element={<QueryRedirect to="/" />} />
      {/* NAV4 (2026-09-13): /cases → /action (案件队列归行动菜单) */}
      <Route path="/cases" element={<QueryRedirect to="/action" />} />

      {/* ===== 工具页组 (PageLayout: ToastProvider + AppNav 侧栏) ===== */}
      <Route element={<PageLayout />}>
        <Route path="/category/:cat" element={<CategoryRedirect />} />
        {/* v1.0.1 一致性重构: /weekly-report 残留 redirect 删除 (无外部引用, redirect 与 /report 重复) */}

        {/* ── 保留的旧路由 (内容尚未迁移) ── */}
        <Route path="/todos" element={<Suspense fallback={<PageFallback />}><P.TodosPage /></Suspense>} />
        <Route path="/history" element={<Suspense fallback={<PageFallback />}><HistoryPageRoute /></Suspense>} />
        <Route path="/skills" element={<Suspense fallback={<PageFallback />}><P.SkillsPage onBack={goBack} /></Suspense>} />
        {/* v0.8 Phase A (A4): 技能商店 (/skill-registry) — /skills 已被 Phase 41 技能库占用, 故用 /skill-store */}
        <Route path="/skill-store" element={<Suspense fallback={<PageFallback />}><SkillStoreRoute /></Suspense>} />
        {/* v0.8 Phase B (B6): 详情页 + 运行历史回放 + 反馈打分 */}
        <Route path="/skill-store/:skillId" element={<Suspense fallback={<PageFallback />}><SkillDetailRoute /></Suspense>} />
        {/* v0.8 Phase C (C4): Skill Builder 4 步向导 */}
        <Route path="/skill-store/new" element={<Suspense fallback={<PageFallback />}><SkillBuilderRoute /></Suspense>} />
        {/* v0.8 Phase D (D2): 技能看板 */}
        <Route path="/dashboard" element={<Suspense fallback={<PageFallback />}><DashboardRoute /></Suspense>} />

        <Route path="/secrets" element={<Suspense fallback={<PageFallback />}><P.SecretsPage onBack={goBack} /></Suspense>} />
        {features.sync && (
          <Route path="/sync" element={<Suspense fallback={<PageFallback />}><P.SyncPage onBack={goBack} /></Suspense>} />
        )}
        <Route path="/settings" element={<Suspense fallback={<PageFallback />}><P.SettingsPage /></Suspense>} />
        <Route path="/report" element={<Suspense fallback={<PageFallback />}><P.ReportPage onBack={goBack} /></Suspense>} />
        {/* NAV4 P3 (2026-09-13, DEV-0178): 维护诊断 /maint (设置菜单「扩展域」段; 走 /api/maintenance/* 已注册端点) */}
        <Route path="/maint" element={<Suspense fallback={<PageFallback />}><P.MaintPage /></Suspense>} />

        {/* 知识管理: 4 大领域 (信息导入 / 处理数据 / 知识库编译 / 知识库复利) + 经验库聚合
         * v0.8.5: 壳回 PageLayout (V1SentinelShell 已删); 知识不是第四层, 从「更多」进入;
         * v1 知识目录 /knowledge/v1 由 C4 挂载 (spec §5)
         */}
        <Route path="/knowledge" element={<Suspense fallback={<PageFallback />}><P.KnowledgePage onBack={goBack} /></Suspense>}>
          <Route index element={<Navigate to="import" replace />} />
          <Route path="import" element={<Suspense fallback={<PageFallback />}><P.KnowledgeImport /></Suspense>} />
          <Route path="process" element={<Suspense fallback={<PageFallback />}><P.KnowledgeProcess /></Suspense>} />
          <Route path="compile" element={<Suspense fallback={<PageFallback />}><P.KnowledgeCompile /></Suspense>} />
          <Route path="compound" element={<Suspense fallback={<PageFallback />}><P.KnowledgeCompound /></Suspense>} />
          <Route path="imported" element={<Suspense fallback={<PageFallback />}><P.KnowledgeFavoritesView /></Suspense>} />
          {/* v0.8.5 C4: v1 知识目录 (复盘沉淀 + 采用/复查面板, spec §5/§6.5) */}
          <Route path="v1" element={<Suspense fallback={<PageFallback />}><P.KnowledgeV1Page /></Suspense>} />
          {/* v0.7.0 (D.9): 4 cognitive mode 物理删除 — 删 briefing/scan/alert/outbox 4 路由 */}
          {/* 保留: deep-read/:id (主路径), review (主路径 SM-2), heatmap (知识图谱) */}
          <Route path="deep-read/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadMode /></Suspense>} />
          <Route path="review" element={<Suspense fallback={<PageFallback />}><P.ReviewMode /></Suspense>} />
          <Route path="heatmap" element={<Suspense fallback={<PageFallback />}><P.AttentionHeatmap /></Suspense>} />
        </Route>
        {/* NAV4 (2026-09-13): 图谱从 /judge/graph 迁入知识菜单 */}
        <Route path="/knowledge/graph" element={<Suspense fallback={<PageFallback />}><P.SentinelGraphPage /></Suspense>} />
        {/* NAV4 P3 (2026-09-13, DEV-0178): 无限画布 demo (ECharts roam + draggable) — 知识菜单附加视图 */}
        <Route path="/knowledge/canvas" element={<Suspense fallback={<PageFallback />}><P.KnowledgeCanvasPage /></Suspense>} />

        <Route path="/reviews" element={<Suspense fallback={<PageFallback />}><P.ReviewPage /></Suspense>} />
        {/* /deep/:type/:id 跨实体深读视图, 与知识库 /knowledge/deep-read/:id 并存 (不同组件) */}
        <Route path="/deep/:type/:id" element={<Suspense fallback={<PageFallback />}><P.DeepReadView /></Suspense>} />
        {/* P1.4: /brief (官方每日简报) 已合并进 /knowledge/briefing, 旧路径重定向 */}
        <Route path="/quality/rejection" element={<Suspense fallback={<PageFallback />}><P.QualityRejectionPage /></Suspense>} />
        {features.codegarden && (
          <>
            <Route path="/codegarden" element={<Suspense fallback={<PageFallback />}><P.CodegardenPage onBack={goBack} /></Suspense>} />
            {features.codegardenPhase2b && (
              <Route path="/codegarden/phase2b" element={<Suspense fallback={<PageFallback />}><P.CodegardenPhase2bPage onBack={goBack} /></Suspense>} />
            )}
          </>
        )}
        {/* SecNews 安全看板 6 视图 — NAV4 (2026-09-13) 拆挂 PageLayout, 由 menuOf() 自动归属四菜单
         * - feed / pipeline / analytics → 资讯菜单 (data)
         * - knowledge → 知识菜单
         * - analyze → 行动菜单
         * - observability → 设置菜单
         * /secnews index 保留 redirect → /secnews/feed; /secnews/image 与 /secnews/settings 已并入 /settings
         * SecNewsShell + StatusBar 已物理删除 (P2), 心跳条由 SentinelShell pipeline bar 提供
         */}
        <Route path="/secnews" element={<Navigate to="/secnews/feed" replace />} />
        <Route path="/secnews/feed" element={<Suspense fallback={<PageFallback />}><P.SecNewsFeed /></Suspense>} />
        <Route path="/secnews/pipeline" element={<Suspense fallback={<PageFallback />}><P.SecNewsPipeline /></Suspense>} />
        <Route path="/secnews/knowledge" element={<Suspense fallback={<PageFallback />}><P.SecNewsKnowledge /></Suspense>} />
        <Route path="/secnews/analyze" element={<Suspense fallback={<PageFallback />}><P.SecNewsAnalyze /></Suspense>} />
        <Route path="/secnews/image" element={<Navigate to="/settings?cat=image_models" replace />} />
        <Route path="/secnews/analytics" element={<Suspense fallback={<PageFallback />}><P.SecNewsAnalytics /></Suspense>} />
        <Route path="/secnews/observability" element={<Suspense fallback={<PageFallback />}><P.SecNewsObservability /></Suspense>} />
        <Route path="/secnews/settings" element={<Navigate to="/settings?cat=pipeline" replace />} />

        {/* crm (/crm) 已随 CRM 域整体删除 (migration 116), 路由与入口一并移除 */}

        {/* 找回丢失前端入口 (v0.6.3): 后端路由已存在, 前端从未接入的 4 域 */}
        {/* DEV-0175: /bid-alert 已随工作台聚焦裁决剔除 (标讯不再属于安全从业者工作台) */}
        <Route path="/tags" element={<Suspense fallback={<PageFallback />}><P.TagsPage onBack={goBack} /></Suspense>} />
        <Route path="/extract" element={<Suspense fallback={<PageFallback />}><P.ExtractPage onBack={goBack} /></Suspense>} />
        <Route path="/search" element={<Suspense fallback={<PageFallback />}><P.UnifiedSearchPage onBack={goBack} /></Suspense>} />

        {/* D1 (Batch ⑧): OAuth 授权回调页 (无 PageLayout, 全屏显示状态) */}
        <Route path="/oauth-callback" element={<Suspense fallback={<PageFallback />}><P.OAuthCallbackPage /></Suspense>} />

        {/* v0.7.1: 未匹配路径回落到哨兵首页 (扩展关闭时旧深链不白屏) */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
