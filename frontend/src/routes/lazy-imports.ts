import React from 'react';

// Stage1 拆分: 50+ React.lazy 从 App.tsx 抽出集中管理。
// 懒加载位置 = 业务模块位置, 与路由表 1:1 映射, 见 routes/index.tsx。
// 注: 原 App.tsx 中声明但从未被路由引用的 FavoritesPanel (死代码) 未迁移。

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
export const SecretsPage = React.lazy(() =>
  import('../components/secrets/SecretsPage').then(m => ({ default: m.SecretsPage }))
);
export const SyncPage = React.lazy(() =>
  import('../components/sync').then(m => ({ default: m.SyncPage }))
);
export const ReportPage = React.lazy(() =>
  import('../components/report/ReportPage').then(m => ({ default: m.ReportPage }))
);

// Phase 1: 三层架构页面
export const DataLayerPage = React.lazy(() =>
  import('../components/data/DataLayerPage').then(m => ({ default: m.DataLayerPage }))
);
export const JudgeLayerPage = React.lazy(() =>
  import('../components/judge/JudgeLayerPage').then(m => ({ default: m.JudgeLayerPage }))
);
export const ActionLayerPage = React.lazy(() =>
  import('../components/action/ActionLayerPage').then(m => ({ default: m.ActionLayerPage }))
);
// Phase 2: 资料层子页面
export const DataImportPage = React.lazy(() =>
  import('../components/data/DataImportPage').then(m => ({ default: m.DataImportPage }))
);
export const DataFavoritesPage = React.lazy(() =>
  import('../components/data/DataFavoritesPage').then(m => ({ default: m.DataFavoritesPage }))
);
// Phase 3: 判断层子页面
export const JudgeTrendsPage = React.lazy(() =>
  import('../components/judge/JudgeTrendsPage').then(m => ({ default: m.JudgeTrendsPage }))
);
export const JudgeBidAnalysisPage = React.lazy(() =>
  import('../components/judge/JudgeBidAnalysisPage').then(m => ({ default: m.JudgeBidAnalysisPage }))
);

// Phase 4: 行动层子页面（包装现有组件，添加行动层导航头）
export const ActionReportPage = React.lazy(() =>
  import('../components/action/ActionReportPage').then(m => ({ default: m.ActionReportPage }))
);
export const ActionCompoundPage = React.lazy(() =>
  import('../components/action/ActionCompoundPage').then(m => ({ default: m.ActionCompoundPage }))
);
export const ActionTodosPage = React.lazy(() =>
  import('../components/action/ActionTodosPage').then(m => ({ default: m.ActionTodosPage }))
);
export const ActionOutboxPage = React.lazy(() =>
  import('../components/action/ActionOutboxPage').then(m => ({ default: m.ActionOutboxPage }))
);
export const ActionReviewPage = React.lazy(() =>
  import('../components/action/ActionReviewPage').then(m => ({ default: m.ActionReviewPage }))
);
export const ActionCodegardenPage = React.lazy(() =>
  import('../components/action/ActionCodegardenPage').then(m => ({ default: m.ActionCodegardenPage }))
);
export const ActionCodegardenPhase2bPage = React.lazy(() =>
  import('../components/action/ActionCodegardenPhase2bPage').then(m => ({ default: m.ActionCodegardenPhase2bPage }))
);
export const ActionSkillsPage = React.lazy(() =>
  import('../components/action/ActionSkillsPage').then(m => ({ default: m.ActionSkillsPage }))
);
export const ActionBidAlertPage = React.lazy(() =>
  import('../components/action/ActionBidAlertPage').then(m => ({ default: m.ActionBidAlertPage }))
);

// 知识管理: 4 大领域 (信息导入 / 处理数据 / 知识库编译 / 知识复利) + 6 模式
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
export const BriefingMode = React.lazy(() =>
  import('../components/knowledge/BriefingMode').then(m => ({ default: m.BriefingMode }))
);
export const ScanMode = React.lazy(() =>
  import('../components/knowledge/ScanMode').then(m => ({ default: m.ScanMode }))
);
export const DeepReadMode = React.lazy(() =>
  import('../components/knowledge/DeepReadMode').then(m => ({ default: m.DeepReadMode }))
);
export const AlertMode = React.lazy(() =>
  import('../components/knowledge/AlertMode').then(m => ({ default: m.AlertMode }))
);
export const OutboxMode = React.lazy(() =>
  import('../components/knowledge/OutboxMode').then(m => ({ default: m.OutboxMode }))
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
export const QualityRejectionPage = React.lazy(() =>
  import('../components/QualityRejectionPage').then(m => ({ default: m.default }))
);

// v4.3: 报纸版式 (Editorial Layout) — 独立全屏视图，与老版式并行
export const EditorialView = React.lazy(() =>
  import('../components/editorial/EditorialView').then(m => ({ default: m.EditorialView }))
);

// SecNews 安全看板 (S0-7)
export const SecNewsShell = React.lazy(() =>
  import('../components/secnews/layout/SecNewsShell').then(m => ({ default: m.SecNewsShell }))
);
export const SecNewsFeed = React.lazy(() =>
  import('../components/secnews/feed/FeedView').then(m => ({ default: m.FeedView }))
);
export const SecNewsPipeline = React.lazy(() =>
  import('../components/secnews/pipeline/PipelineView').then(m => ({ default: m.PipelineView }))
);
export const SecNewsKnowledge = React.lazy(() =>
  import('../components/secnews/knowledge/WikiBrowser').then(m => ({ default: m.WikiBrowser }))
);
export const SecNewsInbox = React.lazy(() =>
  import('../components/secnews/knowledge/InboxScanner').then(m => ({ default: m.InboxScanner }))
);
export const SecNewsLedger = React.lazy(() =>
  import('../components/secnews/pipeline/TokenLedger').then(m => ({ default: m.TokenLedger }))
);
export const SecNewsSettings = React.lazy(() =>
  import('../components/secnews/settings/PipelineSettings').then(m => ({ default: m.PipelineSettings }))
);

// CRM 业绩座舱 (v0.6 security-cockpit 方案 C)
export const CrmPage = React.lazy(() =>
  import('../components/crm/CrmPage').then(m => ({ default: m.CrmPage }))
);

// Phase 4: 工作台 UI (v0.6.1) — 5 视图统一壳
export const WorkbenchPage = React.lazy(() =>
  import('../components/workbench/WorkbenchPage').then(m => ({ default: m.WorkbenchPage }))
);
export const BriefingView = React.lazy(() =>
  import('../components/workbench/BriefingView').then(m => ({ default: m.BriefingView }))
);
export const PipelineView = React.lazy(() =>
  import('../components/workbench/PipelineView').then(m => ({ default: m.PipelineView }))
);
export const KnowledgeView = React.lazy(() =>
  import('../components/workbench/KnowledgeView').then(m => ({ default: m.KnowledgeView }))
);
export const AnalyzeView = React.lazy(() =>
  import('../components/workbench/AnalyzeView').then(m => ({ default: m.AnalyzeView }))
);
export const WorkbenchSettingsView = React.lazy(() =>
  import('../components/workbench/SettingsView').then(m => ({ default: m.SettingsView }))
);
