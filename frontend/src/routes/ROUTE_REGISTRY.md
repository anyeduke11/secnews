# Route Registry — 前端路由映射 (NAV4 四菜单版)

> **路由真源**: [`frontend/src/routes/index.tsx`](index.tsx)（Stage 1 拆分时的约定: "路由声明 = 应用结构图"）。
> 本表为**速查视图**，与 index.tsx 漂移时以 index.tsx 为准并回改本表。
> 历史: P1-3 (2026-08-24) 曾建 49 路由详表; 2026-08-30 重写; v0.8.5 (2026-09-08) 第三次重写; **NAV4 (2026-09-13) 第四次重写**（四菜单壳, 守卫测试 `nav4_shell.test.tsx` 锁定）。
> **P2 (2026-09-13 终稿)**: ①SentinelMoreMenu + UTILITY_GROUPS (17 项) 物理删除, 工具页"我在哪"由 `menuOf(pathname)` 自动归属四菜单; ②SecNewsShell 6 视图拆挂 PageLayout (feed/pipeline/knowledge/analyze/analytics/observability), 由子路由内容归属四菜单; ③主题模式扩 3 态 (light/dark/paper), 纸面版暖米黄纸底 + 衬线字体, 最小侵入仅覆写 6 核心 token; ④nav4_shell 守卫新增 9 用例 (32 总数, +P2 死代码 5 + 纸面 theme 4); ⑤与 `docs/v0.8.5/V0.8.5_PLAN.md §5` 修订注③一致。

## 一、前端路由（NAV4 四菜单壳）

### 资讯 `/` (默认落地)

| 路径 | 组件 | 说明 |
|---|---|---|
| `/` | SentinelHomePage | **情报流**（+ SignalPanel 受管信号区块） |
| `/judge` | → `/` (QueryRedirect 透传 query) | 判断层拆解：判读台主体归资讯「质量」区 |
| `/quality/rejection` | QualityRejectionPage | 质量拒绝样本 |
| `/deep/:type/:id` | DeepReadPage | 深读（跨实体） |
| `/history` | HistoryPage | 浏览历史 |
| `/secnews/feed` `/pipeline` `/analytics` | SecNewsFeed / PipelineView / AnalyticsView | P1 拆挂 PageLayout（SecNewsShell 退役） |

### 知识 `/knowledge`

| 路径 | 组件 | 说明 |
|---|---|---|
| `/knowledge` (+ 9 子路由) | KnowledgePage 嵌套 | **知识库主页**（import/process/compile/compound/imported/v1/deep-read/review/heatmap） |
| `/knowledge/graph` | SentinelGraphPage | 知识图谱（自 `/judge/graph` 迁入） |
| `/knowledge/canvas` | KnowledgeCanvasPage | P3 知识画布（ECharts roam demo） |
| `/judge/graph` | → `/knowledge/graph` (301) | 旧路径保留 |
| `/skill-store` (+`/:skillId` `/new`) | SkillStore / SkillDetail / SkillBuilder | 能力资产 |
| `/dashboard` | Dashboard 技能看板 | 能力资产 |
| `/tags` `/extract` `/search` | TagsPage / ExtractPage / UnifiedSearchPage | 加工工具 |
| `/reviews` | ReviewPage | 间隔复习 |
| `/secnews/knowledge` | WikiBrowser | P1 拆挂 PageLayout（SecNewsShell 退役） |

### 行动 `/action`

| 路径 | 组件 | 说明 |
|---|---|---|
| `/action` | SentinelActionPage | **今日行动**（+ ExecOverviewPanel） |
| `/cases/:caseId` | CaseDetailPage | 案件详情（壳改 action 高亮） |
| `/cases` | → `/action` (QueryRedirect 透传 query) | 案件列表归行动 |
| `/todos` | TodosPage | 待办 |
| `/report` | ReportPage | 周报/月报（产出物） |
| `/garden` | SentinelGardenPage | 泳道（gate `codegarden`） |
| `/secnews/analyze` | SecNewsAnalyze | P1 拆挂 PageLayout（SecNewsShell 退役） |

### 设置 `/settings`

| 路径 | 组件 | 说明 |
|---|---|---|
| `/settings` | SettingsPage | **17 配置分区**（+ 扩展域分组） |
| `/sentinel/settings` | → `/settings?cat=sentinel` | 兼容重定向 |
| `/secrets` | SecretsPage | 密钥管理 |
| `/sync` | SyncPage | 同步与备份（gate `sync`） |
| `/skills` | SkillsPage | 技能库配置（与 skill-store 内容库区分） |
| `/secnews/observability` | ObservabilityTab | P1 拆挂 PageLayout（SecNewsShell 退役） |
| `/codegarden` (+`/phase2b`) | CodegardenPage / Phase2b | 扩展域（gate `codegarden`） |
| `/maint` | MaintPage | P3 维护诊断（复用 `/api/maintenance/*`） |

### 旧路径重定向汇总

| 路径 | 去向 | 说明 |
|---|---|---|
| `/workbench` `/intel` | → `/` | v0.8.5 旧 v1 入口，透传 query |
| `/cases` | → `/action` | NAV4 案件列表归行动 |
| `/judge` | → `/` | NAV4 判断层拆解，透传 query |
| `/judge/graph` | → `/knowledge/graph` | NAV4 图谱迁知识菜单 |
| `/secnews` (index) | → `/secnews/feed` | 兼容 |
| `/category/:cat` | → `/` | 兼容 |
| `*` | → `/` | 兜底 |

| 路径 | 组件 | 归属菜单 |
|---|---|---|
| `/oauth-callback` | OAuthCallbackPage | - |

## 二、后端 API 域 → 前端消费关系

> 后端 router 全量注册见 `backend/api/_registry.py`（真源）; v1 端点清单见 `docs/v0.8.5/V0.8.5_PLAN.md` §6（parity 门 74/74）。gate 语义: 关闭时对应路由不注册 (404)。

| 域 | 前缀 | 前端消费 | 备注 |
|---|---|---|---|
| main hotspot | `/api/hotspots` `/sources` `/quality` `/maintenance` `/secrets` `/settings` 等 | 有 (资讯资料层 + 设置) | core 永远注册 |
| knowledge-master | `/api/knowledge` `/api/wiki` `/api/tags` `/api/extract` `/api/reviews` `/api/search` 等 | 有 (知识菜单 + 行动复习) | |
| kl 管线 | `/api/kl/*` `/api/secnews/*` `/api/digests` | 有 (心跳条 + 资讯/知识/行动各视图) | `secnews` gate |
| ai_hub | `/api/llm/*` | 有 (深读 + 分析) | |
| dsh + agents | `/api/dsh/*` `/api/agents/*` | 有 (设置 DSH 控制卡) | `dsh` gate |
| codegarden | `/api/codegarden*` | 有 (行动泳道 + 设置扩展域) | `codegarden` (+`codegarden_phase2b`) |
| **v1 领域对象** | `/api/v1/signals` `/cases` `/judgments` `/actions` `/runs` `/artifacts` `/knowledge` `/skill-registry/v1` | 有 (资讯 SignalPanel + 行动 CaseDetail + 知识 v1 目录) | demo 零 gate (skill_registry/v1 挂 skill_registry gate) |
| MCP 专用 | `/api/mcp/*` `/api/wiki/*` `/api/profile` `/api/cubox/sync` 等 | 无 (外部 AI Agent 经 MCP 消费) | `mcp` gate; 19 tools 见 `backend/api/mcp_types.py` |

## 三、待办与迁移计划

> 来源: `docs/NAV4_IA_REDESIGN_2026-09-12.md`

| 期 | 内容 | 状态 |
|---|---|---|
| P0 | SentinelShell 4-tab 化 + `menuOf()` + 4 条 redirect + 守卫测试重写 | ✅ 完成 (2026-09-13) |
| P1 | 判读台主体迁入 / 质量区 + CaseQueue 迁入 /action | ✅ 完成 (2026-09-13) |
| P1 | SentinelGraphPage → knowledge + /knowledge/graph 路由 | ✅ 完成 (2026-09-13) |
| P1 | SecNewsShell 拆挂：6 视图直挂 PageLayout, /secnews 索引→feed | ✅ 完成 (2026-09-13) |
| P1 | 更多菜单保留过渡 → P2 评估删除 | 待启动 |
| P2 | 死代码清理 (SecNewsShell 物理删除 + UTILITY_GROUPS) + 文档终稿 + 纸面风 theme | 待启动 |
| P2 | spec 修订: V0.8.5_PLAN §5 修订注③ + AGENTS.md ×2 + PROJECT/PROGRESS | 待启动 |

## 四、关键决策记录

| 决策 | 日期 | 说明 |
|---|---|---|
| NAV4 四菜单壳 | 2026-09-13 | 资讯/知识/行动/设置；`SentinelShell` 唯一壳，`LAYER_DEFS` 扩展为 4 项 |
| 判断层拆解 | 2026-09-13 | 「判断是动词不是房间」：判读台→资讯质量区，CaseQueue→行动，graph→知识 |
| /cases 重定向 | 2026-09-13 | `/cases` → `/action`（案件列表归行动菜单） |
| /judge 重定向 | 2026-09-13 | `/judge` → `/`（透传 query；判读台主体组件拆出后挂资讯质量区） |
| 纸面风 theme | 2026-09-13 (待实施) | 接入现有 `ThemeContext`，demo 的 `--marker`/`--serif` token 映射到现有 CSS 变量体系 |
| SecNewsShell 拆挂 | 2026-09-13 | 6 视图（feed/pipeline/knowledge/analyze/analytics/observability）从 SecNewsShell 子路由改为 PageLayout 直挂；SecNewsShell 退役过渡文件保留至 P2 物理删除；StatusBar 心跳条能力由 SentinelShell pipeline bar 接管 |
