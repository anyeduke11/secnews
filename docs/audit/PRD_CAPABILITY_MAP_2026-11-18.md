# PRD 能力四向映射（B4–B6 防功能丢失基线）

> 依据：`docs/FRONTEND_REWRITE_V1_PLAN.md` §7.3（能力映射前置门，代号 G2）。
> 定位证据日期：2026-11-18。**本表只做定位证据，不做验收判定**；实现侧不自评 PASS，最终结论由 owner 复核。
> 数据源：`design/_research/prd-capabilities.md`（能力清单）、`frontend/src/routes/index.tsx`（路由真源）、`frontend/src/routes/ROUTE_REGISTRY.md`（速查视图）、`frontend/src/AGENTS.md`（禁新壳硬规则）。
> 硬规则提醒：重写后能力只能落进四菜单（资讯 `/`、知识 `/knowledge`、行动 `/action`、设置 `/settings`）的内嵌区块，或经 `PageLayout` 挂入的工具页；**禁止新增一级入口 / 新壳**。

---

## 一、摘要

| 项 | 数值 |
|---|---|
| 能力总条数 | **92**（DATA 19 + KNOW 14 + ACT 19 + SET 15 + XF 25） |
| 与契约 92 条一致性 | ✅ 一致，无偏差（逐条编号连续，无缺号/重号） |
| 已定位（有真实文件落点） | **68** |
| 其中「部分覆盖」（有落点但能力不完整） | 6（DATA-6、DATA-10、ACT-7、ACT-17、SET-5、XF-25） |
| 未定位 | **24**（DATA 4 / KNOW 3 / ACT 5 / SET 5 / XF 7） |
| 有前端测试覆盖的能力 | 47（其余为「无」或仅间接覆盖，见各行） |
| 路由对照结论 | 路由**全部保留**；发现 2 类文档-实现命名漂移 + 1 处状态声明与实现冲突（见第四节） |

说明：多条能力共用同一文件/同一测试属正常（一个页面区块承接多条能力）；表中每条能力单独一行，未做「等」合并。

---

## 二、主映射表

### 2.1 资讯域 `/`（DATA-1 ~ DATA-19，B4 承接）

| 编号 | 能力 | 路由 | 当前落点（文件 · 区块） | 测试 | B4–B6 目标承载 |
|---|---|---|---|---|---|
| DATA-1 | 质量门禁可解释/可追踪 | `/`、`/quality` | `frontend/src/components/sentinel/SentinelHomePage.tsx`（情报流）+ `frontend/src/components/quality/QualityDashboardPage.tsx`（校对室全貌） | `components/sentinel/SentinelHomePage.test.tsx`、`components/quality/QualityDashboardPage.test.tsx` | B4：`/` 情报流 + 工具页 `/quality`（PageLayout 挂入） |
| DATA-2 | 四阅读模式（简报/速览/深读/告警） | `/` | `components/sentinel/SentinelHomePage.tsx`（阅读模式切换条） | `components/sentinel/SentinelHomePage.test.tsx` | B4：`/` 阅读模式条 |
| DATA-3 | pick_score 精选排序 | `/` | `components/sentinel/SentinelHomePage.tsx`（精选视图） | `components/sentinel/SentinelHomePage.test.tsx` | B4：`/` 精选区块 |
| DATA-4 | 告警收窄（4 分类 tab） | `/` | `components/sentinel/NewsAlertList.tsx` | `components/sentinel/NewsAlertList.test.tsx` | B4：`/` 告警视图 |
| DATA-5 | 赞/踩 人工反馈 | `/`、`/history`、`/secnews/feed` | `components/sentinel/ReactionButtons.tsx` + `hooks/useReactions.ts`（挂载于 SentinelHomePage / NewsAlertList / PriorityDigestCard / `components/secnews/feed/FeedView.tsx` / HistoryPage） | `components/sentinel/ReactionButtons.test.tsx`、`hooks/useReactions.test.ts` | B4：`/` 卡片三挂载点 |
| DATA-6 | 兴趣引擎三层归因 | `/` | `frontend/src/lib/interest.ts`（纯函数，无独立 UI 区块） | 无 | B4：`/` feed 排序内部逻辑（不新增 UI） |
| DATA-7 | 内容偏好三层（显式/隐式/负反馈） | `/settings`、`/` | `components/settings/ContentPreferencesCard.tsx` | `components/settings/ContentPreferencesCard.test.tsx` | B6：设置「通用」分区 + B4 feed 消费 |
| DATA-8 | 非安全内容偏好通道 | — | ❌ 未定位（PRD 标注「未实现」；grep `非安全`/`non-security`/`preference` 未命中前端组件） | 无 | 未实现，B4 不承接（记为缺口，需 owner 裁决） |
| DATA-9 | SK-01 优先情报（落盘+推送） | `/` | `components/sentinel/PriorityDigestCard.tsx` | `components/sentinel/PriorityDigestCard.test.tsx` | B4：`/` 顶部优先情报卡 |
| DATA-10 | 摘要降级可见性 | `/` | `components/sentinel/PriorityDigestCard.tsx`（同文件；PRD 标注降级模式展示未实现 → 部分覆盖） | `components/sentinel/PriorityDigestCard.test.tsx` | B4：`/` 优先情报卡内补降级标识 |
| DATA-11 | 拒收日志人话化（原因码→中文） | `/settings?cat=ops`（`/quality/rejection` 已重定向至此） | `components/settings/RejectionLogCard.tsx` + `frontend/src/lib/rejectionReasons.ts` | `components/settings/RejectionLogCard.test.tsx`、`lib/rejectionReasons.test.ts` | B6：设置「运维」分区 |
| DATA-12 | 拒收回放（固定快照） | `/secnews/observability` | `components/secnews/observability/RejectionReplay.tsx` | `components/secnews/observability/RejectionReplay.test.tsx` | B6：设置侧 observability 工具页 |
| DATA-13 | 语义门禁（偏离零容忍） | 无独立前端路由 | ❌ 无前端落点（采集管线后端能力；结果可见于 `settings/RejectionLogCard.tsx`） | 无 | 不新增 UI；B6 沿用拒收日志展示 |
| DATA-14 | 智能分类（category 契约） | 无独立前端路由 | ❌ 无前端落点（后端 `/api/*classify*`；前端无对应区块） | 无 | 不承接 UI（后端能力） |
| DATA-15 | NER 实体（入知识条目） | 无独立前端路由 | ❌ 无前端落点（grep `ner`/`实体`/`entity` 未命中文档详情区块） | 无 | 不承接 UI |
| DATA-16 | MP-1 知识图谱点火（ATT&CK/CVE 对位） | `/knowledge/graph` | `components/sentinel/SentinelGraphPage.tsx`（含画布模式开关，内嵌 `components/shared/editorial/InfiniteCanvas.tsx`） | `components/sentinel/SentinelGraphPage.test.tsx`、`components/shared/editorial/InfiniteCanvas.test.tsx` | B5：知识 `/knowledge/graph` |
| DATA-17 | MP-2 通稿审核（候选人工审定） | `/action/events` | `components/events/EventsReviewPage.tsx` | `components/events/EventsReviewPage.test.tsx` | B5：行动侧工具页 `/action/events` |
| DATA-18 | 类型识别 → 预填事项草案 | `/`（立项）、`/knowledge`（转 Case） | `components/v1/panels/SignalPanel.tsx`（信号→立项）+ `components/knowledge/KnowledgeActionBar.tsx`（知识→Case） | `components/v1/panels/SignalPanel.test.tsx`、`components/knowledge/KnowledgeActionBar.test.tsx` | B4：`/` SignalPanel 区块；B5：知识转 Case 动作条 |
| DATA-19 | 采集供给验收（源矩阵/存活卡） | `/secnews/pipeline` | `components/secnews/pipeline/PipelineView.tsx` + `SourceMatrixCard.tsx` + `AliveCard.tsx` | `components/secnews/pipeline/SourceMatrixCard.test.tsx` | B6：设置侧采集工具页（不新增入口） |

#### 2.1.1 B4 交付后落点复核（2026-11-18）

`SentinelHomePage.tsx` 808 → 299 行（容器），区块落 `components/sentinel/feed/`（`feedModel.ts` / `FeedAtoms.tsx` / `UrlImport.tsx` / `FeedControls.tsx` / `FeedStates.tsx` / `FeedMustRead.tsx` / `FeedStream.tsx`）。上表「组件路径」列中 `SentinelHomePage.tsx` 的引用一律以该目录为准，其余路径未动。

| DATA | B4 复核结论 | 证据 |
|---|---|---|
| DATA-1 质量门禁可解释 | ✅ 保留 | 右栏 `RailWithPipe` + `SignalPanel compact`；`/quality` 工具页未动 |
| DATA-2 四阅读模式 | ✅ 保留 | `FeedControls.tsx` 的 `FeedModeBar`（简报/速览/深读/告警） |
| DATA-3 pick_score 精选 | ✅ 保留 | `FeedStream.tsx` 的 `FeedPicked`（`useQuery('feed:picked')`） |
| DATA-5 赞/踩 | ✅ 保留 | `FeedAtoms.tsx` 的 `FeedRowBinding.onReact` 三挂载点（must-read/queue/read） |
| DATA-6 兴趣引擎三层归因 | ✅ 保留 | 容器 `star()` 内 `trackInterest(item.id,'favorite')` |
| DATA-9 SK-01 优先情报 | ✅ 保留 | 默认分支 `<PriorityDigestCard />`（**未接 useQuery**，偏差 D6） |
| DATA-10 摘要降级可见性 | ◐ 原状（部分覆盖） | 随 DATA-9 未改动；降级标识仍缺 |
| DATA-18 类型识别→立项 | ✅ 保留 | `/` 两处 `<SignalPanel>`（rail compact + 正文全量） |
| DATA-4 告警收窄 | 不属于本批 | `NewsAlertList.tsx` 未改动 |
| DATA-7 内容偏好 | 不属于本批 | `ContentPreferencesCard.tsx`（B6）+ feed 消费逻辑未改 |
| DATA-16/17/19 | 不属于本批 | 分别归 B5 / B5 / B6 |

> 未列出的 DATA-8/11/12/13/14/15 与 B4 无关（未实现或非资讯域）。本复核只证明「区块仍在、可定位」，不构成视觉/交互验收。

### 2.2 知识域 `/knowledge`（KNOW-1 ~ KNOW-14，B5 承接）

| 编号 | 能力 | 路由 | 当前落点（文件 · 区块） | 测试 | B4–B6 目标承载 |
|---|---|---|---|---|---|
| KNOW-1 | Wiki-first 存储与 L1/L2 分层 | `/knowledge`、`/secnews/knowledge` | `components/KnowledgePage.tsx` + `components/knowledge/KnowledgeLayout.tsx` + `KnowledgeTabs.tsx` + `components/secnews/knowledge/WikiBrowser.tsx` | `components/knowledge/KnowledgeTabs.test.tsx` | B5：知识 `/knowledge` 主导航 + 浏览器区块 |
| KNOW-2 | Knowledge 域对象（采用/生命周期） | `/knowledge/v1` | `components/v1/V1Prototype.tsx` 的 `KnowledgeV1Page()`（v1 知识目录视图） | 无（该文件无专属测试；`v1/__tests__/c10`、`c11` 覆盖 CaseDetail 而非本页） | B5：知识 `/knowledge` 内 v1 目录区块 |
| KNOW-3 | SK-05 复用经验（Action 召回） | `/cases/:caseId` | `components/v1/CaseDetail.tsx` 的 `#section-knowledge` 区块 | `components/v1/__tests__/c10_mutation_wiring.test.tsx`、`c11_aggregate_and_sse.test.tsx`（聚合区块间接覆盖） | B5：行动 Case 详情页（`/action` 深链） |
| KNOW-4 | SK-06 复查到期（间隔复习） | `/knowledge/review`、`/reviews` | `components/knowledge/ReviewMode.tsx` + `components/ReviewPage.tsx` | `components/knowledge/ReviewMode.test.tsx`、`components/ReviewPage.test.tsx` | B5：知识 `/knowledge/review` |
| KNOW-5 | SK-04 复盘回流（提炼候选→草稿） | `/action`、`/knowledge` | `components/action/CopilotCards.tsx` + `components/action/ApprovalInbox.tsx` | `components/action/CopilotCards.test.tsx`、`components/action/ApprovalInbox.test.tsx` | B5：行动审批区块 |
| KNOW-6 | 适用条件 / 真实复用验证 | `/knowledge` | ❌ 未定位（PRD 标注「规划中」；grep `适用条件`/`复用验证`/`recall` 未命中前端区块） | 无 | 规划中，B5 不新增入口（若落块需 owner 裁决） |
| KNOW-7 | 资料库前厅（六域入口+派生统计） | `/knowledge/khub` | `components/knowledge/KnowledgeHubPage.tsx` | `components/knowledge/KnowledgeHubPage.test.tsx` | B5：知识 `/knowledge` 前厅区块 |
| KNOW-8 | 编目室（分类/标签/清单） | `/knowledge/library` | `components/knowledge/KnowledgeLibraryPage.tsx` | `components/knowledge/KnowledgeLibraryPage.test.tsx` | B5：知识 `/knowledge` 编目区块 |
| KNOW-9 | 无限画布（节点/连线/缩放） | `/knowledge/graph`（`/knowledge/canvas` 重定向至此） | `components/shared/editorial/InfiniteCanvas.tsx` + `components/sentinel/SentinelGraphPage.tsx` | `components/shared/editorial/InfiniteCanvas.test.tsx`、`components/sentinel/SentinelGraphPage.test.tsx` | B5：知识图谱页画布模式 |
| KNOW-10 | 清样深读 + 批注 | `/reader/:id` | `components/reader/DeepReaderPage.tsx` + `hooks/useAnnotations.ts` | `components/reader/DeepReaderPage.test.tsx` | B5：知识深读区（工具页 PageLayout） |
| KNOW-11 | Cubox 导入 | `/knowledge/import` | `components/knowledge/KnowledgeImport.tsx` | `components/knowledge/KnowledgeImport.test.tsx` | B5：知识导入区块 |
| KNOW-12 | 真源缺列补齐（frontmatter 契约） | 无前端路由 | ❌ 无前端落点（llm-wiki md 真源 + kl_pipeline 后端职责） | 无 | 不承接 UI |
| KNOW-13 | 旧库迁移（knowledge/ → llm-wiki） | 无前端路由 | ❌ 未实现（无迁移 UI / 无入口组件） | 无 | 不承接（数据迁移，非前端） |
| KNOW-14 | AI 副驾（知识摘要/证据卡） | PRD 记为 `/knowledge`；实际落 `/action` | `components/action/CopilotCards.tsx` | `components/action/CopilotCards.test.tsx` | B5：保持在行动 `/action`（与 PRD 路由标注不一致，见第四节风险） |

### 2.3 行动域 `/action`（ACT-1 ~ ACT-19，B5 承接）

| 编号 | 能力 | 路由 | 当前落点（文件 · 区块） | 测试 | B4–B6 目标承载 |
|---|---|---|---|---|---|
| ACT-1 | 九对象账本（Signal→…→RunReceipt） | `/action`、`/cases/:caseId` | `components/v1/panels/CaseQueuePanel.tsx`、`components/v1/CaseDetailPage.tsx`、`components/v1/CaseDetail.tsx` | `components/v1/panels/CaseQueuePanel.test.tsx` | B5：行动 `/action` 队列 + Case 详情 |
| ACT-2 | 审批收件箱（最多三选一） | `/action` | `components/action/ApprovalInbox.tsx` | `components/action/ApprovalInbox.test.tsx` | B5：行动 `/action` 审批区块 |
| ACT-3 | AI 起草研判（草稿→人工采纳） | `/cases/:caseId` | `components/v1/CaseDetail.tsx` 的 `#section-judgments`（起草 + 采纳/否决 mutation） | `components/v1/__tests__/c10_mutation_wiring.test.tsx` | B5：Case 详情研判区块 |
| ACT-4 | AI 副驾四卡（摘要/改写/翻译/问答） | `/action` | `components/action/CopilotCards.tsx` | `components/action/CopilotCards.test.tsx` | B5：行动右侧副驾区块 |
| ACT-5 | 四段指挥台（Case→Claim→Run→Artifact） | `/action` | `components/sentinel/action/ActionCommandConsole.tsx` + `CaseStage.tsx` / `ClaimStage.tsx` / `RunStage.tsx` / `ArtifactStage.tsx` + `components/v1/panels/ExecOverviewPanel.tsx`（挂于 `SentinelActionPage.tsx:563`） | `components/sentinel/action/ActionCommandConsole.test.tsx`、`stages.test.tsx`、`components/v1/panels/ExecOverviewPanel.test.tsx` | B5：行动 `/action` 指挥台区块 |
| ACT-6 | Run 回执（receipt=证据包+证据链） | `/action` | `components/sentinel/action/RunStage.tsx` + `frontend/src/api/v1.ts` | `components/sentinel/action/stages.test.tsx` | B5：Run 段回执卡 |
| ACT-7 | Action finish（结论+expected_revision+幂等） | `/cases/:caseId`、`/action` | `components/v1/CaseDetail.tsx`（7 个 mutation：approve/start/cancel/verify/accept/reject/close；**无独立「finish」UI** → 部分覆盖） | `components/v1/__tests__/c10_mutation_wiring.test.tsx`、`components/sentinel/action/ActionCommandConsole.test.tsx` | B5：Case 详情 + 指挥台统一 finish 动作 |
| ACT-8 | ExecutionPlan（边界/停止条件/预算） | `/action` | `components/sentinel/action/PlanPanel.tsx` | `components/sentinel/action/PlanPanel.test.tsx` | B5：指挥台 Plan 段 |
| ACT-9 | pi 边界执行（can/cannot/verify） | `/action` | `components/sentinel/action/RunStage.tsx`（事件流渲染） | `components/sentinel/action/stages.test.tsx` | B5：指挥台 Run 段 |
| ACT-10 | L3 动态加固（Action→Skill 自动沉淀） | 无前端路由 | ❌ 无前端落点（`audit_log` 后端职责） | 无 | 不承接 UI |
| ACT-11 | L4 治理（审计回放/越界告警） | `/settings?cat=ops`、`/secnews/observability` | `components/settings/OpsRunsPanel.tsx` + `components/secnews/observability/ActiveAlertsBanner.tsx` | `components/settings/OpsRunsPanel.test.tsx` | B6：设置运维分区 |
| ACT-12 | Case 关闭闭环（七项验收） | `/cases/:caseId` | `components/v1/CaseDetail.tsx`（closeCase，含 409 冲突处理） | `components/v1/__tests__/c10_mutation_wiring.test.tsx` | B5：Case 详情关闭区块 |
| ACT-13 | 五类执行模板（情报/供应商/方案/客诉/竞品） | 建项入口 | ❌ 未定位（grep `模板`/`template`/`五类` 未命中模板选择 UI；仅有 `SignalPanel.tsx` 立项与 `KnowledgeActionBar.tsx` 转 Case） | 无（`SignalPanel.test.tsx` 只覆盖立项） | 未实现，B5 不新增入口（缺口登记） |
| ACT-14 | 自定义事项类型 | 无 | ❌ 未定位 | 无 | 不承接 |
| ACT-15 | CodeGarden 实践域（项目/服务/资源/图谱/联动） | `/codegarden`、`/codegarden/phase2b` | `components/codegarden/ProjectBoard.tsx`、`ProjectDetail.tsx`、`ServiceMesh.tsx`、`ResourceHub.tsx`、`DependencyGraph.tsx`、`EventBus.tsx`、`PlaybookList.tsx` | `components/codegarden/ProjectCard.test.tsx`、`ServiceMesh.test.tsx`、`ResourceHub.test.tsx`、`DependencyGraph.test.tsx` | B5 保持现状（gate `codegarden`） |
| ACT-16 | 执行器四期（只读→受限写→学习→复合） | 同 ACT-6~10 | `components/sentinel/action/` 指挥台组件组 | `stages.test.tsx`、`ActionCommandConsole.test.tsx` | B5：指挥台 Run/Artifact 段 |
| ACT-17 | 完整队列可达（不藏筛选后） | `/action` | `components/v1/panels/CaseQueuePanel.tsx` —— **仅被 `components/v1/V1Prototype.tsx` 注释引用，未挂入 `/action`**（`SentinelActionPage.tsx` 只挂 `ExecOverviewPanel`）→ 与 PRD 缺口一致 | `components/v1/panels/CaseQueuePanel.test.tsx` | B5：必须把完整队列挂进 `/action` 主区块 |
| ACT-18 | 观测收口（`/api/ops/kpi` 口径唯一） | `/settings?cat=ops` | ❌ 未定位（grep `ops/kpi`/`kpi` 仅命中 `components/sentinel/review/ReviewOverlay.tsx` 文案，非该端点消费；`OpsRunsPanel.tsx` 走 `/api/ops/runs`） | 无（`OpsRunsPanel.test.tsx` 覆盖 runs 而非 kpi） | B6：设置运维分区补 KPI 卡（需 owner 确认端点） |
| ACT-19 | 30 天目标 / 发布门 | 无前端路由 | ❌ 无前端落点 | 无 | 不承接 UI |

### 2.4 设置域 `/settings`（SET-1 ~ SET-15，B6 承接）

| 编号 | 能力 | 路由 | 当前落点（文件 · 区块） | 测试 | B4–B6 目标承载 |
|---|---|---|---|---|---|
| SET-1 | 设置 IA（7 分区 / 5 组） | `/settings` | `components/settings/SettingsPage.tsx` + `sections.tsx`（总览/采集与管线/通用/模型配置/网络/集成与凭据/运维） | `components/settings/sections.test.ts`、`components/settings/SettingsDashboard.test.tsx` | B6：设置 `/settings` 唯一配置面 |
| SET-2 | Feature gates 可视化 + env 覆盖说明 | `/settings?cat=general` | `components/settings/FeatureGatesCard.tsx` | `components/settings/FeatureGatesCard.test.tsx` | B6：通用分区 |
| SET-3 | 模型配置唯一入口（池/Provider/密钥） | `/settings?cat=models`（`/secnews/image` 重定向至此） | `components/settings/ModelsSettings.tsx` + `ModelPoolPanel.tsx` + `components/quality/ProviderPanel.tsx` | `components/settings/ModelsSettings.test.tsx`、`ModelPoolPanel.test.tsx` | B6：模型配置分区 |
| SET-4 | MCP（开关/token/19 tools 说明） | `/settings?cat=connectivity` | `components/settings/MCPSettingsCard.tsx` | `components/settings/MCPSettingsCard.test.tsx` | B6：集成与凭据分区 |
| SET-5 | WebDAV 同步 + 3-way merge | `/settings?cat=connectivity`、`/sync` | `components/settings/SyncSettings.tsx` + `components/sync/index.tsx`（+ `SyncConfigForm/History/Operations`） | 无（`components/sync/` 下无测试文件） | B6：同步区块（B6 需补测试或明确豁免） |
| SET-6 | 自动入管（auto_intake） | `/settings?cat=pipeline` | `components/settings/AutoIntakeCard.tsx` | `components/settings/AutoIntakeCard.test.tsx` | B6：采集与管线分区 |
| SET-7 | 失败面板（出错+一键运行） | `/settings?cat=ops` | `components/settings/OpsRunsPanel.tsx` | `components/settings/OpsRunsPanel.test.tsx` | B6：运维分区 |
| SET-8 | `/maint` 维护统一入口 | `/maint` | `components/MaintPage.tsx` + `components/settings/DatabaseMaintenance.tsx` | `components/MaintPage.test.tsx`、`components/settings/DatabaseMaintenance.test.tsx` | B6：维护工具页 |
| SET-9 | 治理四件套（配置/审计/备份/发布） | `/settings?cat=*` | ❌ 未定位（能力分散在 `OpsRunsPanel`/`RejectionLogCard`/`MaintPage`，无独立「治理」区块与审计快照卡） | 无 | B6：可选归并入运维分区（owner 裁决） |
| SET-10 | 鉴权边界（`/docs`/`/openapi.json`/`/mcp/sse`） | 无前端路由 | ❌ 无前端落点（后端鉴权） | 无 | 不承接 UI |
| SET-11 | 出站与路径加固 | 无前端路由 | ❌ 无前端落点（后端） | 无 | 不承接 UI |
| SET-12 | run.py 单实例纪律 | 无前端路由 | ❌ 无前端落点（部署纪律） | 无 | 不承接 UI |
| SET-13 | 备份热/冷分层 | `/maint` | `components/MaintPage.tsx`（备份卡） | `components/MaintPage.test.tsx` | B6：维护工具页 |
| SET-14 | dsh 启停（受管子进程） | `/settings?cat=ops` | `components/secnews/settings/DshControlCard.tsx`（`SettingsPage.tsx:111` 挂载） | 无（无 `DshControlCard.test.tsx`） | B6：运维分区（B6 需补测试或明确豁免） |
| SET-15 | 单用户边界（无多用户/RBAC） | 无前端路由 | ❌ 无前端落点（产品纪律声明） | 无 | 不承接 UI |

### 2.5 跨切面（XF-1 ~ XF-25，多数已在 B2/B3 交付，B4–B6 沿用）

| 编号 | 能力 | 路由 | 当前落点（文件 · 区块） | 测试 | B4–B6 目标承载 |
|---|---|---|---|---|---|
| XF-1 | 四菜单唯一壳 | 全站 | `frontend/src/shell/AppShell.tsx` + `shell/MenuNav.tsx`（B8-a 兼容桥删除后，壳实现仅此两处） | `shell/AppShell.test.tsx`、`routes/__tests__/nav4_shell.test.tsx` | B2 已交付；B4–B6 **只换区块，不改壳** |
| XF-2 | 管道心跳条（常驻） | 全站 | `frontend/src/shell/PipeBar.tsx` + `shell/pipe.tsx` | `routes/__tests__/nav4_shell.test.tsx`（含 PipeBar 断言） | 沿用（B2） |
| XF-3 | PageLayout 工具页挂入 + `menuOf` 归属 | 所有工具路由 | `components/PageLayout.tsx` + `shell/menuOf.ts` | `components/PageLayout.test.tsx`、`nav4_shell.test.tsx` | 沿用（B2） |
| XF-4 | 主题 3 态（light/dark/paper） | `/settings?cat=general` + 壳 | `frontend/src/contexts/ThemeContext.tsx` + `shell/MenuNav.tsx`（切换）+ 设置通用分区 | `shell/AppShell.test.tsx`、`nav4_shell.test.tsx` | B6：设置通用分区 |
| XF-5 | 命令栏（⌘K） | 全站 masthead | `components/sentinel/CommandBar.tsx` + `frontend/src/api/commands.ts` | `components/sentinel/CommandBar.test.tsx` | 沿用（B2/B3） |
| XF-6 | 质量规则两层（硬门禁/软偏好） | `/settings?cat=pipeline` | `components/settings/quality/CustomRulesPanel.tsx`（经 `components/settings/QualitySettings.tsx` 挂载） | `components/settings/quality/CustomRulesPanel.test.tsx` | B6：采集与管线分区 |
| XF-7 | receipt 一等公民（RunReceipt/KLReceipt/OutboxReceipt） | `/cases/:caseId` | `components/v1/CaseDetail.tsx`（`#section-evidence` / `#section-actions` 回执与产物） | `components/v1/__tests__/c11_aggregate_and_sse.test.tsx` | B5：Case 详情回执区块 |
| XF-8 | CAS 幂等（expected_revision） | 写路径（Case/审批） | `components/v1/CaseDetail.tsx` + `components/action/ApprovalInbox.tsx` + `frontend/src/api/v1.ts` | `components/v1/__tests__/c10_mutation_wiring.test.tsx`、`components/action/ApprovalInbox.test.tsx` | B3/B5 沿用 |
| XF-9 | 人主律（AI 建议人确认） | `/action` | `components/action/ApprovalInbox.tsx` | `components/action/ApprovalInbox.test.tsx` | B5：审批交互不得改成自动通过 |
| XF-10 | 失败三形态（可重试/降级/需人处理） | `/settings?cat=ops` | `components/settings/OpsRunsPanel.tsx` | `components/settings/OpsRunsPanel.test.tsx` | B6：运维分区 |
| XF-11 | run record 统一埋点 | `/settings?cat=ops` | `components/settings/OpsRunsPanel.tsx` + `frontend/src/api/commands.ts` | `components/settings/OpsRunsPanel.test.tsx` | B6：运维分区 |
| XF-12 | 安全底线八条（Prompt/凭据/路径/确认） | `/action` + `/settings?cat=ops` | `components/sentinel/action/ActionCommandConsole.tsx` + `components/settings/OpsRunsPanel.tsx` | `components/sentinel/action/ActionCommandConsole.test.tsx` | B5/B6 |
| XF-13 | ai_hub 红线（唯一出口） | 无前端路由 | ❌ 无前端落点（后端调用链红线） | 无 | 不承接 UI |
| XF-14 | pi 为写操作主力 / dsh 不当执行器 | 无前端路由 | ❌ 无前端落点（后端引擎分工） | 无 | 不承接 UI |
| XF-15 | dsh 受管进程（降级链） | `/settings?cat=ops` | `components/secnews/settings/DshControlCard.tsx` | 无 | B6：运维分区 |
| XF-16 | 存储哲学（md 真源 / SQLite 投影） | 无前端路由 | ❌ 无前端落点（数据层） | 无 | 不承接 UI |
| XF-17 | 迁移幂等（IF NOT EXISTS） | 无前端路由 | ❌ 无前端落点（DB 迁移） | 无 | 不承接 UI |
| XF-18 | sync apply_bundle 原子性 | `/sync` | `components/sync/index.tsx`（前端仅触发/展示，原子性在后端） | 无 | B6：同步工具页 |
| XF-19 | fetch 竞态守卫（abort） | 全站 | `frontend/src/hooks/useAbortGuard.ts` | `hooks/useAbortGuard.test.tsx` | B3 已交付；B4–B6 复用 |
| XF-20 | 状态库裁决（服务端状态/本地 UI/URL） | 全站 | `frontend/src/lib/api.ts` + `frontend/src/api/*`（domain 模块）+ `domain/v1_0.ts` | `api/__tests__/domain_endpoints.test.ts`、`api/__tests__/v1_url_builder.test.ts` | B3 已交付；B4–B6 复用 |
| XF-21 | i18n 中文硬编码 | 全站 | `frontend/src/contexts/I18nContext.tsx` | `contexts/I18nContext.test.tsx` | 沿用 |
| XF-22 | KPI 口径一致（ops/kpi） | `/settings?cat=ops` | ❌ 无前端落点（前端未消费 `/api/ops/kpi`） | 无 | B6 可选补 KPI 区块（owner 裁决） |
| XF-23 | 工程纪律（lint/tsc/测试门） | 无前端路由 | ❌ 无前端落点（CI 脚本） | 无 | 不承接 UI |
| XF-24 | SSE 实时（重连/退避/去重） | 全站 | `frontend/src/hooks/realtime.ts` + `hooks/useSSE.ts` + `components/v1/useSSEWithRefetch.ts` | `hooks/realtime.test.tsx`、`hooks/useSSE.test.ts` | 沿用（B3） |
| XF-25 | egress 诚实声明（哪些走出去） | `/settings?cat=connectivity` | ❌ 未定位（仅有能力入口，无「出站声明」区块；grep `出站`/`egress` 未命中） | 无 | B6 可在集成分区补说明（owner 裁决） |

---

## 三、未定位清单（含已尝试关键词）

| 编号 | 能力 | 已尝试的搜索 | 判定 |
|---|---|---|---|
| DATA-8 | 非安全内容偏好通道 | 关键词 `非安全`、`non-security`、`preference`；目录 `components/settings` | PRD 标注未实现，前端无落点 |
| DATA-13 | 语义门禁 | `语义门禁`、`semantic`、`gate`；`components/secnews`、`components/settings` | 后端能力，前端无独立落点 |
| DATA-14 | 智能分类 | `classify`、`智能分类`、`category 契约` | 后端能力，前端无独立落点 |
| DATA-15 | NER 实体 | `ner`、`实体`、`entity`；`components/reader` | 后端能力，前端无独立落点 |
| KNOW-6 | 适用条件/真实复用验证 | `适用条件`、`复用验证`、`recall`、`skill` | 规划中，无组件 |
| KNOW-12 | 真源缺列补齐 | `frontmatter`、`缺列`、`schema` | 数据层职责，前端无落点 |
| KNOW-13 | 旧库迁移 | `迁移`、`migrate`、`knowledge/ →` | 未实现 |
| ACT-10 | L3 动态加固 | `加固`、`harden`、`skill 沉淀`、`audit_log` | 后端职责 |
| ACT-13 | 五类执行模板 | `模板`、`template`、`五类`、`tpl` | 无模板选择 UI |
| ACT-14 | 自定义事项类型 | `自定义`、`custom type`、`case_type` | 无 UI |
| ACT-18 | ops/kpi 口径 | `ops/kpi`、`kpi` | 前端未消费该端点 |
| ACT-19 | 30 天目标/发布门 | `30 天`、`目标`、`发布门`、`release gate` | 无 UI |
| SET-9 | 治理四件套 | `治理`、`governance`、`审计`、`audit`、`policy` | 无独立区块，能力分散 |
| SET-10 | 鉴权边界 | `auth`、`鉴权`、`openapi` | 后端职责 |
| SET-11 | 出站与路径加固 | `出站`、`egress`、`公网` | 后端职责 |
| SET-12 | 单实例纪律 | `单实例`、`single instance`、`run.py` | 部署纪律 |
| SET-15 | 单用户边界 | `rbac`、`多用户`、`multi-user` | 产品纪律 |
| XF-13 | ai_hub 红线 | `ai_hub`、`_try_order`、`_resolve_provider` | 后端红线 |
| XF-14 | pi/dsh 分工 | `pi`、`dsh`、`executor` | 后端分工 |
| XF-16 | 存储哲学 | `真源`、`投影`、`projection` | 数据层 |
| XF-17 | 迁移幂等 | `IF NOT EXISTS`、`migration` | DB 层 |
| XF-22 | KPI 口径 | `ops/kpi`、`kpi` | 无前端消费 |
| XF-23 | 工程纪律 | `lint`、`tsc`、`ci` | CI 脚本 |
| XF-25 | egress 诚实声明 | `出站`、`egress`、`对外`、`connectivity` | 未定位（仅有能力入口） |

> 部分定位（有落点、能力不完整，未计入未定位）：DATA-6（纯函数无 UI）、DATA-10（降级标识未实现）、ACT-7（无独立 finish UI）、ACT-17（CaseQueuePanel 未挂载到 `/action`）、SET-5（无测试）、XF-25（仅入口无声明区块）。

---

## 四、与 `frontend/src/routes/ROUTE_REGISTRY.md` 的逐条对照

**结论：路由条目全部保留，无增删；发现 3 类差异（2 命名漂移 + 1 状态声明冲突）与 1 处遗漏登记。**

### 4.1 一致项（抽检全通过）

`/`、`/judge`、`/quality`、`/quality/rejection`、`/deep/:type/:id`、`/history`、`/knowledge`（9 子路由：import/process/compile/compound/imported/v1/deep-read/review/heatmap）、`/knowledge/graph`、`/knowledge/canvas`、`/knowledge/khub`、`/knowledge/library`、`/reader/:id`、`/judge/graph`、`/reviews`、`/secnews/knowledge`、`/action`、`/action/events`、`/cases/:caseId`、`/cases`、`/todos`、`/report`、`/garden`、`/secnews/analyze`、`/settings`（7 分区）、`/sentinel/settings`、`/secrets`、`/sync`、`/skills`、`/secnews/observability`、`/codegarden`（+`/phase2b`）、`/maint`、`/workbench`、`/intel`、`/secnews`→feed、`/secnews/image`→models、`/secnews/settings`→collection、`/category/:cat`、`*`、`/oauth-callback`、`/skill-store`、`/dashboard`、`/tags`、`/extract`、`/search` —— 与 `routes/index.tsx` 实际声明一致。

### 4.2 差异项

| # | 类型 | ROUTE_REGISTRY 表述 | `routes/index.tsx` 实际 | 影响 |
|---|---|---|---|---|
| D1 | 组件命名漂移 | `/deep/:type/:id` → `DeepReadPage` | `P.DeepReadView` | 低（命名不同，实际页面存在）。B4 前建议统一命名，避免误判为缺失 |
| D2 | 组件命名漂移 | `/secnews/*` → `SecNewsFeed` / `PipelineView` / `AnalyticsView` / `WikiBrowser` / `ObservabilityTab` | `P.SecNewsFeed` / `P.SecNewsPipeline` / `P.SecNewsAnalytics` / `P.SecNewsKnowledge` / `P.SecNewsObservability` | 低-中（PageLayout 包装层命名，易被误读为不同路由） |
| D3 | **状态声明与实现冲突** | §三 待办表：「P1 CaseQueue 迁入 `/action` ✅ 完成」 | `components/v1/panels/CaseQueuePanel.tsx` 仅被 `V1Prototype.tsx` 注释提及；`SentinelActionPage.tsx` 只挂 `ExecOverviewPanel`（L563），**未挂 CaseQueuePanel** | **高**：完整队列实际不可达，与 ACT-17 缺口一致；B5 必须先修复再重写 |
| D4 | 文档滞后 | `/reader/:id` 备注「批注未实现」 | `hooks/useAnnotations.ts` + `components/reader/DeepReaderPage.tsx` + `DeepReaderPage.test.tsx` 均存在 | 中：批注能力已在实现的可能，需 owner 复核后更正 registry |

### 4.3 遗漏登记

- ROUTE_REGISTRY §二 只列 `/secnews/observability` 归设置，未列 `/secnews/analytics`、`/secnews/analyze`、`/secnews/pipeline` 的菜单归属；实现侧经 `menuOf` 自动归属，建议 registry 补一列「归属菜单」以免 B4 重写误删。

---

## 五、给 owner 的复核提示

1. **D3 / ACT-17 是最大风险**：`CaseQueuePanel` 有组件、有测试，但没挂进 `/action`。B5 重写前需确认是有意收敛（队列改由 ExecOverviewPanel 承担）还是漏挂 —— 两种结论对应完全不同的重写动作。
2. **24 条未定位中 17 条属后端/工程纪律能力**（DATA-13/14/15、KNOW-12、ACT-10/19、SET-10/11/12/15、XF-13/14/16/17/22/23），前端重写不承载，但需确认这些能力不需要新增前端可见性（若需要即为「新增一级入口」违规或须在四菜单内落区块）。
3. **6 条部分覆盖 + 2 处无测试（SET-5 sync、SET-14 dsh、XF-15）**：重写若按「有测试=安全」推进，这三处会静默丢功能；建议 B6 强制补测试或写入豁免清单。