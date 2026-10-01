import React from 'react';

// Stage1 拆分: 50+ React.lazy 从 App.tsx 抽出集中管理。
// 懒加载位置 = 业务模块位置, 与路由表 1:1 映射, 见 routes/index.tsx。
// 注: 原 App.tsx 中声明但从未被路由引用的 FavoritesPanel (死代码) 未迁移。

// 哨兵终端首页 (V2 设计稿还原, v0.7.1)
export const SentinelHomePage = React.lazy(() =>
  import('../components/sentinel/SentinelHomePage').then(m => ({ default: m.SentinelHomePage }))
);
export const SentinelJudgePage = React.lazy(() =>
  import('../components/sentinel/SentinelJudgePage').then(m => ({ default: m.SentinelJudgePage }))
);
export const SentinelGraphPage = React.lazy(() =>
  import('../components/sentinel/SentinelGraphPage').then(m => ({ default: m.SentinelGraphPage }))
);
export const SentinelActionPage = React.lazy(() =>
  import('../components/sentinel/SentinelActionPage').then(m => ({ default: m.SentinelActionPage }))
);
export const SentinelGardenPage = React.lazy(() =>
  import('../components/sentinel/SentinelGardenPage').then(m => ({ default: m.SentinelGardenPage }))
);

// 全局工具页
export const SettingsPage = React.lazy(() =>
  import('../components/settings/SettingsPage').then(m => ({ default: m.SettingsPage }))
);
export const HistoryPage = React.lazy(() =>
  import('../components/HistoryPage').then(m => ({ default: m.HistoryPage }))
);
export const TodosPage = React.lazy(() =>
  import('../components/TodosPage').then(m => ({ default: m.TodosPage }))
);
export const SkillsPage = React.lazy(() =>
  import('../components/SkillsPage').then(m => ({ default: m.SkillsPage }))
);
// v0.8 Phase A (A4): Skill Store — /skill-registry 技能商店 (/skills 已被 Phase 41 技能库占用)
export const SkillStore = React.lazy(() =>
  import('../components/skills/SkillStore').then(m => ({ default: m.SkillStore }))
);
// v0.8 Phase B (B6): Skill 详情页 + 运行历史回放 + 反馈打分
export const SkillDetail = React.lazy(() =>
  import('../components/skills/SkillDetail').then(m => ({ default: m.SkillDetail }))
);
// v0.8 Phase C (C4): Skill Builder 4 步向导
export const SkillBuilder = React.lazy(() =>
  import('../components/skills/SkillBuilder').then(m => ({ default: m.SkillBuilder }))
);
// v0.8 Phase D D2: Dashboard — skill 状态矩阵 + 触发器时间线 + 健康指标
export const Dashboard = React.lazy(() =>
  import('../components/dashboard/Dashboard').then(m => ({ default: m.Dashboard }))
);
export const SecretsPage = React.lazy(() =>
  import('../components/secrets/SecretsPage').then(m => ({ default: m.SecretsPage }))
);
export const SyncPage = React.lazy(() =>
  import('../components/sync').then(m => ({ default: m.SyncPage }))
);
export const ReportPage = React.lazy(() =>
  import('../components/report/ReportPage').then(m => ({ default: m.ReportPage }))
);

// v0.7.0 (D.8-D.10): 三层架构 (data/judge/action) + 4 cognitive mode 物理删除
// v0.6.3: /workbench 5 视图已并入 SecNews (Briefing→feed 简报卡 / Pipeline→管线观测 /
//   Knowledge→知识库条目浏览 / Analyze→研判 tab / Settings→设置面板 / StatusBar→壳底栏)
// 保留: ReviewMode + DeepReadMode (主路径) + 8 个 knowledge 域组件
// 详细迁移指南: docs/v0.7_migration_checklist.md

// (Phase 1-4 路由已删除, 22 个老路由 404; SecNews 为统一工作台入口)

// 知识管理: 4 大领域 (信息导入 / 处理数据 / 知识库编译 / 知识复利) — 保留 8 路由
// 6 模式去 4 留 2: 删 BriefingMode / ScanMode / AlertMode / OutboxMode (v0.6 已 @deprecated, v0.7 物理删除);
// 保留 ReviewMode (主路径 SM-2) + DeepReadMode (主路径 S4-2 重分析)
export const KnowledgePage = React.lazy(() =>
  import('../components/KnowledgePage').then(m => ({ default: m.KnowledgePage }))
);
export const KnowledgeImport = React.lazy(() =>
  import('../components/knowledge/KnowledgeImport').then(m => ({ default: m.KnowledgeImport }))
);
export const KnowledgeProcess = React.lazy(() =>
  import('../components/knowledge/KnowledgeProcess').then(m => ({ default: m.KnowledgeProcess }))
);
export const KnowledgeCompile = React.lazy(() =>
  import('../components/knowledge/KnowledgeCompile').then(m => ({ default: m.KnowledgeCompile }))
);
export const KnowledgeCompound = React.lazy(() =>
  import('../components/knowledge/KnowledgeCompound').then(m => ({ default: m.KnowledgeCompound }))
);
export const KnowledgeFavoritesView = React.lazy(() =>
  import('../components/knowledge/KnowledgeFavoritesView')
);
export const DeepReadMode = React.lazy(() =>
  import('../components/knowledge/DeepReadMode').then(m => ({ default: m.DeepReadMode }))
);
export const ReviewMode = React.lazy(() =>
  import('../components/knowledge/ReviewMode').then(m => ({ default: m.ReviewMode }))
);
export const AttentionHeatmap = React.lazy(() =>
  import('../components/knowledge/AttentionHeatmap').then(m => ({ default: m.AttentionHeatmap }))
);

// CodeGarden / 深读 / 简报 / 质检
export const CodegardenPage = React.lazy(() =>
  import('../components/CodegardenPage').then(m => ({ default: m.CodegardenPage }))
);
export const CodegardenPhase2bPage = React.lazy(() =>
  import('../components/CodegardenPhase2bPage').then(m => ({ default: m.CodegardenPhase2bPage }))
);
export const ReviewPage = React.lazy(() =>
  import('../components/ReviewPage').then(m => ({ default: m.ReviewPage }))
);
// S4-2: 新版 DeepReadPage (4 节 LLM 深度分析) 覆盖旧 DeepReadView
export const DeepReadView = React.lazy(() =>
  import('../components/DeepReadPage').then(m => ({ default: m.DeepReadPage }))
);
// P1.4: BriefModeView 已删除 — 官方每日简报 (digest) 合并进 /knowledge/briefing
// 2026-10-01: QualityRejectionPage 已删除 — 拒收日志迁 设置→运维 (RejectionLogCard)

// v4.3 报纸版式 (Editorial) 已于 v0.7.1 移除, /editorial 重定向到哨兵终端资料层首页

// SecNews 安全看板 (S0-7) — v0.6.3 起为统一工作台; NAV4 (2026-09-13) 6 视图直挂 PageLayout,
// SecNewsShell 物理删除 (P2), 由 menuOf() 按子路由内容归属四菜单
// (/secnews/inbox 与 /secnews/ledger 独立路由已删: InboxScanner 内嵌知识库,
//  TokenLedger 内嵌管线观测, 无独立入口需求)
export const SecNewsFeed = React.lazy(() =>
  import('../components/secnews/feed/FeedView').then(m => ({ default: m.FeedView }))
);
export const SecNewsPipeline = React.lazy(() =>
  import('../components/secnews/pipeline/PipelineView').then(m => ({ default: m.PipelineView }))
);
export const SecNewsKnowledge = React.lazy(() =>
  import('../components/secnews/knowledge/WikiBrowser').then(m => ({ default: m.WikiBrowser }))
);
export const SecNewsAnalyze = React.lazy(() =>
  import('../components/secnews/analyze/SecNewsAnalyze').then(m => ({ default: m.SecNewsAnalyze }))
);
// v0.7.x SettingsHub: 图片模型页与采集设置页已并入 /settings;
// 旧路由 /secnews/image 与 /secnews/settings 在 index.tsx 用 Navigate 永久 redirect,
// 对应源文件已物理删除, 此处无 lazy export。
export const SecNewsAnalytics = React.lazy(() =>
  import('../components/secnews/analytics/SecNewsAnalytics').then(m => ({ default: m.SecNewsAnalytics }))
);
// v0.7 Batch ③: API 观测面板 — middleware 落表数据可视化
export const SecNewsObservability = React.lazy(() =>
  import('../components/secnews/observability/ObservabilityTab').then(m => ({ default: m.ObservabilityTab }))
);

// CRM (/crm, CrmPage) 已随 CRM 域整体删除 (migration 116)

// 找回丢失前端入口 (v0.6.3: 后端路由已存在, 前端从未接入)
// DEV-0175: BidAlertPage 已随工作台聚焦裁决移除 (路由/入口一并剔除)
export const TagsPage = React.lazy(() =>
  import('../components/tags/TagsPage').then(m => ({ default: m.TagsPage }))
);
export const ExtractPage = React.lazy(() =>
  import('../components/extract/ExtractPage').then(m => ({ default: m.ExtractPage }))
);
export const UnifiedSearchPage = React.lazy(() =>
  import('../components/search/UnifiedSearchPage').then(m => ({ default: m.UnifiedSearchPage }))
);

// D1 (Batch ⑧): OAuth 授权回调页 — OAuth 解锁跳转回此页处理 code
export const OAuthCallbackPage = React.lazy(() =>
  import('./oauth-callback').then(m => ({ default: m.OAuthCallbackPage }))
);

// NAV4 P3 (2026-09-13, DEV-0178): 临时页面 — /maint /knowledge/canvas
// /maint: 维护诊断 (走 /api/maintenance/* 已注册端点)
// /knowledge/canvas: 无限画布 demo (纯前端 ECharts roam)
export const MaintPage = React.lazy(() =>
  import('../components/MaintPage').then(m => ({ default: m.MaintPage }))
);
export const KnowledgeCanvasPage = React.lazy(() =>
  import('../components/KnowledgeCanvasPage').then(m => ({ default: m.KnowledgeCanvasPage }))
);

// Phase 4 (DEV-0183): 新增视图 5 件套 — 有壳有占位, 未实现端点见 docs/UNIMPLEMENTED.md
export const KnowledgeHubPage = React.lazy(() =>
  import('../components/knowledge/KnowledgeHubPage').then(m => ({ default: m.KnowledgeHubPage }))
);
export const KnowledgeLibraryPage = React.lazy(() =>
  import('../components/knowledge/KnowledgeLibraryPage').then(m => ({ default: m.KnowledgeLibraryPage }))
);
export const EventsReviewPage = React.lazy(() =>
  import('../components/events/EventsReviewPage').then(m => ({ default: m.EventsReviewPage }))
);
export const DeepReaderPage = React.lazy(() =>
  import('../components/reader/DeepReaderPage').then(m => ({ default: m.DeepReaderPage }))
);
export const QualityDashboardPage = React.lazy(() =>
  import('../components/quality/QualityDashboardPage').then(m => ({ default: m.QualityDashboardPage }))
);

// v0.8.5: v1 四入口已降级 — /workbench /intel /cases 为 QueryRedirect, 不再挂 page;
// WorkbenchPage/IntelPage/CasesPage 懒导出已删 (组件仍留在 V1Prototype.tsx 供测试引用)。
// KnowledgeV1Page 保留: C4 挂载 /knowledge/v1 (spec §5)。
export const KnowledgeV1Page = React.lazy(() =>
  import('../components/v1/V1Prototype').then(m => ({ default: m.KnowledgeV1Page }))
);
// v0.8.5 C2: /cases/:caseId 判断层深链接 (SentinelShell layer=judge + CaseDetail)
export const CaseDetailPage = React.lazy(() =>
  import('../components/v1/CaseDetailPage').then(m => ({ default: m.CaseDetailPage }))
);
