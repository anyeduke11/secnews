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
export const SentinelSettingsPage = React.lazy(() =>
  import('../components/sentinel/SentinelSettingsPage').then(m => ({ default: m.SentinelSettingsPage }))
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
export const QualityRejectionPage = React.lazy(() =>
  import('../components/QualityRejectionPage').then(m => ({ default: m.default }))
);

// v4.3 报纸版式 (Editorial) 已于 v0.7.1 移除, /editorial 重定向到哨兵终端资料层首页

// SecNews 安全看板 (S0-7) — v0.6.3 起为统一工作台
// (/secnews/inbox 与 /secnews/ledger 独立路由已删: InboxScanner 内嵌知识库,
//  TokenLedger 内嵌管线观测, 无独立入口需求)
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
export const SecNewsAnalyze = React.lazy(() =>
  import('../components/secnews/analyze/SecNewsAnalyze').then(m => ({ default: m.SecNewsAnalyze }))
);
export const SecNewsSettings = React.lazy(() =>
  import('../components/secnews/settings/PipelineSettings').then(m => ({ default: m.PipelineSettings }))
);
export const SecNewsAnalytics = React.lazy(() =>
  import('../components/secnews/analytics/SecNewsAnalytics').then(m => ({ default: m.SecNewsAnalytics }))
);

// CRM 业绩座舱 (v0.6 security-cockpit 方案 C)
export const CrmPage = React.lazy(() =>
  import('../components/crm/CrmPage').then(m => ({ default: m.CrmPage }))
);

// 找回丢失前端入口 (v0.6.3: 后端路由已存在, 前端从未接入)
export const BidAlertPage = React.lazy(() =>
  import('../components/bid/BidAlertPage').then(m => ({ default: m.BidAlertPage }))
);
export const TagsPage = React.lazy(() =>
  import('../components/tags/TagsPage').then(m => ({ default: m.TagsPage }))
);
export const ExtractPage = React.lazy(() =>
  import('../components/extract/ExtractPage').then(m => ({ default: m.ExtractPage }))
);
export const UnifiedSearchPage = React.lazy(() =>
  import('../components/search/UnifiedSearchPage').then(m => ({ default: m.UnifiedSearchPage }))
);
