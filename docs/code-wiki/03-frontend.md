# 03 — 前端详解

> 基准: **v0.7.0** (2026-08-28)。React 18 SPA, 无 SSR, 构建产物为纯静态。
> **v0.7.0 重大变化**: 三层架构 (data/judge/action) 与 4 个认知模式组件物理删除,
> `/workbench` 报纸版 5 视图为唯一首页。

## 1. 技术栈与构建

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 (端口 8898, strictPort) |
| Tailwind CSS | 3.4 | 原子化 CSS (配置改动需重启 dev server) |
| react-router-dom | 6.23 | 客户端路由 |
| ECharts | 6.1 | 复杂图表 (趋势/图谱/热力图; 功能超集, 已移除 recharts) |
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
            └─ src/routes/index.tsx   <Routes> 集中声明 (136 行, v0.7.0)
                 └─ src/routes/lazy-imports.ts  React.lazy 分包 (P.* 命名空间)
```

- 路由声明 = 应用结构图: 所有 `<Route>` 集中在 `routes/index.tsx`, 与 lazy-imports.ts 1:1
- **`routes/ROUTE_REGISTRY.md` 是 CI 强制登记表** — 新增 `<Route>` 必须同时登记, 否则 CI fail
- `PageLayout` (含 ToastProvider + 外层容器) 作为嵌套布局壳
- v0.7.0 首页链: `/` → `Navigate to="/workbench"` → index → `Navigate to="briefing"`

## 3. 路由表 (v0.7.0, 完整 — 摘自 routes/index.tsx 136 行版)

| 路由 | 组件 (lazy) | 说明 |
|------|-------------|------|
| `/editorial` | EditorialView | 报纸版式, 独立全屏不走 PageLayout |
| **`/`** | **→ `/workbench`** | **根路径重定向 (v0.7.0 D.2)** |
| `/category/:cat` | → `/workbench?category=` | 旧路由兼容 (v0.7.0 改指向 workbench) |
| `/weekly-report` | → `/report` | 旧路由兼容 |
| `/todos` `/history` `/skills` `/secrets` | 各页面 | 保留旧路由 (history 共享 useFavorites store) |
| `/sync` ⛭ | SyncPage | feature `sync` |
| `/settings` `/report` | SettingsPage / ReportPage | 设置 / 报告 |
| `/knowledge` | KnowledgePage (onBack) | 知识管理壳, index → import |
| `/knowledge/import` `/process` `/compile` `/compound` | Knowledge* | 4 大领域: 导入/处理/编译/复利 |
| `/knowledge/imported` | KnowledgeFavoritesView | 收藏聚合 |
| `/knowledge/deep-read/:id` | DeepReadMode | 深读主路径 (v0.7 保留) |
| `/knowledge/review` | ReviewMode | SM-2 复习主路径 (v0.7 保留) |
| `/knowledge/heatmap` | AttentionHeatmap | 注意力热力图 (v0.7 保留) |
| `/reviews` | ReviewPage | SM-2 复习独立页 |
| `/deep/:type/:id` | DeepReadView (**→ S4-2 新版 DeepReadPage**) | 跨实体深读, 4 节 LLM 深度分析 |
| `/quality/rejection` | QualityRejectionPage | 质量拒绝流 |
| `/codegarden` ⛭ `/codegarden/phase2b` ⛭ | CodegardenPage / Phase2bPage | feature gates |
| `/secnews` | SecNewsShell | SecNews 安全看板壳, index → feed |
| `/secnews/feed` `/pipeline` `/knowledge` `/inbox` `/ledger` `/settings` | SecNews* | 信息流/管线/知识/收件箱/账本/设置 |
| `/secnews/analytics` | SecNewsAnalytics | **v0.6 S4-3 新增**: CVE 热力图 + ATT&CK 映射 |
| `/crm` ⛭ | CrmPage | feature `crm` (业绩座舱) |
| **`/workbench`** ⛭ | **WorkbenchPage** | **v0.7.0 唯一首页**, feature `workbenchUi`, index → briefing |
| `/workbench/briefing` | BriefingView | 简报 (默认视图, 承接旧 /data + briefing) |
| `/workbench/pipeline` | PipelineView | 采集管线 (承接旧 /judge/quality) |
| `/workbench/knowledge` | KnowledgeView | 知识处理 (承接编译/复利) |
| `/workbench/analyze` | AnalyzeView | 趋势 + CVE + ATT&CK (承接旧 /judge/trends) |
| `/workbench/settings` | WorkbenchSettingsView | 运行时设置 |
| `*` | **→ `/workbench`** | 兜底 (v0.7.0 D.3, 旧深链统一导入工作台) |

> ⛭ = 按 `useFeatureFlags()` 条件渲染, 对应后端 `/api/settings/features`。
>
> **v0.7.0 已删除的 22 个路由** (直接 404): 6 个三层入口 (`/data*` `/judge` `/action`) +
> 8 个 action 子路由 + 2 个 judge 子路由 + 5 个 judge redirect + 4 个认知模式
> (`/knowledge/{briefing,scan,alert,outbox}`) + `/brief`。
> 功能对照表见 `docs/v0.7_migration_checklist.md`。

## 4. Hooks 数据层 (`src/hooks/`)

| 组 | Hook | 要点 |
|----|------|------|
| 核心数据 | `useHotspotData` | 拉取 `/api/hotspots` 热点列表 (分类/分页/排序) |
| 实时 | `useSSE` | `new EventSource('/api/events')`; `onEvent(type, data)` 回调; 断线自动重连 (默认 3s); lastEvent 分帧批处理 |
| Feature flags | `useFeatureFlags` | 拉 `/api/settings/features` (后端 gates 派生), localStorage 缓存 5 分钟, 拉取失败回退 `DEFAULT_FLAGS`; 模块级共享 (App/Header/LayerHeader/SettingsPage 只发一次请求) |
| 收藏 | `useFavorites` | 共享 store + 乐观更新 |
| 知识 | `useKnowledge` `useAnnotations` `useReviews` `useDigest` `useImported` | 知识条目/笔记/SM-2/简报/收藏聚合 |
| CodeGarden | `useCodegardenProjects` `useCodegardenServices` `useCodegardenResources` `useCodegardenOrchestration` | 项目/服务/资源/联动 |
| 安全 | `useSecurityGraph` | Security Graph 数据 |
| 行动 | `useTodos` `useAlerts` `useTags` `useSkills` | 待办/告警/标签/技能 |
| 其它 | `useSync` `useSecrets` `useSearch` `useRecommendations` `useTrendData` `useWeeklyReport` `useRefreshInterval` `useGoHome` `useThemeColors` | 同步/密钥/搜索/推荐/趋势/周报/轮询/回首页/主题色 |

数据流模式: hooks → `lib/api.ts` (fetch) → 后端 REST; 服务端变更通过 SSE
(`/api/events`) 推送 → `useSSE.onEvent` → 触发对应 hook 重新拉取。
无全局状态库 (Redux 等), 依赖 hooks + 模块级共享 store。

`DEFAULT_FLAGS` 前端兜底值 (后端不可达时): `workbenchUi: true`, `sync: true`,
其余 (codegarden/mcp/techStack/securityGraph/crm/codegardenPhase2b) 为 false。
注意: 后端正常时以 `/api/settings/features` 实际值为准 (当前 codegarden=true, crm=true)。

## 5. API 客户端 (`src/lib/api.ts`)

```ts
apiFetch<T>(path, options)        // 统一入口: JSON 头 / 非 2xx 解析 {detail} 抛友好 Error
getJSON<T>(path, options)         // GET 语法糖
postJSON<T>(path, body, options)  // POST 语法糖
```

- 错误解析契约: 后端统一错误体 `{"detail": {"message": "...", "missing": "..."}}`,
  `extractErrorDetail()` 提取后抛 `Error`
- 支持 `parse: 'blob'` (导出文件) 与 loading 回调; 204 返回 undefined
- `lib/crm.ts`: CRM 座舱专用 API 封装 (配 `types/crm.ts`)

## 6. 组件目录树 (`src/components/`, v0.7.0)

```
components/
├── workbench/       # ★ v0.7 唯一首页: WorkbenchPage + WorkbenchLayout + StatusBar
│                    #   + 5 视图 (BriefingView/PipelineView/KnowledgeView/
│                    #     AnalyzeView/SettingsView)
├── secnews/         # SecNews 看板: feed/ (FeedView+FeedCard+FeedFilters)
│                    #   pipeline/ (PipelineView+FunnelBar+QueueCard+AliveCard+TokenLedger)
│                    #   knowledge/ (InboxScanner+WikiBrowser) · layout/ · settings/
├── knowledge/       # 8 个领域组件 + 2 主路径模式 (v0.7 去 4 留 2):
│                    #   KnowledgeImport/Process/Compile/Compound/FavoritesView
│                    #   + DeepReadMode + ReviewMode + AttentionHeatmap
│                    #   (已删: BriefingMode/ScanMode/AlertMode/OutboxMode)
├── codegarden/      # ProjectBoard/ProjectList/ProjectCard/ProjectDetail + Phase2b 三件套:
│                    #   service-mesh/ · resource-hub/ (PortPool) · dependency-graph/
│                    #   + EventBus/PlaybookList/ServiceTopology
├── crm/             # CrmPage + CockpitDashboard + CustomerManager + OpportunityManager
├── security/        # SecurityGraph / SecurityTimeline / SecurityEntityDetail
│                    #   / ComplianceMatrix / TermStandardizer
├── settings/        # SettingsPage 分节: General/Source/Quality/Proxy/Sync/Knowledge/
│                    #   Alert/Export/Database/About/MCPSettingsCard/SecretsStatusCard
├── report/          # DailyReport / WeeklyReport / MonthlyReport + shared
├── sync/            # SyncPage 拆分: SyncConfigForm/SyncOperations/SyncHistory/... + useSyncPage
├── secrets/         # SecretsPage + Setup/Unlock 模态 + SecretCardView
├── editorial/       # EditorialView (报纸版式)
├── favorites/       # FavoriteList / FavoriteItem / FavoriteToolbar
├── layout/          # LayerBadge/LayerCard/LayerHeader/LayerTable/OnboardingHint
├── shared/          # AlertBadge/NoteEditor/ReviewCard/SourceHealthIndicator/TagSelector
└── (根目录 ~60 文件) # PageLayout/Header/LayerNav/HotspotCard/HotspotGrid/TrendChart/
                     #   KnowledgeGraph/ErrorBoundary/Toast/Icon(共享 SVG)/TodosPage/
                     #   SkillsPage/ReviewPage/DeepReadPage(S4-2)/SoulViewer/...
```

**v0.7.0 已删除目录**: `components/data/` (3 文件) · `components/judge/` (3 文件) ·
`components/action/` (10 文件) — 共 16 个 .tsx; 另删 knowledge 4 个认知模式组件
+ 2 个对应 .test.tsx。

约定: **测试 colocated** (`*.test.tsx` 与组件同目录); 共享 SVG 图标统一走 `Icon.tsx`;
`AgihuntCard` 用 `React.memo` 包裹。

## 7. 主题与设计令牌

- `contexts/ThemeContext.tsx`: dark/light 双主题, CSS 变量贯穿
  (组件内如 `var(--text-muted)`); `useThemeColors` 消费令牌
- Tailwind + 自定义令牌共存; 令牌变更脚本见 `scripts/tokenize_colors*.py`

## 8. 前端 Feature Flags

- `config/extensions.ts`: `EXTENSION_ROUTES` 声明「扩展 → 路由路径」映射
  (codegarden ×4 / sync ×1 / mcp 无独立路由)
- `hooks/useFeatureFlags.ts`: 拉取 `/api/settings/features` (后端
  `backend/api/settings.py` 把 feature_gates + config.feature_* 下发), 驱动路由条件渲染
- **`workbenchUi` 是首页开关** — 来自 `config.feature_workbench_ui` (默认 true),
  与后端 feature_gates.toml 的 [extensions] 表无关 (属 config.feature_* 体系)

## 9. 测试

| 层 | 工具 | 入口 |
|----|------|------|
| 单元/组件 | Vitest + jsdom | `npx vitest run` (watch: `--watch`); **304 passed (v0.7.0 验收)** |
| 类型 | tsc | `npx tsc --noEmit` (0 errors) |
| e2e 冒烟 | Playwright | `frontend/e2e/smoke.spec.ts` |
| 路由契约 | ROUTE_REGISTRY.md | CI 校验新增路由必须登记 |

v0.7.0 测试调整: `App.test.tsx` 移出 `/category/ai` (依赖 workbench_ui gate,
MemoryRouter 渲染不稳定) 与已删组件的引用; 净减 18 个测试
(2 个 .test.tsx 引用已删组件) — 属删除而非回归。
