# P0 R-09 前端组件 ↔ API 依赖图

> **需求来源**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md` §4.9 R-09 前端组件 ↔ API 依赖图](../v0.8.8/V0.8.8_REFACTOR_PRD.md)
> (执行版本 `v0.8.8-exec.2` / DEV-0333 之后的当前树快照, 采集日期 **2026-11-10**)
> **关联**: R-13 待办域退役 (DEV-0332) · R-01~R-05 端点退役裁决 · 附录 C「R-09 = 101 覆盖 + 双路径证据」
> **性质**: 纯盘点, 无代码变更; 本文只给**证据与候选**, 删除裁决属 P1 阶段 (需用户逐项批准)。

---

## 1. 采集方法

### 1.1 Router 口径 (与 `scripts/generate_meta.py::count_routers()` 一致)

`count_routers()` 扫描 `backend/api/__init__.py` + `_registry.py` + `_registry_core.py` + `_registry_flags.py` +
`_registry_extensions.py` 中所有 `app.include_router(...)` 调用并计数。本次用 AST 复算同一口径:

| 项 | 值 | 来源 |
|---|---|---|
| PRD §2.2 / §4.9 写的 router 数 | **101** | `V0.8.8_REFACTOR_PRD.md` §2.2 基线表、§4.9 验收标准① |
| **当前树实测 router 数** | **100** | `python scripts/generate_meta.py --check` → `routers: 100`; 本次 AST 复算 `include_router` 调用数亦为 100 |
| 差异原因 | **DEV-0332 退役 todos 路由** | R-13 落地时删除 `backend/api/todos.py` + `_registry_core.py` 注册行 + `backend/core/routers.py` 白名单条目 → router 101→100, core_routers 69→68 |

> **本文一律用 100 出表。** PRD 的 101 是 R-13 落地前的基线快照, 与当前树不一致; 这正是 RA-2 类漂移的典型, 
> 下游 R-01~R-05 / M-2 目标值应同步回写为 100 口径 (本文不代改 spec)。

100 个 `include_router` 调用覆盖 **99 个不同后端模块** (`mcp_phase5_tools` 被注册两次: `kl_router` + `dsh_router`), 
每个模块的端点数 / 前端调用数见 §4 router 覆盖表 —— 满足验收标准①「router 全覆盖」。

### 1.2 端点全集 (520)

| 口径 | 数量 | 说明 |
|---|---|---|
| 静态 AST 提取 (全部 100 个注册 router) | **520** | 递归解析 `APIRouter(prefix=...)` + `include_router` 嵌套, 父 prefix 向子 router 传播; 本文主表口径 |
| 运行时 OpenAPI (`app.openapi()`) | 506 | 其中 `/api/*` = 505, 另含 `GET /` (非 API 路由) |
| 静态有、运行时无 | **15** | 全部来自 `mcp` / `mcp_adapters` / `mcp_phase5_tools` —— `extensions.mcp` gate 默认关 (16 gate 中唯一默认关), 关闭时整族 404 |
| 运行时 `GET /` | 1 | 根路由, 非 `/api/*`, 不计入本文主表 |

### 1.3 前端调用点双路径提取

**路径 A — 直接 fetch**: 扫 `frontend/src/**` 全部 `.ts`/`.tsx` (排除 `*.test.*`/`*.spec.*` 计入「仅测试」档), 
提取 `fetch('…')` / `apiFetch('…')` / `getJSON('…')` / `postJSON('…')` 的 **字符串字面量与模板字符串** 实参。

**路径 B — 封装层反查**: `frontend/src/api/*.ts` (8 个文件: `codegarden/commands/hotspots/knowledge/proposals/secnews/sources/v1.ts`) 
内 `export function` / `export const` 定义的端点函数 → 解析其函数体内的 URL 实参 → 再全仓反查哪些组件 
`import { fn } from '…/api/xxx'` 并调用 `fn(...)` (含 `fn<T>(...)` 泛型调用形态)。

每个调用点在表中标明来自哪条路径 (**A** = 直接 fetch, **B** = 封装层)。

### 1.4 路径模板归一化 (禁止「去尾部 {x}」粗暴规则)

前端模板串的**动态段**统一替换为 `{p}` 后再与后端路径模板逐段比对:

- 后端段 `{item_id}` ↔ 前端段 `${id}` / `${encodeURIComponent(itemId)}` → **视为同一段 (参数位)**;
- 后端段 `{entity_type}` ↔ 前端**字面量** `hotspot` / `knowledge` → **视为同一段 (单值枚举位)**, 
  例: `POST /api/reviews/{entity_type}/{entity_id}/grade` ↔ 前端 `/api/reviews/hotspot/${id}/grade`;
- 段数不等 → **不匹配**。**不做**「去掉尾部 `{x}`」这类降级 —— 那会把 `/api/items` 误并到 `/api/items/{item_id}`。

后端路径参数位在前端**取字面量单值**时按通配匹配 (`loose`), 精确匹配 (`exact`) 优先; 若同一路径存在多个方法, 
按 HTTP method 消歧; method 也对不上且路径唯一时仍归入该端点 (前端 method 推断失配记为该端点的唯一消费者)。

### 1.5 零调用结论的证据标准 (四项检查)

对每个「前端调用点数 = 0」的端点, 额外跑四项检查, 逐项写 **命中 / 未命中** + 证据文件:行号:

| 检查 | 含义 | 扫描范围 |
|---|---|---|
| **(a)** | 是否被 MCP / 命令栏 / 内部服务消费 | `backend/api/mcp*.py` + `command_bar_api.py` + `backend/services/**` + `backend/scheduler/**` |
| **(b)** | 是否有后端内部自调用 (非前端消费, 属另一类) | `backend/**` 非测试代码, **排除该端点的定义文件** |
| **(c)** | 是否仅被测试引用 | `backend/tests/**` + `frontend/src/**/*.test.*` |
| **(d)** | 是否在运维 / 文档中出现 | `docs/**.md` + `README.md` + `PROJECT.md` + `PROGRESS.md` + `scripts/**.py` |

**判定优先级** (count = 0 时): (a)/(b) 命中 → *仅内部*; 否则 (c) 命中 → *仅测试*; 否则 (d) 命中 → *仅文档*; 
四项全未命中 → *零调用* (P1 删除候选)。

---

## 2. 总览

| 指标 | 值 |
|---|---|
| 后端端点总数 (静态 AST, 100 router 全覆盖) | **520** |
| 前端有消费 (调用点 ≥ 1) | **276** |
| 前端零调用 (调用点 = 0) | **244** |
| 判定「有消费」 | **276** |
| 判定「仅内部」 ((a)/(b) 命中) | **29** |
| 判定「仅测试」 ((c) 命中) | **117** |
| 判定「仅文档」 ((d) 命中) | **31** |
| 判定「零调用」 (四项全未命中) | **67** |
| 前端调用点总数 (A + B) | **379** |

---

## 3. 主表: 端点 → 前端调用点数对照表

> 列含义: **序号** | **端点** (方法 + 路径) | **前端调用点数** | **调用点文件:行号** (A=直接 fetch, B=封装层) | **判定**
> 判定: `有消费` / `仅内部` / `仅测试` / `仅文档` / `零调用`

| # | 端点 | 调用点数 | 调用点文件:行号 | 判定 |
|---:|---|---:|---|---|
| 1 | `GET /api/agents/available` | 0 | — | **仅内部** |
| 2 | `POST /api/agents/run` | 0 | — | **仅文档** |
| 3 | `GET /api/alerts` | 0 | — | **仅内部** |
| 4 | `POST /api/alerts/evaluate/{hotspot_id}` | 0 | — | **仅测试** |
| 5 | `GET /api/alerts/rules` | 0 | — | **仅测试** |
| 6 | `POST /api/alerts/rules` | 0 | — | **仅测试** |
| 7 | `DELETE /api/alerts/rules/{rule_id}` | 0 | — | **仅测试** |
| 8 | `GET /api/alerts/rules/{rule_id}` | 0 | — | **仅测试** |
| 9 | `PUT /api/alerts/rules/{rule_id}` | 0 | — | **仅测试** |
| 10 | `GET /api/alerts/v2` | 1 | B `frontend/src/components/sentinel/NewsAlertList.tsx:40` | **有消费** |
| 11 | `POST /api/alerts/v2/evaluate` | 0 | — | **仅文档** |
| 12 | `PUT /api/alerts/v2/read-all` | 1 | B `frontend/src/components/sentinel/NewsAlertList.tsx:64` | **有消费** |
| 13 | `GET /api/alerts/v2/unread-count` | 1 | B `frontend/src/components/sentinel/SentinelHomePage.tsx:360` | **有消费** |
| 14 | `PUT /api/alerts/v2/{alert_id}/read` | 1 | B `frontend/src/components/sentinel/NewsAlertList.tsx:89` | **有消费** |
| 15 | `PUT /api/alerts/v2/{alert_id}/resolve` | 1 | B `frontend/src/components/sentinel/NewsAlertList.tsx:91` | **有消费** |
| 16 | `DELETE /api/alerts/{alert_id}` | 0 | — | **仅内部** |
| 17 | `GET /api/alerts/{alert_id}` | 0 | — | **仅内部** |
| 18 | `PUT /api/alerts/{alert_id}/dismiss` | 0 | — | **零调用** |
| 19 | `PUT /api/alerts/{alert_id}/read` | 0 | — | **零调用** |
| 20 | `GET /api/annotations` | 3 | A `frontend/src/components/ItemDetailDialog.tsx:43`<br>A `frontend/src/components/reader/DeepReaderPage.tsx:313`<br>A `frontend/src/hooks/useAnnotations.ts:66` | **有消费** |
| 21 | `POST /api/annotations` | 2 | A `frontend/src/components/ItemDetailDialog.tsx:99`<br>A `frontend/src/components/reader/DeepReaderPage.tsx:351` | **有消费** |
| 22 | `DELETE /api/annotations/{annotation_id}` | 2 | A `frontend/src/components/reader/DeepReaderPage.tsx:374`<br>A `frontend/src/hooks/useAnnotations.ts:131` | **有消费** |
| 23 | `GET /api/annotations/{annotation_id}` | 0 | — | **仅内部** |
| 24 | `PUT /api/annotations/{annotation_id}` | 1 | A `frontend/src/hooks/useAnnotations.ts:119` | **有消费** |
| 25 | `GET /api/attention/events` | 1 | B `frontend/src/components/knowledge/AttentionHeatmap.tsx:110` | **有消费** |
| 26 | `POST /api/attention/events` | 3 | B `frontend/src/components/knowledge/DeepReadMode.tsx:85`<br>B `frontend/src/components/knowledge/DeepReadMode.tsx:96`<br>B `frontend/src/components/knowledge/DeepReadMode.tsx:106` | **有消费** |
| 27 | `POST /api/cache/clear` | 1 | A `frontend/src/components/settings/DatabaseMaintenance.tsx:132` | **有消费** |
| 28 | `GET /api/cache/stats` | 0 | — | **零调用** |
| 29 | `POST /api/catchup/abort` | 0 | — | **仅测试** |
| 30 | `POST /api/catchup/auto` | 0 | — | **仅测试** |
| 31 | `POST /api/catchup/run` | 0 | — | **仅测试** |
| 32 | `GET /api/catchup/runs/{run_id}` | 0 | — | **仅测试** |
| 33 | `GET /api/catchup/status` | 0 | — | **仅测试** |
| 34 | `GET /api/categories` | 0 | — | **仅测试** |
| 35 | `GET /api/codegarden/candidates` | 0 | — | **仅测试** |
| 36 | `GET /api/codegarden/dependencies` | 0 | — | **仅测试** |
| 37 | `POST /api/codegarden/dependencies` | 0 | — | **仅测试** |
| 38 | `GET /api/codegarden/dependencies/impact` | 0 | — | **仅测试** |
| 39 | `DELETE /api/codegarden/dependencies/{dep_id}` | 0 | — | **零调用** |
| 40 | `POST /api/codegarden/drift/assess` | 0 | — | **仅测试** |
| 41 | `GET /api/codegarden/drift/assessments` | 0 | — | **仅测试** |
| 42 | `PUT /api/codegarden/drift/assessments/{assessment_id}` | 0 | — | **仅测试** |
| 43 | `GET /api/codegarden/events` | 0 | — | **仅测试** |
| 44 | `POST /api/codegarden/events` | 0 | — | **仅测试** |
| 45 | `POST /api/codegarden/from-knowledge` | 0 | — | **仅测试** |
| 46 | `POST /api/codegarden/github/import` | 0 | — | **仅测试** |
| 47 | `GET /api/codegarden/github/metadata` | 1 | A `frontend/src/components/codegarden/GithubImportDialog.tsx:58` | **有消费** |
| 48 | `GET /api/codegarden/playbooks` | 0 | — | **仅测试** |
| 49 | `POST /api/codegarden/playbooks/{name}/run` | 0 | — | **零调用** |
| 50 | `GET /api/codegarden/projects` | 0 | — | **仅测试** |
| 51 | `POST /api/codegarden/projects` | 0 | — | **仅测试** |
| 52 | `DELETE /api/codegarden/projects/{project_id}` | 0 | — | **零调用** |
| 53 | `GET /api/codegarden/projects/{project_id}` | 0 | — | **零调用** |
| 54 | `PATCH /api/codegarden/projects/{project_id}` | 0 | — | **零调用** |
| 55 | `GET /api/codegarden/projects/{project_id}/activities` | 0 | — | **零调用** |
| 56 | `POST /api/codegarden/projects/{project_id}/archive` | 0 | — | **零调用** |
| 57 | `POST /api/codegarden/projects/{project_id}/lifecycle` | 0 | — | **零调用** |
| 58 | `POST /api/codegarden/projects/{project_id}/restore` | 0 | — | **零调用** |
| 59 | `POST /api/codegarden/projects/{project_id}/sync` | 0 | — | **零调用** |
| 60 | `GET /api/codegarden/projects/{project_id}/timeline` | 0 | — | **零调用** |
| 61 | `GET /api/codegarden/projects/{project_id}/upstream` | 0 | — | **零调用** |
| 62 | `GET /api/codegarden/resources` | 0 | — | **仅测试** |
| 63 | `POST /api/codegarden/resources` | 0 | — | **仅测试** |
| 64 | `POST /api/codegarden/resources/allocate-port` | 0 | — | **仅测试** |
| 65 | `GET /api/codegarden/resources/env-templates` | 0 | — | **仅测试** |
| 66 | `POST /api/codegarden/resources/env-templates` | 0 | — | **仅测试** |
| 67 | `GET /api/codegarden/resources/env-templates/{resource_id}` | 0 | — | **仅测试** |
| 68 | `POST /api/codegarden/resources/release-port` | 0 | — | **仅测试** |
| 69 | `DELETE /api/codegarden/resources/{resource_id}` | 0 | — | **零调用** |
| 70 | `GET /api/codegarden/resources/{resource_id}` | 0 | — | **零调用** |
| 71 | `GET /api/codegarden/services` | 0 | — | **仅测试** |
| 72 | `POST /api/codegarden/services` | 0 | — | **仅测试** |
| 73 | `POST /api/codegarden/services/scan` | 0 | — | **仅测试** |
| 74 | `GET /api/codegarden/services/topology` | 0 | — | **仅测试** |
| 75 | `DELETE /api/codegarden/services/{service_id}` | 0 | — | **仅测试** |
| 76 | `GET /api/codegarden/services/{service_id}` | 0 | — | **仅测试** |
| 77 | `PATCH /api/codegarden/services/{service_id}` | 0 | — | **仅测试** |
| 78 | `GET /api/codegarden/services/{service_id}/logs` | 0 | — | **零调用** |
| 79 | `GET /api/codegarden/services/{service_id}/metrics` | 0 | — | **零调用** |
| 80 | `POST /api/codegarden/services/{service_id}/restart` | 0 | — | **零调用** |
| 81 | `GET /api/commands` | 1 | B `frontend/src/api/commands.ts:47` | **有消费** |
| 82 | `POST /api/commands` | 1 | B `frontend/src/components/sentinel/CommandBar.tsx:115` | **有消费** |
| 83 | `GET /api/compliance/controls/{event_type}` | 1 | A `frontend/src/hooks/useCompliance.ts:48` | **有消费** |
| 84 | `GET /api/compliance/frameworks` | 1 | A `frontend/src/hooks/useCompliance.ts:33` | **有消费** |
| 85 | `GET /api/compliance/matrix` | 1 | A `frontend/src/hooks/useCompliance.ts:43` | **有消费** |
| 86 | `GET /api/content/calendar` | 1 | A `frontend/src/components/ContentCalendar.tsx:33` | **有消费** |
| 87 | `POST /api/content/calendar` | 0 | — | **仅测试** |
| 88 | `DELETE /api/content/calendar/{entry_id}` | 1 | A `frontend/src/components/ContentCalendar.tsx:71` | **有消费** |
| 89 | `PATCH /api/content/calendar/{entry_id}` | 0 | — | **仅测试** |
| 90 | `GET /api/content/drafts` | 1 | A `frontend/src/components/ContentDraftList.tsx:25` | **有消费** |
| 91 | `POST /api/content/drafts` | 1 | A `frontend/src/components/ContentDraftList.tsx:64` | **有消费** |
| 92 | `DELETE /api/content/drafts/{draft_id}` | 1 | A `frontend/src/components/ContentDraftList.tsx:78` | **有消费** |
| 93 | `GET /api/content/drafts/{draft_id}` | 1 | A `frontend/src/components/ContentDraftList.tsx:49` | **有消费** |
| 94 | `PATCH /api/content/drafts/{draft_id}` | 0 | — | **零调用** |
| 95 | `POST /api/content/drafts/{draft_id}/publish` | 1 | A `frontend/src/components/PublishDialog.tsx:78` | **有消费** |
| 96 | `GET /api/content/drafts/{draft_id}/publish-history` | 1 | A `frontend/src/components/PublishHistory.tsx:33` | **有消费** |
| 97 | `GET /api/content/templates` | 0 | — | **仅文档** |
| 98 | `POST /api/cubox/sync` | 0 | — | **仅内部** |
| 99 | `POST /api/cve/attack-data/load` | 0 | — | **仅测试** |
| 100 | `GET /api/cve/attack-mapping` | 1 | A `frontend/src/hooks/useAttackMapping.ts:27` | **有消费** |
| 101 | `GET /api/cve/heatmap` | 1 | A `frontend/src/hooks/useCveHeatmap.ts:18` | **有消费** |
| 102 | `GET /api/cve/recent` | 1 | A `frontend/src/components/secnews/analytics/SecNewsAnalytics.tsx:40` | **有消费** |
| 103 | `POST /api/cve/sync` | 0 | — | **仅测试** |
| 104 | `GET /api/deep-read/recent` | 0 | — | **零调用** |
| 105 | `GET /api/deep-read/{entity_type}/{entity_id}` | 0 | — | **仅文档** |
| 106 | `POST /api/deep-read/{entity_type}/{entity_id}` | 1 | A `frontend/src/hooks/useDeepRead.ts:64` | **有消费** |
| 107 | `GET /api/digests` | 0 | — | **仅测试** |
| 108 | `POST /api/digests/generate` | 1 | A `frontend/src/hooks/useDigest.ts:86` | **有消费** |
| 109 | `GET /api/digests/latest` | 1 | A `frontend/src/hooks/useDigest.ts:69` | **有消费** |
| 110 | `GET /api/digests/priority` | 1 | A `frontend/src/components/sentinel/PriorityDigestCard.tsx:46` | **有消费** |
| 111 | `PUT /api/digests/read` | 1 | A `frontend/src/hooks/useDigest.ts:98` | **有消费** |
| 112 | `DELETE /api/digests/{digest_id}` | 0 | — | **零调用** |
| 113 | `GET /api/digests/{digest_id}` | 0 | — | **零调用** |
| 114 | `PUT /api/dsh/control/config` | 1 | A `frontend/src/components/secnews/settings/DshControlCard.tsx:117` | **有消费** |
| 115 | `POST /api/dsh/control/restart` | 1 | A `frontend/src/components/secnews/settings/DshControlCard.tsx:91` | **有消费** |
| 116 | `POST /api/dsh/control/start` | 1 | A `frontend/src/components/secnews/settings/DshControlCard.tsx:91` | **有消费** |
| 117 | `GET /api/dsh/control/status` | 1 | A `frontend/src/components/secnews/settings/DshControlCard.tsx:60` | **有消费** |
| 118 | `POST /api/dsh/control/stop` | 1 | A `frontend/src/components/secnews/settings/DshControlCard.tsx:91` | **有消费** |
| 119 | `GET /api/dsh/health` | 0 | — | **仅测试** |
| 120 | `POST /api/dsh/legacy/items/migrate/run` | 0 | — | **仅测试** |
| 121 | `GET /api/dsh/legacy/items/migrate/status` | 0 | — | **仅测试** |
| 122 | `POST /api/dsh/legacy/migrate/run` | 0 | — | **仅测试** |
| 123 | `GET /api/dsh/legacy/migrate/status` | 0 | — | **仅测试** |
| 124 | `GET /api/dsh/legacy/migrate/v1/mapping` | 0 | — | **仅测试** |
| 125 | `POST /api/dsh/legacy/migrate/v1/promote` | 0 | — | **仅测试** |
| 126 | `GET /api/dsh/legacy/migrate/v1/promote/log` | 0 | — | **仅测试** |
| 127 | `POST /api/dsh/legacy/migrate/v1/run` | 0 | — | **仅测试** |
| 128 | `GET /api/dsh/legacy/migrate/v1/status` | 0 | — | **仅测试** |
| 129 | `GET /api/dsh/session/{session_id}` | 0 | — | **仅测试** |
| 130 | `POST /api/dsh/task` | 1 | A `frontend/src/components/secnews/analyze/SecNewsAnalyze.tsx:75` | **有消费** |
| 131 | `GET /api/event-technique/candidates` | 2 | A `frontend/src/components/events/EventsReviewPage.tsx:90`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:75` | **有消费** |
| 132 | `POST /api/event-technique/candidates` | 1 | A `frontend/src/components/security/EventTypeReviewPage.tsx:109` | **有消费** |
| 133 | `POST /api/event-technique/candidates/{candidate_id}/approve` | 3 | A `frontend/src/components/events/EventsReviewPage.tsx:129`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:119`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:122` | **有消费** |
| 134 | `POST /api/event-technique/candidates/{candidate_id}/reject` | 3 | A `frontend/src/components/events/EventsReviewPage.tsx:147`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:102`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:114` | **有消费** |
| 135 | `GET /api/event-technique/event-types` | 2 | A `frontend/src/components/events/EventsReviewPage.tsx:73`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:63` | **有消费** |
| 136 | `POST /api/event-technique/event-types/{event_type_id}/batch-approve` | 2 | A `frontend/src/components/events/EventsReviewPage.tsx:168`<br>A `frontend/src/components/security/EventTypeReviewPage.tsx:142` | **有消费** |
| 137 | `GET /api/event-technique/event-types/{event_type_id}/techniques` | 0 | — | **零调用** |
| 138 | `GET /api/events` | 0 | — | **仅内部** |
| 139 | `GET /api/export` | 0 | — | **仅内部** |
| 140 | `POST /api/export/rebuild` | 0 | — | **零调用** |
| 141 | `GET /api/export/xlsx` | 0 | — | **仅测试** |
| 142 | `POST /api/extract/auto` | 0 | — | **仅内部** |
| 143 | `POST /api/extract/hotspot/{hotspot_id}` | 1 | A `frontend/src/components/extract/ExtractPage.tsx:71` | **有消费** |
| 144 | `POST /api/extract/knowledge/{item_id}` | 1 | A `frontend/src/components/extract/ExtractPage.tsx:71` | **有消费** |
| 145 | `POST /api/extract/preview` | 0 | — | **仅测试** |
| 146 | `GET /api/favorites` | 1 | A `frontend/src/hooks/useFavorites.ts:78` | **有消费** |
| 147 | `POST /api/favorites` | 1 | A `frontend/src/hooks/useFavorites.ts:127` | **有消费** |
| 148 | `POST /api/favorites/by-hotspot` | 0 | — | **仅内部** |
| 149 | `GET /api/favorites/count` | 0 | — | **仅测试** |
| 150 | `GET /api/favorites/export` | 0 | — | **仅测试** |
| 151 | `DELETE /api/favorites/{hotspot_id}` | 1 | A `frontend/src/hooks/useFavorites.ts:119` | **有消费** |
| 152 | `POST /api/feedback/` | 0 | — | **仅内部** |
| 153 | `GET /api/feedback/entity/{entity_type}/{entity_id}` | 0 | — | **仅测试** |
| 154 | `GET /api/feedback/history` | 0 | — | **仅测试** |
| 155 | `GET /api/feedback/profile` | 0 | — | **仅测试** |
| 156 | `GET /api/feedback/role-summary` | 0 | — | **仅测试** |
| 157 | `GET /api/health` | 2 | A `frontend/src/components/settings/CollectionScheduleInfo.tsx:13`<br>A `frontend/src/components/settings/SettingsDashboard.tsx:115` | **有消费** |
| 158 | `POST /api/history/archive` | 0 | — | **仅文档** |
| 159 | `GET /api/history/batches` | 1 | A `frontend/src/components/HistoryPage.tsx:81` | **有消费** |
| 160 | `GET /api/history/batches/{batch_no}/items` | 1 | A `frontend/src/components/HistoryPage.tsx:117` | **有消费** |
| 161 | `GET /api/history/batches/{batch_no}/range` | 0 | — | **仅测试** |
| 162 | `GET /api/history/batches/{batch_no}/summary` | 1 | A `frontend/src/components/HistoryPage.tsx:133` | **有消费** |
| 163 | `GET /api/hotspots` | 4 | B `frontend/src/components/sentinel/SentinelGardenPage.tsx:316`<br>B `frontend/src/components/sentinel/SentinelGraphPage.tsx:244`<br>B `frontend/src/components/sentinel/SentinelShell.tsx:82`<br>B `frontend/src/hooks/useHotspotData.ts:109` | **有消费** |
| 164 | `GET /api/hotspots/picked` | 1 | B `frontend/src/components/sentinel/SentinelHomePage.tsx:373` | **有消费** |
| 165 | `GET /api/hotspots/{item_id}` | 1 | B `frontend/src/api/hotspots.ts:79` | **有消费** |
| 166 | `POST /api/image/generate` | 0 | — | **仅测试** |
| 167 | `POST /api/image/understand` | 0 | — | **仅测试** |
| 168 | `GET /api/info-filter/gate` | 0 | — | **仅测试** |
| 169 | `POST /api/info-filter/preview` | 0 | — | **仅测试** |
| 170 | `GET /api/info-filter/rules` | 1 | A `frontend/src/components/quality/QualityDashboardPage.tsx:56` | **有消费** |
| 171 | `POST /api/info-filter/rules` | 0 | — | **仅测试** |
| 172 | `DELETE /api/info-filter/rules/{rule_id}` | 1 | A `frontend/src/components/secnews/settings/InfoFilterCard.tsx:150` | **有消费** |
| 173 | `PATCH /api/info-filter/rules/{rule_id}` | 1 | A `frontend/src/components/secnews/settings/InfoFilterCard.tsx:136` | **有消费** |
| 174 | `GET /api/interest/content-prefs/recommendations` | 1 | A `frontend/src/components/settings/ContentPreferencesCard.tsx:120` | **有消费** |
| 175 | `GET /api/interest/domains/recommendations` | 1 | A `frontend/src/components/settings/PracticeDomainsCard.tsx:92` | **有消费** |
| 176 | `GET /api/interest/reactions` | 1 | A `frontend/src/lib/interest.ts:69` | **有消费** |
| 177 | `DELETE /api/interest/reactions/{item_id}` | 1 | A `frontend/src/lib/interest.ts:61` | **有消费** |
| 178 | `POST /api/interest/reset` | 1 | A `frontend/src/components/settings/PracticeDomainsCard.tsx:128` | **有消费** |
| 179 | `POST /api/interest/signals` | 2 | A `frontend/src/lib/interest.ts:32`<br>A `frontend/src/lib/interest.ts:53` | **有消费** |
| 180 | `GET /api/interest/weights` | 1 | A `frontend/src/components/settings/PracticeDomainsCard.tsx:65` | **有消费** |
| 181 | `GET /api/kl/compounding` | 1 | A `frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx:90` | **有消费** |
| 182 | `GET /api/kl/concepts` | 0 | — | **仅文档** |
| 183 | `GET /api/kl/graph` | 0 | — | **仅文档** |
| 184 | `GET /api/kl/health` | 0 | — | **仅测试** |
| 185 | `POST /api/kl/import/bookmarks` | 0 | — | **仅文档** |
| 186 | `POST /api/kl/import/url` | 2 | A `frontend/src/components/secnews/analyze/SecNewsAnalyze.tsx:53`<br>A `frontend/src/components/sentinel/SentinelHomePage.tsx:167` | **有消费** |
| 187 | `GET /api/kl/inbox/list` | 0 | — | **零调用** |
| 188 | `POST /api/kl/inbox/scan` | 0 | — | **仅文档** |
| 189 | `GET /api/kl/items/{item_id}` | 0 | — | **仅测试** |
| 190 | `PUT /api/kl/items/{item_id}` | 0 | — | **仅测试** |
| 191 | `GET /api/kl/liveness` | 0 | — | **仅文档** |
| 192 | `POST /api/kl/liveness/sweep` | 0 | — | **仅文档** |
| 193 | `GET /api/kl/metrics` | 0 | — | **仅内部** |
| 194 | `GET /api/kl/metrics/counters` | 0 | — | **仅测试** |
| 195 | `GET /api/kl/metrics/stage-counts` | 0 | — | **零调用** |
| 196 | `POST /api/kl/pipeline/advance` | 0 | — | **仅文档** |
| 197 | `POST /api/kl/pipeline/drain` | 0 | — | **仅文档** |
| 198 | `POST /api/kl/pipeline/retry` | 0 | — | **仅文档** |
| 199 | `GET /api/kl/pipeline/stats` | 2 | A `frontend/src/components/sentinel/SentinelShell.tsx:61`<br>B `frontend/src/components/secnews/pipeline/TokenLedger.tsx:28` | **有消费** |
| 200 | `GET /api/kl/planning-actions` | 2 | A `frontend/src/components/knowledge/KnowledgePlanningPanel.tsx:118`<br>A `frontend/src/components/sentinel/SentinelActionPage.tsx:178` | **有消费** |
| 201 | `PUT /api/kl/planning-actions/{action_id}/status` | 2 | A `frontend/src/components/knowledge/KnowledgePlanningPanel.tsx:139`<br>A `frontend/src/components/sentinel/SentinelActionPage.tsx:224` | **有消费** |
| 202 | `GET /api/kl/quarantine/list` | 0 | — | **零调用** |
| 203 | `POST /api/kl/rollback/{item_id}` | 0 | — | **仅内部** |
| 204 | `POST /api/knowledge/bookmarks/import` | 0 | — | **仅文档** |
| 205 | `POST /api/knowledge/chunks/generate/{item_id}` | 0 | — | **仅测试** |
| 206 | `GET /api/knowledge/chunks/search` | 0 | — | **仅测试** |
| 207 | `GET /api/knowledge/chunks/{item_id}` | 1 | B `frontend/src/components/knowledge/DeepReadMode.tsx:141` | **有消费** |
| 208 | `POST /api/knowledge/classify/batch` | 0 | — | **零调用** |
| 209 | `GET /api/knowledge/classify/stats` | 0 | — | **零调用** |
| 210 | `POST /api/knowledge/compile` | 1 | A `frontend/src/components/CompileTrigger.tsx:35` | **有消费** |
| 211 | `GET /api/knowledge/compile/preview` | 1 | A `frontend/src/components/CompileTrigger.tsx:22` | **有消费** |
| 212 | `GET /api/knowledge/concepts` | 2 | A `frontend/src/components/sentinel/SentinelGraphPage.tsx:241`<br>B `frontend/src/components/secnews/knowledge/WikiItemBrowser.tsx:40` | **有消费** |
| 213 | `POST /api/knowledge/concepts/link/batch` | 0 | — | **零调用** |
| 214 | `GET /api/knowledge/concepts/{slug}` | 1 | A `frontend/src/components/ConceptDetailDialog.tsx:20` | **有消费** |
| 215 | `POST /api/knowledge/cubox/import-cards` | 0 | — | **仅测试** |
| 216 | `POST /api/knowledge/cubox/import-dir` | 0 | — | **仅测试** |
| 217 | `GET /api/knowledge/federation` | 1 | A `frontend/src/components/FederationStatus.tsx:13` | **有消费** |
| 218 | `GET /api/knowledge/graph` | 2 | B `frontend/src/components/KnowledgeGraph.tsx:37`<br>B `frontend/src/components/sentinel/SentinelGraphPage.tsx:240` | **有消费** |
| 219 | `GET /api/knowledge/health` | 2 | B `frontend/src/components/HealthDashboard.tsx:11`<br>B `frontend/src/components/KnowledgePage.tsx:29` | **有消费** |
| 220 | `GET /api/knowledge/hub-stats` | 1 | A `frontend/src/components/knowledge/KnowledgeHubPage.tsx:50` | **有消费** |
| 221 | `POST /api/knowledge/import-from-history` | 1 | A `frontend/src/components/HistoryPage.tsx:60` | **有消费** |
| 222 | `GET /api/knowledge/imported` | 1 | A `frontend/src/hooks/useImported.ts:39` | **有消费** |
| 223 | `GET /api/knowledge/items` | 3 | A `frontend/src/components/knowledge/KnowledgeLibraryPage.tsx:57`<br>B `frontend/src/components/knowledge/KnowledgeProcess.tsx:47`<br>B `frontend/src/components/secnews/knowledge/WikiItemBrowser.tsx:39` | **有消费** |
| 224 | `DELETE /api/knowledge/items/{item_id}` | 1 | B `frontend/src/components/ItemDetailDialog.tsx:149` | **有消费** |
| 225 | `GET /api/knowledge/items/{item_id}` | 0 | — | **仅内部** |
| 226 | `PATCH /api/knowledge/items/{item_id}` | 1 | B `frontend/src/components/ItemDetailDialog.tsx:132` | **有消费** |
| 227 | `GET /api/knowledge/obsidian/conflicts` | 0 | — | **零调用** |
| 228 | `POST /api/knowledge/obsidian/open` | 0 | — | **零调用** |
| 229 | `POST /api/knowledge/obsidian/watchdog/start` | 0 | — | **零调用** |
| 230 | `GET /api/knowledge/obsidian/watchdog/status` | 0 | — | **零调用** |
| 231 | `POST /api/knowledge/obsidian/watchdog/stop` | 0 | — | **零调用** |
| 232 | `GET /api/knowledge/plans` | 1 | A `frontend/src/components/LearningPanel.tsx:27` | **有消费** |
| 233 | `POST /api/knowledge/plans` | 0 | — | **仅文档** |
| 234 | `POST /api/knowledge/plans/generate` | 1 | A `frontend/src/components/LearningPanel.tsx:61` | **有消费** |
| 235 | `GET /api/knowledge/plans/{week}` | 0 | — | **仅文档** |
| 236 | `PATCH /api/knowledge/plans/{week}` | 0 | — | **仅文档** |
| 237 | `GET /api/knowledge/progress` | 1 | A `frontend/src/components/MasteryGauge.tsx:14` | **有消费** |
| 238 | `POST /api/knowledge/progress/sync` | 0 | — | **零调用** |
| 239 | `GET /api/knowledge/progress/{concept_slug}` | 0 | — | **零调用** |
| 240 | `PATCH /api/knowledge/progress/{concept_slug}` | 0 | — | **零调用** |
| 241 | `POST /api/knowledge/projection/rebuild` | 0 | — | **零调用** |
| 242 | `GET /api/knowledge/search` | 0 | — | **仅测试** |
| 243 | `GET /api/knowledge/skills` | 3 | B `frontend/src/components/SkillConfigDialog.tsx:65`<br>B `frontend/src/components/SkillEntryGrid.tsx:45`<br>B `frontend/src/components/SkillEntryGrid.tsx:103` | **有消费** |
| 244 | `POST /api/knowledge/skills` | 0 | — | **仅测试** |
| 245 | `POST /api/knowledge/skills/seed` | 0 | — | **零调用** |
| 246 | `DELETE /api/knowledge/skills/{skill_id}` | 0 | — | **零调用** |
| 247 | `PATCH /api/knowledge/skills/{skill_id}` | 1 | A `frontend/src/components/SkillConfigDialog.tsx:105` | **有消费** |
| 248 | `GET /api/knowledge/skills/{skill_name}/validate` | 1 | A `frontend/src/components/PublishDialog.tsx:61` | **有消费** |
| 249 | `GET /api/knowledge/soul` | 1 | A `frontend/src/components/SoulViewer.tsx:10` | **有消费** |
| 250 | `POST /api/knowledge/soul/regenerate` | 1 | A `frontend/src/components/SoulViewer.tsx:19` | **有消费** |
| 251 | `GET /api/knowledge/summaries` | 0 | — | **仅文档** |
| 252 | `POST /api/knowledge/summaries/weekly` | 0 | — | **零调用** |
| 253 | `POST /api/knowledge/sync` | 0 | — | **仅文档** |
| 254 | `GET /api/knowledge/tasks` | 1 | B `frontend/src/components/TaskMonitor.tsx:27` | **有消费** |
| 255 | `POST /api/knowledge/tasks` | 1 | B `frontend/src/components/TaskSubmitDialog.tsx:82` | **有消费** |
| 256 | `GET /api/knowledge/tasks/{task_id}` | 2 | A `frontend/src/components/LearningPanel.tsx:96`<br>A `frontend/src/components/knowledge/KnowledgeImport.tsx:91` | **有消费** |
| 257 | `GET /api/knowledge/topics` | 2 | A `frontend/src/components/KnowledgeFilters.tsx:33`<br>A `frontend/src/components/knowledge/KnowledgeLibraryPage.tsx:84` | **有消费** |
| 258 | `POST /api/llm/evaluate` | 1 | A `frontend/src/components/secnews/analyze/SecNewsAnalyze.tsx:92` | **有消费** |
| 259 | `GET /api/llm/pool` | 2 | A `frontend/src/components/settings/ModelPoolPanel.tsx:88`<br>A `frontend/src/components/settings/ModelPoolPanel.tsx:128` | **有消费** |
| 260 | `POST /api/llm/pool/detect` | 0 | — | **零调用** |
| 261 | `POST /api/llm/pool/route` | 1 | A `frontend/src/components/settings/ModelPoolPanel.tsx:148` | **有消费** |
| 262 | `GET /api/llm/pool/routing` | 1 | A `frontend/src/components/settings/ModelPoolPanel.tsx:78` | **有消费** |
| 263 | `GET /api/llm/status` | 3 | A `frontend/src/components/settings/ModelsSettings.tsx:31`<br>A `frontend/src/components/settings/QualitySettings.tsx:47`<br>A `frontend/src/components/settings/quality/ProviderPanel.tsx:45` | **有消费** |
| 264 | `POST /api/maintenance/backup-verify` | 1 | A `frontend/src/components/MaintPage.tsx:242` | **有消费** |
| 265 | `GET /api/maintenance/backups` | 2 | A `frontend/src/components/MaintPage.tsx:223`<br>A `frontend/src/components/MaintPage.tsx:260` | **有消费** |
| 266 | `POST /api/maintenance/backups/compact` | 1 | A `frontend/src/components/MaintPage.tsx:255` | **有消费** |
| 267 | `POST /api/maintenance/cleanup` | 1 | A `frontend/src/components/settings/DatabaseMaintenance.tsx:119` | **有消费** |
| 268 | `POST /api/maintenance/cleanup-duplicates` | 1 | A `frontend/src/components/settings/DatabaseMaintenance.tsx:104` | **有消费** |
| 269 | `POST /api/maintenance/cleanup-quality-logs` | 2 | A `frontend/src/components/MaintPage.tsx:292`<br>A `frontend/src/components/settings/DatabaseMaintenance.tsx:84` | **有消费** |
| 270 | `GET /api/maintenance/dirty-report` | 2 | A `frontend/src/components/MaintPage.tsx:186`<br>A `frontend/src/components/settings/DatabaseMaintenance.tsx:54` | **有消费** |
| 271 | `GET /api/maintenance/duplicates` | 1 | A `frontend/src/components/settings/DatabaseMaintenance.tsx:55` | **有消费** |
| 272 | `GET /api/maintenance/health` | 2 | A `frontend/src/components/MaintPage.tsx:185`<br>A `frontend/src/components/settings/DatabaseMaintenance.tsx:52` | **有消费** |
| 273 | `GET /api/maintenance/index-health` | 1 | A `frontend/src/components/MaintPage.tsx:200` | **有消费** |
| 274 | `GET /api/maintenance/orphans` | 0 | — | **零调用** |
| 275 | `GET /api/maintenance/quality-log-tiers` | 1 | A `frontend/src/components/MaintPage.tsx:211` | **有消费** |
| 276 | `GET /api/maintenance/table-stats` | 1 | A `frontend/src/components/settings/DatabaseMaintenance.tsx:53` | **有消费** |
| 277 | `POST /api/maintenance/vacuum` | 2 | A `frontend/src/components/MaintPage.tsx:271`<br>A `frontend/src/components/settings/DatabaseMaintenance.tsx:70` | **有消费** |
| 278 | `POST /api/mcp/dsh/analyze` | 0 | — | **仅内部** |
| 279 | `GET /api/mcp/dsh/session/{session_id}` | 0 | — | **仅内部** |
| 280 | `POST /api/mcp/kl/enqueue` | 0 | — | **仅内部** |
| 281 | `POST /api/mcp/kl/retry` | 0 | — | **仅内部** |
| 282 | `GET /api/mcp/kl/status` | 0 | — | **仅内部** |
| 283 | `POST /api/mcp/phase8/enrich-concept` | 0 | — | **仅测试** |
| 284 | `POST /api/mcp/phase8/link-items` | 0 | — | **仅测试** |
| 285 | `POST /api/mcp/phase8/score-item` | 0 | — | **仅测试** |
| 286 | `POST /api/mcp/phase8/trigger-codegarden-drift` | 0 | — | **仅测试** |
| 287 | `GET /api/mcp/status` | 1 | A `frontend/src/components/settings/MCPSettingsCard.tsx:52` | **有消费** |
| 288 | `GET /api/mcp/tools` | 1 | A `frontend/src/components/settings/MCPSettingsCard.tsx:53` | **有消费** |
| 289 | `GET /api/mode/current` | 1 | A `frontend/src/components/settings/ModeSwitcher.tsx:32` | **有消费** |
| 290 | `GET /api/mode/modes` | 1 | A `frontend/src/components/settings/ModeSwitcher.tsx:33` | **有消费** |
| 291 | `PUT /api/mode/switch` | 1 | A `frontend/src/components/settings/ModeSwitcher.tsx:49` | **有消费** |
| 292 | `GET /api/observability/alerts/active` | 1 | B `frontend/src/components/secnews/observability/ActiveAlertsBanner.tsx:51` | **有消费** |
| 293 | `POST /api/observability/alerts/{alert_id}/ack` | 1 | A `frontend/src/components/secnews/observability/ActiveAlertsBanner.tsx:69` | **有消费** |
| 294 | `GET /api/observability/audit` | 0 | — | **仅测试** |
| 295 | `GET /api/observability/channels` | 0 | — | **仅测试** |
| 296 | `PUT /api/observability/channels` | 0 | — | **仅测试** |
| 297 | `POST /api/observability/channels/test` | 0 | — | **零调用** |
| 298 | `GET /api/observability/deliveries` | 0 | — | **仅测试** |
| 299 | `GET /api/observability/llm-usage` | 0 | — | **零调用** |
| 300 | `GET /api/observability/llm/health` | 0 | — | **仅测试** |
| 301 | `POST /api/observability/llm/health/{provider}/reset` | 0 | — | **仅文档** |
| 302 | `GET /api/observability/recent` | 1 | A `frontend/src/components/secnews/observability/ObservabilityDashboard.tsx:62` | **有消费** |
| 303 | `GET /api/observability/sampling` | 0 | — | **仅测试** |
| 304 | `PUT /api/observability/sampling` | 0 | — | **仅测试** |
| 305 | `GET /api/observability/summary` | 1 | B `frontend/src/components/secnews/observability/ObservabilityDashboard.tsx:61` | **有消费** |
| 306 | `GET /api/observability/thresholds` | 0 | — | **仅测试** |
| 307 | `PUT /api/observability/thresholds` | 0 | — | **仅测试** |
| 308 | `GET /api/observability/timeseries` | 0 | — | **仅内部** |
| 309 | `GET /api/ops/kpi` | 0 | — | **仅测试** |
| 310 | `GET /api/ops/runs` | 1 | A `frontend/src/components/settings/OpsRunsPanel.tsx:65` | **有消费** |
| 311 | `GET /api/profile` | 0 | — | **仅内部** |
| 312 | `GET /api/proposals` | 2 | B `frontend/src/components/action/ApprovalInbox.tsx:309`<br>B `frontend/src/components/action/ApprovalInbox.tsx:310` | **有消费** |
| 313 | `POST /api/proposals` | 0 | — | **仅内部** |
| 314 | `POST /api/proposals/copilot-draft` | 4 | B `frontend/src/components/action/ApprovalInbox.tsx:340`<br>B `frontend/src/components/action/CopilotCards.test.tsx:63`<br>B `frontend/src/components/action/CopilotCards.test.tsx:73`<br>B `frontend/src/components/action/CopilotCards.tsx:74` | **有消费** |
| 315 | `POST /api/proposals/draft-judgment` | 4 | B `frontend/src/components/action/ApprovalInbox.tsx:339`<br>B `frontend/src/components/action/CopilotCards.test.tsx:47`<br>B `frontend/src/components/action/CopilotCards.tsx:73`<br>B `frontend/src/components/v1/CaseDetail.tsx:248` | **有消费** |
| 316 | `POST /api/proposals/failed` | 0 | — | **零调用** |
| 317 | `POST /api/proposals/runs/{run_id}/retry` | 0 | — | **仅测试** |
| 318 | `GET /api/proposals/{proposal_id}` | 0 | — | **零调用** |
| 319 | `POST /api/proposals/{proposal_id}/approve` | 1 | B `frontend/src/components/action/ApprovalInbox.tsx:104` | **有消费** |
| 320 | `POST /api/proposals/{proposal_id}/reject` | 1 | B `frontend/src/components/action/ApprovalInbox.tsx:117` | **有消费** |
| 321 | `POST /api/proxy/health/reset` | 1 | A `frontend/src/components/settings/ProxySettings.tsx:165` | **有消费** |
| 322 | `GET /api/proxy/settings` | 1 | A `frontend/src/components/settings/ProxySettings.tsx:102` | **有消费** |
| 323 | `PUT /api/proxy/settings` | 1 | A `frontend/src/components/settings/ProxySettings.tsx:119` | **有消费** |
| 324 | `GET /api/proxy/test` | 1 | A `frontend/src/components/settings/ProxySettings.tsx:147` | **有消费** |
| 325 | `GET /api/quality/custom-rules` | 1 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:82` | **有消费** |
| 326 | `POST /api/quality/custom-rules` | 1 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:108` | **有消费** |
| 327 | `POST /api/quality/custom-rules/dry-run` | 1 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:173` | **有消费** |
| 328 | `GET /api/quality/custom-rules/gates` | 1 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:83` | **有消费** |
| 329 | `DELETE /api/quality/custom-rules/{rule_id}` | 1 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:144` | **有消费** |
| 330 | `PUT /api/quality/custom-rules/{rule_id}` | 2 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:112`<br>A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:130` | **有消费** |
| 331 | `GET /api/quality/logs` | 0 | — | **仅测试** |
| 332 | `GET /api/quality/rejection-log` | 1 | A `frontend/src/components/settings/RejectionLogCard.tsx:34` | **有消费** |
| 333 | `GET /api/quality/rejection-stats` | 0 | — | **零调用** |
| 334 | `GET /api/quality/rejections` | 1 | B `frontend/src/components/secnews/observability/RejectionReplay.tsx:84` | **有消费** |
| 335 | `GET /api/quality/rules` | 2 | A `frontend/src/components/settings/QualitySettings.tsx:32`<br>A `frontend/src/components/settings/quality/QualityRulesPanel.tsx:55` | **有消费** |
| 336 | `PUT /api/quality/rules` | 2 | A `frontend/src/components/settings/quality/CustomRulesPanel.tsx:157`<br>A `frontend/src/components/settings/quality/QualityRulesPanel.tsx:49` | **有消费** |
| 337 | `GET /api/quality/source-reputation` | 0 | — | **仅测试** |
| 338 | `GET /api/quality/summary` | 2 | A `frontend/src/components/quality/QualityDashboardPage.tsx:55`<br>A `frontend/src/components/sentinel/SentinelHomePage.tsx:336` | **有消费** |
| 339 | `GET /api/recommend/{entity_type}/{entity_id}` | 1 | A `frontend/src/components/knowledge/DeepReadMode.tsx:122` | **有消费** |
| 340 | `POST /api/refresh` | 1 | B `frontend/src/hooks/useHotspotData.ts:203` | **有消费** |
| 341 | `GET /api/reports/daily` | 0 | — | **零调用** |
| 342 | `GET /api/reports/daily/overview` | 1 | A `frontend/src/components/report/DailyReport.tsx:26` | **有消费** |
| 343 | `GET /api/reports/monthly` | 0 | — | **零调用** |
| 344 | `GET /api/reports/monthly/available` | 0 | — | **零调用** |
| 345 | `GET /api/reports/monthly/overview` | 1 | A `frontend/src/components/report/MonthlyReport.tsx:42` | **有消费** |
| 346 | `GET /api/reports/weekly/available` | 0 | — | **零调用** |
| 347 | `GET /api/reports/weekly/overview` | 1 | A `frontend/src/components/report/WeeklyReport.tsx:54` | **有消费** |
| 348 | `GET /api/reviews/cards` | 1 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:378` | **有消费** |
| 349 | `GET /api/reviews/due` | 4 | A `frontend/src/components/knowledge/ReviewMode.tsx:106`<br>A `frontend/src/components/sentinel/SentinelActionPage.tsx:179`<br>A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:134`<br>A `frontend/src/hooks/useReviews.ts:70` | **有消费** |
| 350 | `GET /api/reviews/forecast` | 1 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:289` | **有消费** |
| 351 | `GET /api/reviews/history` | 1 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:290` | **有消费** |
| 352 | `GET /api/reviews/stats` | 3 | A `frontend/src/components/sentinel/SentinelActionPage.tsx:180`<br>A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:291`<br>A `frontend/src/hooks/useReviews.ts:84` | **有消费** |
| 353 | `DELETE /api/reviews/{entity_type}/{entity_id}` | 1 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:426` | **有消费** |
| 354 | `GET /api/reviews/{entity_type}/{entity_id}` | 0 | — | **零调用** |
| 355 | `PATCH /api/reviews/{entity_type}/{entity_id}` | 1 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:411` | **有消费** |
| 356 | `POST /api/reviews/{entity_type}/{entity_id}` | 2 | A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:401`<br>A `frontend/src/hooks/useReviews.ts:119` | **有消费** |
| 357 | `POST /api/reviews/{entity_type}/{entity_id}/grade` | 4 | A `frontend/src/components/knowledge/ReviewMode.tsx:156`<br>A `frontend/src/components/sentinel/SentinelActionPage.tsx:251`<br>A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:147`<br>A `frontend/src/hooks/useReviews.ts:106` | **有消费** |
| 358 | `POST /api/reviews/{entity_type}/{entity_id}/undo` | 2 | A `frontend/src/components/sentinel/SentinelActionPage.tsx:288`<br>A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:166` | **有消费** |
| 359 | `GET /api/search` | 2 | A `frontend/src/components/search/UnifiedSearchPage.tsx:78`<br>A `frontend/src/components/sentinel/review/ReviewOverlay.tsx:389` | **有消费** |
| 360 | `GET /api/secnews/feed` | 1 | A `frontend/src/components/secnews/feed/FeedView.tsx:50` | **有消费** |
| 361 | `GET /api/secnews/knowledge` | 1 | A `frontend/src/components/secnews/knowledge/WikiBrowser.tsx:31` | **有消费** |
| 362 | `GET /api/secnews/pipeline` | 2 | B `frontend/src/components/secnews/pipeline/PipelineView.tsx:45`<br>B `frontend/src/components/settings/KLQueueCard.tsx:10` | **有消费** |
| 363 | `GET /api/secnews/stats` | 1 | A `frontend/src/components/sentinel/SentinelActionPage.tsx:181` | **有消费** |
| 364 | `GET /api/secrets` | 4 | A `frontend/src/components/SkillConfigDialog.tsx:66`<br>A `frontend/src/components/settings/SecretsStatusCard.tsx:19`<br>A `frontend/src/components/settings/quality/SecretsPanel.tsx:43`<br>A `frontend/src/hooks/useSecrets.ts:84` | **有消费** |
| 365 | `POST /api/secrets` | 2 | A `frontend/src/components/settings/ModelPoolPanel.tsx:114`<br>A `frontend/src/hooks/useSecrets.ts:155` | **有消费** |
| 366 | `GET /api/secrets/export` | 0 | — | **仅测试** |
| 367 | `POST /api/secrets/import` | 1 | A `frontend/src/hooks/useSecrets.ts:231` | **有消费** |
| 368 | `POST /api/secrets/lock` | 3 | A `frontend/src/components/settings/SecretsStatusCard.tsx:90`<br>A `frontend/src/components/settings/quality/SecretsPanel.tsx:77`<br>A `frontend/src/hooks/useSecrets.ts:148` | **有消费** |
| 369 | `GET /api/secrets/oauth-config` | 2 | A `frontend/src/components/secrets/UnlockModal.tsx:38`<br>A `frontend/src/hooks/useSecrets.ts:241` | **有消费** |
| 370 | `POST /api/secrets/reset` | 0 | — | **仅测试** |
| 371 | `POST /api/secrets/rotate` | 0 | — | **仅内部** |
| 372 | `GET /api/secrets/rotation-status` | 1 | A `frontend/src/components/secrets/RotationBanner.tsx:29` | **有消费** |
| 373 | `POST /api/secrets/setup` | 1 | A `frontend/src/hooks/useSecrets.ts:125` | **有消费** |
| 374 | `GET /api/secrets/status` | 5 | A `frontend/src/components/settings/ModelPoolPanel.tsx:100`<br>A `frontend/src/components/settings/SecretsStatusCard.tsx:16`<br>A `frontend/src/components/settings/SettingsDashboard.tsx:116`<br>A `frontend/src/components/settings/quality/SecretsPanel.tsx:44`<br>A `frontend/src/hooks/useSecrets.ts:70` | **有消费** |
| 375 | `GET /api/secrets/unlock` | 0 | — | **仅测试** |
| 376 | `POST /api/secrets/unlock` | 2 | A `frontend/src/components/settings/quality/SecretsPanel.tsx:67`<br>A `frontend/src/hooks/useSecrets.ts:136` | **有消费** |
| 377 | `POST /api/secrets/unlock-with-oauth` | 2 | A `frontend/src/hooks/useSecrets.ts:249`<br>A `frontend/src/routes/oauth-callback.tsx:44` | **有消费** |
| 378 | `DELETE /api/secrets/{secret_id}` | 2 | A `frontend/src/components/settings/quality/SecretsPanel.tsx:114`<br>A `frontend/src/hooks/useSecrets.ts:183` | **有消费** |
| 379 | `PATCH /api/secrets/{secret_id}` | 1 | A `frontend/src/hooks/useSecrets.ts:169` | **有消费** |
| 380 | `POST /api/secrets/{secret_id}/reveal` | 2 | A `frontend/src/components/settings/quality/SecretsPanel.tsx:85`<br>A `frontend/src/hooks/useSecrets.ts:192` | **有消费** |
| 381 | `POST /api/secrets/{secret_id}/test` | 2 | A `frontend/src/components/settings/quality/SecretsPanel.tsx:94`<br>A `frontend/src/hooks/useSecrets.ts:202` | **有消费** |
| 382 | `POST /api/security/enrich` | 0 | — | **零调用** |
| 383 | `GET /api/security/entities` | 0 | — | **仅文档** |
| 384 | `GET /api/security/entities/{entity_id}` | 0 | — | **零调用** |
| 385 | `GET /api/security/entities/{entity_id}/related` | 1 | A `frontend/src/components/security/SecurityEntityDetail.tsx:20` | **有消费** |
| 386 | `GET /api/security/graph` | 1 | A `frontend/src/hooks/useSecurityGraph.ts:47` | **有消费** |
| 387 | `GET /api/security/mitre/cache` | 0 | — | **仅文档** |
| 388 | `POST /api/security/mitre/sync` | 0 | — | **仅文档** |
| 389 | `POST /api/security/terminology/normalize` | 0 | — | **仅文档** |
| 390 | `GET /api/security/terminology/search` | 0 | — | **仅文档** |
| 391 | `GET /api/security/terminology/suggest` | 0 | — | **零调用** |
| 392 | `GET /api/security/terminology/taxonomy` | 0 | — | **仅文档** |
| 393 | `GET /api/settings/auto-intake` | 0 | — | **仅测试** |
| 394 | `PATCH /api/settings/auto-intake` | 2 | A `frontend/src/components/settings/AutoIntakeCard.tsx:29`<br>A `frontend/src/components/settings/AutoIntakeCard.tsx:42` | **有消费** |
| 395 | `GET /api/settings/content-preferences` | 2 | A `frontend/src/components/settings/ContentPreferencesCard.tsx:128`<br>A `frontend/src/components/settings/ContentPreferencesCard.tsx:156` | **有消费** |
| 396 | `PATCH /api/settings/content-preferences` | 1 | A `frontend/src/components/settings/ContentPreferencesCard.tsx:149` | **有消费** |
| 397 | `GET /api/settings/feature-gates` | 1 | A `frontend/src/components/settings/FeatureGatesCard.tsx:51` | **有消费** |
| 398 | `PUT /api/settings/feature-gates/{name}` | 1 | A `frontend/src/components/settings/FeatureGatesCard.tsx:63` | **有消费** |
| 399 | `GET /api/settings/features` | 0 | — | **仅内部** |
| 400 | `GET /api/settings/interests` | 1 | A `frontend/src/components/settings/PracticeDomainsCard.tsx:75` | **有消费** |
| 401 | `PATCH /api/settings/interests` | 1 | A `frontend/src/components/settings/PracticeDomainsCard.tsx:106` | **有消费** |
| 402 | `POST /api/settings/llm-provider` | 1 | A `frontend/src/components/settings/quality/ProviderPanel.tsx:36` | **有消费** |
| 403 | `GET /api/settings/mcp/config` | 1 | A `frontend/src/components/settings/MCPSettingsCard.tsx:55` | **有消费** |
| 404 | `PUT /api/settings/mcp/enabled` | 1 | A `frontend/src/components/settings/MCPSettingsCard.tsx:89` | **有消费** |
| 405 | `GET /api/settings/refresh-interval` | 1 | A `frontend/src/components/sentinel/SentinelHomePage.tsx:347` | **有消费** |
| 406 | `POST /api/settings/refresh-interval` | 0 | — | **仅测试** |
| 407 | `POST /api/settings/scenario-model` | 1 | A `frontend/src/components/settings/ScenarioModelsPanel.tsx:60` | **有消费** |
| 408 | `GET /api/skill-builder` | 0 | — | **仅内部** |
| 409 | `POST /api/skill-builder` | 1 | A `frontend/src/components/skills/SkillBuilder.tsx:214` | **有消费** |
| 410 | `POST /api/skill-builder/validate` | 1 | A `frontend/src/components/skills/SkillBuilder.tsx:194` | **有消费** |
| 411 | `DELETE /api/skill-builder/{skill_id}` | 0 | — | **零调用** |
| 412 | `GET /api/skill-builder/{skill_id}` | 0 | — | **零调用** |
| 413 | `PATCH /api/skill-builder/{skill_id}` | 0 | — | **零调用** |
| 414 | `GET /api/skill-registry` | 1 | A `frontend/src/components/dashboard/Dashboard.tsx:79` | **有消费** |
| 415 | `GET /api/skill-registry/runs/{run_id}` | 0 | — | **仅测试** |
| 416 | `POST /api/skill-registry/runs/{run_id}/feedback` | 1 | A `frontend/src/components/skills/FeedbackBar.tsx:30` | **有消费** |
| 417 | `GET /api/skill-registry/v1` | 1 | B `frontend/src/api/v1.ts:670` | **有消费** |
| 418 | `GET /api/skill-registry/v1/{skill_id}` | 1 | B `frontend/src/api/v1.ts:674` | **有消费** |
| 419 | `GET /api/skill-registry/{skill_id}` | 2 | A `frontend/src/hooks/useSkillRegistry.ts:81`<br>A `frontend/src/hooks/useSkillRegistry.ts:164` | **有消费** |
| 420 | `POST /api/skill-registry/{skill_id}/disable` | 0 | — | **仅文档** |
| 421 | `POST /api/skill-registry/{skill_id}/enable` | 0 | — | **仅文档** |
| 422 | `POST /api/skill-registry/{skill_id}/run` | 1 | A `frontend/src/components/skills/SkillStore.tsx:100` | **有消费** |
| 423 | `GET /api/skill-registry/{skill_id}/runs` | 1 | A `frontend/src/hooks/useSkillRegistry.ts:123` | **有消费** |
| 424 | `GET /api/skills` | 1 | A `frontend/src/hooks/useSkills.ts:76` | **有消费** |
| 425 | `POST /api/skills` | 0 | — | **仅测试** |
| 426 | `GET /api/skills/count_by_source` | 1 | A `frontend/src/hooks/useSkills.ts:95` | **有消费** |
| 427 | `DELETE /api/skills/{skill_id}` | 1 | A `frontend/src/hooks/useSkills.ts:153` | **有消费** |
| 428 | `PATCH /api/skills/{skill_id}` | 1 | A `frontend/src/hooks/useSkills.ts:139` | **有消费** |
| 429 | `GET /api/sources/alerts` | 1 | B `frontend/src/api/sources.ts:179` | **有消费** |
| 430 | `GET /api/sources/custom` | 2 | B `frontend/src/components/settings/SourceSettings.tsx:78`<br>B `frontend/src/components/settings/SourceSettings.tsx:98` | **有消费** |
| 431 | `POST /api/sources/custom` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:98` | **有消费** |
| 432 | `DELETE /api/sources/custom/{sid}` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:116` | **有消费** |
| 433 | `POST /api/sources/custom/{sid}/probe` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:131` | **有消费** |
| 434 | `POST /api/sources/custom/{sid}/toggle` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:123` | **有消费** |
| 435 | `GET /api/sources/health` | 3 | A `frontend/src/components/secnews/pipeline/SourceMatrixCard.tsx:56`<br>A `frontend/src/components/settings/SettingsDashboard.tsx:118`<br>B `frontend/src/components/sentinel/SentinelShell.tsx:92` | **有消费** |
| 436 | `GET /api/sources/health/by-source/{category}/{source_name}` | 1 | B `frontend/src/api/sources.ts:140` | **有消费** |
| 437 | `POST /api/sources/health/by-source/{category}/{source_name}/dead` | 1 | B `frontend/src/api/sources.ts:156` | **有消费** |
| 438 | `POST /api/sources/health/by-source/{category}/{source_name}/reset` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:63` | **有消费** |
| 439 | `GET /api/sources/health/trend` | 1 | B `frontend/src/api/sources.ts:130` | **有消费** |
| 440 | `GET /api/sources/health/trend/{source}` | 1 | B `frontend/src/api/sources.ts:134` | **有消费** |
| 441 | `GET /api/sources/health/v2` | 2 | B `frontend/src/components/settings/SourceSettings.tsx:53`<br>B `frontend/src/components/settings/SourceSettings.tsx:64` | **有消费** |
| 442 | `GET /api/sources/stats` | 1 | B `frontend/src/components/settings/SourceSettings.tsx:50` | **有消费** |
| 443 | `GET /api/sources/system` | 0 | — | **仅测试** |
| 444 | `DELETE /api/sources/system/{sid}` | 0 | — | **仅测试** |
| 445 | `PATCH /api/sources/system/{sid}` | 0 | — | **仅测试** |
| 446 | `POST /api/sources/{source_id}/probe` | 1 | B `frontend/src/api/sources.ts:190` | **有消费** |
| 447 | `GET /api/stats` | 1 | A `frontend/src/components/settings/SettingsDashboard.tsx:117` | **有消费** |
| 448 | `POST /api/sync/auto` | 2 | A `frontend/src/components/settings/SyncSettings.tsx:28`<br>A `frontend/src/hooks/useSync.ts:143` | **有消费** |
| 449 | `POST /api/sync/bidirectional` | 1 | A `frontend/src/hooks/useSync.ts:173` | **有消费** |
| 450 | `GET /api/sync/bundle/preview` | 1 | A `frontend/src/hooks/useSync.ts:111` | **有消费** |
| 451 | `DELETE /api/sync/config` | 1 | A `frontend/src/hooks/useSync.ts:136` | **有消费** |
| 452 | `POST /api/sync/config` | 1 | A `frontend/src/hooks/useSync.ts:127` | **有消费** |
| 453 | `GET /api/sync/conflicts` | 1 | A `frontend/src/components/sync/useSyncPage.ts:99` | **有消费** |
| 454 | `POST /api/sync/conflicts/auto-resolve` | 1 | A `frontend/src/components/sync/useSyncPage.ts:215` | **有消费** |
| 455 | `POST /api/sync/conflicts/resolve` | 0 | — | **仅测试** |
| 456 | `GET /api/sync/history` | 1 | A `frontend/src/hooks/useSync.ts:99` | **有消费** |
| 457 | `POST /api/sync/pull` | 1 | A `frontend/src/hooks/useSync.ts:162` | **有消费** |
| 458 | `POST /api/sync/push` | 1 | A `frontend/src/hooks/useSync.ts:151` | **有消费** |
| 459 | `GET /api/sync/status` | 2 | A `frontend/src/components/settings/SyncSettings.tsx:21`<br>A `frontend/src/hooks/useSync.ts:74` | **有消费** |
| 460 | `POST /api/sync/test` | 1 | A `frontend/src/hooks/useSync.ts:119` | **有消费** |
| 461 | `GET /api/tags` | 1 | A `frontend/src/components/tags/TagsPage.tsx:46` | **有消费** |
| 462 | `POST /api/tags` | 1 | A `frontend/src/components/tags/TagsPage.tsx:62` | **有消费** |
| 463 | `GET /api/tags/by-hotspot/{hotspot_id}` | 0 | — | **仅测试** |
| 464 | `GET /api/tags/suggest` | 1 | A `frontend/src/components/tags/TagsPage.tsx:94` | **有消费** |
| 465 | `DELETE /api/tags/{tag_id}` | 1 | A `frontend/src/components/tags/TagsPage.tsx:80` | **有消费** |
| 466 | `GET /api/tech-stack` | 0 | — | **仅测试** |
| 467 | `POST /api/tech-stack` | 0 | — | **仅测试** |
| 468 | `GET /api/tech-stack/impact` | 0 | — | **仅测试** |
| 469 | `DELETE /api/tech-stack/{tech_id}` | 0 | — | **零调用** |
| 470 | `GET /api/tech-stack/{tech_id}` | 0 | — | **零调用** |
| 471 | `PUT /api/tech-stack/{tech_id}` | 0 | — | **零调用** |
| 472 | `GET /api/trends` | 0 | — | **仅内部** |
| 473 | `GET /api/trigger/webhook/health` | 0 | — | **仅测试** |
| 474 | `POST /api/trigger/webhook/{source}` | 0 | — | **仅测试** |
| 475 | `GET /api/v1/actions` | 1 | B `frontend/src/api/v1.ts:350` | **有消费** |
| 476 | `POST /api/v1/actions/generate` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:280` | **有消费** |
| 477 | `GET /api/v1/actions/{action_id}` | 1 | B `frontend/src/api/v1.ts:364` | **有消费** |
| 478 | `POST /api/v1/actions/{action_id}/approve` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:174` | **有消费** |
| 479 | `POST /api/v1/actions/{action_id}/cancel` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:191` | **有消费** |
| 480 | `POST /api/v1/actions/{action_id}/start` | 2 | B `frontend/src/components/sentinel/action/ActionCommandConsole.tsx:87`<br>B `frontend/src/components/v1/CaseDetail.tsx:180` | **有消费** |
| 481 | `GET /api/v1/artifacts` | 1 | B `frontend/src/api/v1.ts:402` | **有消费** |
| 482 | `POST /api/v1/artifacts` | 1 | B `frontend/src/api/v1.ts:420` | **有消费** |
| 483 | `GET /api/v1/artifacts/{artifact_id}` | 1 | B `frontend/src/api/v1.ts:416` | **有消费** |
| 484 | `POST /api/v1/artifacts/{artifact_id}/accept` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:203` | **有消费** |
| 485 | `POST /api/v1/artifacts/{artifact_id}/reject` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:209` | **有消费** |
| 486 | `POST /api/v1/artifacts/{artifact_id}/verify` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:197` | **有消费** |
| 487 | `GET /api/v1/cases` | 5 | B `frontend/src/components/sentinel/action/ActionCommandConsole.tsx:41`<br>B `frontend/src/components/v1/panels/CaseQueuePanel.tsx:28`<br>B `frontend/src/components/v1/panels/CaseQueuePanel.tsx:29`<br>B `frontend/src/components/v1/panels/ExecOverviewPanel.tsx:35`<br>B `frontend/src/components/v1/panels/SignalPanel.tsx:143` | **有消费** |
| 488 | `POST /api/v1/cases` | 1 | B `frontend/src/components/v1/panels/SignalPanel.tsx:143` | **有消费** |
| 489 | `GET /api/v1/cases/{case_id}` | 0 | — | **仅测试** |
| 490 | `PATCH /api/v1/cases/{case_id}` | 2 | B `frontend/src/components/v1/CaseDetailPage.tsx:36`<br>B `frontend/src/api/v1.ts:116` | **有消费** |
| 491 | `GET /api/v1/cases/{case_id}/aggregate` | 3 | B `frontend/src/components/sentinel/action/ActionCommandConsole.tsx:62`<br>B `frontend/src/components/v1/CaseDetail.tsx:85`<br>B `frontend/src/components/v1/panels/ExecOverviewPanel.tsx:42` | **有消费** |
| 492 | `POST /api/v1/cases/{case_id}/close` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:220` | **有消费** |
| 493 | `GET /api/v1/judgments` | 1 | B `frontend/src/api/v1.ts:151` | **有消费** |
| 494 | `POST /api/v1/judgments/generate` | 0 | — | **仅测试** |
| 495 | `GET /api/v1/judgments/{judgment_id}` | 1 | B `frontend/src/api/v1.ts:168` | **有消费** |
| 496 | `POST /api/v1/judgments/{judgment_id}/publish` | 1 | B `frontend/src/components/v1/CaseDetail.tsx:263` | **有消费** |
| 497 | `GET /api/v1/knowledge` | 3 | B `frontend/src/components/v1/CaseDetail.tsx:103`<br>B `frontend/src/components/v1/V1Prototype.tsx:65`<br>B `frontend/src/components/v1/V1Prototype.tsx:99` | **有消费** |
| 498 | `POST /api/v1/knowledge/generate` | 1 | B `frontend/src/api/v1.ts:594` | **有消费** |
| 499 | `GET /api/v1/knowledge/{knowledge_id}` | 1 | B `frontend/src/api/v1.ts:586` | **有消费** |
| 500 | `POST /api/v1/knowledge/{knowledge_id}/adopt` | 2 | B `frontend/src/components/v1/CaseDetail.tsx:302`<br>B `frontend/src/components/v1/V1Prototype.tsx:140` | **有消费** |
| 501 | `GET /api/v1/knowledge/{knowledge_id}/adoptions` | 1 | B `frontend/src/api/v1.ts:615` | **有消费** |
| 502 | `POST /api/v1/knowledge/{knowledge_id}/deprecate` | 1 | B `frontend/src/components/v1/V1Prototype.tsx:175` | **有消费** |
| 503 | `POST /api/v1/knowledge/{knowledge_id}/outcome` | 1 | B `frontend/src/components/v1/V1Prototype.tsx:159` | **有消费** |
| 504 | `POST /api/v1/knowledge/{knowledge_id}/publish` | 1 | B `frontend/src/components/v1/V1Prototype.tsx:174` | **有消费** |
| 505 | `GET /api/v1/knowledge/{knowledge_id}/recall` | 1 | B `frontend/src/api/v1.ts:627` | **有消费** |
| 506 | `POST /api/v1/knowledge/{knowledge_id}/retract` | 1 | B `frontend/src/components/v1/V1Prototype.tsx:176` | **有消费** |
| 507 | `GET /api/v1/knowledge/{knowledge_id}/reuse` | 5 | B `frontend/src/components/v1/CaseDetail.tsx:109`<br>B `frontend/src/components/v1/V1Prototype.tsx:74`<br>B `frontend/src/components/v1/V1Prototype.tsx:107`<br>B `frontend/src/components/v1/V1Prototype.tsx:147`<br>B `frontend/src/components/v1/V1Prototype.tsx:162` | **有消费** |
| 508 | `GET /api/v1/runs` | 1 | B `frontend/src/api/v1.ts:384` | **有消费** |
| 509 | `GET /api/v1/runs/{run_id}` | 1 | B `frontend/src/api/v1.ts:398` | **有消费** |
| 510 | `GET /api/v1/signals` | 2 | B `frontend/src/components/v1/panels/SignalPanel.tsx:35`<br>B `frontend/src/components/v1/panels/SignalPanel.tsx:95` | **有消费** |
| 511 | `GET /api/weekly-report` | 0 | — | **仅测试** |
| 512 | `POST /api/weekly-report/generate` | 0 | — | **仅文档** |
| 513 | `GET /api/weekly-report/latest` | 0 | — | **仅文档** |
| 514 | `POST /api/weekly-report/snapshot` | 0 | — | **零调用** |
| 515 | `GET /api/weekly-report/{week_start}` | 0 | — | **零调用** |
| 516 | `GET /api/wiki/graph` | 0 | — | **仅内部** |
| 517 | `GET /api/wiki/read` | 1 | A `frontend/src/components/reader/DeepReaderPage.tsx:303` | **有消费** |
| 518 | `POST /api/wiki/search` | 1 | A `frontend/src/components/search/UnifiedSearchPage.tsx:81` | **有消费** |
| 519 | `POST /api/wiki/trace` | 0 | — | **仅内部** |
| 520 | `POST /api/wiki/write` | 0 | — | **仅内部** |

---

## 4. Router 覆盖表 (100 个 `include_router` 调用)

**顶层注册 router (99 个模块, 由 `_registry_*.py` 的 `include_router` 直接挂载)** —— 这 99 个模块 
对应 100 次 `include_router` 调用 (`mcp_phase5_tools` 注册了 `kl_router` + `dsh_router` 两次):

| # | 后端模块 | 注册文件 | 端点数 | 前端有消费 | 前端零调用 |
|---:|---|---|---:|---:|---:|
| 1 | `action_api` | `_registry_extensions.py` | 6 | 6 | 0 |
| 2 | `agents_api` | `_registry_extensions.py` | 2 | 0 | 2 |
| 3 | `alert_api` | `_registry_flags.py` | 6 | 5 | 1 |
| 4 | `alerts` | `_registry_flags.py` | 11 | 0 | 11 |
| 5 | `annotations` | `_registry_core.py` | 5 | 4 | 1 |
| 6 | `artifact_api` | `_registry_extensions.py` | 6 | 6 | 0 |
| 7 | `attention_events_api` | `_registry_core.py` | 2 | 2 | 0 |
| 8 | `auto_intake_api` | `_registry_extensions.py` | 2 | 1 | 1 |
| 9 | `cache` | `_registry_core.py` | 2 | 1 | 1 |
| 10 | `catchup` | `_registry_flags.py` | 5 | 0 | 5 |
| 11 | `categories` | `_registry_core.py` | 1 | 0 | 1 |
| 12 | `codegarden` | `_registry_core.py` | 16 | 1 | 15 |
| 13 | `codegarden_ops` | `_registry_core.py` | 27 | 0 | 27 |
| 14 | `codegarden_phase14` | `_registry_flags.py` | 4 | 0 | 4 |
| 15 | `command_bar_api` | `_registry_extensions.py` | 2 | 2 | 0 |
| 16 | `compliance` | `_registry_core.py` | 3 | 3 | 0 |
| 17 | `content` | `_registry_core.py` | 12 | 8 | 4 |
| 18 | `content_preferences_api` | `_registry_core.py` | 2 | 2 | 0 |
| 19 | `cubox_import_api` | `_registry_extensions.py` | 2 | 0 | 2 |
| 20 | `cve_analytics` | `_registry_core.py` | 4 | 3 | 1 |
| 21 | `deep_read` | `_registry_core.py` | 3 | 1 | 2 |
| 22 | `digests` | `_registry_flags.py` | 7 | 4 | 3 |
| 23 | `dsh_api` | `_registry_extensions.py` | 3 | 1 | 2 |
| 24 | `dsh_control_api` | `_registry_extensions.py` | 5 | 5 | 0 |
| 25 | `event_technique_api` | `_registry_extensions.py` | 2 | 2 | 0 |
| 26 | `event_types_api` | `_registry_extensions.py` | 5 | 4 | 1 |
| 27 | `events` | `_registry_core.py` | 1 | 0 | 1 |
| 28 | `export` | `_registry_core.py` | 3 | 0 | 3 |
| 29 | `extract` | `_registry_flags.py` | 3 | 2 | 1 |
| 30 | `favorites` | `_registry_core.py` | 5 | 3 | 2 |
| 31 | `feedback_api` | `_registry_extensions.py` | 5 | 0 | 5 |
| 32 | `health` | `_registry_core.py` | 1 | 1 | 0 |
| 33 | `health_stats` | `_registry_core.py` | 1 | 1 | 0 |
| 34 | `history` | `_registry_core.py` | 5 | 3 | 2 |
| 35 | `hotspots` | `_registry_core.py` | 3 | 3 | 0 |
| 36 | `image` | `_registry_flags.py` | 2 | 0 | 2 |
| 37 | `info_filter_api` | `_registry_extensions.py` | 6 | 3 | 3 |
| 38 | `interest_api` | `_registry_extensions.py` | 7 | 7 | 0 |
| 39 | `judgment_api` | `_registry_extensions.py` | 4 | 3 | 1 |
| 40 | `kl_compounding_api` | `_registry_flags.py` | 1 | 1 | 0 |
| 41 | `kl_metrics_api` | `_registry_flags.py` | 4 | 0 | 4 |
| 42 | `kl_pipeline_api` | `_registry_extensions.py` | 15 | 2 | 13 |
| 43 | `kl_planning_api` | `_registry_flags.py` | 2 | 2 | 0 |
| 44 | `kl_rollback_api` | `_registry_flags.py` | 1 | 0 | 1 |
| 45 | `knowledge_api` | `_registry_extensions.py` | 1 | 1 | 0 |
| 46 | `knowledge_chunks_api` | `_registry_core.py` | 3 | 1 | 2 |
| 47 | `knowledge_classify_api` | `_registry_flags.py` | 2 | 0 | 2 |
| 48 | `knowledge_imported` | `_registry_flags.py` | 1 | 1 | 0 |
| 49 | `kpi_api` | `_registry_core.py` | 1 | 0 | 1 |
| 50 | `legacy_items_migrate_api` | `_registry_extensions.py` | 2 | 0 | 2 |
| 51 | `legacy_migrate_api` | `_registry_extensions.py` | 2 | 0 | 2 |
| 52 | `legacy_migrate_v1_api` | `_registry_extensions.py` | 5 | 0 | 5 |
| 53 | `llm_pool_api` | `_registry_flags.py` | 4 | 3 | 1 |
| 54 | `llm_status` | `_registry_flags.py` | 2 | 2 | 0 |
| 55 | `mcp` | `_registry_core.py` | 2 | 2 | 0 |
| 56 | `mcp_adapters` | `_registry_flags.py` | 4 | 0 | 4 |
| 57 | `mcp_agent_tools` | `_registry_flags.py` | 4 | 0 | 4 |
| 58 | `mcp_phase5_tools` | `_registry_flags.py` | 5 | 0 | 5 |
| 59 | `mcp_settings_api` | `_registry_core.py` | 2 | 2 | 0 |
| 60 | `mode` | `_registry_core.py` | 3 | 3 | 0 |
| 61 | `observability_audit_api` | `_registry_extensions.py` | 1 | 0 | 1 |
| 62 | `observability_router` | `_registry_flags.py` | 9 | 0 | 9 |
| 63 | `ops_runs_api` | `_registry_flags.py` | 1 | 1 | 0 |
| 64 | `proxy` | `_registry_core.py` | 4 | 4 | 0 |
| 65 | `quality` | `_registry_core.py` | 4 | 3 | 1 |
| 66 | `quality_api` | `_registry_extensions.py` | 1 | 1 | 0 |
| 67 | `quality_rejection_api` | `_registry_core.py` | 3 | 1 | 2 |
| 68 | `quality_rules_api` | `_registry_extensions.py` | 5 | 5 | 0 |
| 69 | `quality_rules_dry_run_api` | `_registry_flags.py` | 1 | 1 | 0 |
| 70 | `recommend` | `_registry_flags.py` | 1 | 1 | 0 |
| 71 | `refresh` | `_registry_core.py` | 1 | 1 | 0 |
| 72 | `reports` | `_registry_core.py` | 7 | 3 | 4 |
| 73 | `reviews` | `_registry_flags.py` | 5 | 4 | 1 |
| 74 | `reviews_manage` | `_registry_flags.py` | 6 | 6 | 0 |
| 75 | `run_api` | `_registry_extensions.py` | 2 | 2 | 0 |
| 76 | `run_ledger_api` | `_registry_extensions.py` | 9 | 5 | 4 |
| 77 | `search` | `_registry_flags.py` | 1 | 1 | 0 |
| 78 | `secnews_dashboard_api` | `_registry_extensions.py` | 4 | 4 | 0 |
| 79 | `security` | `_registry_core.py` | 11 | 2 | 9 |
| 80 | `settings` | `_registry_core.py` | 7 | 5 | 2 |
| 81 | `settings_flags_api` | `_registry_core.py` | 2 | 2 | 0 |
| 82 | `skill_builder_api` | `_registry_extensions.py` | 6 | 2 | 4 |
| 83 | `skill_registry_api` | `_registry_extensions.py` | 5 | 3 | 2 |
| 84 | `skill_registry_runs_api` | `_registry_extensions.py` | 3 | 2 | 1 |
| 85 | `skill_registry_v1_api` | `_registry_extensions.py` | 2 | 2 | 0 |
| 86 | `skills` | `_registry_core.py` | 5 | 4 | 1 |
| 87 | `sync` | `_registry_core.py` | 13 | 12 | 1 |
| 88 | `tags` | `_registry_core.py` | 5 | 4 | 1 |
| 89 | `tech_stack` | `_registry_flags.py` | 6 | 0 | 6 |
| 90 | `trends` | `_registry_core.py` | 1 | 0 | 1 |
| 91 | `trigger_webhook_api` | `_registry_extensions.py` | 2 | 0 | 2 |
| 92 | `v1_signals_api` | `_registry_extensions.py` | 1 | 1 | 0 |
| 93 | `weekly_report` | `_registry_core.py` | 5 | 0 | 5 |
| 94 | `wiki_tools` | `_registry_flags.py` | 5 | 2 | 3 |

**嵌套 router (29 个模块, 由父 router 的 `router.include_router(...)` 挂载)** —— 
它们**不**占 `count_routers()` 的计数, 但端点同样对外可达, 必须一并纳入依赖图:

| # | 后端模块 | 父 router | 端点数 | 前端有消费 | 前端零调用 |
|---:|---|---|---:|---:|---:|
| 1 | `knowledge_concepts` | `knowledge` | 5 | 4 | 1 |
| 2 | `knowledge_import` | `knowledge` | 7 | 5 | 2 |
| 3 | `knowledge_items` | `knowledge` | 6 | 4 | 2 |
| 4 | `knowledge_obsidian` | `knowledge` | 5 | 0 | 5 |
| 5 | `knowledge_ops` | `knowledge` | 5 | 4 | 1 |
| 6 | `knowledge_plans` | `knowledge` | 11 | 3 | 8 |
| 7 | `knowledge_skills` | `knowledge` | 6 | 3 | 3 |
| 8 | `maintenance_db_api` | `maintenance` | 9 | 8 | 1 |
| 9 | `maintenance_retention_api` | `maintenance` | 5 | 5 | 0 |
| 10 | `observability_metrics_api` | `observability_router` | 7 | 4 | 3 |
| 11 | `secrets_keys_api` | `secrets` | 4 | 4 | 0 |
| 12 | `secrets_lifecycle_api` | `secrets` | 5 | 4 | 1 |
| 13 | `secrets_oauth_api` | `secrets` | 2 | 2 | 0 |
| 14 | `secrets_reset_api` | `secrets` | 1 | 0 | 1 |
| 15 | `secrets_reveal_api` | `secrets` | 2 | 2 | 0 |
| 16 | `secrets_rotation_api` | `secrets` | 4 | 2 | 2 |
| 17 | `source_custom_api` | `sources` | 4 | 4 | 0 |
| 18 | `source_health_api` | `sources` | 4 | 4 | 0 |
| 19 | `source_probe_api` | `sources` | 1 | 1 | 0 |
| 20 | `source_stats_api` | `sources` | 4 | 4 | 0 |
| 21 | `source_system_api` | `sources` | 3 | 0 | 3 |
| 22 | `source_trend_api` | `sources` | 2 | 2 | 0 |
| 23 | `v1_case_query_api` | `case_api` | 2 | 1 | 1 |
| 24 | `v1_case_relation_api` | `case_api` | 1 | 1 | 0 |
| 25 | `v1_case_update_api` | `case_api` | 1 | 1 | 0 |
| 26 | `v1_case_write_api` | `case_api` | 2 | 2 | 0 |
| 27 | `v1_knowledge_query_api` | `knowledge_api` | 3 | 3 | 0 |
| 28 | `v1_knowledge_reuse_api` | `knowledge_api` | 4 | 4 | 0 |
| 29 | `v1_knowledge_write_api` | `knowledge_api` | 4 | 4 | 0 |

合计 **94 顶层 + 29 嵌套 = 123 个后端模块**, 承载 **520 个端点**; 
顶层对应 100 次 `include_router` 调用 (差 1 = `mcp_phase5_tools` 注册两次)。**验收标准①「router 全覆盖」达成。**

---

## 5. 已知 3 例误报复盘 (PRD §4.9 技术约束指定)

起草期只做**路径 A** (直接 fetch) 扫描, 漏掉**路径 B** (`frontend/src/api/*.ts` 封装层) 与 `getJSON/postJSON` 形态, 
导致 3 个**实际有消费**的端点被误判为「零调用 → 孤儿」。逐例复盘如下。

### 5.1 `/api/search` — 封装层 + 查询串拼接 双重遮蔽

| 项 | 内容 |
|---|---|
| 误判原因 | ① 实际调用走 `getJSON<T>()` (封装在 `frontend/src/lib/api.ts`), 不是裸 `fetch(` → 路径 A 的正则 `fetch\('/api/` **零命中**; ② URL 形如 `` `/api/search?q=${encodeURIComponent(trimmed)}&limit=50` `` —— 模板串 + 查询串, 简单字面量比对也对不上 |
| 真实调用点 | **2 个** (均路径 A·封装函数): `frontend/src/components/sentinel/review/ReviewOverlay.tsx:389` (`getJSON('/api/search?q=…&sources=hotspot,knowledge&limit=10')`)、`frontend/src/components/search/UnifiedSearchPage.tsx:78` (`getJSON('/api/search?q=…&limit=50')`) |
| 修正方法 | 调用形态白名单扩为 `fetch / apiFetch / getJSON / postJSON` 四形态; 模板串归一化时**先剥查询串**再比对路径段 |

### 5.2 `/api/commands` — 只查组件内 fetch, 漏了 `api/commands.ts` 封装层

| 项 | 内容 |
|---|---|
| 误判原因 | `POST /api/commands` 的 URL 字面量只存在于 `frontend/src/api/commands.ts:43` (`postJSON('/api/commands', { text })`) —— 组件里**没有** `/api/commands` 字面量。路径 A 扫描组件 → 零命中 → 误判孤儿 |
| 真实调用点 | **1 个** (路径 B): `frontend/src/components/sentinel/CommandBar.tsx:115` 调用封装函数 `runCommand(text)` → 封装层 `frontend/src/api/commands.ts:43` → `POST /api/commands` |
| 附带发现 | 同族 `GET /api/commands` (`listCommands`, `api/commands.ts:47`) **封装层有、组件无** —— 这不是误报, 而是**真的无人调用**的封装函数 (见 §6 孤儿封装函数清单) |
| 修正方法 | 增加路径 B: 解析 `api/*.ts` 的导出函数 → 反查 `import { fn } from '…/api/xxx'` 且调用 `fn(...)` 的组件 |

### 5.3 `/api/v1/signals` — 同 5.2, 封装层在 `api/v1.ts`

| 项 | 内容 |
|---|---|
| 误判原因 | URL 字面量只存在于 `frontend/src/api/v1.ts:701` (`` getJSON(`/api/v1/signals${buildQuery(q)}`) ``) —— 组件 `SignalPanel.tsx` 里**没有** `/api/v1/signals` 字面量, 只有 `listSignals({...})` |
| 真实调用点 | **2 个** (路径 B): `frontend/src/components/v1/panels/SignalPanel.tsx:35` (`listSignals({subject_id, days:30, limit:20})`, Subject 抽屉下钻) 与 `:95` (`listSignals({days, limit})`, 资讯右栏 Signal 摘要) |
| 修正方法 | 同 5.2 (路径 B 反查); 另需支持 `buildQuery(q)` 这类**查询串构造函数**的模板串 —— 归一化时把 `${buildQuery(...)}` 判为查询串并丢弃, 只留路径段 |

> **统一修正规则 (已落进本次采集脚本)**: ① 调用形态四件套; ② 模板串按「动态段 → `{p}` / 查询串 → 丢弃」二分处理; 
> ③ 双路径各自的命中都要计入调用点数, 并在表中标注 A / B 来源; ④ 封装层**有**而组件**无**的封装函数单独列孤儿清单, 
> 不与「端点零调用」混为一谈 (前者是前端死代码, 后者是后端候选)。

---

## 6. 零调用端点候选清单 (含四项检查表)

共 **244** 个前端调用点数 = 0 的端点。下表逐项给出 (a)(b)(c)(d) 四项检查结论与证据。

**裁决建议图例**:

- 🔴 **P1 删除候选** — 四项全未命中, 无任何消费方 → 建议 P1 裁决「删除」或「保留并登记豁免」;
- 🟡 **待人工确认** — 命中 (c) 仅测试 (测试自身即消费方) 或仅 (d) 文档 → 需产品判断「测试是否有业务含义」;
- 🟢 **勿动** — 命中 (a)/(b), 有 MCP / 命令栏 / 内部服务 / 后端自调用消费 → 保留。

| # | 端点 | (a) MCP/命令栏/服务 | (b) 后端自调用 | (c) 仅测试 | (d) 运维/文档 | 证据摘要 | 裁决建议 |
|---:|---|---|---|---|---|---|---|
| 1 | `GET /api/agents/available` | 命中 | 命中 | 命中 | 命中 | backend/services/skill_registry/builtin.py:/api/agents/available (L174) | 🟢 勿动 (有内部消费) |
| 2 | `POST /api/agents/run` | 未命中 | 未命中 | 未命中 | 命中 | docs/Observability_PRD_v1.0.md:/api/agents/run (L50); docs/superpowers/specs/2026-09-22-settings-refactor-design.md:/api/agents/run (L15); README.md:/api/agents/run (L195) | 🟡 待确认 (仅文档提及) |
| 3 | `GET /api/alerts` | 命中 | 命中 | 命中 | 命中 | backend/services/alert_service.py:/api/alerts (L273) | 🟢 勿动 (有内部消费) |
| 4 | `POST /api/alerts/evaluate/{hotspot_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/evaluate (L113); backend/tests/test_alerts_api.py:/api/alerts/evaluate (L7) | 🟡 待确认 (仅测试引用) |
| 5 | `GET /api/alerts/rules` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/rules (L111); backend/tests/test_mcp_write_tools.py:/api/alerts/rules (L10); backend/tests/test_alerts_api.py:/api/alerts/rules (L4) | 🟡 待确认 (仅测试+文档) |
| 6 | `POST /api/alerts/rules` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/rules (L111); backend/tests/test_mcp_write_tools.py:/api/alerts/rules (L10); backend/tests/test_alerts_api.py:/api/alerts/rules (L4) | 🟡 待确认 (仅测试+文档) |
| 7 | `DELETE /api/alerts/rules/{rule_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/rules (L111); backend/tests/test_mcp_write_tools.py:/api/alerts/rules (L10); backend/tests/test_alerts_api.py:/api/alerts/rules (L4) | 🟡 待确认 (仅测试+文档) |
| 8 | `GET /api/alerts/rules/{rule_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/rules (L111); backend/tests/test_mcp_write_tools.py:/api/alerts/rules (L10); backend/tests/test_alerts_api.py:/api/alerts/rules (L4) | 🟡 待确认 (仅测试+文档) |
| 9 | `PUT /api/alerts/rules/{rule_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase3_acceptance.py:/api/alerts/rules (L111); backend/tests/test_mcp_write_tools.py:/api/alerts/rules (L10); backend/tests/test_alerts_api.py:/api/alerts/rules (L4) | 🟡 待确认 (仅测试+文档) |
| 10 | `POST /api/alerts/v2/evaluate` | 未命中 | 未命中 | 未命中 | 命中 | docs/superpowers/plans/2026-09-27-news-alerts-p1.md:/api/alerts/v2/evaluate (L1099) | 🟡 待确认 (仅文档提及) |
| 11 | `DELETE /api/alerts/{alert_id}` | 未命中 | 命中 | 未命中 | 未命中 | backend/api/_registry_flags.py:/api/alerts/{alert_id} (L57) | 🟢 勿动 (有内部消费) |
| 12 | `GET /api/alerts/{alert_id}` | 未命中 | 命中 | 未命中 | 未命中 | backend/api/_registry_flags.py:/api/alerts/{alert_id} (L57) | 🟢 勿动 (有内部消费) |
| 13 | `PUT /api/alerts/{alert_id}/dismiss` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 14 | `PUT /api/alerts/{alert_id}/read` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 15 | `GET /api/annotations/{annotation_id}` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_types.py:/api/annotations (L112) | 🟢 勿动 (有内部消费) |
| 16 | `GET /api/cache/stats` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 17 | `POST /api/catchup/abort` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_catchup_api.py:/api/catchup/abort (L9) | 🟡 待确认 (仅测试引用) |
| 18 | `POST /api/catchup/auto` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_catchup_api.py:/api/catchup/auto (L12) | 🟡 待确认 (仅测试引用) |
| 19 | `POST /api/catchup/run` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_catchup_api.py:/api/catchup/run (L4) | 🟡 待确认 (仅测试+文档) |
| 20 | `GET /api/catchup/runs/{run_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_catchup_api.py:/api/catchup/runs/{run_id} (L13) | 🟡 待确认 (仅测试引用) |
| 21 | `GET /api/catchup/status` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_catchup_api.py:/api/catchup/status (L8); backend/tests/test_feature_gates.py:/api/catchup/status (L51) | 🟡 待确认 (仅测试+文档) |
| 22 | `GET /api/categories` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/categories (L34); backend/tests/test_api.py:/api/categories (L7) | 🟡 待确认 (仅测试+文档) |
| 23 | `GET /api/codegarden/candidates` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_api.py:/api/codegarden/candidates (L285); backend/tests/test_codegarden_e2e.py:/api/codegarden/candidates (L4) | 🟡 待确认 (仅测试引用) |
| 24 | `GET /api/codegarden/dependencies` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/dependencies (L255); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/dependencies (L123); frontend/src/components/sentinel/SentinelGardenPage.test.tsx:/api/codegarden/dependencies (L75) | 🟡 待确认 (仅测试+文档) |
| 25 | `POST /api/codegarden/dependencies` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/dependencies (L255); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/dependencies (L123); frontend/src/components/sentinel/SentinelGardenPage.test.tsx:/api/codegarden/dependencies (L75) | 🟡 待确认 (仅测试+文档) |
| 26 | `GET /api/codegarden/dependencies/impact` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/dependencies/impact (L332); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/dependencies/impact (L159) | 🟡 待确认 (仅测试引用) |
| 27 | `DELETE /api/codegarden/dependencies/{dep_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 28 | `POST /api/codegarden/drift/assess` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_drift.py:/api/codegarden/drift/assess (L8) | 🟡 待确认 (仅测试+文档) |
| 29 | `GET /api/codegarden/drift/assessments` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_feature_gates.py:/api/codegarden/drift/assessments (L62) | 🟡 待确认 (仅测试引用) |
| 30 | `PUT /api/codegarden/drift/assessments/{assessment_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_feature_gates.py:/api/codegarden/drift/assessments (L62) | 🟡 待确认 (仅测试引用) |
| 31 | `GET /api/codegarden/events` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/events (L344); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/events (L137); frontend/src/components/sentinel/SentinelGardenPage.test.tsx:/api/codegarden/events (L74) | 🟡 待确认 (仅测试+文档) |
| 32 | `POST /api/codegarden/events` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/events (L344); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/events (L137); frontend/src/components/sentinel/SentinelGardenPage.test.tsx:/api/codegarden/events (L74) | 🟡 待确认 (仅测试+文档) |
| 33 | `POST /api/codegarden/from-knowledge` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_api.py:/api/codegarden/from-knowledge (L292); backend/tests/test_codegarden_e2e.py:/api/codegarden/from-knowledge (L5) | 🟡 待确认 (仅测试+文档) |
| 34 | `POST /api/codegarden/github/import` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_api.py:/api/codegarden/github/import (L231) | 🟡 待确认 (仅测试+文档) |
| 35 | `GET /api/codegarden/playbooks` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/playbooks (L380); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/playbooks (L245); frontend/src/components/codegarden/DependencyGraph.test.tsx:/api/codegarden/playbooks (L47) | 🟡 待确认 (仅测试引用) |
| 36 | `POST /api/codegarden/playbooks/{name}/run` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 37 | `GET /api/codegarden/projects` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_api.py:/api/codegarden/projects (L116); backend/tests/test_codegarden_e2e.py:/api/codegarden/projects (L8); backend/tests/test_feature_gates.py:/api/codegarden/projects (L58) | 🟡 待确认 (仅测试+文档) |
| 38 | `POST /api/codegarden/projects` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_api.py:/api/codegarden/projects (L116); backend/tests/test_codegarden_e2e.py:/api/codegarden/projects (L8); backend/tests/test_feature_gates.py:/api/codegarden/projects (L58) | 🟡 待确认 (仅测试+文档) |
| 39 | `DELETE /api/codegarden/projects/{project_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 40 | `GET /api/codegarden/projects/{project_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 41 | `PATCH /api/codegarden/projects/{project_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 42 | `GET /api/codegarden/projects/{project_id}/activities` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 43 | `POST /api/codegarden/projects/{project_id}/archive` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 44 | `POST /api/codegarden/projects/{project_id}/lifecycle` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 45 | `POST /api/codegarden/projects/{project_id}/restore` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 46 | `POST /api/codegarden/projects/{project_id}/sync` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 47 | `GET /api/codegarden/projects/{project_id}/timeline` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 48 | `GET /api/codegarden/projects/{project_id}/upstream` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 49 | `GET /api/codegarden/resources` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources (L193); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/resources (L109); frontend/src/components/codegarden/ResourceHub.test.tsx:/api/codegarden/resources (L42) | 🟡 待确认 (仅测试+文档) |
| 50 | `POST /api/codegarden/resources` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources (L193); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/resources (L109); frontend/src/components/codegarden/ResourceHub.test.tsx:/api/codegarden/resources (L42) | 🟡 待确认 (仅测试+文档) |
| 51 | `POST /api/codegarden/resources/allocate-port` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources/allocate-port (L222); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/resources/allocate-port (L109) | 🟡 待确认 (仅测试引用) |
| 52 | `GET /api/codegarden/resources/env-templates` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources/env-templates (L466) | 🟡 待确认 (仅测试+文档) |
| 53 | `POST /api/codegarden/resources/env-templates` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources/env-templates (L466) | 🟡 待确认 (仅测试+文档) |
| 54 | `GET /api/codegarden/resources/env-templates/{resource_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources/env-templates (L466) | 🟡 待确认 (仅测试+文档) |
| 55 | `POST /api/codegarden/resources/release-port` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/resources/release-port (L240); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/resources/release-port (L191) | 🟡 待确认 (仅测试引用) |
| 56 | `DELETE /api/codegarden/resources/{resource_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 57 | `GET /api/codegarden/resources/{resource_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 58 | `GET /api/codegarden/services` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/codegarden/services (L61); backend/tests/test_codegarden_ops_api.py:/api/codegarden/services (L91); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services (L95) | 🟡 待确认 (仅测试+文档) |
| 59 | `POST /api/codegarden/services` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/codegarden/services (L61); backend/tests/test_codegarden_ops_api.py:/api/codegarden/services (L91); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services (L95) | 🟡 待确认 (仅测试+文档) |
| 60 | `POST /api/codegarden/services/scan` | 未命中 | 未命中 | 命中 | 未命中 | frontend/src/components/codegarden/ServiceMesh.test.tsx:/api/codegarden/services/scan (L152) | 🟡 待确认 (仅测试引用) |
| 61 | `GET /api/codegarden/services/topology` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_codegarden_ops_api.py:/api/codegarden/services/topology (L158); backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services/topology (L224); frontend/src/components/sentinel/SentinelGardenPage.test.tsx:/api/codegarden/services/topology (L72) | 🟡 待确认 (仅测试+文档) |
| 62 | `DELETE /api/codegarden/services/{service_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services/{service_id} (L153) | 🟡 待确认 (仅测试引用) |
| 63 | `GET /api/codegarden/services/{service_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services/{service_id} (L153) | 🟡 待确认 (仅测试引用) |
| 64 | `PATCH /api/codegarden/services/{service_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_codegarden_ops_e2e.py:/api/codegarden/services/{service_id} (L153) | 🟡 待确认 (仅测试引用) |
| 65 | `GET /api/codegarden/services/{service_id}/logs` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 66 | `GET /api/codegarden/services/{service_id}/metrics` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 67 | `POST /api/codegarden/services/{service_id}/restart` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 68 | `POST /api/content/calendar` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/content/calendar (L36) | 🟡 待确认 (仅测试+文档) |
| 69 | `PATCH /api/content/calendar/{entry_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/content/calendar (L36) | 🟡 待确认 (仅测试+文档) |
| 70 | `PATCH /api/content/drafts/{draft_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 71 | `GET /api/content/templates` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/content/templates (L471) | 🟡 待确认 (仅文档提及) |
| 72 | `POST /api/cubox/sync` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_adapters.py:/api/cubox/sync (L71) | 🟢 勿动 (有内部消费) |
| 73 | `POST /api/cve/attack-data/load` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_cve_compliance_routes.py:/api/cve/attack-data/load (L19) | 🟡 待确认 (仅测试+文档) |
| 74 | `POST /api/cve/sync` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/cve/sync (L63); backend/tests/test_cve_knowledge_sync.py:/api/cve/sync (L8) | 🟡 待确认 (仅测试+文档) |
| 75 | `GET /api/deep-read/recent` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 76 | `GET /api/deep-read/{entity_type}/{entity_id}` | 未命中 | 未命中 | 未命中 | 命中 | docs/CHANGELOG.md:/api/deep-read/{entity_type}/{entity_id} (L1066); docs/progress-archive/v0.5-execution.md:/api/deep-read/{entity_type}/{entity_id} (L145) | 🟡 待确认 (仅文档提及) |
| 77 | `GET /api/digests` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_phase4_acceptance.py:/api/digests (L310); backend/tests/test_mcp_write_tools.py:/api/digests (L11); backend/tests/test_digests_priority_api.py:/api/digests (L1) | 🟡 待确认 (仅测试+文档) |
| 78 | `DELETE /api/digests/{digest_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 79 | `GET /api/digests/{digest_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 80 | `GET /api/dsh/health` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_dsh_api.py:/api/dsh/health (L4); backend/tests/test_feature_gates.py:/api/dsh/health (L78) | 🟡 待确认 (仅测试+文档) |
| 81 | `POST /api/dsh/legacy/items/migrate/run` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_legacy_items_migrate_service.py:/api/dsh/legacy/items/migrate/run (L184) | 🟡 待确认 (仅测试+文档) |
| 82 | `GET /api/dsh/legacy/items/migrate/status` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_legacy_items_migrate_service.py:/api/dsh/legacy/items/migrate/status (L201) | 🟡 待确认 (仅测试引用) |
| 83 | `POST /api/dsh/legacy/migrate/run` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_t17_e2e_audit_sse.py:/api/dsh/legacy/migrate/run (L69) | 🟡 待确认 (仅测试+文档) |
| 84 | `GET /api/dsh/legacy/migrate/status` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_t17_e2e_audit_sse.py:/api/dsh/legacy/migrate/status (L79) | 🟡 待确认 (仅测试+文档) |
| 85 | `GET /api/dsh/legacy/migrate/v1/mapping` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_c13_legacy_migrate_v1_api.py:/api/dsh/legacy/migrate/v1/mapping (L162) | 🟡 待确认 (仅测试+文档) |
| 86 | `POST /api/dsh/legacy/migrate/v1/promote` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_c13_legacy_migrate_v1_api.py:/api/dsh/legacy/migrate/v1/promote (L173) | 🟡 待确认 (仅测试+文档) |
| 87 | `GET /api/dsh/legacy/migrate/v1/promote/log` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_c13_legacy_migrate_v1_api.py:/api/dsh/legacy/migrate/v1/promote/log (L183) | 🟡 待确认 (仅测试+文档) |
| 88 | `POST /api/dsh/legacy/migrate/v1/run` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_c13_legacy_migrate_v1_api.py:/api/dsh/legacy/migrate/v1/run (L108) | 🟡 待确认 (仅测试+文档) |
| 89 | `GET /api/dsh/legacy/migrate/v1/status` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_c13_legacy_migrate_v1_api.py:/api/dsh/legacy/migrate/v1/status (L141) | 🟡 待确认 (仅测试+文档) |
| 90 | `GET /api/dsh/session/{session_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_dsh_api.py:/api/dsh/session (L6) | 🟡 待确认 (仅测试+文档) |
| 91 | `GET /api/event-technique/event-types/{event_type_id}/techniques` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 92 | `GET /api/events` | 未命中 | 命中 | 命中 | 命中 | backend/main.py:/api/events (L281) | 🟢 勿动 (有内部消费) |
| 93 | `GET /api/export` | 命中 | 命中 | 命中 | 命中 | backend/services/export_service.py:/api/export (L54) | 🟢 勿动 (有内部消费) |
| 94 | `POST /api/export/rebuild` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 95 | `GET /api/export/xlsx` | 未命中 | 未命中 | 命中 | 命中 | frontend/src/components/settings/ExportActionsCard.test.tsx:/api/export/xlsx (L11) | 🟡 待确认 (仅测试+文档) |
| 96 | `POST /api/extract/auto` | 命中 | 未命中 | 未命中 | 命中 | backend/api/mcp_adapters.py:/api/extract/auto (L109) | 🟢 勿动 (有内部消费) |
| 97 | `POST /api/extract/preview` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_extract_api.py:/api/extract/preview (L4) | 🟡 待确认 (仅测试引用) |
| 98 | `POST /api/favorites/by-hotspot` | 命中 | 未命中 | 未命中 | 未命中 | backend/api/mcp_adapters.py:/api/favorites/by-hotspot (L163) | 🟢 勿动 (有内部消费) |
| 99 | `GET /api/favorites/count` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_favorites.py:/api/favorites/count (L392) | 🟡 待确认 (仅测试+文档) |
| 100 | `GET /api/favorites/export` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_favorites.py:/api/favorites/export (L423) | 🟡 待确认 (仅测试+文档) |
| 101 | `POST /api/feedback/` | 未命中 | 命中 | 命中 | 未命中 | backend/extensions/__init__.py:/api/feedback/ (L87) | 🟢 勿动 (有内部消费) |
| 102 | `GET /api/feedback/entity/{entity_type}/{entity_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_feedback_api.py:/api/feedback/entity (L8) | 🟡 待确认 (仅测试引用) |
| 103 | `GET /api/feedback/history` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_feedback_api.py:/api/feedback/history (L6) | 🟡 待确认 (仅测试引用) |
| 104 | `GET /api/feedback/profile` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/feedback/profile (L75); backend/tests/test_feedback_api.py:/api/feedback/profile (L5) | 🟡 待确认 (仅测试+文档) |
| 105 | `GET /api/feedback/role-summary` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_feedback_api.py:/api/feedback/role-summary (L7) | 🟡 待确认 (仅测试引用) |
| 106 | `POST /api/history/archive` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/history/archive (L487) | 🟡 待确认 (仅文档提及) |
| 107 | `GET /api/history/batches/{batch_no}/range` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_history_api.py:/api/history/batches/{batch_no}/range (L17) | 🟡 待确认 (仅测试引用) |
| 108 | `POST /api/image/generate` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_image_api.py:/api/image/generate (L56) | 🟡 待确认 (仅测试+文档) |
| 109 | `POST /api/image/understand` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_image_api.py:/api/image/understand (L119) | 🟡 待确认 (仅测试+文档) |
| 110 | `GET /api/info-filter/gate` | 未命中 | 未命中 | 命中 | 未命中 | frontend/src/components/secnews/settings/InfoFilterCard.test.tsx:/api/info-filter/gate (L5) | 🟡 待确认 (仅测试引用) |
| 111 | `POST /api/info-filter/preview` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_info_filter_api.py:/api/info-filter/preview (L190); frontend/src/components/secnews/settings/InfoFilterCard.test.tsx:/api/info-filter/preview (L231) | 🟡 待确认 (仅测试引用) |
| 112 | `POST /api/info-filter/rules` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_info_filter_api.py:/api/info-filter/rules (L81); frontend/src/components/quality/QualityDashboardPage.test.tsx:/api/info-filter/rules (L18); frontend/src/components/secnews/settings/InfoFilterCard.test.tsx:/api/info-filter/rules (L77) | 🟡 待确认 (仅测试+文档) |
| 113 | `GET /api/kl/concepts` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/concepts (L234); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/concepts (L232) | 🟡 待确认 (仅文档提及) |
| 114 | `GET /api/kl/graph` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/graph (L235); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/graph (L233) | 🟡 待确认 (仅文档提及) |
| 115 | `GET /api/kl/health` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_kl_metrics.py:/api/kl/health (L173) | 🟡 待确认 (仅测试引用) |
| 116 | `POST /api/kl/import/bookmarks` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/import/bookmarks (L226); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/import/bookmarks (L224) | 🟡 待确认 (仅文档提及) |
| 117 | `GET /api/kl/inbox/list` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 118 | `POST /api/kl/inbox/scan` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/inbox/scan (L227); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/inbox/scan (L225) | 🟡 待确认 (仅文档提及) |
| 119 | `GET /api/kl/items/{item_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_kl_path_traversal.py:/api/kl/items/{item_id} (L4) | 🟡 待确认 (仅测试+文档) |
| 120 | `PUT /api/kl/items/{item_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_kl_path_traversal.py:/api/kl/items/{item_id} (L4) | 🟡 待确认 (仅测试+文档) |
| 121 | `GET /api/kl/liveness` | 未命中 | 未命中 | 未命中 | 命中 | docs/progress-archive/v0.5-execution.md:/api/kl/liveness (L110); docs/progress-archive/v0.6-records.md:/api/kl/liveness (L523) | 🟡 待确认 (仅文档提及) |
| 122 | `POST /api/kl/liveness/sweep` | 未命中 | 未命中 | 未命中 | 命中 | docs/progress-archive/v0.5-execution.md:/api/kl/liveness/sweep (L110); docs/progress-archive/v0.6-records.md:/api/kl/liveness/sweep (L523) | 🟡 待确认 (仅文档提及) |
| 123 | `GET /api/kl/metrics` | 未命中 | 命中 | 命中 | 命中 | backend/api/_registry_flags.py:/api/kl/metrics (L27) | 🟢 勿动 (有内部消费) |
| 124 | `GET /api/kl/metrics/counters` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_kl_metrics.py:/api/kl/metrics/counters (L166) | 🟡 待确认 (仅测试引用) |
| 125 | `GET /api/kl/metrics/stage-counts` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 126 | `POST /api/kl/pipeline/advance` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/pipeline/advance (L230); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/pipeline/advance (L228) | 🟡 待确认 (仅文档提及) |
| 127 | `POST /api/kl/pipeline/drain` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/pipeline/drain (L229); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/pipeline/drain (L227) | 🟡 待确认 (仅文档提及) |
| 128 | `POST /api/kl/pipeline/retry` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/SECNEWS_INTEGRATION_TASKS.md:/api/kl/pipeline/retry (L231); docs/archived/2026-09-09-sweep/HOTSPOT_SECNEWS_INTEGRATION.md:/api/kl/pipeline/retry (L229) | 🟡 待确认 (仅文档提及) |
| 129 | `GET /api/kl/quarantine/list` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 130 | `POST /api/kl/rollback/{item_id}` | 未命中 | 命中 | 命中 | 命中 | backend/api/_registry_flags.py:/api/kl/rollback (L28) | 🟢 勿动 (有内部消费) |
| 131 | `POST /api/knowledge/bookmarks/import` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-15-v1.4-phase-1b-checklist.md:/api/knowledge/bookmarks/import (L18); docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-15-v1.4-phase-1b-spec.md:/api/knowledge/bookmarks/import (L64) | 🟡 待确认 (仅文档提及) |
| 132 | `POST /api/knowledge/chunks/generate/{item_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_chunks_api.py:/api/knowledge/chunks/generate/{item_id} (L149) | 🟡 待确认 (仅测试引用) |
| 133 | `GET /api/knowledge/chunks/search` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_chunks_api.py:/api/knowledge/chunks/search (L7) | 🟡 待确认 (仅测试+文档) |
| 134 | `POST /api/knowledge/classify/batch` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 135 | `GET /api/knowledge/classify/stats` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 136 | `POST /api/knowledge/concepts/link/batch` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 137 | `POST /api/knowledge/cubox/import-cards` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_cubox_import.py:/api/knowledge/cubox/import-cards (L9); frontend/src/components/knowledge/KnowledgeImport.test.tsx:/api/knowledge/cubox/import-cards (L17) | 🟡 待确认 (仅测试引用) |
| 138 | `POST /api/knowledge/cubox/import-dir` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_cubox_import.py:/api/knowledge/cubox/import-dir (L208); frontend/src/components/knowledge/KnowledgeImport.test.tsx:/api/knowledge/cubox/import-dir (L23) | 🟡 待确认 (仅测试+文档) |
| 139 | `GET /api/knowledge/items/{item_id}` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_types.py:/api/knowledge/items/{item_id} (L120) | 🟢 勿动 (有内部消费) |
| 140 | `GET /api/knowledge/obsidian/conflicts` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 141 | `POST /api/knowledge/obsidian/open` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 142 | `POST /api/knowledge/obsidian/watchdog/start` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 143 | `GET /api/knowledge/obsidian/watchdog/status` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 144 | `POST /api/knowledge/obsidian/watchdog/stop` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 145 | `POST /api/knowledge/plans` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/knowledge/plans (L449) | 🟡 待确认 (仅文档提及) |
| 146 | `GET /api/knowledge/plans/{week}` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/knowledge/plans/{week} (L450) | 🟡 待确认 (仅文档提及) |
| 147 | `PATCH /api/knowledge/plans/{week}` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/knowledge/plans/{week} (L450) | 🟡 待确认 (仅文档提及) |
| 148 | `POST /api/knowledge/progress/sync` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 149 | `GET /api/knowledge/progress/{concept_slug}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 150 | `PATCH /api/knowledge/progress/{concept_slug}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 151 | `POST /api/knowledge/projection/rebuild` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 152 | `GET /api/knowledge/search` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_knowledge_api_contract.py:/api/knowledge/search (L184) | 🟡 待确认 (仅测试引用) |
| 153 | `POST /api/knowledge/skills` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_knowledge_api_contract.py:/api/knowledge/skills (L237) | 🟡 待确认 (仅测试+文档) |
| 154 | `POST /api/knowledge/skills/seed` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 155 | `DELETE /api/knowledge/skills/{skill_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 156 | `GET /api/knowledge/summaries` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/hotspot_v1.7_PRD.md:/api/knowledge/summaries (L2318) | 🟡 待确认 (仅文档提及) |
| 157 | `POST /api/knowledge/summaries/weekly` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 158 | `POST /api/knowledge/sync` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/superpowers/plans/2026-07-14-v1.4-phase-1a-knowledge-foundation.md:/api/knowledge/sync (L1615); docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-15-v1.4-phase-1b-checklist.md:/api/knowledge/sync (L230); docs/archived/2026-09-09-sweep/superpowers/specs/2026-07-14-v1.4-knowledge-dashboard-design.md:/api/knowledge/sync (L454) | 🟡 待确认 (仅文档提及) |
| 159 | `POST /api/llm/pool/detect` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 160 | `GET /api/maintenance/orphans` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 161 | `POST /api/mcp/dsh/analyze` | 命中 | 命中 | 未命中 | 未命中 | backend/api/mcp_types.py:/api/mcp/dsh/analyze (L195) | 🟢 勿动 (有内部消费) |
| 162 | `GET /api/mcp/dsh/session/{session_id}` | 命中 | 命中 | 未命中 | 未命中 | backend/api/mcp_types.py:/api/mcp/dsh/session/{session_id} (L203) | 🟢 勿动 (有内部消费) |
| 163 | `POST /api/mcp/kl/enqueue` | 命中 | 命中 | 未命中 | 未命中 | backend/api/mcp_types.py:/api/mcp/kl/enqueue (L171) | 🟢 勿动 (有内部消费) |
| 164 | `POST /api/mcp/kl/retry` | 命中 | 命中 | 未命中 | 未命中 | backend/api/mcp_types.py:/api/mcp/kl/retry (L187) | 🟢 勿动 (有内部消费) |
| 165 | `GET /api/mcp/kl/status` | 命中 | 命中 | 未命中 | 未命中 | backend/api/mcp_types.py:/api/mcp/kl/status (L179) | 🟢 勿动 (有内部消费) |
| 166 | `POST /api/mcp/phase8/enrich-concept` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_mcp_agent_tools.py:/api/mcp/phase8/enrich-concept (L110) | 🟡 待确认 (仅测试引用) |
| 167 | `POST /api/mcp/phase8/link-items` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_mcp_agent_tools.py:/api/mcp/phase8/link-items (L142) | 🟡 待确认 (仅测试引用) |
| 168 | `POST /api/mcp/phase8/score-item` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_mcp_agent_tools.py:/api/mcp/phase8/score-item (L73) | 🟡 待确认 (仅测试引用) |
| 169 | `POST /api/mcp/phase8/trigger-codegarden-drift` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_mcp_agent_tools.py:/api/mcp/phase8/trigger-codegarden-drift (L179) | 🟡 待确认 (仅测试引用) |
| 170 | `GET /api/observability/audit` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_interest_engine.py:/api/observability/audit (L234); backend/tests/test_settings_content_preferences.py:/api/observability/audit (L7); backend/tests/test_settings_interests.py:/api/observability/audit (L8) | 🟡 待确认 (仅测试+文档) |
| 171 | `GET /api/observability/channels` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_alert_channels.py:/api/observability/channels (L317) | 🟡 待确认 (仅测试引用) |
| 172 | `PUT /api/observability/channels` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_alert_channels.py:/api/observability/channels (L317) | 🟡 待确认 (仅测试引用) |
| 173 | `POST /api/observability/channels/test` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 174 | `GET /api/observability/deliveries` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_alert_channels.py:/api/observability/deliveries (L344) | 🟡 待确认 (仅测试引用) |
| 175 | `GET /api/observability/llm-usage` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 176 | `GET /api/observability/llm/health` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_llm_health_api.py:/api/observability/llm/health (L1) | 🟡 待确认 (仅测试+文档) |
| 177 | `POST /api/observability/llm/health/{provider}/reset` | 未命中 | 未命中 | 未命中 | 命中 | docs/progress-archive/v1.0-track-records.md:/api/observability/llm/health/{provider}/reset (L356) | 🟡 待确认 (仅文档提及) |
| 178 | `GET /api/observability/sampling` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_observability_sampling.py:/api/observability/sampling (L224) | 🟡 待确认 (仅测试+文档) |
| 179 | `PUT /api/observability/sampling` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_observability_sampling.py:/api/observability/sampling (L224) | 🟡 待确认 (仅测试+文档) |
| 180 | `GET /api/observability/thresholds` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_observability_thresholds.py:/api/observability/thresholds (L180); frontend/src/components/secnews/observability/Batch4.test.tsx:/api/observability/thresholds (L110) | 🟡 待确认 (仅测试引用) |
| 181 | `PUT /api/observability/thresholds` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_observability_thresholds.py:/api/observability/thresholds (L180); frontend/src/components/secnews/observability/Batch4.test.tsx:/api/observability/thresholds (L110) | 🟡 待确认 (仅测试引用) |
| 182 | `GET /api/observability/timeseries` | 命中 | 命中 | 命中 | 命中 | backend/services/skill_registry/builtin.py:/api/observability/timeseries (L159) | 🟢 勿动 (有内部消费) |
| 183 | `GET /api/ops/kpi` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_kpi_api.py:/api/ops/kpi (L128) | 🟡 待确认 (仅测试+文档) |
| 184 | `GET /api/profile` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_adapters.py:/api/profile (L29); backend/api/mcp_types.py:/api/profile (L87) | 🟢 勿动 (有内部消费) |
| 185 | `POST /api/proposals` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_types.py:/api/proposals (L212) | 🟢 勿动 (有内部消费) |
| 186 | `POST /api/proposals/failed` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 187 | `POST /api/proposals/runs/{run_id}/retry` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_run_ledger.py:/api/proposals/runs/{run_id}/retry (L511) | 🟡 待确认 (仅测试+文档) |
| 188 | `GET /api/proposals/{proposal_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 189 | `GET /api/quality/logs` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_api.py:/api/quality/logs (L14) | 🟡 待确认 (仅测试+文档) |
| 190 | `GET /api/quality/rejection-stats` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 191 | `GET /api/quality/source-reputation` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_api.py:/api/quality/source-reputation (L15) | 🟡 待确认 (仅测试+文档) |
| 192 | `GET /api/reports/daily` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 193 | `GET /api/reports/monthly` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 194 | `GET /api/reports/monthly/available` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 195 | `GET /api/reports/weekly/available` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 196 | `GET /api/reviews/{entity_type}/{entity_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 197 | `GET /api/secrets/export` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_secrets_api.py:/api/secrets/export (L230) | 🟡 待确认 (仅测试+文档) |
| 198 | `POST /api/secrets/reset` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_secrets_reset_guard.py:/api/secrets/reset (L1); backend/tests/test_secrets_api.py:/api/secrets/reset (L285) | 🟡 待确认 (仅测试引用) |
| 199 | `POST /api/secrets/rotate` | 命中 | 命中 | 命中 | 命中 | backend/scheduler/jobs/security.py:/api/secrets/rotate (L422) | 🟢 勿动 (有内部消费) |
| 200 | `GET /api/secrets/unlock` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_secrets_api.py:/api/secrets/unlock (L78); backend/tests/test_oauth_secrets.py:/api/secrets/unlock (L146) | 🟡 待确认 (仅测试引用) |
| 201 | `POST /api/security/enrich` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 202 | `GET /api/security/entities` | 未命中 | 未命中 | 未命中 | 命中 | docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md:/api/security/entities (L166); docs/audit/P0_R07_JOB_INVENTORY_2026-11-10.md:/api/security/entities (L87) | 🟡 待确认 (仅文档提及) |
| 203 | `GET /api/security/entities/{entity_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 204 | `GET /api/security/mitre/cache` | 未命中 | 未命中 | 未命中 | 命中 | docs/CHANGELOG.md:/api/security/mitre/cache (L468); docs/progress-archive/v0.7-records.md:/api/security/mitre/cache (L574) | 🟡 待确认 (仅文档提及) |
| 205 | `POST /api/security/mitre/sync` | 未命中 | 未命中 | 未命中 | 命中 | docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md:/api/security/mitre/sync (L406) | 🟡 待确认 (仅文档提及) |
| 206 | `POST /api/security/terminology/normalize` | 未命中 | 未命中 | 未命中 | 命中 | docs/SECURITY_KNOWLEDGE_GRAPH_DEV_PLAN.md:/api/security/terminology/normalize (L568); docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md:/api/security/terminology/normalize (L187) | 🟡 待确认 (仅文档提及) |
| 207 | `GET /api/security/terminology/search` | 未命中 | 未命中 | 未命中 | 命中 | docs/SECURITY_KNOWLEDGE_GRAPH_DEV_PLAN.md:/api/security/terminology/search (L569); docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md:/api/security/terminology/search (L191) | 🟡 待确认 (仅文档提及) |
| 208 | `GET /api/security/terminology/suggest` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 209 | `GET /api/security/terminology/taxonomy` | 未命中 | 未命中 | 未命中 | 命中 | docs/SECURITY_KNOWLEDGE_GRAPH_DEV_PLAN.md:/api/security/terminology/taxonomy (L570); docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md:/api/security/terminology/taxonomy (L192) | 🟡 待确认 (仅文档提及) |
| 210 | `GET /api/settings/auto-intake` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_auto_intake_api.py:/api/settings/auto-intake (L4); frontend/src/components/settings/AutoIntakeCard.test.tsx:/api/settings/auto-intake (L17) | 🟡 待确认 (仅测试+文档) |
| 211 | `GET /api/settings/features` | 未命中 | 命中 | 命中 | 命中 | backend/extensions/__init__.py:/api/settings/features (L91) | 🟢 勿动 (有内部消费) |
| 212 | `POST /api/settings/refresh-interval` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_source_cadence_gate.py:/api/settings/refresh-interval (L10); frontend/src/components/sentinel/SentinelHomePage.test.tsx:/api/settings/refresh-interval (L582) | 🟡 待确认 (仅测试+文档) |
| 213 | `GET /api/skill-builder` | 未命中 | 命中 | 命中 | 命中 | backend/extensions/__init__.py:/api/skill-builder (L49) | 🟢 勿动 (有内部消费) |
| 214 | `DELETE /api/skill-builder/{skill_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 215 | `GET /api/skill-builder/{skill_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 216 | `PATCH /api/skill-builder/{skill_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 217 | `GET /api/skill-registry/runs/{run_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_skill_registry_runs_api.py:/api/skill-registry/runs/{run_id} (L275) | 🟡 待确认 (仅测试+文档) |
| 218 | `POST /api/skill-registry/{skill_id}/disable` | 未命中 | 未命中 | 未命中 | 命中 | scripts/check_v1_endpoint_parity.py:/api/skill-registry/{skill_id}/disable (L98) | 🟡 待确认 (仅文档提及) |
| 219 | `POST /api/skill-registry/{skill_id}/enable` | 未命中 | 未命中 | 未命中 | 命中 | scripts/check_v1_endpoint_parity.py:/api/skill-registry/{skill_id}/enable (L97) | 🟡 待确认 (仅文档提及) |
| 220 | `POST /api/skills` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/skills (L46); backend/tests/test_skills.py:/api/skills (L59); frontend/src/components/skills/SkillStore.test.tsx:/api/skills (L7) | 🟡 待确认 (仅测试+文档) |
| 221 | `GET /api/sources/system` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_source_system_api.py:/api/sources/system (L94) | 🟡 待确认 (仅测试+文档) |
| 222 | `DELETE /api/sources/system/{sid}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_source_system_api.py:/api/sources/system (L94) | 🟡 待确认 (仅测试+文档) |
| 223 | `PATCH /api/sources/system/{sid}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_source_system_api.py:/api/sources/system (L94) | 🟡 待确认 (仅测试+文档) |
| 224 | `POST /api/sync/conflicts/resolve` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_sync_api.py:/api/sync/conflicts/resolve (L389) | 🟡 待确认 (仅测试+文档) |
| 225 | `GET /api/tags/by-hotspot/{hotspot_id}` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_extract_api.py:/api/tags/by-hotspot (L90); backend/tests/test_tags_api.py:/api/tags/by-hotspot/{hotspot_id} (L8) | 🟡 待确认 (仅测试引用) |
| 226 | `GET /api/tech-stack` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/tech-stack (L72); backend/tests/test_tech_stack_api.py:/api/tech-stack (L4); backend/tests/test_phase2_acceptance.py:/api/tech-stack (L266) | 🟡 待确认 (仅测试+文档) |
| 227 | `POST /api/tech-stack` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/tech-stack (L72); backend/tests/test_tech_stack_api.py:/api/tech-stack (L4); backend/tests/test_phase2_acceptance.py:/api/tech-stack (L266) | 🟡 待确认 (仅测试+文档) |
| 228 | `GET /api/tech-stack/impact` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/tech-stack/impact (L72); backend/tests/test_tech_stack_api.py:/api/tech-stack/impact (L9); backend/tests/test_phase2_acceptance.py:/api/tech-stack/impact (L266) | 🟡 待确认 (仅测试+文档) |
| 229 | `DELETE /api/tech-stack/{tech_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 230 | `GET /api/tech-stack/{tech_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 231 | `PUT /api/tech-stack/{tech_id}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 232 | `GET /api/trends` | 未命中 | 命中 | 命中 | 命中 | backend/repository/trend_repo.py:/api/trends (L129) | 🟢 勿动 (有内部消费) |
| 233 | `GET /api/trigger/webhook/health` | 未命中 | 未命中 | 命中 | 未命中 | backend/tests/test_trigger_sources.py:/api/trigger/webhook/health (L201) | 🟡 待确认 (仅测试引用) |
| 234 | `POST /api/trigger/webhook/{source}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_trigger_sources.py:/api/trigger/webhook/{source} (L8) | 🟡 待确认 (仅测试+文档) |
| 235 | `GET /api/v1/cases/{case_id}` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_case_service.py:/api/v1/cases/{case_id} (L385) | 🟡 待确认 (仅测试+文档) |
| 236 | `POST /api/v1/judgments/generate` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_judgment_api.py:/api/v1/judgments/generate (L61) | 🟡 待确认 (仅测试+文档) |
| 237 | `GET /api/weekly-report` | 未命中 | 未命中 | 命中 | 命中 | backend/tests/test_feature_gates.py:/api/weekly-report (L47) | 🟡 待确认 (仅测试+文档) |
| 238 | `POST /api/weekly-report/generate` | 未命中 | 未命中 | 未命中 | 命中 | docs/archived/2026-09-09-sweep/FRONTEND_BACKEND_ALIGNMENT_AUDIT.md:/api/weekly-report/generate (L142); docs/archived/2026-09-09-sweep/IMPROVEMENT_PLAN.md:/api/weekly-report/generate (L642) | 🟡 待确认 (仅文档提及) |
| 239 | `GET /api/weekly-report/latest` | 未命中 | 未命中 | 未命中 | 命中 | docs/audit/P0_R07_JOB_INVENTORY_2026-11-10.md:/api/weekly-report/latest (L92); docs/archived/2026-09-09-sweep/IMPROVEMENT_PLAN.md:/api/weekly-report/latest (L639) | 🟡 待确认 (仅文档提及) |
| 240 | `POST /api/weekly-report/snapshot` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 241 | `GET /api/weekly-report/{week_start}` | 未命中 | 未命中 | 未命中 | 未命中 | 四项均无引用 | 🔴 P1 删除候选 |
| 242 | `GET /api/wiki/graph` | 命中 | 命中 | 命中 | 命中 | backend/api/mcp_types.py:/api/wiki/graph (L145) | 🟢 勿动 (有内部消费) |
| 243 | `POST /api/wiki/trace` | 命中 | 命中 | 命中 | 未命中 | backend/api/mcp_types.py:/api/wiki/trace (L153) | 🟢 勿动 (有内部消费) |
| 244 | `POST /api/wiki/write` | 命中 | 命中 | 命中 | 未命中 | backend/api/mcp_types.py:/api/wiki/write (L162) | 🟢 勿动 (有内部消费) |

### 6.1 四项全未命中 — 纯零调用死端点 (67 个, 优先送 P1 裁决)

| 端点 | 后端模块 |
|---|---|
| `PUT /api/alerts/{alert_id}/dismiss` | `alerts` |
| `PUT /api/alerts/{alert_id}/read` | `alerts` |
| `GET /api/cache/stats` | `cache` |
| `DELETE /api/codegarden/dependencies/{dep_id}` | `codegarden_ops` |
| `POST /api/codegarden/playbooks/{name}/run` | `codegarden_ops` |
| `DELETE /api/codegarden/projects/{project_id}` | `codegarden` |
| `GET /api/codegarden/projects/{project_id}` | `codegarden` |
| `PATCH /api/codegarden/projects/{project_id}` | `codegarden` |
| `GET /api/codegarden/projects/{project_id}/activities` | `codegarden` |
| `POST /api/codegarden/projects/{project_id}/archive` | `codegarden` |
| `POST /api/codegarden/projects/{project_id}/lifecycle` | `codegarden` |
| `POST /api/codegarden/projects/{project_id}/restore` | `codegarden` |
| `POST /api/codegarden/projects/{project_id}/sync` | `codegarden` |
| `GET /api/codegarden/projects/{project_id}/timeline` | `codegarden` |
| `GET /api/codegarden/projects/{project_id}/upstream` | `codegarden` |
| `DELETE /api/codegarden/resources/{resource_id}` | `codegarden_ops` |
| `GET /api/codegarden/resources/{resource_id}` | `codegarden_ops` |
| `GET /api/codegarden/services/{service_id}/logs` | `codegarden_ops` |
| `GET /api/codegarden/services/{service_id}/metrics` | `codegarden_ops` |
| `POST /api/codegarden/services/{service_id}/restart` | `codegarden_ops` |
| `PATCH /api/content/drafts/{draft_id}` | `content` |
| `GET /api/deep-read/recent` | `deep_read` |
| `DELETE /api/digests/{digest_id}` | `digests` |
| `GET /api/digests/{digest_id}` | `digests` |
| `GET /api/event-technique/event-types/{event_type_id}/techniques` | `event_types_api` |
| `POST /api/export/rebuild` | `export` |
| `GET /api/kl/inbox/list` | `kl_pipeline_api` |
| `GET /api/kl/metrics/stage-counts` | `kl_metrics_api` |
| `GET /api/kl/quarantine/list` | `kl_pipeline_api` |
| `POST /api/knowledge/classify/batch` | `knowledge_classify_api` |
| `GET /api/knowledge/classify/stats` | `knowledge_classify_api` |
| `POST /api/knowledge/concepts/link/batch` | `knowledge_concepts` |
| `GET /api/knowledge/obsidian/conflicts` | `knowledge_obsidian` |
| `POST /api/knowledge/obsidian/open` | `knowledge_obsidian` |
| `POST /api/knowledge/obsidian/watchdog/start` | `knowledge_obsidian` |
| `GET /api/knowledge/obsidian/watchdog/status` | `knowledge_obsidian` |
| `POST /api/knowledge/obsidian/watchdog/stop` | `knowledge_obsidian` |
| `POST /api/knowledge/progress/sync` | `knowledge_plans` |
| `GET /api/knowledge/progress/{concept_slug}` | `knowledge_plans` |
| `PATCH /api/knowledge/progress/{concept_slug}` | `knowledge_plans` |
| `POST /api/knowledge/projection/rebuild` | `knowledge_import` |
| `POST /api/knowledge/skills/seed` | `knowledge_skills` |
| `DELETE /api/knowledge/skills/{skill_id}` | `knowledge_skills` |
| `POST /api/knowledge/summaries/weekly` | `knowledge_plans` |
| `POST /api/llm/pool/detect` | `llm_pool_api` |
| `GET /api/maintenance/orphans` | `maintenance_db_api` |
| `POST /api/observability/channels/test` | `observability_router` |
| `GET /api/observability/llm-usage` | `observability_metrics_api` |
| `POST /api/proposals/failed` | `run_ledger_api` |
| `GET /api/proposals/{proposal_id}` | `run_ledger_api` |
| `GET /api/quality/rejection-stats` | `quality_rejection_api` |
| `GET /api/reports/daily` | `reports` |
| `GET /api/reports/monthly` | `reports` |
| `GET /api/reports/monthly/available` | `reports` |
| `GET /api/reports/weekly/available` | `reports` |
| `GET /api/reviews/{entity_type}/{entity_id}` | `reviews` |
| `POST /api/security/enrich` | `security` |
| `GET /api/security/entities/{entity_id}` | `security` |
| `GET /api/security/terminology/suggest` | `security` |
| `DELETE /api/skill-builder/{skill_id}` | `skill_builder_api` |
| `GET /api/skill-builder/{skill_id}` | `skill_builder_api` |
| `PATCH /api/skill-builder/{skill_id}` | `skill_builder_api` |
| `DELETE /api/tech-stack/{tech_id}` | `tech_stack` |
| `GET /api/tech-stack/{tech_id}` | `tech_stack` |
| `PUT /api/tech-stack/{tech_id}` | `tech_stack` |
| `POST /api/weekly-report/snapshot` | `weekly_report` |
| `GET /api/weekly-report/{week_start}` | `weekly_report` |

> **裁决前置条件 (P1)**: ① R-09 本身是盘点, 删除属 P3; ② 每个候选项须走 P2 消融矩阵 (§7.4) —— 
> 「关掉后零失败 + 零观测变化」才可下「删除」结论; ③ 一项一个 commit, commit message 带 `R-xx` 编号; 
> ④ 删除后 `python scripts/generate_meta.py --fix` 同步 `ARCHITECTURE.md` 数字 (CI 有 `--check`)。

---

## 7. 前端未使用孤儿 (反向结论)

R-09 的另一半用途: 从「有端点无组件」外, 也要看「有封装无组件」。以下两类是**前端死代码**, 与后端删除候选分开裁决。

### 7.1 封装层有、组件无调用的端点函数

| 封装函数 | 位置 | 目标端点 |
|---|---|---|
| `createArtifact()` | `frontend/src/api/v1.ts` | `POST /api/v1/artifacts` |
| `generateKnowledge()` | `frontend/src/api/v1.ts` | `POST /api/v1/knowledge/generate` |
| `getAction()` | `frontend/src/api/v1.ts` | `GET /api/v1/actions/{p}` |
| `getArtifact()` | `frontend/src/api/v1.ts` | `GET /api/v1/artifacts/{p}` |
| `getHotspot()` | `frontend/src/api/hotspots.ts` | `GET /api/hotspots/{p}` |
| `getJudgment()` | `frontend/src/api/v1.ts` | `GET /api/v1/judgments/{p}` |
| `getKnowledge()` | `frontend/src/api/v1.ts` | `GET /api/v1/knowledge/{p}` |
| `getRun()` | `frontend/src/api/v1.ts` | `GET /api/v1/runs/{p}` |
| `getSourceAlerts()` | `frontend/src/api/sources.ts` | `GET /api/sources/alerts` |
| `getSourceHealthBySource()` | `frontend/src/api/sources.ts` | `GET /api/sources/health/by-source/{p}/{p}` |
| `getSourceHealthTrend()` | `frontend/src/api/sources.ts` | `GET /api/sources/health/trend` |
| `getSourceHealthTrendBySource()` | `frontend/src/api/sources.ts` | `GET /api/sources/health/trend/{p}` |
| `getV1Skill()` | `frontend/src/api/v1.ts` | `GET /api/skill-registry/v1/{p}` |
| `listActions()` | `frontend/src/api/v1.ts` | `GET /api/v1/actions` |
| `listAdoptions()` | `frontend/src/api/v1.ts` | `GET /api/v1/knowledge/{p}/adoptions` |
| `listArtifacts()` | `frontend/src/api/v1.ts` | `GET /api/v1/artifacts` |
| `listCommands()` | `frontend/src/api/commands.ts` | `GET /api/commands` |
| `listJudgments()` | `frontend/src/api/v1.ts` | `GET /api/v1/judgments` |
| `listRuns()` | `frontend/src/api/v1.ts` | `GET /api/v1/runs` |
| `listV1Skills()` | `frontend/src/api/v1.ts` | `GET /api/skill-registry/v1` |
| `markSourceDead()` | `frontend/src/api/sources.ts` | `POST /api/sources/health/by-source/{p}/{p}/dead` |
| `probeSource()` | `frontend/src/api/sources.ts` | `POST /api/sources/{p}/probe` |
| `recallKnowledgeForCase()` | `frontend/src/api/v1.ts` | `GET /api/v1/knowledge/{p}/recall` |
| `updateCase()` | `frontend/src/api/v1.ts` | `PATCH /api/v1/cases/{p}` |

共 **24** 个封装函数定义了真实后端端点但无任何组件调用 —— 这些端点因此被判为「零调用/仅内部/仅测试」, 
**不是**后端死端点, 而是**前端死封装**。裁决方向应为「删前端封装函数」或「接上组件」, 不应据此删后端端点。

### 7.2 无任何外部引用的前端组件

| 组件文件 |
|---|
| `frontend/src/components/AddTodoForm.tsx` |
| `frontend/src/components/LocaleToggle.tsx` |
| `frontend/src/components/security/EventTypeCard.tsx` |
| `frontend/src/components/security/EventTypeReviewPage.tsx` |
| `frontend/src/components/layout/LayerBadge.tsx` |
| `frontend/src/components/shared/editorial/Ticket.tsx` |
| `frontend/src/components/shared/editorial/EditorialCard.tsx` |
| `frontend/src/components/shared/editorial/Masthead.tsx` |
| `frontend/src/components/shared/editorial/PressBar.tsx` |
| `frontend/src/components/shared/editorial/IconButton.tsx` |
| `frontend/src/components/shared/editorial/SectionHead.tsx` |
| `frontend/src/components/shared/editorial/BandNav.tsx` |
| `frontend/src/components/shared/editorial/WireList.tsx` |

共 **13** 个 `.tsx` 组件在 `frontend/src/**` 内无任何外部引用 (仅被自己的 `*.test.tsx` 引用, 或完全孤立)。
其中 `frontend/src/components/shared/editorial/*` (8 个) 是成组的未接线设计资产 —— 建议整组裁决, 不逐个评估。

> **交叉发现**: `POST /api/event-technique/candidates` 的**唯一**前端消费方是孤儿组件 
> `frontend/src/components/security/EventTypeReviewPage.tsx` —— 该端点虽在主表判为「有消费」, 
> 但消费链本身已断 (组件不挂载) → 属**连带孤儿**, 裁决时应与该组件一并处理。

---

## 8. 已知局限

1. **前端 method 推断**: 前端未显式传 `method` 时按调用函数推断 (`postJSON`→POST, `getJSON`/`apiFetch`/`fetch`→GET)。 
   若组件用 `apiFetch(url, { method: 'PUT' })` 形式, 由尾随 `method:` 字面量捕获; 若 method 由变量传入则回退 GET, 
   可能在「同一路径多方法」时归错方法 (表中该端点仍会被正确归属, 只是方法标注可能偏移)。
2. **动态路径拼接**: `buildQuery(...)` / `qs` / `params.toString()` 等查询串构造函数按「丢弃」处理, 
   只有**路径段**参与匹配。若后端存在同一路径的多形态 (如 `/api/x` 与 `/api/x/`), 前端尾斜杠归一可能掩盖差异。
3. **反射/动态路由消费未覆盖**: 后端若有基于字符串拼接或配置驱动的自调用 (不经 `include_router` 的注册路由), 
   (b) 检查只做文本命中, 可能漏判 —— RA-1 已列此风险, 建议 P2 消融复核。
4. **`GET /` 与非 `/api/*` 路由**不在主表内 (前端不走 HTTP 直接访问)。
5. **MCP gate 默认关**: 15 个 `mcp` 族端点在默认配置下不注册 (404), 本表按「静态存在」计入 520, 
   它们的前端调用点数天然为 0 —— 这类应按 (a) 命中处理, 不进入删除候选。
6. **测试文件计入「仅测试」档**: `frontend/src/**/*.test.tsx` 中的 URL 字面量不计入「有消费」, 
   只作为 (c) 检查的证据 —— 因为测试消费 ≠ 业务消费。
7. **孤儿组件判定基于标识符文本匹配**: 同名标识符可能造成假阳性/假阴性; `frontend/src/routes/` 的懒加载 
   (`React.lazy(() => import(...))`) 已计入引用, 但动态 import 字符串拼接场景无法覆盖。
8. **本表不构成删除结论**: 依 PRD §8.1, 端点删除在 P3, 须先过 P1 用户逐项批准 + P2 消融矩阵。

---

## 9. 复现命令

```bash
# 1. router 口径实测 (应为 100, PRD 写 101)
python scripts/generate_meta.py --check

# 2. 端点全集 (静态 AST, 递归 include_router + prefix 传播)
#    → 520 条, 与运行时 OpenAPI 的差集 = 15 个 mcp 族 (gate 默认关)

# 3. 前端双路径调用点 (路径 A: fetch/apiFetch/getJSON/postJSON 四形态;
#    路径 B: api/*.ts 导出函数 → import 反查组件调用点)
#    → 调用点总数见 §2 总览

# 4. 零调用端点四项检查 (a) MCP/命令栏/服务 (b) 后端自调用
#    (c) 仅测试引用 (d) 运维/文档
```

---

*本文件由 R-09 盘点产出, 只含证据与候选, 不含删除结论。采集脚本为一次性工具, 未入库。*
