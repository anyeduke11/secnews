# Route Registry — 跨 7 个子模块的路由映射表

> **状态**: P1-3 任务产出 (2026-08-24)
> **来源**: docs/P0_AUDIT.md §三 (后端 213 → 现网 268 路由) + frontend/src/routes/index.tsx (49 路由)
> **作用**: 任何后端新增 `/api/*` 或前端新增 `<Route>` 都必须在此表登记，否则视为"orphan route" — CI 会在路由 mismatch audit 阶段 fail

## 一、7 个子模块边界

| # | 子模块 | 前端路径 (pages) | 后端 prefix | 入口组件 | 入口 router | 备注 |
|---|--------|------------------|-------------|----------|-------------|------|
| 1 | **main hotspot** | `/`, `/data/*`, `/judge/*`, `/action/*`, `/todos`, `/history`, `/skills`, `/secrets`, `/settings`, `/report`, `/quality/*`, `/reviews`, `/brief`, `/editorial`, `/deep/:type/:id`, `/weekly-report`, `/category/:cat` | `/api/hotspots`, `/api/sources`, `/api/alerts`, `/api/secrets`, `/api/maintenance`, `/api/quality`, `/api/catchup`, `/api/history`, `/api/weekly-report`, `/api/bid-alert`, `/api/export`, `/api/mode`, `/api/skills`, `/api/cache`, `/api/proxy`, `/api/settings`, `/api/todos`, `/api/cve`, `/api/events`, `/api/health`, `/api/refresh`, `/api/stats`, `/api/trends`, `/api/reports`, `/api/sync` | 资料/判断/行动三层 + 全局工具 | 各 router | core 永远注册 |
| 2 | **codegarden** | `/codegarden`, `/codegarden/phase2b`, `/action/codegarden`, `/action/codegarden/phase2b` | `/api/codegarden` (35) | CodegardenPage / ActionCodegardenPage | codegarden router | **feature gate**: `codegarden` (默认关) |
| 3 | **kl** (backend-only) | (无独立 frontend, 通过 main 路由的 KnowledgeCompound/KnowledgeProcess 调用) | `/api/kl` (18), `/api/digests` (5) | KnowledgeProcess / KnowledgeCompound (内嵌展示) | kl_pipeline router | backend-only, 前端走 KnowledgeProcess 间接触发 |
| 4 | **ai_hub** (backend-only) | (无独立 frontend, 通过 KnowledgeActionBar / KnowledgeProcess 触发) | `/api/llm` (2), `/api/recommend` (1) | KnowledgeActionBar / KnowledgeProcess | ai_hub router | backend-only, 通过 `/api/digests/generate` 触发日报 |
| 5 | **knowledge-master** | `/knowledge/*` (12 子路由) | `/api/knowledge` (42), `/api/wiki` (5), `/api/tags` (4), `/api/favorites` (4), `/api/content` (7), `/api/extract` (3), `/api/reviews` (4), `/api/annotations` (2), `/api/attention` (1), `/api/search` (1), `/api/categories` (1) | KnowledgePage | knowledge router + wiki router | skill "knowledge-master" 调用入口 |
| 6 | **secnews** | `/secnews/*` (5 子路由: feed/pipeline/knowledge/inbox/ledger) | `/api/secnews` (4) | SecNewsShell | secnews router | **feature gate**: `secnews` (默认关) |
| 7 | **security_cockpit** (设计资产, 不在 hotspot frontend) | (无 — security-cockpit/ 是独立设计稿) | `/api/security` (10) | (设计资产目录 `security-cockpit/`) | security router | **future**: security cockpit SPA 接入点 |

**总计**:
- 后端 268 路由（含根 /）
- 前端 49 路由（routes/index.tsx, 含 Navigate 重定向 + Lazy Suspense）
- 子模块归属占比: main hotspot 117 (44%) / knowledge-master 73 (27%) / codegarden 35 (13%) / kl+ai_hub 26 (10%) / security_cockpit 10 (4%) / secnews 4 (1%) / 其他 3 (1%)

## 二、前端 49 路由按子模块分组

### 2.1 main hotspot (33 路由)

| # | 路径 | 组件 | Feature Flag | 类型 |
|---|------|------|--------------|------|
| 1 | `/` | → `/data` (重定向) | - | Navigate |
| 2 | `/data` | DataLayerPage | - | Page |
| 3 | `/data/import` | DataImportPage | - | Page |
| 4 | `/data/favorites` | DataFavoritesPage | - | Page |
| 5 | `/data/history` | HistoryPageRoute | - | Page (hook) |
| 6 | `/judge` | JudgeLayerPage | - | Page |
| 7 | `/action` | ActionLayerPage | - | Page |
| 8 | `/category/:cat` | → `/data?category=...` | - | Navigate |
| 9 | `/weekly-report` | → `/report` | - | Navigate (v0.4 兼容) |
| 10 | `/action/report` | ActionReportPage | - | Page |
| 11 | `/action/compound` | ActionCompoundPage | - | Page |
| 12 | `/action/todos` | ActionTodosPage | - | Page |
| 13 | `/action/outbox` | ActionOutboxPage | - | Page |
| 14 | `/action/review` | ActionReviewPage | - | Page |
| 15 | `/action/skills` | ActionSkillsPage | - | Page |
| 16 | `/action/bid-alert` | ActionBidAlertPage | - | Page |
| 17 | `/judge/trends` | JudgeTrendsPage | - | Page |
| 18 | `/judge/bid-analysis` | JudgeBidAnalysisPage | - | Page |
| 19 | `/judge/quality` | → `/quality/rejection` | - | Navigate |
| 20 | `/judge/heatmap` | → `/knowledge/heatmap` | - | Navigate |
| 21 | `/judge/graph` | → `/knowledge/process` | - | Navigate |
| 22 | `/judge/compile` | → `/knowledge/compile` | - | Navigate |
| 23 | `/judge/read` | → `/knowledge/briefing` | - | Navigate |
| 24 | `/todos` | TodosPage | - | Page (v0.4 兼容) |
| 25 | `/history` | HistoryPageRoute | - | Page (v0.4 兼容) |
| 26 | `/skills` | SkillsPage | - | Page (v0.4 兼容) |
| 27 | `/secrets` | SecretsPage | - | Page (v0.4 兼容) |
| 28 | `/sync` | SyncPage | `sync` (默认开) | Page (v0.4 兼容) |
| 29 | `/settings` | SettingsPage | - | Page |
| 30 | `/report` | ReportPage | - | Page |
| 31 | `/reviews` | ReviewPage | - | Page |
| 32 | `/deep/:type/:id` | DeepReadView | - | Page (跨实体深读) |
| 33 | `/brief` | → `/knowledge/briefing` | - | Navigate (P1.4 合并) |
| 34 | `/quality/rejection` | QualityRejectionPage | - | Page |
| 35 | `/editorial` | EditorialView | - | Page (独立全屏, v4.3) |
| 36 | `*` (fallback) | → `/data` | - | Navigate (兜底) |

### 2.2 codegarden (4 路由, feature gate)

| # | 路径 | 组件 | Feature Flag |
|---|------|------|--------------|
| 37 | `/codegarden` | CodegardenPage | `codegarden` |
| 38 | `/codegarden/phase2b` | CodegardenPhase2bPage | `codegarden` + `codegarden_phase2b` |
| 39 | `/action/codegarden` | ActionCodegardenPage | `codegarden` |
| 40 | `/action/codegarden/phase2b` | ActionCodegardenPhase2bPage | `codegarden` + `codegarden_phase2b` |

### 2.3 knowledge-master (12 路由, nested under /knowledge)

| # | 路径 | 组件 |
|---|------|------|
| 41 | `/knowledge` | KnowledgePage (parent) |
| 42 | `/knowledge` (index) | → `import` |
| 43 | `/knowledge/import` | KnowledgeImport |
| 44 | `/knowledge/process` | KnowledgeProcess (KL 阶段详情) |
| 45 | `/knowledge/compile` | KnowledgeCompile |
| 46 | `/knowledge/compound` | KnowledgeCompound (KL 触发器健康度) |
| 47 | `/knowledge/imported` | KnowledgeFavoritesView |
| 48 | `/knowledge/briefing` | BriefingMode (官方每日简报) |
| 49 | `/knowledge/scan` | ScanMode (深读浏览) |
| 50 | `/knowledge/deep-read` | → `scan` |
| 51 | `/knowledge/deep-read/:id` | DeepReadMode |
| 52 | `/knowledge/alert` | AlertMode |
| 53 | `/knowledge/outbox` | OutboxMode |
| 54 | `/knowledge/review` | ReviewMode |
| 55 | `/knowledge/heatmap` | AttentionHeatmap |

### 2.4 secnews (5 路由, feature gate)

| # | 路径 | 组件 | Feature Flag |
|---|------|------|--------------|
| 56 | `/secnews` | SecNewsShell (parent) | `secnews` |
| 57 | `/secnews` (index) | → `feed` | `secnews` |
| 58 | `/secnews/feed` | SecNewsFeed | `secnews` |
| 59 | `/secnews/pipeline` | SecNewsPipeline (KL 5 阶段漏斗) | `secnews` |
| 60 | `/secnews/knowledge` | SecNewsKnowledge (WikiBrowser) | `secnews` |
| 61 | `/secnews/inbox` | SecNewsInbox (InboxScanner) | `secnews` |
| 62 | `/secnews/ledger` | SecNewsLedger (TokenLedger) | `secnews` |

### 2.5 kl / ai_hub (0 frontend routes — 通过 main hotspot 间接调用)

- kl: KnowledgeProcess (`/knowledge/process`) + KnowledgeCompound (`/knowledge/compound`) 展示 KL 阶段状态
- ai_hub: KnowledgeActionBar 调用 `/api/digests/generate` 触发日报

### 2.6 security_cockpit (0 frontend routes — 设计资产目录)

- 设计资产: `security-cockpit/` (pages/partials/assets + colors_and_type.css)
- 后端 prefix: `/api/security` (10 路由, 给未来独立 SPA 准备)
- 当前**未在 hotspot frontend 接入**

## 三、7 个 mismatch 修复记录 (P1-1)

| # | 路由 | 风险 | 裁决 | 修复方式 |
|---|------|------|------|----------|
| 1 | `/api/favorites/a` | 高 | **测试 mock URL** (useFavorites.test.ts:176, 非真调用) | 不修代码, test 自带 |
| 2 | `/api/kl/planning-actions/1/status` | 高 | **测试 mock URL** (Phase13PlanningPanel.test.tsx:150) | 不修代码, test 自带 |
| 3 | `/api/llm/digest` | 中 | **真 mismatch** | 改为 `/api/digests/generate` (KnowledgeActionBar.tsx + test) |
| 4 | `/api/mcp/status` | 中 | **feature gate 设计** (`mcp=false` 默认关闭, 路由不注册) | 前端 try/catch + ok check, 404 不崩 |
| 5 | `/api/mcp/tools` | 中 | **feature gate 设计** | 同上 |
| 6 | `/api/settings/mcp/enabled` | 中 | **feature gate 设计** | 同上 |
| 7 | `/api/soul` | 中 | **真 mismatch** | 改为 `/api/knowledge/soul` (JudgeLayerPage.tsx) |

## 四、新增路由规则 (CI enforcement)

每次新增 `<Route>` 或 `/api/*` endpoint 必须:

1. **路由声明**: 在 routes/index.tsx 或 backend/api/<router>.py 加代码
2. **本表登记**: 在 §一 子模块边界表 + §二 前端分组 或 §三 后端分布更新
3. **测试覆盖**: 前端加 `<Route>` 必须有对应 Vitest 测试 (含懒加载 fallback)
4. **Feature flag 标注**: 若依赖 feature gate, 必须在 `<Route>` 上用 `features.<flag> && <Route>` 包裹, 并在本表"Feature Flag"列标 `flag_name`
5. **跨子模块**: 若涉及多子模块, 需在 commit message 标 `[multi-module: a, b]`

## 五、orphan 检测脚本 (manual)

```bash
# 1. 后端独有 (注册但前端未调)
.venv/bin/python -c "from backend.main import app; print('\n'.join(sorted(app.openapi()['paths'].keys())))" \
  | grep "^/api/" > /tmp/backend_routes.txt
grep -rh "fetch(\`/api/[^\`]*\`" frontend/src/ \
  | grep -oE "/api/[a-zA-Z0-9/_\-{}.]+" | sort -u > /tmp/frontend_calls.txt
comm -23 /tmp/backend_routes.txt /tmp/frontend_calls.txt | wc -l   # 当前 ~94

# 2. 前端独有 (调用但后端无)
comm -13 /tmp/backend_routes.txt /tmp/frontend_calls.txt

# 3. 路由注册表覆盖率
grep -E "^\| .*[a-z].*\|$" frontend/src/routes/ROUTE_REGISTRY.md | wc -l
```

## 六、未决事项

- 安全 cockpit SPA 是否接入 hotspot frontend (P2 任务, 等 design 终稿)
- kl / ai_hub 是否有独立 frontend 入口 (当前决策: 不独立, 通过 KnowledgeProcess 嵌入)
- Phase 7 dsh 移植后, 7 个子模块可能进一步拆分 (Phase 8+)

---

**维护者**: 在 PR 加 `<Route>` 或后端 router 时, 必须同步本表; 否则 CI 的 `audit_route_registry.py` 会 fail
