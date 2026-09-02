# 03 — 前端详解

> 基准: **v0.7.4-cleanup (Batch ⑨, 2026-09-01)**。React 18 SPA, 无 SSR, 构建产物为纯静态。
> **v0.7.1 后首页 = 哨兵终端全屏页** (报纸版 EditorialView 已退役, 仅保留重定向)。

## 1. 技术栈与构建

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 (端口 8898, strictPort) |
| Tailwind CSS | 3.4 | 原子化 CSS (配置改动需重启 dev server) |
| react-router-dom | 6.23 | 客户端路由 |
| ECharts | 6.x | 复杂图表 (趋势/图谱/热力图; 已移除 recharts) |
| Vitest + jsdom | 2.x / 25.x | 单元测试 (colocated `*.test.tsx`) |
| i18n | — | **0 依赖**: `contexts/I18nContext` (zh-CN/en-US) + `LocaleToggle` (Batch ⑧⑨) |

`vite.config.ts` 关键配置:

```ts
server: {
  host: '0.0.0.0',
  port: 8898,
  strictPort: true,          // 端口被占用直接报错, 禁止漂移
  proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
}
```

`package.json`: name `hotspot-map`, version `0.7.0` (tag 线 v0.7.*)。scripts:
`dev` (8898 严格端口) / `build` (tsc + vite build) / `preview` / vitest。

## 2. 入口链

```
index.html
  └─ src/main.tsx          BrowserRouter + ErrorBoundary → App
       └─ src/App.tsx      ThemeProvider + I18nProvider → AppRoutes
            └─ src/routes/index.tsx   <Routes> 集中声明 (~139 行)
                 └─ src/routes/lazy-imports.ts  React.lazy 分包 (P.* 命名空间)
```

- 路由声明 = 应用结构图: 所有 `<Route>` 集中在 `routes/index.tsx`, 与 lazy-imports.ts 1:1
- **哨兵域页面不走 PageLayout** (独立全屏, 壳由 `SentinelShell` 提供);
  业务页走 `PageLayout` (含 ToastProvider + 外层容器) 嵌套布局
- `routes/ROUTE_REGISTRY.md` 是路由速查登记表 (真源 = index.tsx)
- 首页链: `/` → SentinelHomePage; `*` → `<Navigate to="/" replace>`

## 3. 路由表 (v0.7.4, 完整 — 摘自 routes/index.tsx)

| 路由 | 组件 (lazy) | 说明 |
|------|-------------|------|
| `/editorial` | → `/` (Navigate) | 报纸版退役重定向 (v0.7.1) |
| **`/`** | **SentinelHomePage** | **哨兵终端首页 (唯一根 + `*` fallback)** |
| `/judge` | SentinelJudgePage | 哨兵·判断层 (独立全屏) |
| `/judge/graph` | SentinelGraphPage | 哨兵·图谱 (独立全屏) |
| `/action` | SentinelActionPage | 哨兵·行动层 (独立全屏) |
| `/garden` | SentinelGardenPage | 哨兵·花园 (CodeGarden 入口, 独立全屏) |
| `/sentinel/settings` | SentinelSettingsPage | 哨兵·设置 (独立全屏) |
| `/category/:cat` | → `/` (CategoryRedirect) | 旧路由兼容 |
| `/weekly-report` | → `/report` | 旧路由兼容 |
| `/todos` `/history` `/skills` `/secrets` | 各页面 | 保留旧路由 (history 共享 useFavorites store) |
| `/sync` ⛭ | SyncPage | feature `sync` |
| `/settings` | SettingsPage | 运行时设置 (分节) |
| `/report` | ReportPage | 日报/周报/月报 |
| `/knowledge` | KnowledgePage | 知识管理壳, index → import |
| `/knowledge/import` `/process` `/compile` `/compound` | Knowledge* | 4 大领域 |
| `/knowledge/imported` | KnowledgeFavoritesView | 收藏聚合 |
| `/knowledge/deep-read/:id` | DeepReadMode | 深读主路径 (保留) |
| `/knowledge/review` | ReviewMode | SM-2 复习主路径 (保留) |
| `/knowledge/heatmap` | AttentionHeatmap | 注意力热力图 (保留) |
| `/reviews` | ReviewPage | SM-2 复习独立页 |
| `/deep/:type/:id` | DeepReadView | 跨实体深读 (S4-2 四节 LLM 分析) |
| `/quality/rejection` | QualityRejectionPage | 质量拒绝流 |
| `/codegarden` ⛭ | CodegardenPage | feature `codegarden` (M1) |
| `/codegarden/phase2b` ⛭ | CodegardenPhase2bPage | feature `codegardenPhase2b` (已开) |
| `/secnews` | SecNewsShell | SecNews 统一工作台壳, index → feed |
| `/secnews/feed` `/pipeline` `/knowledge` `/analyze` | SecNews* | 信息流/管线/知识/研判 tab |
| `/secnews/analytics` | SecNewsAnalytics | CVE 热力图 + ATT&CK 映射 |
| `/secnews/observability` | SecNewsObservability | **v0.7.3 新增**: 观测看板 tab |
| `/secnews/settings` | SecNewsSettings | 采集/管线/LLM 设置 |
| `/crm` ⛭ | CrmPage | feature `crm` (业绩座舱) |
| `/bid-alert` `/tags` `/extract` `/search` | Bid/Tags/Extract/UnifiedSearch | v0.6.3 找回的 4 域入口 |
| `/oauth-callback` | OAuthCallbackPage | **Batch ⑧**: OAuth 授权回调 (全屏状态页) |
| `*` | **→ `/`** | 兜底回哨兵首页 (扩展关闭时旧深链不白屏) |

> ⛭ = 按 `useFeatureFlags()` 条件渲染, 对应后端 `/api/settings/features`。
> 注意: workbench (`/workbench*`) 路由在 v0.6.3 workbench 并入 SecNews 时已删除;
> 报纸版 `/editorial` 只保留重定向。v0.7.0 物理删除的 22 个三层路由继续 404。

## 4. Hooks 数据层 (`src/hooks/`, ~26 个)

| 组 | Hook | 要点 |
|----|------|------|
| 核心数据 | `useHotspotData` | `/api/hotspots` 列表 (分类/分页/排序) |
| 实时 | `useSSE` | `EventSource('/api/events')`; `onEvent(type, data)`; 断线重连 (3s); lastEvent 分帧批处理 |
| Feature flags | `useFeatureFlags` | `/api/settings/features` + localStorage 缓存 5 分钟 + DEFAULT_FLAGS 兜底; 模块级共享 |
| 收藏 | `useFavorites` | 共享 store + 乐观更新 |
| 知识 | `useKnowledge` `useAnnotations` `useReviews` `useDigest` `useImported` `useDeepRead` | 条目/笔记/SM-2/简报/收藏/深读 |
| CodeGarden | `useCodegardenProjects` `useCodegardenServices` `useCodegardenResources` `useCodegardenOrchestration` | 项目/服务/资源/联动 |
| 安全 | `useSecurityGraph` `useCveHeatmap` `useAttackMapping` `useCompliance` | 图谱/热力图/ATT&CK/合规 |
| 行动 | `useTodos` `useAlerts` `useSkills` `useSecrets` | 待办/告警/技能/密钥 |
| 其它 | `useSync` `useSearch` `useRecommendations` `useTrendData` `useWeeklyReport` `useRefreshInterval` `useGoHome` `useThemeColors` | 同步/搜索/推荐/趋势/周报/轮询/回首页/主题色 |

数据流模式: hooks → `lib/api.ts` (fetch) → 后端 REST; 服务端变更经 SSE (`/api/events`)
推送 → `useSSE.onEvent` → 触发对应 hook 重新拉取。无全局状态库 (Redux 等)。
`DEFAULT_FLAGS` 兜底: `true: [codegarden, crm, sync, techStack, securityGraph, codegardenPhase2b?]`
以 `/api/settings/features` 实际值为准 (后端为真源)。

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

## 6. 组件目录树 (`src/components/`, v0.7.4)

```
components/
├── sentinel/        # ★ v0.7.1 唯一首页族: SentinelShell + SentinelRail
│                    #   + Home/Judge/Graph/Action/Garden/Settings 页
│                    #   (独立全屏, 不套 PageLayout; 各自 .css)
├── secnews/         # SecNews 工作台:
│   ├── feed/        #   FeedView + FeedFilters + FeedCard + DigestCard
│   ├── pipeline/    #   PipelineView + FunnelBar + QueueCard + AliveCard + TokenLedger
│   ├── analyze/     #   SecNewsAnalyze (研判)
│   ├── analytics/   #   SecNewsAnalytics + CveHeatmap + AttackNavigator + ComplianceMatrix
│   │                #                                + FrameworkFilter
│   ├── observability/ # v0.7.3: ObservabilityDashboard + ActiveAlertsBanner
│   │                #   + ThresholdEditor + ObservabilityTab
│   ├── layout/      #   SecNewsShell + SecNewsHeader + StatusBar (obs 段 + 告警角标)
│   └── settings/    #   PipelineSettings + DshControlCard + AgentRunnerCard
├── settings/        # SettingsPage 分节: General/Source/Quality/Proxy/Sync/Knowledge/
│                    #   Alert/Export/Database/About + MCPSettingsCard + SecretsStatusCard
│                    #   + QualitySettings (LLM Provider 切换 + 密钥管理面板)
│                    #   + FeedbackSettings + ModeSwitcher
├── secrets/         # SecretsPage + Setup/Unlock 模态 + MasterKeyPromptModal
│                    #   + RotationBanner (90 天轮换提醒) + AddOrEditForm
├── codegarden/      # ProjectBoard/ProjectCard/ProjectDetail/… + Phase2b 三件套
│                    #   service-mesh/ · resource-hub/ · dependency-graph/
│                    #   + EventBus/PlaybookList/ServiceTopology/UpstreamStatus
├── crm/             # CrmPage + CockpitDashboard + CustomerManager + OpportunityManager
├── security/        # SecurityGraph / SecurityEntityDetail / ComplianceMatrix
├── report/          # DailyReport / WeeklyReport / MonthlyReport + shared
├── sync/            # SyncConfigForm / SyncOperations / SyncHistory / … + useSyncPage
├── layout/          # LayerBadge/LayerCard/LayerTable/OnboardingHint
├── shared/          # NoteEditor / ReviewCard
├── bid/ · extract/ · tags/ · search/   # v0.6.3 找回入口
└── (根目录 ~40 文件) # PageLayout/Header/HotspotCard/HotspotGrid/TrendChart/KnowledgeGraph/
                     #   ErrorBoundary/Toast/Icon(共享 SVG)/TodosPage/SkillsPage/
                     #   ReviewPage/DeepReadPage(S4-2)/SoulViewer/MasteryGauge/
                     #   LocaleToggle/EmptyState/HealthDashboard/FederationStatus/…
```

约定: **测试 colocated** (`*.test.tsx` 同目录); 共享 SVG 统一走 `Icon.tsx`;
`AgihuntCard` 用 `React.memo`; 新组件选择器 scoped 在 `.sentinel`, 不污染全局样式。

## 7. 主题与 i18n

- `contexts/ThemeContext.tsx`: dark/light 双主题, CSS 变量贯穿 (`var(--text-muted)` 等);
  `useThemeColors` 消费令牌
- `contexts/I18nContext.tsx` (**Batch ⑧⑨, 0 依赖**): zh-CN / en-US 双语言表 +
  `useI18n()`; `LocaleToggle.tsx` 切换; 10+ 组件接入 120+ key
- a11y 系统化: `role="alert"` / `role="status"` + aria-live / aria-label 段 (Batch ⑧ D6)

## 8. 前端 Feature Flags

- `config/extensions.ts`: `EXTENSION_ROUTES` 声明「扩展 → 路由路径」映射
- `hooks/useFeatureFlags.ts`: 拉取 `/api/settings/features`, 驱动路由条件渲染
- 哨兵路由固定渲染 (不 gate); 扩展路由 (sync/codegarden/codegardenPhase2b/crm) 条件渲染

## 9. 测试

| 层 | 工具 | 入口 |
|----|------|------|
| 单元/组件 | Vitest + jsdom | `npx vitest run` (watch: `--watch`); **345+ passed (Batch ⑧ 验收, Batch ⑨ 续增)** |
| 类型 | tsc | `npx tsc --noEmit` (0 errors) |
| e2e 冒烟 | Playwright | `frontend/e2e/smoke.spec.ts` |
| 路由契约 | ROUTE_REGISTRY.md | 新路由登记 (真源 = index.tsx) |

哨兵域页面均有 colocated 测试 (SentinelHomePage/JudgePage/ActionPage/GardenPage/
GraphPage/SettingsPage .test.tsx); 观测面板 2 个测试文件 (ObservabilityDashboard +
Batch4); MasterKeyPromptModal / UnlockModal 有独立测试。