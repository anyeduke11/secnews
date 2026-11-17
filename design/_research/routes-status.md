# 全站路由与实现状态盘点（routes-status）

> 生成日期: 2026-11-17 ｜ 仓库: hotspot @ v0.8.9（主干流量专项 P0~P6 已交付，30 天观测窗内）
> 方法: 以文件存在性为唯一证据，三类数据源交叉核对；凡未经文件证实的判断一律标注「待证」。
> 数据源:
> ① `frontend/src/routes/ROUTE_REGISTRY.md`（速查视图）+ 真源 `frontend/src/routes/index.tsx` + `frontend/src/routes/lazy-imports.ts`（同目录注册表代码文件，实测存在）
> ② `docs/v0.8.5/V0.8.5_PLAN.md` §5 路由表（L97~L128）与 §6 接口消费表（L129~L199）
> ③ `backend/api/` 全量 `APIRouter(prefix=...)` 提取（120 处声明 / 67 个不同 prefix，grep 实测）
> 组件存在性核对: lazy-imports.ts 引用的 43 个页面组件路径逐一 `test -f` 实测，全部存在。
> 说明: ROUTE_REGISTRY.md 声称的注册真源 `backend/api/_registry.py` 实测存在（文件含路由注册清单结构）。

## 一、结论摘要

- **前端路由声明总计 60 条**（`index.tsx` 逐条清点）: **页面路由 44 条，全部 ✅**（组件文件均存在、UNIMPLEMENTED.md 五视图占位已闭环）；**重定向兼容 16 条，全部 ○**（目标路由均已声明，**未发现死链**）。
- 页面路由按菜单分布（归属依据 = ROUTE_REGISTRY.md 分节 + `index.tsx` 注释 + spec 修订注④）: **资讯 7 / 知识 23 / 行动 5 / 设置 8 / 无菜单 1**（oauth-callback）。
- **◐（后端就绪、前端未见）共 4 个 API 域**: `/api/catchup` `/api/feedback` `/api/image` `/api/tech-stack`（前端全量 grep 引用文件数 = 0）。无「后端就绪但页面缺失」的路由级 ◐。
- 与 v1.0 相关的旧四入口 `/workbench` `/intel` `/cases` 均为 QueryRedirect 重定向兼容（单列第五节）。
- 发现两处**文档-代码漂移**（见第七节）: ROUTE_REGISTRY.md 的 hub-stats「未实现」标注已过时；spec §5 基表的 `/judge`「恢复」、`/garden`「恢复」与代码现状（重定向退役）冲突，spec 未挂 R-14 修订注。

## 二、全量路由表 · 页面路由（44 条，✅）

状态图例: ✅ 前端已实现（组件文件实测存在）｜◐ 后端就绪前端未见｜○ 仅规划或重定向兼容。
「主要消费 API」为组件文件内 grep 实测（`/api/*` 字面量）；标注「hook」= 经 hooks 层调用（hooks 文件实测引用对应 prefix）；标注「子组件」= API 调用在子组件文件内（父文件未直书路径）。menuOf 归属以 ROUTE_REGISTRY.md 分节为准。

### 资讯（data）— 7 条

| 路径 | 页面组件 | 功能 | 主要消费 API | 状态 | 判定依据 |
|---|---|---|---|---|---|
| `/` | SentinelHomePage | 情报流首页（SignalPanel 受管信号区块 + ToastProvider） | `/api/hotspots` `/api/hotspots/picked` `/api/sources/health`* `/api/kl/pipeline/stats`* `/api/favorites` `/api/quality/summary` `/api/kl/import/url` `/api/events`(SSE) + v1 区块 `/api/v1/signals` `/api/v1/cases`(spec §6.1) | ✅ | `index.tsx` L94 + `components/sentinel/SentinelHomePage.tsx` 存在；带 * 者为 spec §6.1 断言项（组件经 hooks 消费） |
| `/history` | HistoryPage | 浏览历史 | `/api/history/batches` `/api/knowledge/import-from-history` | ✅ | `index.tsx` HistoryPageRoute + `components/HistoryPage.tsx` 存在 |
| `/quality` | QualityDashboardPage | 校对室全貌（门禁统计 + 信息过滤规则） | `/api/quality/summary` `/api/info-filter/rules` | ✅ | `index.tsx` + `components/quality/QualityDashboardPage.tsx` 存在；UNIMPLEMENTED.md #5 已闭环 |
| `/deep/:type/:id` | DeepReadPage（懒导出名 DeepReadView） | 跨实体 AI 判读流深读 | `/api/deep-read` | ✅ | `index.tsx` + `components/DeepReadPage.tsx` 存在 |
| `/secnews/feed` | FeedView | 安全资讯流 | `/api/secnews/feed` | ✅ | `index.tsx` + `components/secnews/feed/FeedView.tsx` 存在 |
| `/secnews/pipeline` | PipelineView | 管线观测 | `/api/secnews/*`（stats 等） | ✅ | `index.tsx` + `components/secnews/pipeline/PipelineView.tsx` 存在 |
| `/secnews/analytics` | SecNewsAnalytics | 分析视图（CVE 近况） | `/api/cve/recent`（+ `/api` 根前缀 cve_analytics.py） | ✅ | `index.tsx` + `components/secnews/analytics/SecNewsAnalytics.tsx` 存在 |

### 知识（knowledge）— 23 条

| 路径 | 页面组件 | 功能 | 主要消费 API | 状态 | 判定依据 |
|---|---|---|---|---|---|
| `/knowledge` | KnowledgePage | 知识库主页（嵌套壳，index→import） | `/api/knowledge` | ✅ | `index.tsx` 嵌套组 + `components/KnowledgePage.tsx` 存在 |
| `/knowledge/import` | KnowledgeImport | 信息导入 | `/api/knowledge/sync` `/api/knowledge/tasks` `/api/knowledge/cubox/*` `/api/knowledge/obsidian/*` | ✅ | 组件存在；cubox/obsidian 后端文件实测（`cubox_import_api.py` `knowledge_obsidian.py`） |
| `/knowledge/process` | KnowledgeProcess | 处理数据 | `/api/knowledge/items` | ✅ | 组件存在 + `knowledge_items.py` 实测 |
| `/knowledge/compile` | KnowledgeCompile | 知识库编译 | 子组件（CompileTrigger/TaskMonitor 等） | ✅ | 组件存在；API 在子组件（对应 `knowledge_plans.py` 等编译域，逐端点映射待证） |
| `/knowledge/compound` | KnowledgeCompound | 知识库复利 | 子组件（LearningPanel 等） | ✅ | 组件存在；API 在子组件（kl 域，待证） |
| `/knowledge/imported` | KnowledgeFavoritesView | 已导入收藏 | hook `useImported` | ✅ | 组件存在 |
| `/knowledge/v1` | KnowledgeV1Page | v1 知识目录（复盘沉淀 + 采用/复查） | `/api/v1/knowledge`（spec §6.5） | ✅ | `index.tsx` + `components/v1/V1Prototype.tsx`（KnowledgeV1Page 导出）存在；`v1_knowledge_*.py` ×3 实测 |
| `/knowledge/deep-read/:id` | DeepReadMode | 知识条目深读（4 cognitive mode 删除后保留主路径） | `/api/knowledge` `/api/recommend/knowledge` `/api/attention/events` | ✅ | 组件存在 |
| `/knowledge/review` | ReviewMode | 条目复习（SM-2） | `/api/reviews/due` `/api/reviews/grade` `/api/knowledge/items` | ✅ | 组件存在 |
| `/knowledge/heatmap` | AttentionHeatmap | 关注度热力图 | `/api/attention/events` `/api/knowledge` | ✅ | 组件存在 + `attention_events_api.py` 实测 |
| `/knowledge/graph` | SentinelGraphPage | 知识图谱（自 /judge/graph 迁入，画布模式开关） | `/api` 根前缀域（graph 相关，待证） | ✅ | `index.tsx` + `components/sentinel/SentinelGraphPage.tsx` 存在 |
| `/knowledge/khub` | KnowledgeHubPage | 资料库前厅（六域聚合统计） | `/api/knowledge/hub-stats` `/api/kl/pipeline/stats` `/api/quality/summary` | ✅ | 组件存在；端点实测 `backend/api/knowledge_api.py:32`（REGISTRY「未实现」标注已过时） |
| `/knowledge/library` | KnowledgeLibraryPage | 编目室（四维筛选 + 翻页） | `/api/knowledge/items` `/api/knowledge/topics` `/api/wiki/search` | ✅ | 组件存在；UNIMPLEMENTED.md #2 已闭环（DEV-0189） |
| `/reader/:id` | DeepReaderPage | 清样深读（wiki 条目阅读流 + 批注） | `/api/wiki/read` `/api/annotations` | ✅ | 组件存在；UNIMPLEMENTED.md #4 已闭环（DEV-0190）+ `annotations.py` 实测 |
| `/reviews` | ReviewPage | 间隔复习 | hook `useReviews`（`/api/reviews`） | ✅ | 组件存在 |
| `/skill-store` | SkillStore | 能力资产商店 | `/api/skill-registry`（v1 + legacy） | ✅ | `SkillStoreRoute` + `components/skills/SkillStore.tsx` 存在 |
| `/skill-store/:skillId` | SkillDetail | 技能详情 + 运行历史回放 | `/api/skill-registry/*` | ✅ | 组件存在 |
| `/skill-store/new` | SkillBuilder | 4 步创建向导 | `/api/skill-builder` `/api/skill-builder/validate` | ✅ | 组件存在 + `skill_builder_api.py` 实测 |
| `/dashboard` | Dashboard | 技能看板（状态矩阵/时间线/健康） | `/api/skill-registry/runs` `/api/trigger/tickets` | ✅ | 组件存在 |
| `/tags` | TagsPage | 标签加工 | `/api/tags` `/api/tags/suggest` | ✅ | 组件存在 + `tags.py` 实测 |
| `/extract` | ExtractPage | 抽取工具 | `/api/extract` `/api/extract/hotspot` `/api/extract/knowledge` `/api/extract/preview` | ✅ | 组件存在 + `extract.py` 实测 |
| `/search` | UnifiedSearchPage | 统一搜索 | `/api/search` `/api/wiki/search` | ✅ | 组件存在 + `search.py` `wiki_tools.py` 实测 |
| `/secnews/knowledge` | WikiBrowser | wiki 条目浏览（SecNewsShell 拆挂） | `/api/secnews/knowledge` `/api/wiki` | ✅ | 组件存在 + `wiki_tools.py` 实测 |

### 行动（action）— 5 条

| 路径 | 页面组件 | 功能 | 主要消费 API | 状态 | 判定依据 |
|---|---|---|---|---|---|
| `/action` | SentinelActionPage | 今日行动（ExecOverviewPanel 四段指挥台 + SM-2 复习 + planning-actions） | `/api/kl/planning-actions` `/api/reviews/due` `/api/reviews/stats` `/api/secnews/stats` + v1 区块 `/api/v1/cases`(§6.4) | ✅ | `index.tsx` + `components/sentinel/SentinelActionPage.tsx` 存在；文件头注释确认不再消费 `/api/todos`（R-13） |
| `/cases/:caseId` | CaseDetailPage | 案件详情（壳 layer=action，?section= 定位） | `/api/v1/cases/{id}/aggregate` `/api/v1/judgments/*` `/api/v1/actions/*` `/api/v1/artifacts/*` `/api/v1/knowledge*`（spec §6.3 全量） | ✅ | 组件存在；v1 后端 11 文件实测（cases ×4 / judgments / actions ×2 / runs ×2 / artifacts / signals / v1 knowledge ×3） |
| `/action/events` | EventsReviewPage | 通稿审核（MP-2 候选人工审定） | `/api/event-technique` 七端点 | ✅ | 组件存在 + `event_technique_api.py` `event_types_api.py` 实测；UNIMPLEMENTED.md #3 已闭环 |
| `/report` | ReportPage | 周报/月报（产出物） | 子组件（DailyReport/Weekly/Monthly） | ✅ | 组件存在；`/api/reports` 前端引用 3 文件（子组件内，待逐端点核对） |
| `/secnews/analyze` | SecNewsAnalyze | 研判视图 | `/api/llm/evaluate` `/api/kl/import/url` `/api/dsh/task` `/api/settings/features` | ✅ | 组件存在 |

### 设置（settings）— 8 条

| 路径 | 页面组件 | 功能 | 主要消费 API | 状态 | 判定依据 |
|---|---|---|---|---|---|
| `/settings` | SettingsPage | 7 配置分区（overview/general/models/collection/network/connectivity/ops，修订注⑤） | `/api/settings/*`（features/mcp/feature-gates/interests 等，§6.6） `/api/interest/*` | ✅ | 组件存在 + `settings.py` `settings_flags_api.py` `mcp_settings_api.py` `content_preferences_api.py` `auto_intake_api.py` 实测 |
| `/skills` | SkillsPage | 技能库配置（Phase 41） | hook `useSkills`（`/api/skills`） | ✅ | 组件存在 + `skills.py` 实测 |
| `/secrets` | SecretsPage | 密钥管理 | hook `useSecrets`（`/api/secrets`） | ✅ | 组件存在 + `secrets_*.py` ×6 实测 |
| `/sync` | SyncPage | 同步与备份（**gate `sync`**，关闭时路由不渲染） | `/api/sync/conflicts` 等 | ✅ | `index.tsx` `features.sync` 条件渲染 + `components/sync/index.tsx` 存在 + `sync.py` 实测 |
| `/maint` | MaintPage | 维护诊断（DEV-0178 P3，复用已注册端点） | `/api/maintenance/*`（health/vacuum/dirty-report/cleanup 等 10 端点，修订注④） | ✅ | 组件存在 + `maintenance_db_api.py` `maintenance_retention_api.py` 实测 |
| `/codegarden` | CodegardenPage | CodeGarden 扩展域（**gate `codegarden`**） | hook `useCodegardenProjects`（`/api/codegarden`） | ✅ | 条件渲染 + 组件存在 + `codegarden.py` `codegarden_ops.py` 实测 |
| `/codegarden/phase2b` | CodegardenPhase2bPage | Phase 2b 服务网格（**gate `codegarden_phase2b`**） | hook `useCodegardenServices` | ✅ | 嵌套条件渲染 + 组件存在 |
| `/secnews/observability` | ObservabilityTab | API 观测面板（middleware 落表可视化） | 子组件（ObservabilityDashboard 等，`/api/observability`） | ✅ | 组件存在 + `observability_router.py` `observability_audit_api.py` 实测 |

### 无菜单 — 1 条

| 路径 | 页面组件 | 功能 | 主要消费 API | 状态 | 判定依据 |
|---|---|---|---|---|---|
| `/oauth-callback` | OAuthCallbackPage | OAuth 授权回调（全屏状态页） | `/api/secrets/oauth-exchange` `/api/secrets/unlock-with-oauth` | ✅ | `index.tsx` + `routes/oauth-callback.tsx` 存在 + `secrets_oauth_api.py` 实测 |

## 三、全量路由表 · 重定向兼容（16 条，○）

| 路径 | 去向 | 类型 | 依据（index.tsx 实测） |
|---|---|---|---|
| `/judge` | `/`（透传 query） | QueryRedirect | NAV4 判断层拆解；SentinelJudgePage 已物理删除（lazy-imports.ts 注释） |
| `/judge/graph` | `/knowledge/graph` | Navigate | NAV4 图谱迁知识菜单 |
| `/cases` | `/action`（透传 query） | QueryRedirect | NAV4 案件列表归行动（2026-09-14 修订注④） |
| `/garden` | `/action`（透传 query） | QueryRedirect | v0.8.8 R-14 泳道页退役 |
| `/todos` | `/action`（透传 query） | QueryRedirect | v0.8.8 R-13 待办域退役，`api/todos.py` 后端实测已不存在 |
| `/category/:cat` | `/` | CategoryRedirect | v0.6.3 兼容 |
| `/sentinel/settings` | `/settings?cat=general` | Navigate | 兼容重定向 |
| `/quality/rejection` | `/settings?cat=ops` | Navigate | 2026-10-01 拒收日志迁设置运维区 |
| `/knowledge/canvas` | `/knowledge/graph`（透传 query） | QueryRedirect | DEV-0295 画布 demo 退役 |
| `/knowledge`（index） | `/knowledge/import` | Navigate | 嵌套子路由默认页 |
| `/secnews` | `/secnews/feed` | Navigate | SecNewsShell 拆挂兼容 |
| `/secnews/image` | `/settings?cat=models` | Navigate | 模型配置并入设置页 |
| `/secnews/settings` | `/settings?cat=collection` | Navigate | 采集配置并入设置页 |
| `/workbench` `/intel` `/cases` | 见第五节（v1 旧入口专项） | QueryRedirect | v0.8.5 降级（本表计入 16 条中的 3 条） |
| `*` | `/` | Navigate | v0.7.1 兜底（扩展关闭时旧深链不白屏） |

> 全部 16 条重定向的**目标路由均已在本表声明，未发现死链**。gate 依赖说明: `/sync` `/codegarden` `/codegarden/phase2b` 按 feature gate 条件渲染，gate 关闭时旧深链落 `*` → `/`，不白屏。

## 四、后端 API prefix 清单（120 处声明 / 67 个不同 prefix）

> 提取命令: `grep -rn "APIRouter(prefix=" backend/api --include="*.py"`（实测 120 行；`mcp_phase5_tools.py` 一个文件声明 2 个 router）。9 个文件挂 `/api` 根前缀（子路径写在各 route 上，如 events/health/refresh/compliance/cve_analytics/attention/mcp 系）。注册真源 `backend/api/_registry.py` 实测存在；核心白名单 `backend/core/routers.py` 实测存在。
> 「前端引用」= `grep -rl "/api/<seg>" frontend/src --include="*.ts*" | wc -l` 全量实测。

| 前缀（去重后按域） | 声明文件数 | 前端引用 | 判定 |
|---|---|---|---|
| `/api/knowledge`（+`/chunks`） | 11 | 39 | ✅ 消费中（知识域主力） |
| `/api/v1/*`（signals/cases/judgments/actions/runs/artifacts/knowledge） | 11 | 26 | ✅ 消费中（SignalPanel/CaseDetail/ExecOverviewPanel/KnowledgeV1Page） |
| `/api/kl` `/api/secnews` `/api/quality` `/api/hotspots` `/api/sources` `/api/settings` `/api/secrets` `/api/llm` `/api/skill-registry`(+/v1) `/api/observability` `/api/reviews` `/api/maintenance` `/api/interest` `/api/wiki` `/api/info-filter` `/api/dsh`(+/control/legacy ×3) `/api/mcp/*` `/api/event-technique` `/api/reviews` `/api/favorites` `/api/history` `/api/deep-read` `/api/annotations` `/api/alerts`(+/v2) `/api/content` `/api/extract` `/api/tags` `/api/reports` `/api/search` `/api/skills` `/api/skill-builder` `/api/sync` `/api/codegarden` `/api/ops` `/api/digests` `/api/commands` `/api/cve`(根前缀实现) `/api/agents` `/api/export` `/api/proxy` `/api/security` `/api/recommend` `/api/refresh` `/api/mode` `/api/cache` `/api/compliance`(根前缀) `/api/proposals` `/api/trigger/webhook` `/api/mode` | 各 1~15 | 1~15 | ✅ 有消费（≥1 个前端文件命中；部分为根前缀域，子路径在 route 上） |
| `/api/catchup`（`catchup.py`） | 1 | **0** | **◐ 后端就绪前端未见** |
| `/api/feedback`（`feedback_api.py`） | 1 | **0** | **◐ 后端就绪前端未见** |
| `/api/image`（`image.py`） | 1 | **0** | **◐ 后端就绪前端未见**（注意: 前端已无 `/secnews/image` 页，该路由已重定向 `/settings?cat=models`） |
| `/api/tech-stack`（`tech_stack.py`） | 1 | **0** | **◐ 后端就绪前端未见**（`tech_stack` gate 默认开但无页面消费） |
| MCP 专用组（`mcp.py` `mcp_adapters.py` `mcp_agent_tools.py` `mcp_phase5_tools.py`） | 5 | 3（仅 settings/mcp 配置卡） | 外部消费（外部 AI Agent 经 MCP 消费，`mcp` gate；ROUTE_REGISTRY §二明示「无前端消费」为设计意图，不计 ◐） |

## 五、v1 四入口重定向兼容专项

> v1.0 四入口弯路与回摆的最终处置（spec §5「v1 四入口降级」+ `index.tsx` 注释「QueryRedirect 透传 query (spec §5, FactCheck #5)」）。`/cases/:caseId` 是真实页面（✅），不属于本节。

| 路径 | v1.0 原状 | 现状 | 去向 | 依据 |
|---|---|---|---|---|
| `/workbench` | V1SentinelShell + WorkbenchPage | QueryRedirect（透传 query） | `/` | `index.tsx` 实测；WorkbenchPage 懒导出已删（lazy-imports.ts 注释），统计卡废弃 |
| `/intel` | V1SentinelShell + IntelPage | QueryRedirect（透传 query） | `/` | 同上；v1 信号流由资料层 SignalPanel 承接 |
| `/cases` | V1SentinelShell + CasesPage | QueryRedirect（透传 query） | `/action` | 同上；2026-09-14 修订注④从 `/judge` 改判 `/action` |
| `/v1-prototype` | 已删除 | 保持删除（无路由声明） | — | spec §5 实测一致，`index.tsx` 无此路由 |
| 组件遗存 | — | `components/v1/V1Prototype.tsx` 仍在仓（仅 KnowledgeV1Page 导出被路由引用，Workbench/Intel/Cases 页面组件留作测试引用） | — | 文件实测存在 |

## 六、接口消费表核对（spec §6 vs 实测）

- §6.1 资料层 `/`: 7 项端点与 SentinelHomePage 实测消费一致（`/api/todos` 已随 R-13 从 §6.1 删除，实测前后端均无）。
- §6.2 判断层 `/judge`: 该层已被 NAV4 拆解（判读台归 `/` 质量区），§6.2 标题与路由现状**不一致**，但端点清单（hotspots/trends/quality/kl/llm/v1 cases）仍被现页面消费。
- §6.3 `/cases/:caseId`: 9 类端点全部有后端文件支撑（v1 ×11 文件实测）。
- §6.4 `/action`: todos 三端点退役一致；planning-actions/reviews/secnews stats/v1 cases 聚合实测一致。
- §6.5 `/knowledge`: v1 knowledge 读写 6 端点 ↔ `v1_knowledge_*.py` ×3 实测一致。
- §6.6 工具页: settings 7 cat、skill-registry、observability、mcp 配置、feature-gates 端点均有对应后端文件。

## 七、发现与冲突（按证据等级）

1. **ROUTE_REGISTRY.md 漂移（文档过时，高置信）**: REGISTRY 知识节写「`/knowledge/khub` … hub-stats 未实现见 UNIMPLEMENTED.md」「`/knowledge/library` … 清单端点未实现」；但 UNIMPLEMENTED.md（2026-09-16 状态行）已宣告五视图全部闭环（C1/C2/C3 = DEV-0189/0190/0191），且端点实测存在（`backend/api/knowledge_api.py:32` `@router.get("/api/knowledge/hub-stats")`）。一手代码 > 文档，REGISTRY 应回改。
2. **spec §5 基表与代码冲突（文档过时，高置信）**: §5 写 `/judge`「恢复 SentinelJudgePage + CaseQueuePanel」、`/garden`「恢复 SentinelGardenPage」；实测 `/judge`→重定向且 SentinelJudgePage 物理删除（lazy-imports.ts 注释「组件 563 行不可达」），`/garden`→重定向（R-14）。spec 自带 2026-09-13/14 修订注覆盖了部分 NAV4 变更，但 **R-13/R-14（v0.8.8）无修订注挂入 §5**。按项目「spec 漂移禁止」纪律应回写。
3. **重定向零死链（高置信）**: 16 条重定向目标全部为已声明路由；`/api/todos` 在 SentinelActionPage.tsx 中仅出现于文件头注释（「本屏不再消费」），非运行时调用。
4. **4 个后端域前端零引用（高置信，逐项 grep=0）**: `/api/catchup` `/api/feedback` `/api/image` `/api/tech-stack`。是否为「有意仅外部/管线消费」待证。
5. **gate 条件路由（确定）**: `/sync`（gate sync）、`/codegarden`（codegarden）、`/codegarden/phase2b`（codegarden_phase2b）按 `useFeatureFlags()` 条件渲染（index.tsx 实测），关闭时走 `*` 兜底。

## 八、待证项

- `ReportPage` / `KnowledgeCompile` / `KnowledgeCompound` / `ObservabilityTab` 的逐端点映射: API 调用在子组件内，本轮只证到子组件文件存在与 prefix 级引用数，未逐端点核对。
- `/knowledge/graph`、`/knowledge/compile|compound` 消费的具体端点归属（graph 域后端挂 `/api` 根前缀的哪个文件）。
- `_registry.py` 注册条数与 ARCHITECTURE.md 门禁数字（99 routers）是否一致——本轮未跑 `generate_meta.py --check`。

## 九、建议的下一步

1. 用 `python scripts/generate_meta.py --check` 核对架构数字门禁（routers 计数）。
2. 回改 ROUTE_REGISTRY.md khub/library 两处「未实现」标注；给 spec §5 补 R-13/R-14 修订注（或按 DEV_LOG 纪律留痕）。
3. 对 4 个 ◐ 域（catchup/feedback/image/tech-stack）各做一次调用方反查（grep 调用方 / scheduler / MCP tools），判定「外部消费」还是「待下线」。
