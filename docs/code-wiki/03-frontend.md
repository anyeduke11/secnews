# 03 — 前端详解

> 基准: v0.6.2 (2026-08-28)。React 18 SPA, 无 SSR, 构建产物为纯静态。
>
> **本文件是 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §一"系统总览"中前端层的细节展开** — 详列 5 大子目录、hooks 数据层、设计令牌、workbench/ 5 视图。

## 1. 技术栈与构建

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 (端口 8898, strictPort) |
| Tailwind CSS | 3.4 | 原子化 CSS (配置改动需重启 dev server) |
| react-router-dom | 6.23 | 客户端路由 |
| ECharts | 6.1 | 复杂图表 (趋势/图谱/仪表盘; 功能超集, 已移除 recharts) |
| Vitest + jsdom | 2.x / 25.x | 单元测试 (colocated `*.test.tsx`) |
| Playwright | — | e2e 冒烟 (`e2e/smoke.spec.ts`) |

`vite.config.ts` 关键配置:

```ts
server: {
  host: '0.0.0.0',
  port: 8898,
  strictPort: true,          // 端口被占用直接报错, 禁止漂移
  proxy: {
    '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  },
}
```

`package.json` scripts: `dev` (8898 严格端口) / `build` (tsc + vite build) / `preview` /
vitest 相关脚本。

## 2. 入口链

```
index.html
  └─ src/main.tsx      BrowserRouter + ErrorBoundary → App
       └─ src/App.tsx  ThemeProvider (contexts/ThemeContext) → AppRoutes
            └─ src/routes/index.tsx   <Routes> 集中声明 (与 lazy-imports.ts 1:1)
                 └─ src/routes/lazy-imports.ts  React.lazy 分包 (P.* 命名空间)
```

- 路由声明 = 应用结构图: 所有 `<Route>` 集中在 `routes/index.tsx`
- **`routes/ROUTE_REGISTRY.md` 是 CI 强制登记表** — 新增 `<Route>` 必须同时登记,
  否则 CI fail (记录跨 7 个子模块的路由与后端 API 对齐关系, 含历史 mismatch 修复)
- `PageLayout` (含 ToastProvider + 外层容器) 作为嵌套布局壳

## 3. 路由表 (v0.4.3, 完整)

| 路由 | 组件 (lazy) | 说明 |
|------|-------------|------|
| `/editorial` | EditorialView | 报纸版式, 独立全屏不走 PageLayout |
| `/` | → `/data` | 默认重定向 |
| `/data` | DataLayerPage | 资料层首页 |
| `/data/import` | DataImportPage | 数据导入 |
| `/data/favorites` | DataFavoritesPage | 收藏 |
| `/data/history` `/history` | HistoryPage (共享 useFavorites store) | 历史 |
| `/judge` | JudgeLayerPage | 判断层 |
| `/judge/trends` | JudgeTrendsPage | 趋势分析 |
| `/judge/bid-analysis` | JudgeBidAnalysisPage | 标讯分析 |
| `/judge/quality`→`/quality/rejection` | QualityRejectionPage | 质量拒绝流 (重定向) |
| `/action` | ActionLayerPage | 行动层 |
| `/action/report` `/action/compound` `/action/todos` `/action/outbox` `/action/review` `/action/skills` | 各 Action*Page | 报告/复利/待办/整理/复习/技能 |
| `/action/codegarden` ⛭ | ActionCodegardenPage | feature `codegarden` |
| `/action/codegarden/phase2b` ⛭ | ActionCodegardenPhase2bPage | feature `codegardenPhase2b` |
| `/action/bid-alert` | ActionBidAlertPage | 标讯提醒 |
| `/knowledge` | KnowledgePage (onBack) | 知识管理壳, index → import |
| `/knowledge/import` `/process` `/compile` `/compound` | Knowledge* | 4 大领域: 导入/处理/编译/复利 |
| `/knowledge/imported` | KnowledgeFavoritesView | 收藏聚合 |
| `/knowledge/briefing` | BriefingMode | 简报 (旧 `/brief` 重定向至此) |
| `/knowledge/scan` | ScanMode | 扫描 |
| `/knowledge/deep-read/:id` | DeepReadMode | 深读 |
| `/knowledge/alert` `/outbox` `/review` `/heatmap` | Alert/Outbox/Review Mode · AttentionHeatmap | 告警/整理/复习/热力图 |
| `/reviews` | ReviewPage | SM-2 复习 |
| `/deep/:type/:id` | DeepReadView | 跨实体深读 (与 deep-read 并存) |
| `/todos` `/skills` `/secrets` `/settings` `/report` | 各页面 | 保留旧路由 |
| `/sync` ⛭ | SyncPage | feature `sync` |
| `/codegarden` ⛭ `/codegarden/phase2b` ⛭ | CodegardenPage / Phase2bPage | feature gates |
| `/secnews` | SecNewsShell | SecNews 安全看板壳, index → feed |
| `/secnews/feed` `/pipeline` `/knowledge` `/inbox` `/ledger` `/settings` | SecNews* | 信息流/管线/知识/收件箱/账本/设置 |
| `/crm` ⛭ | CrmPage | feature `crm` (业绩座舱) |
| `/workbench` ⛭ | WorkbenchPage | feature `workbenchUi`, index → briefing |
| `/workbench/briefing` `/pipeline` `/knowledge` `/analyze` `/settings` | 5 视图 | 统一工作台 |
| `/category/:cat` | → `/data?category=` | 旧路由兼容 |
| `*` | → `/data` | 兜底 (扩展关闭时旧深链不白屏) |

> ⛭ = 按 `useFeatureFlags()` 条件渲染, 对应后端 feature_gates。

## 4. Hooks 数据层 (`src/hooks/`, 27 个)

| 组 | Hook | 要点 |
|----|------|------|
| 核心数据 | `useHotspotData` | 拉取 `/api/hotspots` 热点列表 (分类/分页/排序) |
| 实时 | `useSSE` | `new EventSource('/api/events')`; `onEvent(type, data)` 回调; 断线自动重连 (默认 3s); lastEvent 分帧批处理 |
| 收藏 | `useFavorites` | 共享 store + 乐观更新 (v1.8 起多个页面共用同一份, 不再各持一份) |
| 知识 | `useKnowledge` `useAnnotations` `useReviews` `useDigest` `useImported` | 知识条目/笔记/SM-2/简报/收藏聚合 |
| CodeGarden | `useCodegardenProjects` `useCodegardenServices` `useCodegardenResources` `useCodegardenOrchestration` | 项目/服务/资源/联动 |
| 安全 | `useSecurityGraph` | Security Graph 数据 |
| 行动 | `useTodos` `useAlerts` `useTags` `useSkills` | 待办/告警/标签/技能 |
| 其它 | `useSync` `useSecrets` `useSearch` `useRecommendations` `useTrendData` `useWeeklyReport` `useRefreshInterval` `useGoHome` `useThemeColors` `useFeatureFlags` | 同步/密钥/搜索/推荐/趋势/周报/轮询/回首页/主题色/feature flags |

数据流模式: hooks → `lib/api.ts` (fetch) → 后端 REST; 服务端变更通过 SSE
(`/api/events`) 推送 → `useSSE.onEvent` → 触发对应 hook 重新拉取 (无全局状态库,
依赖 hooks + 共享 store)。

## 5. API 客户端 (`src/lib/api.ts`)

```ts
apiFetch<T>(path, options)   // 统一入口: JSON 头 / 非 2xx 解析 {detail} 抛友好 Error
getJSON<T>(path, options)    // GET 语法糖
postJSON<T>(path, body, options)  // POST 语法糖
```

- 错误解析契约: 后端统一错误体 `{"detail": {"message": "...", "missing": "..."}}`,
  `extractErrorDetail()` 提取后抛 `Error`, 前端据此展示
- 支持 `parse: 'blob'` (导出文件) 与 loading 回调; 204 返回 undefined
- `lib/crm.ts`: CRM 座舱专用 API 封装 (配 `types/crm.ts`)

## 6. 组件目录树 (`src/components/`)

```
components/
├── action/          # 行动层 10 页面壳 (ActionLayerPage / ActionReportPage / ...)
├── data/            # 资料层 3 页 (DataLayerPage / DataImportPage / DataFavoritesPage)
├── judge/           # 判断层 3 页 (JudgeLayerPage / JudgeTrendsPage / JudgeBidAnalysisPage)
├── knowledge/       # 知识域 ~30 文件: 4 大领域页 (Import/Process/Compile/Compound)
│   │                #   + 6 认知模式 (Briefing/Scan/DeepRead/Alert/Outbox/Review)
│   │                #   + AttentionHeatmap / LifecycleProgress / KnowledgePlanningPanel
│   │                #   / KnowledgeCompoundingDashboard / Phase13 仪表盘
├── secnews/         # SecNews 看板: feed/ (FeedView+FeedCard+FeedFilters)
│                    #   pipeline/ (PipelineView+FunnelBar+QueueCard+AliveCard+TokenLedger)
│                    #   knowledge/ (InboxScanner+WikiBrowser) · layout/ · settings/
├── codegarden/      # ProjectBoard/ProjectList/ProjectCard/ProjectDetail + Phase2b 三件套:
│                    #   service-mesh/ · resource-hub/ (PortPool) · dependency-graph/
│                    #   (DepGraph+ImpactResultDialog) + EventBus/PlaybookList/ServiceTopology
├── crm/             # CrmPage + CockpitDashboard + CustomerManager + OpportunityManager
├── workbench/       # WorkbenchPage + 5 视图 (Briefing/Pipeline/Knowledge/Analyze/Settings)
├── security/        # SecurityGraph / SecurityTimeline / SecurityEntityDetail
│                    #   / ComplianceMatrix / TermStandardizer
├── settings/        # SettingsPage 分节: General/Source/Quality/Proxy/Sync/Knowledge/
│                    #   Alert/Export/Database/About/MCPSettingsCard/SecretsStatusCard
├── report/          # DailyReport / WeeklyReport / MonthlyReport + shared
├── sync/            # SyncPage 拆分: SyncConfigForm/SyncOperations/SyncHistory/... + useSyncPage
├── secrets/         # SecretsPage + Setup/Unlock 模态 + SecretCardView
├── editorial/       # EditorialView (报纸版式)
├── favorites/       # FavoriteList / FavoriteItem / FavoriteToolbar
├── layout/          # LayerBadge/LayerCard/LayerHeader/LayerTable/OnboardingHint (三层架构 UI 原语)
├── shared/          # AlertBadge/NoteEditor/ReviewCard/SourceHealthIndicator/TagSelector
└── (根目录 ~60 文件) # PageLayout/Header/LayerNav/HotspotCard/HotspotGrid/TrendChart/
                     #   KnowledgeGraph/ErrorBoundary/Toast/Icon(共享 SVG)/TodosPage/
                     #   SkillsPage/ReviewPage/DeepReadView/SoulViewer/AlertCenter/...
```

约定: **测试 colocated** (`*.test.tsx` 与组件同目录); 共享 SVG 图标统一走 `Icon.tsx`;
`AgihuntCard` 用 `React.memo` 包裹 (重渲染优化)。

## 7. 主题与设计令牌

- `contexts/ThemeContext.tsx`: dark/light 双主题, CSS 变量贯穿
  (组件内如 `var(--text-muted)`); `useThemeColors` 消费令牌
- Tailwind + 自定义令牌共存; 令牌变更脚本见 `scripts/tokenize_colors*.py`
- `OnboardingHint`: 6 个认知模式组件首次 view 显示提示, 二次访问隐藏

## 8. 前端 Feature Flags

- `config/extensions.ts`: `EXTENSION_ROUTES` 声明「扩展 → 路由路径」映射
  (codegarden ×4 / sync ×1 / mcp 无独立路由, 设置卡片内嵌)
- `hooks/useFeatureFlags.ts`: 拉取后端 gates 状态, 驱动路由条件渲染 —
  与后端 `backend/extensions` 同源, 保证前后端可见性一致

## 9. 测试

| 层 | 工具 | 入口 |
|----|------|------|
| 单元/组件 | Vitest + jsdom | `npx vitest run` (watch: `--watch`); setup 在 `src/test/setup.ts` |
| 类型 | tsc | `npx tsc --noEmit` |
| e2e 冒烟 | Playwright | `frontend/e2e/smoke.spec.ts` |
| 路由契约 | ROUTE_REGISTRY.md | CI 校验新增路由必须登记 |
