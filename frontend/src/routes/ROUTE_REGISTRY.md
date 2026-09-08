# Route Registry — 前端路由映射

> **路由真源**: [`frontend/src/routes/index.tsx`](index.tsx)（Stage 1 拆分时的约定: "路由声明 = 应用结构图"）。
> 本表为**速查视图**，与 index.tsx 漂移时以 index.tsx 为准并回改本表。
> 历史: P1-3 (2026-08-24) 曾建 49 路由详表并声称 CI 校验——该 CI 校验从未存在；2026-08-30 重写为现状速查；**v0.8.5 (2026-09-08) 反向收敛后本表第三次重写**（三层 Sentinel 恢复为唯一壳, 守卫测试 `v085_route_shell.test.tsx` 锁定）。

## 一、前端路由（v0.8.5 现状）

### 三层 Sentinel（独立全屏 SentinelLayout, 无 AppNav; 壳由页内 SentinelShell 提供心跳条）

| 路径 | 组件 | 说明 |
|---|---|---|
| `/` | SentinelHomePage | **资料层**（+ SignalPanel 受管信号区块, 立项携证据） |
| `/judge` | SentinelJudgePage | **判断层**（+ CaseQueuePanel） |
| `/judge/graph` | SentinelGraphPage | 知识图谱 |
| `/action` | SentinelActionPage | **行动层**（+ ExecOverviewPanel） |
| `/garden` | SentinelGardenPage | 泳道（gate `codegarden`） |
| `/cases/:caseId` | CaseDetailPage | 判断层深链（`?section=` 定位; D1.2 起 aggregate 携带证据材料） |

### 旧 v1 四入口重定向（v0.8.5 反向收敛, 透传 query）

| 路径 | 去向 |
|---|---|
| `/workbench` `/intel` | → `/` |
| `/cases` | → `/judge` |
| `/v1-prototype` | 已物理删除（组件仅存测试引用） |

### 工具页（PageLayout + AppNav; AppNav 首组=三层真实路径）

| 路径 | 组件 | Gate |
|---|---|---|
| `/knowledge` (+ `import`/`process`/`compile`/`compound`/`imported`/`deep-read/:id`/`review`/`heatmap`) | KnowledgePage 嵌套 | - |
| `/knowledge/v1` | KnowledgeV1Page（v1 知识目录+采用/生命周期, D3 召回配套） | - |
| `/skill-store` (+`/:skillId` `/new`) | SkillStore / SkillDetail / SkillBuilder | - |
| `/dashboard` | Dashboard 技能看板 | - |
| `/todos` `/history` `/skills` `/secrets` `/settings` `/report` `/reviews` | 各独立页 | - |
| `/sync` | SyncPage | `sync` |
| `/quality/rejection` | QualityRejectionPage | - |
| `/deep/:type/:id` | DeepReadPage (S4-2 四节深读) | - |
| `/sentinel/settings` | → `/settings?cat=sentinel` (Navigate; SentinelSettingsPage 作为 settings 分区渲染) | - |
| `/oauth-callback` | OAuthCallbackPage | - |
| `/category/:cat` | → `/` (Navigate 兼容) | - |
| `*` | → `/` (兜底) | - |

### SecNews 统一工作台（PageLayout 内 + SecNewsShell 底部 StatusBar）

| 路径 | 组件 |
|---|---|
| `/secnews` (index → feed) | SecNewsShell |
| `/secnews/feed` `/pipeline` `/knowledge` `/analyze` `/analytics` `/observability` | FeedView / PipelineView / WikiBrowser / SecNewsAnalyze / SecNewsAnalytics / ObservabilityTab |
| `/secnews/image` `/secnews/settings` | → `/settings?cat=…` (Navigate 永久 redirect) |

### 扩展域（feature gate 条件注册）

| 路径 | 组件 | Gate |
|---|---|---|
| `/codegarden` (+`/phase2b`) | CodegardenPage / Phase2b | `codegarden` (+`codegarden_phase2b`) |
| `/crm` | CrmPage | `crm` |
| `/bid-alert` `/tags` `/extract` `/search` | BidAlertPage / TagsPage / ExtractPage / UnifiedSearchPage | - |

## 二、后端 API 域 → 前端消费关系

> 后端 router 全量注册见 `backend/api/_registry.py`（真源）; v1 端点清单见 `docs/v0.8.5/V0.8.5_PLAN.md` §6（parity 门 74/74）。gate 语义: 关闭时对应路由不注册 (404)。

| 域 | 前缀 | 前端消费 | 备注 |
|---|---|---|---|
| main hotspot | `/api/hotspots` `/sources` `/quality` `/maintenance` `/secrets` `/settings` 等 | 有 (三层资料/判读/右栏 rail) | core 永远注册 |
| knowledge-master | `/api/knowledge` `/api/wiki` `/api/tags` `/api/extract` `/api/reviews` `/api/search` 等 | 有 (/knowledge 域 + /tags /extract /search + /judge/graph) | |
| kl 管线 | `/api/kl/*` `/api/secnews/*` `/api/digests` | 有 (心跳条/secnews/复利 rail) | `secnews` gate |
| ai_hub | `/api/llm/*` | 有 (判读台 AI 评测, D2 出稿链路依赖) | |
| dsh + agents | `/api/dsh/*` `/api/agents/*` | 有 (含 legacy migrate API) | `dsh` gate |
| codegarden | `/api/codegarden*` | 有 (/garden /codegarden) | `codegarden` (+`codegarden_phase2b`) |
| crm | `/api/crm/*` | 有 (/crm) | `crm` gate |
| **v1 领域对象** | `/api/v1/signals` `/cases` `/judgments` `/actions` `/runs` `/artifacts` `/knowledge` `/skill-registry/v1` | 有 (三层区块 + /cases/:id + /knowledge/v1 + /skill-store 分桶) | demo 零 gate (skill_registry/v1 挂 skill_registry gate); 74 端点 parity 门 |
| MCP 专用 | `/api/mcp/*` `/api/wiki/*` `/api/profile` `/api/cubox/sync` 等 | 无 (外部 AI Agent 经 MCP 消费) | `mcp` gate; 19 tools 见 `backend/api/mcp_types.py` |
