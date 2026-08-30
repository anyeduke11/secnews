# Route Registry — 前端路由映射

> **路由真源**: [`frontend/src/routes/index.tsx`](index.tsx)（Stage 1 拆分时的约定: "路由声明 = 应用结构图"）。
> 本表为**速查视图**，与 index.tsx 漂移时以 index.tsx 为准并回改本表。
> 历史: P1-3 (2026-08-24) 曾建 49 路由详表并声称 CI 校验——该 CI 校验从未存在，且 v0.7.0 删三层目录 / v0.6.3 workbench 并入 SecNews 后详表全部过期，2026-08-30 重写为现状速查。

## 一、前端路由（当前现状, ~35 条）

### 哨兵终端（独立全屏, 不走 PageLayout）

| 路径 | 组件 |
|---|---|
| `/` | SentinelHomePage |
| `/judge` | SentinelJudgePage |
| `/judge/graph` | SentinelGraphPage |
| `/action` | SentinelActionPage |
| `/garden` | SentinelGardenPage |
| `/sentinel/settings` | SentinelSettingsPage |
| `/editorial` | → `/` (Navigate, v4.3 报纸版退役) |

### 全局工具与知识（PageLayout 内）

| 路径 | 组件 | Gate |
|---|---|---|
| `/todos` `/history` `/skills` `/secrets` `/settings` `/report` `/reviews` | 各独立页 | - |
| `/sync` | SyncPage | `sync` |
| `/quality/rejection` | QualityRejectionPage | - |
| `/deep/:type/:id` | DeepReadPage (S4-2 四节深读) | - |
| `/knowledge` (+ `import`/`process`/`compile`/`compound`/`imported`/`deep-read/:id`/`review`/`heatmap`) | KnowledgePage 嵌套 | - |
| `/category/:cat` `/weekly-report` | → `/` / → `/report` (Navigate 兼容) | - |
| `*` | → `/` (兜底) | - |

### SecNews 统一工作台 (v0.6.3 起)

| 路径 | 组件 |
|---|---|
| `/secnews` (index → feed) | SecNewsShell |
| `/secnews/feed` `/pipeline` `/knowledge` `/analyze` `/analytics` `/settings` | FeedView / PipelineView / WikiBrowser / SecNewsAnalyze / SecNewsAnalytics / PipelineSettings |

> v0.6.3: `/workbench` 5 视图已并入 (Briefing→feed 简报卡, Analyze→研判 tab, Settings→设置面板, StatusBar→壳底栏); `/secnews/inbox` + `/secnews/ledger` 孤儿路由已删 (能力内嵌于知识库/管线 tab)。

### 扩展域（feature gate 条件注册）

| 路径 | 组件 | Gate |
|---|---|---|
| `/codegarden` | CodegardenPage | `codegarden` |
| `/codegarden/phase2b` | CodegardenPhase2bPage | `codegarden` + `codegarden_phase2b` |
| `/crm` | CrmPage | `crm` |
| `/bid-alert` `/tags` `/extract` `/search` | BidAlertPage / TagsPage / ExtractPage / UnifiedSearchPage (v0.6.3 找回入口) | - |

## 二、后端 API 域 → 前端消费关系

> 后端 65 router 全量注册见 `backend/api/_registry.py`（真源）。gate 语义: 关闭时对应路由不注册 (404)。

| 域 | 前缀 | 前端消费 | 备注 |
|---|---|---|---|
| main hotspot | `/api/hotspots` `/sources` `/quality` `/maintenance` `/secrets` `/settings` 等 | 有 | core 永远注册 |
| knowledge-master | `/api/knowledge` `/api/wiki` `/api/tags` `/api/extract` `/api/reviews` `/api/search` 等 | 有 (knowledge 域页 + /tags /extract /search) | |
| kl 管线 | `/api/kl/*` `/api/secnews/*` `/api/digests` | 有 (secnews feed/pipeline/knowledge) | `secnews` gate |
| ai_hub | `/api/llm/*` | 有 (/secnews/analyze 研判, digest) | |
| dsh + agents | `/api/dsh/*` `/api/agents/*` | 有 (DshControlCard / AgentRunnerCard / 研判双轨) | `dsh` gate (v0.6.3 内置化) |
| codegarden | `/api/codegarden*` | 有 | `codegarden` (+`codegarden_phase2b`) gate |
| crm | `/api/crm/*` | 有 (/crm) | `crm` gate |
| MCP 专用 | `/api/mcp/*` `/api/wiki/*` `/api/profile` `/api/cubox/sync` 等 | 无 (外部 AI Agent 经 MCP 消费) | `mcp` gate; 19 tools 见 `backend/api/mcp_types.py` |
