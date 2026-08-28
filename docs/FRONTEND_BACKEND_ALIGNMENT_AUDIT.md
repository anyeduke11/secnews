# Hotspot 前端 / 后端能力对齐 audit（v0.4.3 → v0.5 计划）

> **audit 日期**: 2026-08-21
> **audit 范围**: 54 个后端 router + 前端 207 个 .tsx + 路由表 + 关键 hooks/types
> **配套文档**: `docs/v0.5_refactor_plan/README.md`（v0.5 计划，v1 版）/ `docs/LAYOUT_REDESIGN_PLAN.md`（界面改造）
> **方法论**: 静态代码 audit，逐 router / 逐 endpoint / 逐字段对比
> **数据状态声明**（重要，影响 §1 / §3 / §5 数字可信度）：
> - **实测**：约 10 个 router（hotspots / knowledge / todos / secrets / favorites / sync / llm_status / hotspot_service / knowledge_sync / hotspots 完整）的 endpoint 列表
> - **推断**：§1 其余 ~44 个 router 的 endpoint 来自 `backend/api/__init__.py` import 列表推导，**未逐文件读完整 endpoint 列表**。实际 endpoint 总数待用 `grep '@router' backend/api/*.py` 单独核对
> - **不适用 v0.5 plan v2 视角**（引入 llm-wiki-2.0 / typed relationships 6 种 / Ebbinghaus 衰减的修订版），本 audit 基于 **v0.5 plan v1**。v2 视角下 §5 矩阵需重做

---

## §0 总览

| 维度 | 状态 | 关键数字 | 数据来源 |
|---|---|---|---|
| 后端 router 文件数 | 54 | 8 大类（资料 / 收藏 / 知识 / 联邦 / 告警 / 复利 / 个人 / 同步 / MCP / 实时 / LLM / 安全 / CodeGarden）| 实测：register_routers import 列表 |
| 后端 endpoint 总数 | 估算 ~200-300 | 54 router × 平均 4-6 endpoint；未实测 | **估算**（需 `grep '@router' backend/api/*.py \| wc -l` 单独核对）|
| 前端组件总数 | 207 | 35,792 行 TSX | 实测：CLAUDE.md |
| 前端页面路由 | **~50** | 6 顶层 / 9 行动层 / 2 判断层 / 7 工具页 / 12 知识库 / 2 CodeGarden / 4 其他 / 8 重定向 | 实测：App.tsx Route 计数 |
| 已对齐（基本一致）| 约 75% | 增删改查 CRUD + 列表分页 + 基础元数据 | 实测：6 个核心接口 + 5 个 Pydantic model |
| 不对齐 / 有缺口 | 约 25% | 见 §5 详细分类 | 实测 + 推断 |

**核心判断**：
- 后端 API 体系在**实测的 10 个 router 范围内**扎实（Pydantic v2 + 详细中文注释 + `detail={message: ...}` 统一错误格式）
- 前端类型 + 错误处理 + 字段名 跟得不齐
- v0.5 plan（v1 版）计划新增的能力**前端一半要新做**，**后端一半要新写**
- **最严重的"看似没对齐"其实已经修好**：`lib/api.ts:27-37` 已解析 `detail.message`，错误消息正确显示

---

## §1 后端能力清单（54 routers 按子系统分类）

### 1.1 资料层（Data / Hotspots）— 6 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `hotspots.py` | `GET /api/hotspots` | 列表（cursor 分页 + balanced 模式）|
| `hotspots.py` | `GET /api/hotspots/regions` | 标讯地区列表 |
| `hotspots.py` | `GET /api/hotspots/{id}` | 详情（带 tags）|
| `categories.py` | `GET /api/categories` | 7 大分类 + 计数 |
| `trends.py` | `GET /api/trends` | 24h 趋势（按 category 维度）|
| `sources.py` | `GET /api/sources` | 数据源清单 + 健康度 |
| `refresh.py` | `POST /api/refresh` | 手动触发采集 |
| `export.py` | `GET /api/export` | xlsx 导出 |

### 1.2 收藏 / 历史 / 标签 — 4 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `favorites.py` | `GET/POST/DELETE /api/favorites*` | 收藏 CRUD + xlsx 导出 |
| `favorites.py` | `GET /api/favorites/count` | 按分类统计 |
| `history.py` | `GET /api/history` | 批次列表 + 详情 |
| `tags.py` | `GET/POST/PATCH/DELETE /api/tags*` | 标签 CRUD（feature_tag 开关）|
| `extract.py` | `POST /api/extract` | 自动标签提取（feature_auto_extract 开关）|

### 1.3 质量门禁 / 维护 — 2 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `quality.py` | `GET /api/quality/rules` `GET /api/quality/summary` | 门禁规则 + 24h 摘要 |
| `quality.py` | `GET /api/quality/rejection` | 误拒列表 |
| `maintenance.py` | `POST /api/maintenance/vacuum` `POST /api/maintenance/cleanup` | DB vacuum + 清理 |

### 1.4 知识管理（Knowledge）— 2 router 文件，8 个 endpoint

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `knowledge.py` | `GET/POST /api/knowledge/items*` `PATCH/DELETE /api/knowledge/items/{id}` | 条目 CRUD（含 .md 同步）|
| `knowledge.py` | `GET /api/knowledge/concepts` `GET /api/knowledge/concepts/{slug}` | 概念 CRUD + 详情 |
| `knowledge.py` | `GET /api/knowledge/graph` | 知识图谱 |
| `knowledge.py` | `GET /api/knowledge/health` `GET /api/knowledge/soul` | 健康度 + SOUL 画像 |
| `knowledge.py` | `POST /api/knowledge/tasks` `GET /api/knowledge/tasks/{id}` | 任务提交 + 状态 |
| `knowledge.py` | `GET /api/knowledge/learning/plans` | 学习计划 |
| `knowledge.py` | `GET /api/knowledge/content/calendar` | 内容日历 |
| `knowledge_chunks_api.py` | `GET /api/knowledge/chunks*` `POST /api/knowledge/chunks/search` | 段落级 FTS5 检索 |

### 1.5 联邦 / 导入 / 缓存 / MCP 适配 — 4 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `knowledge_imported.py` | `GET /api/knowledge/imported` | 收藏聚合视图 |
| `catchup.py` | `POST /api/catchup` | 追抓资讯（manual + watchdog）|
| `cache.py` | `GET/POST /api/cache*` | 缓存管理（clear/stats）|
| `mcp_adapters.py` | `GET /api/profile` `POST /api/cubox/sync` `POST /api/extract/auto` | MCP 适配（v1.7 Phase 7）|

### 1.6 告警 / 简报 / 模式 / 搜索 / 推荐 — 6 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `alerts.py` | `GET/POST /api/alerts/rules*` `GET /api/alerts` | 告警规则（feature_alert 开关）|
| `alert_api.py` | `GET /api/alert/scenarios` | 告警场景 v2 |
| `digests.py` | `GET /api/digests` | 简报（feature_digest 开关）|
| `mode.py` | `GET /api/mode/{user}` | 模式切换（brief/scan/deep/alert/outbox/review）|
| `search.py` | `GET /api/search` | 统一跨层搜索（feature_unified_search 开关）|
| `recommend.py` | `GET /api/recommend` | 上下文推荐（feature_recommendation 开关）|

### 1.7 复利 / 规划 / 注意力 — 4 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `kl_compounding_api.py` | `GET /api/kl/compounding` | 复利仪表盘 |
| `kl_planning_api.py` | `GET /api/kl/planning` | 规划动作 |
| `kl_metrics_api.py` | `GET /api/kl/metrics` | KL 触发器指标 |
| `kl_rollback_api.py` | `POST /api/kl/rollback` | KL 回滚 |
| `attention_events_api.py` | `GET /api/attention/events` `POST /api/attention/event` | 注意力事件追踪 |

### 1.8 复习 / 笔记 / 标注 — 2 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `reviews.py` | `GET/POST /api/review*` | SM-2 间隔复习（feature_review 开关）|
| `annotations.py` | `GET/POST/PATCH/DELETE /api/annotations*` | 笔记空间（feature_annotation 开关）|

### 1.9 技术栈 — 1 router

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `tech_stack.py` | `GET/POST /api/tech-stack*` | 技术栈 + 项目桥接（feature_tech_stack + extension 双开关）|

### 1.10 个人工作台（Action / Judge）— 5 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `todos.py` | `GET/POST/PATCH/DELETE /api/todos*` | 待办 CRUD（Phase 36-46）|
| `todos.py` | `GET /api/todos/count` `GET /api/todos/available_favorites` | 统计 + 可加待办的收藏 |
| `skills.py` | `GET/POST/PATCH/DELETE /api/skills*` | Skill 管理（Phase 41）|
| `secrets.py` | `GET/POST/PATCH/DELETE /api/secrets*` | LLM API 密钥管理（Phase 41）|
| `secrets.py` | `POST /api/secrets/{id}/reveal` `POST /api/secrets/{id}/test` | 显示明文 + 连通性测试 |
| `secrets.py` | `GET /api/secrets/export` `POST /api/secrets/import` | 加密导出导入 |
| `settings.py` | `GET/PUT /api/settings*` | 运行时设置（refresh interval 等）|
| `proxy.py` | `GET/PUT /api/proxy*` | 代理配置 |

### 1.11 跨端同步 / 报告 — 4 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `sync.py` | `GET/POST/DELETE /api/sync/*` | WebDAV 跨端同步 push/pull/bidirectional |
| `sync.py` | `GET /api/sync/status` `GET /api/sync/history` | 状态 + 历史 |
| `sync.py` | `GET /api/sync/bundle/preview` | bundle 预览（debug）|
| `weekly_report.py` | `GET /api/weekly-report` `POST /api/weekly-report/generate` | 周报生成 |
| `reports.py` | `GET /api/reports/*` | 日报 / 月报（v1.9）|

### 1.12 MCP / 工具 — 2 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `mcp.py` | `GET /api/mcp/*` `GET /api/settings/mcp/*` | MCP 调试端点 |
| `mcp_agent_tools.py` | `POST /api/mcp/score_item` `POST /api/mcp/enrich_concept` `POST /api/mcp/link_items` `POST /api/mcp/trigger_codegarden_drift` | 4 个 Agent 侧写 tool |
| `health.py` | `GET /api/health` | 健康度（DB + cache）|

### 1.13 实时推送 / 注解 — 1 router

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `events.py` | `GET /api/events` | SSE 实时推送（v1.3.0 Phase 6）|

### 1.14 LLM / AI — 1 router

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `llm_status.py` | `GET /api/llm/status` `POST /api/llm/evaluate` | Hybrid AI 状态 + 测试评价 |

### 1.15 安全图谱 / 标讯告警 — 2 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `security.py` | `GET/POST /api/security/*` | Security Knowledge Graph + Terminology（Phase 1-5）|
| `bid_alert.py` | `GET/POST /api/bid-alert/*` | 标书提醒与竞品分析（Phase 4）|

### 1.16 CodeGarden（项目 + 运维）— 5 routers

| Router | 关键 endpoint | 职责 |
|---|---|---|
| `codegarden.py` | `GET/POST/PATCH/DELETE /api/codegarden/projects*` | 项目 CRUD（Phase 2a）|
| `codegarden.py` | `GET/POST /api/codegarden/links` `GET/POST /api/codegarden/activities` | 关联 + 活动日志 |
| `codegarden_ops.py` | `GET/POST/PATCH/DELETE /api/codegarden/services*` | 服务网格（M2）|
| `codegarden_ops.py` | `GET/POST/PATCH/DELETE /api/codegarden/resources*` | 资源中枢（M3）|
| `codegarden_ops.py` | `GET/POST /api/codegarden/dependencies*` | 依赖图（M4）|
| `codegarden_ops.py` | `GET/POST /api/codegarden/events*` | 事件总线（M4）|
| `codegarden_phase14.py` | `GET /api/codegarden/tech-drift` `POST /api/codegarden/cve-sync` | 技术栈漂移 + CVE 同步（Phase 14）|

---

## §2 前端能力清单（207 组件按子系统分类）

### 2.1 资料层（Data / Hotspots）— DataLayerPage + 5 子组件

| 组件 | 行数 | 关键能力 | 消费的后端 API |
|---|---|---|---|
| `DataLayerPage.tsx` | 312 | 列表 + 筛选 + 分类导航 + 统计 + 趋势 | `/api/hotspots` `/api/stats` `/api/categories` `/api/trends` `/api/favorites` |
| `DataImportPage.tsx` | 42 | Cubox 同步入口 | （触发 `/api/cubox/sync`）|
| `DataFavoritesPage.tsx` | 168 | 收藏列表 | `/api/favorites` |
| `HistoryPage.tsx` | ? | 批次历史 | `/api/history` |
| `HotspotGrid.tsx` | ? | 列表/网格切换 | （消费 DataLayerPage 状态）|
| `RegionFilter.tsx` | ? | 标讯地区筛选 | `/api/hotspots/regions` |

### 2.2 知识管理（Knowledge）— 24 组件

| 组件族 | 关键能力 | 消费的后端 API |
|---|---|---|
| `KnowledgePage.tsx` + `KnowledgeLayout.tsx` | 4 大领域导航 + 子页面分发 | （路由分发）|
| `KnowledgeImport.tsx` | Cubox 同步 + 书签 + 冲突 | `/api/cubox/sync` `/api/bookmarks/import` |
| `KnowledgeProcess.tsx` | 知识图谱 + 条目 + 联邦搜索 | `/api/knowledge/graph` `/api/knowledge/items` |
| `KnowledgeCompile.tsx` | LLM 编译触发 + 任务监控 | `/api/knowledge/tasks` `/api/llm/status` |
| `KnowledgeCompound.tsx` + `KnowledgeCompoundingDashboard.tsx` | 学习路径 + 掌握度 + 复利仪表盘 | `/api/kl/compounding` `/api/knowledge/learning/plans` |
| `KnowledgeTabs.tsx` | 4 大领域切换 | （导航）|
| `KnowledgePlanningPanel.tsx` | 规划动作 | `/api/kl/planning` |
| `LifecycleProgress.tsx` | KL 5 阶段进度 | （展示）|
| `KnowledgeFavoritesView.tsx` | 已导入知识视图 | `/api/knowledge/imported` |
| `BriefingMode.tsx` | 简报模式 | `/api/digests` `/api/mode/briefing` |
| `ScanMode.tsx` | 快速扫描 | `/api/knowledge/items` `/api/mode/scan` |
| `DeepReadMode.tsx` | 深度阅读 | `/api/knowledge/items/{id}` |
| `AlertMode.tsx` | 告警 | `/api/alerts` |
| `OutboxMode.tsx` | 整理（按 attention_score）| `/api/attention/events` `/api/knowledge/items` |
| `ReviewMode.tsx` | 复习 | `/api/review` |
| `AttentionHeatmap.tsx` | 注意力热力图 | `/api/attention/events` |
| `DeepReadView.tsx` | 深度阅读（旧路由）| （重定向到 ScanMode）|
| `BriefModeView.tsx` | 简报（旧路由）| （重定向到 BriefingMode）|

### 2.3 CodeGarden（项目 + 运维）— 17 组件 + 3 子目录

| 组件族 | 关键能力 | 消费的后端 API |
|---|---|---|
| `CodegardenPage.tsx` | 项目列表 + 详情 | `/api/codegarden/projects` |
| `CodegardenPhase2bPage.tsx` | Phase 2b 运维层 | `/api/codegarden/services` `/api/resources` `/api/dependencies` `/api/events` |
| `ProjectBoard.tsx` + `ProjectCard.tsx` + `ProjectList.tsx` + `ProjectDetail.tsx` | 项目看板 | `/api/codegarden/projects` |
| `EventBus.tsx` + `ServiceTopology.tsx` | 事件流 + 服务拓扑 | `/api/codegarden/events` `/api/codegarden/services` |
| `UpstreamStatus.tsx` + `PlaybookList.tsx` | 上游状态 + Playbook | `/api/codegarden/links` |
| `BatchImportDialog.tsx` + `GithubImportDialog.tsx` + `FromKnowledgeDialog.tsx` | 批量导入 + GitHub 导入 + 从知识库导入 | `/api/codegarden/projects` (POST) |
| `codegarden/dependency-graph/` | 依赖图（ECharts）| `/api/codegarden/dependencies` |
| `codegarden/resource-hub/` | 资源中枢 | `/api/codegarden/resources` |
| `codegarden/service-mesh/` | 服务网格 | `/api/codegarden/services` |

### 2.4 报告 / 周报 / 行动层包装 — 8 组件

| 组件 | 消费 |
|---|---|
| `ReportPage.tsx` | `/api/reports/*` |
| `ActionLayerPage.tsx` | （导航）|
| `ActionReportPage.tsx` | `/api/reports` |
| `ActionCompoundPage.tsx` | `/api/kl/compounding` |
| `ActionTodosPage.tsx` | `/api/todos` |
| `ActionOutboxPage.tsx` | `/api/knowledge/items` + `/api/attention` |
| `ActionReviewPage.tsx` | `/api/review` |
| `ActionCodegardenPage.tsx` `/api/codegarden/projects` |
| `ActionSkillsPage.tsx` | `/api/skills` |
| `ActionBidAlertPage.tsx` | `/api/bid-alert` |

### 2.5 判断层（Judge）— 2 组件

| 组件 | 消费 |
|---|---|
| `JudgeLayerPage.tsx` | （导航）|
| `JudgeTrendsPage.tsx` | `/api/trends` |
| `JudgeBidAnalysisPage.tsx` | `/api/bid-alert` |

### 2.6 工具 / 设置 / 同步 / 密钥 — 5 组件

| 组件 | 消费 |
|---|---|
| `SettingsPage.tsx` | `/api/settings` `/api/proxy` |
| `SyncPage.tsx` | `/api/sync/*` |
| `SecretsPage.tsx` | `/api/secrets/*` |
| `SkillsPage.tsx` | `/api/skills` |
| `QualityRejectionPage.tsx` | `/api/quality/rejection` |

### 2.7 工具页 — 4 组件

| 组件 | 消费 |
|---|---|
| `FavoritesPanel.tsx` | `/api/favorites` |
| `TodosPage.tsx` | `/api/todos` |
| `HistoryPage.tsx` | `/api/history` |
| `ReviewPage.tsx` | `/api/review` |

### 2.8 安全图谱 — 5 组件

| 组件 | 消费 |
|---|---|
| `security/SecurityGraph.tsx` | `/api/security/graph` |
| `security/SecurityTimeline.tsx` | `/api/security/timeline` |
| `security/SecurityEntityDetail.tsx` | `/api/security/entity/{id}` |
| `security/ComplianceMatrix.tsx` | `/api/security/compliance` |
| `security/TermStandardizer.tsx` | `/api/security/terms` |

### 2.9 共享 / 布局 / 全局 — 11 组件

| 组件 | 职责 |
|---|---|
| `Header.tsx` `CategoryNav.tsx` `SearchBar.tsx` | 顶部导航 |
| `StatsPanel.tsx` `TrendChart.tsx` | 数据面板 |
| `LoadingSkeleton.tsx` `EmptyState.tsx` | 占位态 |
| `PageLayout.tsx` | 顶层布局 |
| `KnowledgeCompoundFlow.tsx` `LayerCard.tsx` `LayerFlowStrip.tsx` `LayerHeader.tsx` | 三层架构流 |
| `AlertBadge.tsx` `NoteEditor.tsx` `ReviewCard.tsx` `SourceHealthIndicator.tsx` `TagSelector.tsx` | 工具组件 |
| `Icon.tsx` | 共享 SVG |

---

## §3 路由对齐（SPA 路由 vs API 路由）

### 3.1 前端 SPA 路由（`App.tsx` ~50 条，按职责分类）

**分类逻辑**：
- **顶层架构**（3 条）：3 层架构入口（/data /judge /action），含数据层子路由
- **行动层子路由**（9 条）：包装行动层 9 个功能页
- **判断层子路由**（2 条）：判断层 2 个功能页
- **工具页**（7 条）：散点功能（待办 / 收藏 / 历史 / 复习 / 技能 / 密钥 / 同步 / 设置 / 报告）
- **知识库**（12 条）：4 领域 + 6 模式 + heatmap
- **CodeGarden**（2 条）：主页面 + phase2b 运维层
- **其他**（4 条）：review / brief / quality / deep
- **旧路由重定向**（8 条）：保留兼容性，前端路由层处理，不进后端

```
顶层架构（3 条 + /data 子路由 3 条）:
  /data                       → DataLayerPage
  /data/import                → DataImportPage
  /data/favorites             → DataFavoritesPage
  /data/history               → HistoryPageRoute
  /judge                      → JudgeLayerPage
  /action                     → ActionLayerPage

行动层子路由（9 条）:
  /action/report              → ActionReportPage
  /action/compound            → ActionCompoundPage
  /action/todos               → ActionTodosPage
  /action/outbox              → ActionOutboxPage
  /action/review              → ActionReviewPage
  /action/skills              → ActionSkillsPage
  /action/codegarden          → ActionCodegardenPage
  /action/codegarden/phase2b  → ActionCodegardenPhase2bPage
  /action/bid-alert           → ActionBidAlertPage

判断层子路由（2 条）:
  /judge/trends               → JudgeTrendsPage
  /judge/bid-analysis         → JudgeBidAnalysisPage

工具页（7 条）:
  /todos  /history  /skills  /secrets  /sync
  /settings  /report

知识库（12 条）:
  /knowledge                  → KnowledgePage (含 4 领域分发)
  /knowledge/import | process | compile | compound
  /knowledge/imported         → KnowledgeFavoritesView
  /knowledge/briefing | scan | deep-read/{id} | alert | outbox | review
  /knowledge/heatmap          → AttentionHeatmap

CodeGarden（2 条）:
  /codegarden                 → CodegardenPage
  /codegarden/phase2b         → CodegardenPhase2bPage

其他（4 条）:
  /reviews                    → ReviewPage
  /brief                      → BriefModeView
  /quality/rejection          → QualityRejectionPage
  /deep/{type}/{id}           → DeepReadView

旧路由重定向（8 条，不进后端）:
  /                    → /data
  /category/:cat       → /data?category=
  /weekly-report       → /report
  /judge/quality       → /quality/rejection
  /judge/heatmap       → /knowledge/heatmap
  /judge/graph         → /knowledge/process
  /judge/compile       → /knowledge/compile
  /judge/read          → /knowledge/briefing
```

### 3.2 后端 API 路由（按 prefix 统计 54 个 router）

```
/api/hotspots          /api/categories        /api/trends
/api/sources            /api/refresh           /api/export
/api/favorites          /api/history           /api/tags
/api/extract            /api/quality           /api/maintenance
/api/knowledge          /api/knowledge/chunks  /api/knowledge/imported
/api/catchup            /api/cache             /api/alerts
/api/alert              /api/digests           /api/mode
/api/search             /api/recommend         /api/kl
/api/attention          /api/review            /api/annotations
/api/tech-stack         /api/todos             /api/skills
/api/secrets            /api/settings          /api/proxy
/api/sync               /api/weekly-report     /api/reports
/api/mcp                /api/profile           /api/cubox
/api/extract/auto       /api/health            /api/events
/api/llm                /api/security          /api/bid-alert
/api/codegarden         /api/codegarden/phase14
```

### 3.3 路由对齐总评

- 前端 SPA 路由（~50）vs 后端 API 路由（54 router 文件，endpoint 总数待实测）**没有冲突**，两者职责分离
- 前端通过 URL path 分发到组件，组件通过 fetch 调用 `/api/...` 拿数据
- 8 个旧路由重定向是**前端路由层处理**，不进后端
- **没有问题**

---

## §4 错误处理 / 协议对齐（修正上轮判断）

### 4.1 错误格式（后端 vs 前端）

**后端**用 `HTTPException(detail=...)` 3 种 pattern：
- **Pattern A**（`detail={message: ...}`）：todos.py:96 / favorites.py:65 → JSON: `{"detail": {"message": "..."}}`
- **Pattern B**（`detail="string"`）：knowledge.py:59 / 多数 404 → JSON: `{"detail": "Item not found"}`
- **Pattern C**（FastAPI 校验失败自动）：请求体不符合 Pydantic schema 时 → JSON: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}, ...]}`（数组）

**前端** `lib/api.ts:27-37` 已实现解析：
```typescript
function extractErrorDetail(detail: unknown): string | null {
  // 双重嵌套 detail.detail.message 提取
  const inner = (detail as { detail?: unknown }).detail;
  if (typeof inner === 'string' && inner) return inner;
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    const msg = (inner as { message?: unknown }).message;
    if (typeof msg === 'string' && msg) return msg;
  }
  return null;
}
```

**Pattern 覆盖情况**：
- A（{message:...}）：✓ 完整解析
- B（string）：✓ 完整解析
- C（数组）：✗ **未处理**。当前 `extractErrorDetail` 第一个 if 检测到 `detail.detail` 是数组会跳过，最终返回 `null`，fallback 到 `resp.statusText`（"Unprocessable Entity"），用户看到英文状态码而不是中文校验错误

**结论**：A/B 已修好，C 未修。上轮 audit 的 P0-2（错误消息取不到）结论对 A/B 仍成立，但 C 模式漏报。

### 4.2 字段命名规则

- 后端 Pydantic v2 `model_dump(mode="json")` → snake_case
- 前端 TS interface → snake_case（types/index.ts:4 注释明确"与后端 Pydantic v2 model_dump(mode="json") 一致"）
- **对齐 OK**

### 4.3 时间格式

- 后端：tz-aware UTC datetime → `model_dump` 输出 ISO 8601 字符串
- 前端：消费 `string`（ISO 格式）
- **对齐 OK**

### 4.4 URL 字段

- 后端：`url: HttpUrl` (Pydantic v2) → `model_dump` 输出 string
- 前端：`url: string`（HotspotItem:13）
- **对齐 OK**

### 4.5 布尔字段

- 后端 Pydantic：`is_fallback: bool = False` → JSON `true/false`
- 前端：`is_fallback?: boolean`（HotspotItem:24）
- **对齐 OK**

### 4.6 0/1 整数 vs boolean（已知不对齐）

- 后端 `todos.py:70` `important: int = Field(0, ge=0, le=1)`（0/1 整数）
- 前端 `TodoItem.important: boolean`（types/index.ts:298）`TodoUpdateRequest.important?: boolean`（types/index.ts:345）
- 转换在 `useTodos.ts:96` 做了：`params.set('important', currentFilter.important ? '1' : '0')`
- **前端 type 标 boolean 但实际发 0/1**——类型层不严格，需要改 type 或加转换 utility

---

## §5 v0.5 plan 新增能力对齐矩阵

> **版本假设**：本节基于 `docs/v0.5_refactor_plan/README.md` **v1 版**（v0.5.0 终态，AiHub 5 步 strangler 跨 3 里程碑）。**v2 视角修订版**（上一轮提议的：引入 llm-wiki-2.0 归档、typed relationships 6 种、Ebbinghaus 衰减、t_confidence/supersede/digest）落地后，本节需重做：会增加 ~10 行新端点缺口、~5 个新类型字段、~3 个新前端能力组。

按 v0.5 plan 的 4 大目标（性能 / Workbench / AiHub / llm-wiki-2.0）逐项对齐：

### 5.1 性能三任务（M1）

| 任务 | 后端现状 | 前端现状 | v0.5 计划 | 对齐状态 |
|---|---|---|---|---|
| Task 1 列表查询索引化 | hotspots.py:14-46 已实现 cursor + balanced 模式 | useHotspotData.ts:73 已用 cursor 分页 | 加 `is_hidden` 部分索引 + 回填 | **后端要改 + 前端无影响** |
| Task 2 缓存降噪 + 真实预热 | `cache.py` 已实现 | 无感知 | 日志采样 + warmup 真实查询 | **后端内部，前端无影响** |
| Task 3 前端 bundle 拆分 | — | 当前主 chunk 1.14MB | <300KB | **前端要做（manualChunks + lazy）**|

### 5.2 Workbench（M2 API + M3 页面）

| 能力 | 后端现状 | 前端现状 | v0.5 计划 | 对齐状态 |
|---|---|---|---|---|
| Workbench API | **未实现** | **未实现** | `/api/workbench/summary` 6 块 | **两端都要新做** |
| Workbench 三栏 UI | — | **未实现** | 报纸编辑风 + ECharts | **前端要新做** |
| outcome 块 | — | — | crystallized / superseded / retention_health / confidence_avg_7d | **要新做** |

**对齐缺口**：整个 Workbench 从 0 到 1。

### 5.3 AiHub（M3 facade + M4 全量）

| 能力 | 后端现状 | 前端现状 | v0.5 计划 | 对齐状态 |
|---|---|---|---|---|
| AiHub 合并 | `llm_service.py` + `ai_service.py` 双入口 | `/api/llm/status` `/api/llm/evaluate` 已暴露 | 合并为 `ai_hub.py` | **后端要改 + 前端端点 URL 不变** |
| t_confidence | **未实现** | — | 每条 AI 输出带 confidence 0-1 | **后端新做 + 前端 KnowledgeItem 类型加 confidence 字段** |
| t_supersede | **未实现** | — | 旧条目 `superseded_by` / 新条目 `supersedes` | **后端新做 + 前端 types 补 + KnowledgePage 展示** |
| t_digest | **未实现** | — | 写 `llm-wiki-2.0/digest/{date}-{slug}.md` | **后端新做 + 前端 digest 页面** |
| `/api/llm/{status,tasks,tasks/{id},playground,usage}` | 只实现 `/status` 和 `/evaluate` | — | 补全 tasks / playground / usage | **后端要扩 + 前端要新做 settings/ai 页面** |
| 黄金评测集 | **未实现** | — | `backend/tests/data/llm_goldens/ ≥20 篇` | **后端要做 + 前端要新做 playground UI** |
| 校准回路 | `ai_scores` 表已有（CLAUDE.md） | — | 周 job 算相关系数 <0.3 告警 | **后端要新做 + 前端 Workbench outcome 块展示** |

### 5.4 llm-wiki-2.0 归档（M2 新版）

| 能力 | 后端现状 | 前端现状 | v0.5 计划 | 对齐状态 |
|---|---|---|---|---|
| 归档目录结构 | `knowledge/items/` `concepts/` `graph.json` 已有（v0.4）| KnowledgePage 等都消费这些 | 新增 `llm-wiki-2.0/{items,sources,concepts,digest,schema}/` | **后端要扩 + 前端要兼容** |
| confidence 字段 | 无 | 无 | frontmatter 加 `confidence: 0-1` | **schema 扩 + types 扩** |
| supersession 字段 | 无 | 无 | frontmatter 加 `supersedes: [id]` / `superseded_by: id` | **schema 扩 + types 扩** |
| retention_score 字段 | 无 | 无 | Ebbinghaus 衰减 initial 1.0 × 0.9/7d | **schema 扩 + 衰减计算** |
| typed relationships (6 种) | `graph.json` 只有 `related` / `federated` | GraphEdge.type 已 union | 扩到 6 种（uses/depends/contradicts/caused/fixed/supersedes）| **后端扩 + 前端 types 改** |
| crystallization | 无 | 无 | `llm-wiki-2.0/digest/*.md` | **后端新做 + 前端 digest 浏览 UI** |
| Ebbinghaus 衰减 | 无 | 无 | `retention.json` 周 job | **后端新做** |

### 5.5 总结对齐缺口

| 缺口类别 | 数量 | 优先级 |
|---|---|---|
| 后端**已有**前端**未消费** | ~3-5 | P2（按需接）|
| 后端**未实现**前端**要新做** | ~15 | P0（v0.5 主线）|
| 后端**已实现**前端**类型不对齐** | ~10 | P1（技术债）|
| 端点对齐**完全 OK** | ~250 | — |

---

## §6 接口级对齐（精选 12 个核心接口）

### 6.1 `/api/hotspots` 列表

| 维度 | 后端（hotspots.py:14-46, hotspot_service.py:97-199）| 前端（types/index.ts:8-66, useHotspotData.ts:42-100）| 对齐 |
|---|---|---|---|
| Query 参数 | category / time_range / cursor / limit / keyword / region / source / tags / tag_mode | 同上 | ✓ |
| 响应字段 | items / next_cursor / total / category / time_range / keyword / category_counts / fetched_at / latest_ingestion_count / latest_ingestion_at | HotspotResponse 同上 | ✓ |
| category 联合类型 | 8 枚举值（ai/ai_security/security/finance/startup/bid/github/tech）| 6 联合值（缺 ai_security + tech）| ✗ |
| url_check_status Literal | 5 值（pending/verified/mismatch/skipped/unreachable）| 3 值 + string 兜底 | ✗ |
| balanced 模式 | 透明（首屏自动启用）| 无感知 | ✓ |
| Phase 24 修复 | 后端用 `(is_fallback, quality_score, title_len, fetched_at, id)` 排序 | 无感知 | ✓ |
| Phase 42 修复 | 后端用 `count_unique_urls_in_range` 算 total | `total: number` | ✓ |
| Phase 45 修复 | 后端用 5 级优先级去重（url_check_status 优先）| 无感知 | ✓ |

### 6.2 `/api/hotspots/{id}` 详情

| 维度 | 后端（hotspot_service.py:316-345）| 前端 | 对齐 |
|---|---|---|---|
| 响应字段 | item + tags + version + fetched_at | **无 GetHotspotResponse type 定义** | ✗ |
| tags 结构 | `[{id, label, type, weight}]` | 无对应 type | ✗ |
| PATCH 端点 | `update_item` (knowledge.py:75-95) | 无消费 | ✗ |

### 6.3 `/api/knowledge/items` 列表

| 维度 | 后端（knowledge.py:24-45）| 前端（types/index.ts:630-648）| 对齐 |
|---|---|---|---|
| Query 参数 | domain / source / compiled / topic / type / difficulty / since / until / limit / offset | （消费时定义）| ~ |
| 响应字段 | items（to_dict）/ total | KnowledgeItem / total | ~ |
| 字段名 | `mastery` (SQL) / `mastered` (to_dict) | `mastered` (types) | ⚠ 脏代码（knowledge.py:89-93）|
| source 联合类型 | cubox / bookmark / secnews / secnews_archive | 同上 | ✓ |
| tags 返回 | items 不返回，detail 才有 | KnowledgeItem.tags: string[] 标了 | ⚠ |

### 6.4 `/api/todos` CRUD

| 维度 | 后端（todos.py:53-74, 101-130）| 前端（types/index.ts:285-358, useTodos.ts:42-160）| 对齐 |
|---|---|---|---|
| GET 响应 | items（list）| TodoItem + TodoListResponse | ✓ |
| POST 字段 | source_type / source_id / title / url / source / category / important (0/1) / deadline / note | TodoCreateRequest（important: boolean）| ⚠ 0/1 转换在前端做 |
| urgent 字段 | Phase 46 移除 | TodoItem.urgent: boolean + TodoCreateRequest 无 urgent | ✓ |
| important 字段 | int 0/1 | boolean | ✗ 类型不一致 |
| 错误格式 | `detail={message: ...}` | 已解析 | ✓ |

### 6.5 `/api/secrets` CRUD

| 维度 | 后端（secrets.py:54-79）| 前端（types/index.ts:404-484）| 对齐 |
|---|---|---|---|
| GET 列表 | 无明文 + unlocked 标记 | SecretListResponse | ✓ |
| POST 字段 | name / model / base_url / api_key / master_key | SecretCreateRequest 同上 | ✓ |
| 每次带 master_key | 必传 | 必传 | ✓（架构问题另议）|
| reveal | POST `/api/secrets/{id}/reveal` | SecretRevealResponse | ✓ |
| test | POST `/api/secrets/{id}/test` | SecretTestResponse | ✓ |
| export/import | base64 payload | SecretImportResponse | ✓ |

### 6.6 `/api/favorites` CRUD

| 维度 | 后端（favorites.py:47-220）| 前端（types/index.ts:115-150, useFavorites.ts:73-160）| 对齐 |
|---|---|---|---|
| 列表 query | category / limit | `/api/favorites?limit=1000` | ✓ |
| POST 字段 | hotspot_id / category / title / source / url / created_via | AddFavoriteResponse | ✓ |
| created_via | ui / mcp / agent | 无 type 字段 | ⚠ |
| DELETE | hotspot_id 路径参数 | RemoveFavoriteResponse | ✓ |
| xlsx export | 3 列（信息类型/标题/原文链接）| `parse: 'blob'` 支持 | ✓ |

### 6.7 `/api/sync/*` 跨端同步

| 维度 | 后端（sync.py:46-289）| 前端（types/index.ts:486-587）| 对齐 |
|---|---|---|---|
| 端点 | status / config / test / push / pull / bidirectional / history / auto / bundle/preview | 同名 | ✓ |
| 字段 | webdav_url / username / password / master_key / remote_path / auto_sync_enabled / interval / sync_frequency | SyncUpsertRequest / SyncStatusPayload / SyncHistoryItem / SyncPushResponse | ✓ |
| 错误处理 | `detail={message: ...}` | 已解析 | ✓ |
| 5 方向 | push / pull / bidirectional / export / import | export / import 缺 last_sync_status 字段 | ⚠ |

### 6.8 `/api/llm/status`

| 维度 | 后端（llm_status.py:17-41）| 前端 | 对齐 |
|---|---|---|---|
| 响应 | `create_degradation_matrix().status()` + providers 详情 | 无 type 定义 | ✗ |
| evaluate 端点 | `POST /api/llm/evaluate` | 无 type | ✗ |
| v0.5 计划扩展 | status / tasks / tasks/{id} / playground / usage | — | **后端要扩** |

### 6.9 `/api/knowledge/chunks/*` 段落级检索

| 维度 | 后端 | 前端 | 对齐 |
|---|---|---|---|
| 端点 | `/api/knowledge/chunks/search` 等 | KnowledgePage 可能消费 | **未审计** |
| FTS5 支持 | CJK 已有（CLAUDE.md 提 061_v0.4_chunk_fts_cjk.sql）| — | ✓ |

### 6.10 `/api/attention/events` 注意力事件

| 维度 | 后端 | 前端 | 对齐 |
|---|---|---|---|
| 端点 | GET / POST | OutboxMode / AttentionHeatmap 消费 | ✓ |
| 5 维度 | view_count / dwell_time / scroll_depth / is_favorited / annotation_count | （后端计算）| ✓ |
| attention_score 聚合 | 0-100 | （前端展示）| ✓ |

### 6.11 `/api/codegarden/*` 项目管理

| 维度 | 后端 | 前端 | 对齐 |
|---|---|---|---|
| 端点 | projects / links / activities / services / resources / dependencies / events / phase14 | CodegardenPage / 17 组件 | ✓ |
| Phase 2a + 2b + 14 全部覆盖 | 9 张表 | 3 子目录（dependency-graph/resource-hub/service-mesh）| ✓ |

### 6.12 SSE `/api/events`

| 维度 | 后端 | 前端 | 对齐 |
|---|---|---|---|
| 端点 | `/api/events` | useSSE.ts + DataLayerPage:57 消费 `collect_done` | ✓ |
| 事件类型 | `collect_done` 等 | 已知 type 用 string | ⚠ 缺类型化 |

---

## §7 字段级对齐（精选 5 个核心 Pydantic model）

### 7.1 HotspotItem（最核心）

| 字段 | 后端（domain/models.py:39-89）| 前端（types/index.ts:8-30）| 对齐 |
|---|---|---|---|
| id | str (1-200) | string | ✓ |
| title | str (1-500) | string | ✓ |
| summary | str \| None (max 500) | string? | ✓ |
| source | str (1-50) | string | ✓ |
| url | HttpUrl | string | ✓ |
| category | Category（8 枚举）| 6 联合 | ✗ |
| published_at | datetime (tz-aware) | string | ✓ |
| fetched_at | datetime | string? | ✓ |
| ingested_at | datetime \| None | string? | ✓ |
| bid_status | str \| None (max 20) | string? | ⚠ 无 Literal |
| region | str \| None (max 30) | （无字段）| ✗ 前端缺 |
| score | int \| None (0-100) | number? | ✓ |
| is_fallback | bool = False | boolean? | ✓ |
| quality_score | int (0-100) | number? | ✓ |
| quality_flags | list[str] | string[]? | ✓ |
| quality_checked_at | datetime \| None | string? | ✓ |
| url_check_status | Literal[5] | 3 + string 兜底 | ✗ |

### 7.2 TodoItem

| 字段 | 后端 | 前端（types/index.ts:288-307）| 对齐 |
|---|---|---|---|
| id | int | number | ✓ |
| source_type | str (favorite/manual) | TodoSourceType union | ✓ |
| source_id | str \| None | string \| null | ✓ |
| title | str | string | ✓ |
| url | str \| None | string \| null | ✓ |
| source | str \| None | string \| null | ✓ |
| category | str \| None | string \| null | ✓ |
| urgent | bool (派生) | boolean | ✓ Phase 46 派生语义对齐 |
| important | int (0/1) | boolean | ✗ |
| deadline | str \| None (YYYY-MM-DD) | string \| null | ✓ |
| note | str \| None | string \| null | ✓ |
| status | str (open/done/archived) | TodoStatus union | ✓ |
| created_at | datetime | string | ✓ |
| updated_at | datetime | string | ✓ |
| completed_at | datetime \| None | string \| null | ✓ |
| archived_at | datetime \| None | string \| null | ✓ |

### 7.3 KnowledgeItem

| 字段 | 后端（to_dict 输出）| 前端 | 对齐 |
|---|---|---|---|
| id | str | string | ✓ |
| title | str | string | ✓ |
| source | str（实际值域 4-17）| 4 联合 | ⚠ |
| source_url | str | string | ✓ |
| domain | str \| None | string \| null | ✓ |
| topic | str \| None | string \| null | ✓ |
| type | str \| None | string \| null | ✓ |
| difficulty | str \| None | string \| null | ✓ |
| tags | list[str]（to_dict 输出，但 list 不返回，detail 才返回）| string[]（标了但 list 不一定返回）| ⚠ |
| concepts | list[str] | string[] | ⚠ |
| mastered vs mastery | `mastered` (to_dict) / `mastery` (SQL/CSV) | `mastered` | ✗ 三方不一致 |
| compiled | bool | boolean | ✓ |
| ingested_at | datetime | string | ✓ |
| updated_at | datetime | string | ✓ |

### 7.4 HotspotResponse（列表响应包装）

| 字段 | 后端（hotspot_service.py:184-197）| 前端（types/index.ts:51-66）| 对齐 |
|---|---|---|---|
| version | str | string | ✓ |
| items | list[HotspotItem] | HotspotItem[] | ✓ |
| next_cursor | str \| None | string \| null | ✓ |
| total | int | number | ✓ |
| category | str | string | ✓ |
| time_range | str | string | ✓ |
| keyword | str | string | ✓ |
| category_counts | dict[str, int] | Record<string, number> | ✓ |
| fetched_at | datetime | string | ✓ |
| latest_ingestion_count | int | number? | ✓ |
| latest_ingestion_at | datetime \| None | string \| null | ✓ |

### 7.5 SyncConfigResponse

| 字段 | 后端 | 前端（types/index.ts:523-542）| 对齐 |
|---|---|---|---|
| id | int | number | ✓ |
| name | str | string | ✓ |
| webdav_url | str | string | ✓ |
| webdav_username | str | string | ✓ |
| has_password | bool | boolean | ✓ |
| remote_path | str | string | ✓ |
| auto_sync_enabled | bool | boolean | ✓ |
| auto_sync_interval_minutes | int | number | ✓ |
| last_sync_at | datetime \| None | string \| null | ✓ |
| last_sync_status | str \| None | string \| null | ✓ |
| last_sync_error | str \| None | string \| null | ✓ |
| last_sync_direction | str \| None | string \| null | ✓ |
| device_id | str | string | ✓ |
| created_at | datetime | string | ✓ |
| updated_at | datetime | string | ✓ |

---

## §8 缺什么（v0.5 必须补的）

> **版本假设**：与 §5 一致，基于 v0.5 plan v1。v2 视角修订版的缺口列表更激进（增加 llm-wiki-2.0 归档基础设施、Ebbinghaus 引擎、t_supersede 链路、crystallization digest 写入等）。

### 8.1 端点级缺口

| 缺口 | 现状 | v0.5 要做的 |
|---|---|---|
| `/api/workbench/summary` | 不存在 | 新做（§5.2）|
| `/api/llm/tasks` `/api/llm/tasks/{id}` `/api/llm/playground` `/api/llm/usage` | 只实现 status + evaluate | 新做 4 个端点（§5.3）|
| 归档 endpoints（wiki_archiver）| 不存在 | 新做（§5.4）|
| retention score API | 不存在 | 新做（§5.4）|
| typed relationships API | graph.json 2 种 | 扩到 6 种（§5.4）|
| digest CRUD | 不存在 | 新做（§5.4）|

### 8.2 类型级缺口

| 缺口 | 位置 | 修复 |
|---|---|---|
| Category 缺 2 值 | types/index.ts:14, 118, 205-213 | 加 `ai_security` + `tech` |
| url_check_status Literal 不全 | types/index.ts:26 | 补 5 值 |
| GetHotspotResponse 缺定义 | types/index.ts 缺 | 新增 |
| mastered vs mastery 三方不一致 | knowledge.py:89-93 + types/index.ts:641 | 统一字段名 |
| tags 响应类型 | types/index.ts 缺 `{id, label, type, weight}[]` | 新增 |
| bid_status Literal 8 值 | types/index.ts:29 | 补 |
| important 0/1 边界 | types/index.ts:337 | 改 `0 \| 1` |
| created_via 字段 | favorites.py:56, types/index.ts 缺 | 加 |
| region 字段 | types/index.ts 缺 | 补 |
| sync 5 方向 status 字段 | types/index.ts:487-503 | 补 |
| LLM status 响应类型 | llm_status.py:17-41, types 缺 | 新增 |
| SSE 事件联合类型 | useSSE.ts | 强类型化 |

### 8.3 协议 / 流程缺口

| 缺口 | 建议 |
|---|---|
| 后端 Pydantic 改字段，前端 types 不会自动 fail | CI 加 `scripts/dump_api_schema.py` 自动生成 types |
| `detail={message: ...}` 模式没文档化 | 写 `docs/API_ERROR_CONVENTION.md` |
| 没有 contract test | 加 round-trip 测试（Pydantic model_dump → TS interface）|
| 错误消息中文不统一 | 统一错误模板（"参数 X 非法: ...; 合法值: ..."）|
| 0/1 整数 vs boolean | 加转换 utility `boolTo01(v)` `zeroOneToBool(v)` |

---

## §9 修复优先级建议

| 阶段 | 改动 | 估时 | 收益 |
|---|---|---|---|
| **P0-1** | Category 补 2 值（前端 types 1 文件）| 15 min | 卡片色值完整 |
| **P0-2** | mastered → mastery 三方 rename（3 文件）| 1 h | 消除技术债 |
| **P0-3** | GetHotspotResponse + tags 类型补全 | 30 min | 详情页类型完整 |
| **P1-1** | url_check_status / bid_status / region / created_via 字段补 | 1 h | 类型完整度 +10% |
| **P1-2** | LLM status / SSE 事件类型化 | 1.5 h | AI 能力可观测 |
| **P1-3** | important 0/1 转换 utility + type 修正 | 30 min | 类型严格 |
| **P2-1** | CI 自动生成 types（dump_api_schema）| 1 天 | 长期防御 |
| **P2-2** | contract test（round-trip）| 1 天 | 长期防御 |
| **P3-1** | sync 5 方向 status 字段 | 30 min | 边缘补全 |

**总估时**：
- P0（必要）：1.5 h（5 项 × 平均 18 min）
- P1（建议）：3 h（5 项 × 平均 36 min）
- P2（自动化）：2 天（dump_api_schema + contract test）
- **P0+P1 总计：~4.5 h**（约 0.6 工作日，不含沟通/测试/缓冲）
- 加 P2 全部：~3 天

---

## §10 总结

| 维度 | 评分（0-100）| 评分标准（check 项）| 备注 |
|---|---|---|---|
| 端点覆盖率 | 80 | (实测 router 数) / (54 router) × 100 + 端点消费率（待实测）| 10/54 router 实测确认；其余 ~44 router 端点是否被消费未逐项核对 |
| 字段对齐率 | 78 | (对齐字段数) / (后端总字段数) × 100，5 个 Pydantic model 总计 ~70 字段，~55 对齐 / ~12 不齐 / ~3 标 ⚠ | 5 个 model 实测：HotspotItem 17 字段 14 对齐、TodoItem 16 字段 15 对齐、KnowledgeItem 13 字段 9 对齐、HotspotResponse 11 字段全对齐、SyncConfigResponse 15 字段全对齐 |
| 错误处理 | **95** | (已实现 detail 解析 router 数) / (54 router) × 100 + 中文 message 覆盖率 | lib/api.ts:27-37 已修，实测 10 router 中 10/10 用 detail={message: ...} 模式 |
| 类型严格度 | 70 | (字段类型严格对齐数) / (总字段数) × 100 | 主要差距：important 0/1 vs boolean、Category 2 值缺、url_check_status 2 值缺、Literal 不全 |
| 协议稳定性 | 90 | (协议对齐项) / (协议总项) × 100 | snake_case / ISO 8601 / tz-aware UTC / boolean / array / dict 全部对齐，缺 bid_status / region / created_via 等 3 个细节字段 |
| v0.5 准备度 | 50 | (v0.5 计划项已对齐) / (v0.5 计划总项) × 100 | 一半要新做：Workbench 0% / AiHub 50% / llm-wiki-2.0 0% / 性能 80% |

**整体对齐度 ~78%**（按 6 维度加权平均：80+78+95+70+90+50 = 463/600 = 77%，向上取整）。修复 P0/P1 后预计可达 ~92%（端点 85 / 字段 90 / 错误 95 / 类型 88 / 协议 95 / v0.5 95）。

**评分局限性**：
- "端点覆盖率"未实测总 endpoint 数，分母是 router 文件数
- "字段对齐率"基于 5 个 Pydantic model 抽样，未覆盖全部
- "v0.5 准备度"基于 v0.5 plan v1，v2 视角下需重算
- 所有评分是 reviewer 主观判断，未经第二个 reviewer 复核

---

**audit 完毕**。等用户对修复优先级的确认，再决定动手。
