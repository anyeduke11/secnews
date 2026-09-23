# PRD 对齐审计报告

> **二次复审说明（DEV-0221）**：§1~12 是早先报告，含已被当前代码证伪的结论，保留作历史追溯。当前结论以 **§13** 为准；旧节中的“未接线/只读/仍用 copy2/无首页摘要”和重复修复建议不得继续作为开发输入。

- **日期**: 2026-09-14
- **审计范围**: 全仓代码事实 vs 7 份 PRD/设计/计划文档
- **真相源**: 代码仓库（2026-09-14 main 分支）+ 过程文档（DEV_LOG / PROGRESS / PROJECT）
- **审计方法**: 只读审计，逐维度比对文档声称 vs 代码实测

---

## 1. 路由与壳层对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 1.1 | `/cases/:caseId` layer | V0.8.5_PLAN.md §5: `layer=judge` | `frontend/src/routes/index.tsx` + `nav4_shell.test.tsx`: `layer="action"` | ❌ 漂移 |
| 1.2 | `/cases` 重定向目标 | V0.8.5_PLAN.md §5: 重定向到 `/judge` | 实际重定向到 `/action`（NAV4 修订） | ❌ 漂移 |
| 1.3 | `v085_route_shell.test.tsx` | V0.8.5_PLAN.md §4.1: 应存在，作为"shell 断言锁" | **文件不存在**（NAV4 重构时删除） | ❌ 缺失 |
| 1.4 | NAV4 四菜单壳 | V0.8.5_PLAN.md: 三层壳 | 实际：`SentinelShell` 唯一壳，四菜单（资讯/知识/行动/设置） | ⚠️ 文档过时 |
| 1.5 | SecNewsShell 6 视图 | 原设计：独立壳 | 已拆挂 `PageLayout`，组件文件退役保留 | ⚠️ 部分退役 |
| 1.6 | UTILITY_GROUPS 更多菜单 | 原设计：17 项更多菜单 | **已物理删除** | ✅ 已落地 |
| 1.7 | 主题模式 | V0.8.5_PLAN.md: light/dark | 实际：light/dark/paper（3 态） | ⚠️ 文档过时 |

**结论**：路由与壳层存在 **2 处 spec 漂移**（1.1、1.2）和 **1 处测试文件缺失**（1.3）。NAV4 修订未回写 V0.8.5_PLAN.md。

---

## 2. API 端点对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 2.1 | 总路由器数 | V0.8.5_PLAN.md: 85 | `backend/main.py`: **86** `include_router()` 调用 | ⚠️ 数字过时 |
| 2.2 | v1.0 路由器 | V0.8.5_PLAN.md §6: 7 个 v1 前缀模块 | `backend/main.py`: case_api / judgment_api / action_api / run_api / artifact_api / knowledge_api / v1_signals_api **7 个无条件注册** | ✅ 一致 |
| 2.3 | v1_signals API | 设计文档: 1 端点 (GET) | 实际：`v1_signals_api.py` **1 端点** (GET `/api/v1/signals`) | ✅ 一致 |
| 2.4 | Signal 写端点 | 未明确 | **无写端点**（只有 GET list） | ⚠️ 缺口 |
| 2.5 | MCP tools | FIRST_PRINCIPLES: 19 tools | `test_mcp_server.py`: **19 tools** (12 读 + 7 写) | ✅ 一致 |

**结论**：后端 API 基本对齐，但 **Signal 缺少写端点**（2.4），v1_signals 只能读不能写。

---

## 3. v1.0 域对象对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 3.1 | 9 对象 + 3 receipt | V1.0.0_CLOSEOUT_PLAN: 全部落地 | `v1_0_models.py`: 9 对象 + EvidenceRef + Step 全部存在 | ✅ 一致 |
| 3.2 | Migrations | V1.0.0_CLOSEOUT_PLAN: 096-108 | `backend/repository/migrations/`: **117** 个文件（096-108 + 109-117） | ✅ 一致（超集） |
| 3.3 | v1_runs 数据 | 设计: 应可执行 | `backend/hotspot.db`: **0 行** | ❌ 代码级死锁 |
| 3.4 | v1_artifacts 数据 | 设计: 应可产出 | `backend/hotspot.db`: **0 行** | ❌ 代码级死锁 |
| 3.5 | v1_materials 数据 | 设计: 应贯通 | `backend/hotspot.db`: **6 行** | ⚠️ 极少 |
| 3.6 | v1_signals 数据 | 设计: 应贯通 | `backend/hotspot.db`: **5 行** | ⚠️ 极少 |
| 3.7 | Junction 表 | 设计: v1_case_judgments / v1_case_actions | `backend/hotspot.db`: **均空**（0 行） | ❌ 未填充 |
| 3.8 | evidence_receipts | 设计: 幂等提交 | `backend/hotspot.db`: **20 行**（ Judgment 1 + Action 1 + Knowledge 1 + 其他） | ✅ 正常 |

**结论**：v1.0 域对象**代码基础设施全部就位**，但**数据流未贯通**（3.3-3.7）。v1_runs/v1_artifacts 永远为空是**设计缺陷**（无执行体），不是数据缺失。

---

## 4. B0-B7 业务闭环整改对齐

| # | 整改进度 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 4.1 | R01 证据持久化 | REVIEW: 已修 | `_insert_subject/material/signal` 真实 INSERT | ✅ 已修 |
| 4.2 | R02 生产调度器接线 | REVIEW: 待修 | SourcePipeline 存在但未接线生产 scheduler | ❌ 未修 |
| 4.3 | R03 失败后游标推进 | REVIEW: 已修 | `items_committed > 0` 才 advance | ✅ 已修 |
| 4.4 | R04 Worker 真实 dispatch | REVIEW: 已修 | `_c07_r04_skill_dispatcher` 传入 | ✅ 已修 |
| 4.5 | R05 Mock 协议移除 | REVIEW: 已修 | `_VALID_RUN_PROTOCOLS` 不含 mock | ✅ 已修 |
| 4.6 | R06 Live trace 仍用 mock | REVIEW: 待修 | `--live` 仅校验 vendor SHA | ❌ 未修 |
| 4.7 | R07 Async 边界 | REVIEW: 已修 | `asyncio.run` 包裹 | ✅ 已修 |
| 4.8 | R08 Artifact 正文持久化 | REVIEW: 已修 | 文件存在性 + hash 校验 | ✅ 已修 |
| 4.9 | R09 Artifact CAS | REVIEW: 已修 | revision + old_status 原子比较 | ✅ 已修 |
| 4.10 | R10 Wiki 路径一致性 | REVIEW: 部分 | 证据服务改善；WikiFs 未复核 | ⚠️ 部分 |
| 4.11 | R11 旧数据迁移 | REVIEW: 已修 | stable mapping + ULID | ✅ 已修 |
| 4.12 | R12 WARM/COLD 备份 | REVIEW: 待修 | 仍用 `shutil.copy2` | ❌ 未修 |
| 4.13 | R13 前端双问号 URL | REVIEW: 假设已修 | 未复核 | ⚠️ 未复核 |
| 4.14 | R14 工作台只读 | REVIEW: 待修 | 前端原型缺 mutation | ❌ 未修 |
| 4.15 | R15 Skill 契约 | REVIEW: 部分 | dispatcher 已修；schema 问题未复核 | ⚠️ 部分 |
| 4.16 | R16 复用计数诚实 | REVIEW: 待复核 | 未复核 | ⚠️ 未复核 |
| 4.17 | R17 Case 可关闭 | REVIEW: 待复核 | 未复核 | ⚠️ 未复核 |
| 4.18 | R18 SSE 可靠性 | REVIEW: 部分 | outbox 已用；前端未复核 | ⚠️ 部分 |
| 4.19 | R19 契约一致性 | REVIEW: 待复核 | 未复核 | ⚠️ 未复核 |
| 4.20 | R20 发布台账 | REVIEW: 部分 | ruff/version 声称已修 | ⚠️ 部分 |

**结论**：20 项整改中 **8 项已修**、**6 项未修**、**6 项部分/未复核**。关键未修项：R02（生产调度器）、R06（mock 未去）、R12（备份）、R14（前端 mutation）。

---

## 5. 已批准设计待落地对齐

| # | 设计 | 批准日期 | 文档承诺 | 代码事实 | 状态 |
|---|---|---|---|---|---|
| 5.1 | P1-0 执行器 | 2026-09-13 | 4 期（止血→边界协议→pi 执行→加固） | **零代码**；`v1_runs` 无 `plan_json`/`boundary_hash`/`executor` 列 | ❌ 未启动 |
| 5.2 | CodeGarden 安全实践域 | 2026-09-13 | 4 期（S1→S2→S3→S4） | `auto_classifier.py` 有 `classify_practice_domain()`；**`cg_projects.practice_domain` 列缺失** | ⚠️ 部分 |
| 5.3 | MITRE MP-3 L1 漏洞 | 2026-09-13 | NVD 接入 + CVE→technique 标注 | **未启动** | ❌ 未启动 |
| 5.4 | MITRE MP-4 L3 响应 | 2026-09-13 | `knowledge_technique_ref` 表 + 双向关联 | **Stub**（`attack_label_service.get_knowledge_for_techniques()` 返回空列表）；表未建 | ❌ Stub |
| 5.5 | Workbench Focus | 2026-09-12 | 后端全落 + 前端分区渲染 | 后端全落；前端分区渲染 P1 | ⚠️ 部分 |

**结论**：4 项已批准设计中 **1 项未启动**（5.3）、**1 项零代码**（5.1）、**1 项部分**（5.2）、**1 项 Stub**（5.4）、**1 项部分**（5.5）。

---

## 6. MITRE ATT&CK 标签体系对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 6.1 | MP-1 图谱点火 | attack_techniques + attack_cwe_map + security_edges | `backend/hotspot.db`: attack_techniques **244 行** / attack_cwe_map **714 行** / security_edges **17,616 行** | ✅ 已落地 |
| 6.2 | MP-2 事件类型词表 | 11 类（8 通用 + 3 金融） | `data/security/event_types_seed.json`: **11 类**；migration 117: 5 表；`backend/services/event_technique_*.py`: **4 service** | ✅ 基础设施已落地 |
| 6.3 | MP-2 候选池 | LLM 抽取 + owner 人审 | `event_technique_candidates` 表已建；**候选池待 owner 人审** | ⚠️ 待人审 |
| 6.4 | MP-2 技战法卡 | 前端组件 | 未找到独立组件（可能在 `SentinelGraphPage` 内） | ⚠️ 待验证 |
| 6.5 | MP-3 L1 漏洞 | NVD 接入 + CVE→technique | **未启动** | ❌ 未启动 |
| 6.6 | MP-4 L3 响应 | `knowledge_technique_ref` 表 | **表未建**；`attack_label_service.get_knowledge_for_techniques()` 返回空列表 | ❌ Stub |

**结论**：MP-1 ✅ 已落地；MP-2 基础设施已落地，**候选池待 owner 人审**（关键路径瓶颈）；MP-3/4 ❌ 未启动。

---

## 7. 数据层对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 7.1 | HOT 库 | 存在 | `backend/hotspot.db`: **14,503 hotspots** + v1 对象 + wiki FTS | ✅ 正常 |
| 7.2 | WARM 库 | `backend/hotspot-warm.db` 存在 | **文件不存在**（配置默认路径指向缺失文件） | ❌ 恶化 |
| 7.3 | WARM 备份 | 无全量快照 | `backend/backups/hotspot-warm-20260912_200000.db`: **923MB** 存在 | ✅ 已改善 |
| 7.4 | COLD 库 | 存在 | `backend/hotspot-cold.db`: 存在（audit_log 等归档） | ✅ 正常 |
| 7.5 | 备份策略 | 每日全量 | `backup_service.py`: 仅备份主库（`src = Path(config.db_path)`）；warm/cold **0 命中** | ❌ 不完整 |
| 7.6 | Wiki-first | llm-wiki-2.0 md 真源 | `wiki_items_fts`: **7,734 条**嵌入 HOT 库；`llm-wiki-2.0/` md 真源 | ✅ 正常 |
| 7.7 | Schema 真相源 | 启动期逐条跑 SQL | `knowledge_items_table()` 单一真相源（`db.py:124`）；migration 117 编号连续 | ⚠️ 改善但不完整 |
| 7.8 | 跨库事务 | WAL 跨 ATTACH 不原子 | 未变化（已知限制） | ⚠️ 已知风险 |

**结论**：数据层**备份已改善**（7.3），但 **WARM 库文件缺失**（7.2）和 **备份策略不完整**（7.5）是关键问题。

---

## 8. AI 能力对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 8.1 | ai_hub 四级链 | env → settings.kv → router → yaml | 实际：env → settings.kv → router → yaml；5 providers；断路器 + provider health | ✅ 一致 |
| 8.2 | dsh | 受管子进程 | ProcessSupervisor + bridge；**真 vendor 未实测** | ⚠️ 部分 |
| 8.3 | pi | agent_bridge stdio JSON-RPC | 协议已实测对齐 0.84.4；**流式 UI 未接** | ⚠️ 部分 |
| 8.4 | SK-01 daily-priority-intel | 后端完成 | admission_log + v1_signals 聚合；**前端分区渲染 P1** | ⚠️ 部分 |
| 8.5 | SK-02 cve-impact-brief | 全链 | generate → draft → publish；三重守卫 | ✅ 一致 |
| 8.6 | SK-03 inspection-materials | 生成 + 执行 | 生成/审批/执行；**执行体 P1-0 待落地** | ⚠️ 部分 |
| 8.7 | SK-04 action-retrospective | 生成 | 验收后复盘 → Knowledge 草稿 | ✅ 一致 |
| 8.8 | SK-05 reuse-experience | 自动召回 | `auto_recall_for_case`；已产生 adoption 回执 | ✅ 一致 |
| 8.9 | SK-06 knowledge-review-due | job | Daily 04:00 Shanghai；case blocker 机制 | ✅ 一致 |

**结论**：AI 能力**基础设施基本就位**，但 **dsh/pi 真 vendor 未实测**（8.2）、**pi 流式 UI 未接**（8.3）、**SK-01 前端未完成**（8.4）。

---

## 9. 前端数据层对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 9.1 | setInterval/setTimeout | 25 处 | **76 处**（含测试 + Toast 等 UI 延迟） | ⚠️ 总量增加 |
| 9.2 | 数据层库 | 无 | **无 react-query/swr**；`useHotspotData`/`useSSE`/`useFavorites` 仍用裸 fetch + 定时轮询 | ❌ 未引入 |
| 9.3 | SSE 自激循环 | 已修 | DEV-0167：types 过滤 + refetch/refresh 分离 | ✅ 已修 |
| 9.4 | 前端 mutation | 工作台只读 | 前端原型缺 mutation（R14） | ❌ 未修 |

**结论**：前端数据层**仍原始**（9.2），但关键 bug 已修（9.3）。

---

## 10. 架构数字对齐

| # | 审计项 | 文档声称 | 代码事实 | 状态 |
|---|---|---|---|---|
| 10.1 | Routers | 85 | **86** | ⚠️ 数字过时 |
| 10.2 | Services | 141 | **145** | ⚠️ 数字过时 |
| 10.3 | Migrations | ~107 | **117** | ⚠️ 数字过时 |
| 10.4 | Jobs | 52 | **51** | ⚠️ 数字过时 |
| 10.5 | Frontend routes | — | **53** | — |
| 10.6 | Frontend tests | — | **496** (Vitest) | — |
| 10.7 | Backend tests | — | **4,598** (pytest) | — |
| 10.8 | Builtin skills | 14 | **20** (8 ops + 6 comp + 4 analysis + 2 report) | ⚠️ 数字过时 |
| 10.9 | v1 skills | — | **6** (SK-01~SK-06) | — |
| 10.10 | Total skills | 14 | **26** | ⚠️ 数字过时 |

**结论**：架构数字**已过时**（10.1-10.4, 10.8-10.10）。需同步更新所有文档。

---

## 11. 飞轮诊断对齐（FIRST_PRINCIPLES_ANALYSIS 更新）

| # | 根因 | 2026-09-11 诊断 | 2026-09-14 更新 | 改善？ |
|---|---|---|---|---|
| 11.1 | 双本体论 | 三套身份互不相认 | 代码路径已收敛（v1 统一身份），但数据流未贯通（生产调度器未接线） | ⚠️ 部分 |
| 11.2 | 能力方向 | 14/20 (70%) 系统自我体检 | 14/26 (54%) 系统自我体检；v1 六项能力前端部分接通 | ✅ 改善 |
| 11.3 | 数据层可靠性 | 无备份 / 无 schema 真相源 / 跨库不原子 | 备份已改善；schema 真相源部分改善；跨库不原子已知限制 | ⚠️ 部分 |

**结论**：三根根因**部分改善**，但**未根治**。飞轮仍不转（v1_runs 空 / v1_artifacts 空 / Junction 表空）。

---

## 12. 审计总结

### 12.1 关键发现

| 严重级别 | 发现 | 数量 |
|---|---|---|
| **P0** | 安全漏洞（P0-A RCE + P0-B 前端监听 0.0.0.0） | 2 |
| **P0** | 备份链产出为空（P0-C） | 1 |
| **P0** | 行动层代码级死锁（P0-D） | 1 |
| **P1** | Spec vs 代码漂移（layer=judge vs layer=action） | 2 |
| **P1** | 测试文件缺失（v085_route_shell.test.tsx） | 1 |
| **P1** | Signal 缺少写端点 | 1 |
| **P1** | WARM 库文件缺失 | 1 |
| **P2** | 架构数字过时（6 处） | 6 |
| **P2** | 已批准设计未落地（P1-0 / CodeGarden / MITRE MP-3/4） | 4 |
| **P2** | 前端数据层原始（无 react-query） | 1 |

### 12.2 文档 superseded 清单

| 文档 | 状态 | 取代者 |
|---|---|---|
| `docs/v0.8.5/V0.8.5_PLAN.md` | ⚠️ 部分 superseded | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` |
| `docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md` | ❌ Superseded | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` |
| `docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md` | ❌ Superseded | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` |
| `docs/WORKBENCH_FOCUS_PRD_v1.0.md` | ❌ Superseded | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` |
| `docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md` | ❌ Superseded | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` §3 |
| `docs/DESIGN_P10_EXECUTOR_2026-09-13.md` | 📋 已批准未落地 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` §5.1 |
| `docs/DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md` | 📋 已批准未落地 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` §5.2 |
| `docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md` | 📋 已批准未落地 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` §5.3 |
| `docs/v1.0/V1.0.1_V0.8_UI_CONVERGENCE_PLAN.md` | ❌ Superseded | — |
| `docs/v1.0/V1.0.0_UI_UX_SPEC.md` | ❌ Superseded | — |

### 12.3 建议后续行动

1. **立即**：更新 V0.8.5_PLAN.md §5 路由表（`layer=action`、`/cases` → `/action`）
2. **立即**：恢复或重建 `v085_route_shell.test.tsx`（或明确 `nav4_shell.test.tsx` 为其 successor）
3. **F0 期**：P1-0a 止血（v1_runs 人工回执通道） + R02（生产调度器接线）
4. **F1 期**：D1 点火贯通（SourcePipeline → 生产调度器 → v1_signals）
5. **文档维护**：建立"单一权威 PRD"维护纪律——所有后续设计/计划变更必须同步更新 `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`

## 13. 二次复审：安全人员工作成果与当前代码对齐

- 时间：2026-09-14；关联 DEV-0221 / CHECK-0003。
- 基线：HEAD `7c6b3d23a6bd563267059207f727be8d671e38a6` + 本轮开始前已存在的工作树修改。NAV4 壳/主题改动、旧组件删除及未跟踪 PRD 均保留。
- 方法：按“用户要完成的工作 → 页面入口 → API → 服务 → 持久化 → 已有测试”反向追踪，应用 prd-iterative 三维审查与 redesign-existing-projects 体验诊断。
- 范围：全仓结构和过程记录梳理，关键业务链源码抽查；不是逐行审完全部仓库，也不是生产验收或完整安全扫描。
- 证据等级：A=本轮读取源码；B=本轮隔离定向测试通过；C=历史记录未复证；D=待 owner 裁决建议。A/B 均不等于真实工作场景验收。

### 13.1 核心结论

**方向成立，当前 PRD 不适合直接用作下一轮实施任务书。** 四菜单、本地优先、以事项串联证据与成果、复用经验证经验，符合已记录的 owner 目标；但现 PRD 混合了技术盘点、过期故障清单和远期目标，缺少明确岗位、日常成果、场景边界和可比较的成效指标。

当前产品可以概括为“资讯和知识平台，已经接入部分事项能力”。它还不能仅凭已有表、API、Skill 和测试数量，被认定为“安全人员从发现问题到交付成果的完整 AI 工作台”。

建议保留三项核心价值：**找到值得跟进的问题；形成有依据的结论或可核验产物；在下一次工作中复用适用经验**。这是待裁决的取舍原则，不新增产品范围。

### 13.2 需求澄清台账

| 维度 | 从当前材料得到的答案 | 状态 |
|---|---|---|
| 用户画像 | 单人安全从业者；历史曾偏安全分析/金融模板，近期裁决转向安全研究与实践 | 主岗位和首个成果仍待本轮回答 |
| 技术架构 | FastAPI、SQLite、Markdown、React 18、Vite 5、Tailwind 3；dsh/pi 为受管能力 | 已有约束，不重复询问 |
| 产品形态 | 本机 B/S 工作台；资讯、知识、行动、设置四菜单，能力嵌入既有页 | 已有约束，不另建壳 |
| 数据来源 | 采集热点、v1 信号、导入资料、wiki、人工判断与回执；开源候选须全量识别后排序 | 已有来源；关联覆盖需验收 |
| 成员粒度 | 首期单用户，暂无引入多租户依据 | 保留，不扩展团队系统 |
| 隐私定位 | 本地优先，但外部模型与同步可出站 | “数据不出域”已纠正；敏感资料范围后续按岗位澄清 |
| MVP 边界 | 现有 F0~F5 范围大，掺入 MITRE/CodeGarden 全阶段和历史修复 | 需随主岗位逐轮收敛 |

本轮已发出一个问题：优先以安全研究与实践、企业安全运营，还是金融合规与安全管理的日常成果检验产品。**在用户回答前不把推荐选项视为确认**。继续完成不依赖答案的事实审查；暂不输出声称已裁决的新版九章 PRD。

### 13.3 原报告需要撤回的事实判断

| 原判断 | 当前核对结果 | 证据 |
|---|---|---|
| SourcePipeline 未接生产 scheduler | 已注册 `v1_signal_intake_tick`，job 调 `run_intake_tick`；真实源持续运行效果未知 | A/B：[scheduler.py:199](../../backend/scheduler/scheduler.py)、[collect.py:558](../../backend/scheduler/jobs/collect.py)、`test_v1_ingest_bridge.py` |
| SK-01 无 API、无首页、无分区 | `/api/digests/priority` + 首页 `PriorityDigestCard` + practice_partitions 已存在 | A/B：[PriorityDigestCard.tsx:28](../../frontend/src/components/sentinel/PriorityDigestCard.tsx)、[SentinelHomePage.tsx:455](../../frontend/src/components/sentinel/SentinelHomePage.tsx) |
| Case 前端只读、无关闭操作 | 已有审批/启动/取消/验证/接受/拒绝/关闭及生成判断、行动 | A/B：[CaseDetail.tsx:148](../../frontend/src/components/v1/CaseDetail.tsx)、`c10_mutation_wiring.test.tsx` |
| WARM/COLD 仍 copy2 在线备份 | `backup_side_dbs` 调 `_snapshot_db`，后者用 SQLite Connection.backup | A/B：[backup_service.py:155](../../backend/services/backup_service.py)、`test_backup_service.py` |
| 前端仍裸 fetch、SSE 未统一 | 域客户端、lib/api、realtime.ts 已落，后续 DEV-0211 迁移 Sentinel | A/B：[realtime.ts](../../frontend/src/hooks/realtime.ts)、`c11_aggregate_and_sse.test.tsx` |
| 复用计数未诚实化 | `reuse_receipt` 等已从 adoption 表派生，来源关联与采用分离 | A/B：[knowledge_reuse.py:64](../../backend/services/knowledge_reuse.py)、`test_c12_knowledge_adoption.py` |
| 所有 Case 无法关闭 | 研究型无 Action 时可凭发布判断关闭；执行型另有守卫 | A/B：[case_service.py:478](../../backend/services/case_service.py)、`test_c08_artifact_cas_wiki_caseclose.py` |
| WARM 缺省路径不存在等于生产库缺失 | 环境变量可覆写路径，本轮无运行进程/三库查询证据，不能下结论 | A/C：[config/__init__.py:49](../../backend/config/__init__.py) |
| 4,598 pytest、0 skip 是当前全量结果 | PROGRESS 历史实际写 4,598 passed / 9 skipped；本轮只运行定向测试 | B/C：[PROGRESS.md](../../PROGRESS.md) |
| 13 gate 仍包含 crm | TOML 已去 crm、加入 interest_engine；数量相同掩盖成员变化 | A：[feature_gates.toml:16](../../backend/config/feature_gates.toml) |
| 全部 wiki 已接入自动复利 | 自动召回只查 v1_knowledge 的 published 行，不能代表全量 wiki | A：[knowledge_reuse.py:423](../../backend/services/knowledge_reuse.py) |
| SK-04 已由 CaseDetail 消费 | `generateKnowledge` 仅有客户端定义，无组件调用；后端生成存在 | A：[v1.ts:623](../../frontend/src/api/v1.ts)、[CaseDetail.tsx:395](../../frontend/src/components/v1/CaseDetail.tsx) |

以上属于本轮事实更正，不撤销此前开发成果，不以一次测试替代生产有效性证明。

### 13.4 按影响排序的发现

本节 P0 指阻断产品承诺/方案实施的矛盾，P1 指妨碍核心工作成果的问题，P2 指体验与治理增强。没有把代码计数、框架偏好或未复现的历史事故升格为漏洞。

#### RA-01 · P0 · “数据不出域”与实际外部推理能力矛盾

- 证据：PRD §1.1 原承诺；[gateway.py:739](../../backend/services/ai_hub/gateway.py) 构造外部模型地址，745 行把 prompt 放入请求，762 行发送。已有 egress 白名单保护凭据目的地，但这不等于材料不离开本机。
- 影响：安全人员可能按“全部本地”的理解处理内部材料，实际使用条件与产品承诺不同。这里证明的是能力边界，不声称本轮观察到数据泄露。
- 建议：表述改为本地优先，并按资料类型声明允许的推理/同步目的地；离线和敏感材料限制若要承诺，须有独立实现与验证。
- 处理：权威 PRD 文案已更正；出站产品策略仍待定位澄清，未修改 ai_hub。

#### RA-02 · P0 · 已批准执行设计的完成语义和约束保证存在冲突

- 证据：[执行器设计 §3/§5](../DESIGN_P10_EXECUTOR_2026-09-13.md) 计划把关闭条件改为“有终态 run 或 accepted artifact”；当前 [case_service.py:447](../../backend/services/case_service.py) 区分活动行动、活动运行、产物和发布判断。同一设计把 cwd/网络环境变量作为约束，而系统层隔离到后期才加。
- 影响：失败/取消也是终态，不能单凭终态证明工作完成；工作目录和环境变量也不能阻止任意子进程访问绝对路径或直接联网。产物写入的只读分析任务同样不是“零写入”。
- 建议：人工回执路线保留，记录操作者、产物、结果和验收；“停止/取消/研究完成/执行完成”分别表达。真实 pi 工具运行前需证明所声明的约束能被强制执行；验证未完成时不承诺任意工具都在边界内。
- 处理：在 PRD F0-6 记录复议原因。既有审批粒度、人工 plan 兜底等 owner 选择保留；本轮不擅自放宽守卫，也不标记设计风险已关闭。

#### RA-03 · P1 · 四菜单壳成立，但阻塞事项失去常规入口

- 证据：[routes/index.tsx:112](../../frontend/src/routes/index.tsx) 先声明 `/judge→/`，121 行仍留同路径页面；[SentinelJudgePage.tsx:559](../../frontend/src/components/sentinel/SentinelJudgePage.tsx) 是 CaseQueuePanel 唯一挂载点；[ExecOverviewPanel.tsx:35](../../frontend/src/components/v1/panels/ExecOverviewPanel.tsx) 只取 open/in_progress 的 8 条。[CaseDetailPage.tsx:72](../../frontend/src/components/v1/CaseDetailPage.tsx) “返回事项列表”实际跳 `/judge` 后回首页。
- 影响：blocked 事项以及总览截断之外的事项不能通过这条常规动线被发现；有详情深链不等于有事项管理。
- 建议：完整队列放回 `/action` 的既有内容区，支持状态/阻塞原因/检索/分页，详情返回保留过滤上下文。继续使用唯一四菜单。
- 验收：一条 blocked 事项、超过 8 条活跃事项、从详情返回原列表，均在浏览器内可完成。

#### RA-04 · P1 · 安全人员覆盖承诺大于当前输入契约

- 证据：[CaseDetail.tsx:233](../../frontend/src/components/v1/CaseDetail.tsx) 从标题/问题解析 CVE，243 行无 CVE 直接拒绝生成；252 行以证据标题代作 subject_name。[GenerateKnowledgeRequest:32](../../backend/api/v1_knowledge_write_api.py) 强制 action_id、cve_id 非空。
- 影响：工具评估、钓鱼分析、法规解读等无 CVE 工作无法自然复用同一出稿链；资料标题不等于组织的受影响资产上下文。研究型事项无需 Action 可关闭，却没有对称的无 Action 复盘输入。
- 建议：先确定第一岗位任务，明确 CVE 专项与普通研究各自输入、证据、结论和完成条件。缺资产时允许通用研究，但不声称判断本单位已受影响或已经排查完成。
- 验收：至少一个 CVE 和一个选定的非 CVE 任务，都无需伪造 CVE/action_id。

#### RA-05 · P1 · “启动成功”目前只代表 v1 Run 入队

- 证据：[run_orchestrator.py:62](../../backend/services/run_orchestrator.py) 只调 create_or_replay；[run_service.py:142](../../backend/services/run_service.py) 创建 queued 后返回；当前类没有 v1 Run claim/finish 执行实现。`worker_pump` 的 Skill 调度存在，不能自动推断消费了这条 v1 Action 链。
- 影响：页面已有“启动”不代表工具已经执行或能产出 Artifact。现 PRD 这项真实缺口需要保留，但不能扩大为所有研究事项都不能关闭。
- 建议：先交付已批准的人工回执闭环，再接受约束的执行器；排队、执行中、超时、失败、成功、已验收分别显示，重试有明确 attempt 语义。
- 验收：实际产生 Run 终态和文件产物，并完成校验、验收；重试不重复执行同一批准计划。

#### RA-06 · P1 · 首页摘要已有展示，但缺少推进工作和解释降级的能力

- 证据：[PriorityDigestCard.tsx:19](../../frontend/src/components/sentinel/PriorityDigestCard.tsx) 接收 mode/suggested_actions；107~111 行只渲染文字列表。[digests.py:45](../../backend/api/digests.py) 降级可能仍返回 HTTP 200。首页普通热点可深读，受管信号另在页面尾部立项。
- 影响：用户读到重点后仍要重新找原文/信号；无数据与模型失败都可能表现为普通空摘要。系统健康的 HTTP 状态不能替代业务结果。
- 建议：摘要带来源与更新时间、降级原因、对应事项或立项动作；复用现有信号和证据身份，不再造第四种内容 ID。
- 验收：从一条摘要连续到原文和事项；无源数据、模型失败、缓存陈旧各有准确状态。

#### RA-07 · P1 · 经验生成未在事项页闭合，知识默认入口偏加工而非使用

- 证据：`generateKnowledge` 在 [v1.ts:623](../../frontend/src/api/v1.ts) 有定义，组件无调用；[CaseDetail.tsx:411](../../frontend/src/components/v1/CaseDetail.tsx) 空态让用户等 SK-04 发布，却无生成入口。`/knowledge` 在 [routes/index.tsx:170](../../frontend/src/routes/index.tsx) 默认重定向 import；经验目录在 v1 子路由。
- 影响：完成事项后无法沿当前页面连续把成果变成经验；已有后端发布/目录/采用不等于日常复盘可用。
- 建议：事项内“整理经验”带入真实判断、执行或人工结果；审阅后发布。知识菜单优先呈现可查可用经验和待复查内容，加工工具保留为辅助入口。
- 验收：从已完成事项产出经验，再由第二个事项找到并采用，全程不直接调用 API。

#### RA-08 · P1 · 关键词相似与“经验适用”尚未形成完整契约

- 证据：[knowledge_reuse.py:423](../../backend/services/knowledge_reuse.py) 全取 published 的标题/正文做 CVE/词命中；不筛 expiry_at/review_at，也不在该召回函数核对前提和反例。另一个 recall 入口以 Case tags 弱匹配条件，采用与 outcome 已有存储。
- 影响：相关但已过期或前提不满足的知识仍可能列为候选；大量 wiki 文档也不会因为存在 FTS 就自然进入此召回。不能将推荐次数或采用点击等同于有效复利。
- 建议：保留可解释规则，先展示条件差异、过期/待复查状态、源版本，记录人工采用与使用结果；按测量决定索引优化或检索扩展。
- 验收：过期、反例冲突、撤回、无匹配均有明确行为；第二个独立事项采用后有实际结果。

#### RA-09 · P1 · 路线图按技术层串行，推迟用户能感知的最小成果

- 证据：PRD F0 退出要求 Artifact，F3 才交完整执行器；F4 绑定 MP-2/3/4，F5 才做“已存在”的摘要和复用。原九章技能要求中的用户故事、日常操作流、数据模型和可量化成功指标被架构数字替代。
- 影响：可能重新开发已有能力，也可能把简单研究闭环绑定到完整执行/标签系统，迟迟无法让用户试用。
- 建议：按研究成果、人工实践成果、受控执行成果逐次交付；每次都包含输入到复用的最短路径，扩展工程服务于已选场景。
- 验收：每期用一个真实任务证明价值，不以 router/service/Skill 数量作为退出条件。

#### RA-10 · P1 · CodeGarden 和 MITRE 设计尚有交叉契约冲突

- 证据：[CodeGarden 设计 §3/§4](../DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md) 写 phase2b 关闭、8 实践域、migration 117；当前 TOML 为 true，实践域已改 10 域，117 已由事件类型迁移占用。[attack_label_service.py:87](../../backend/services/attack_label_service.py) 的响应知识关联确为 stub。
- 影响：照稿实施会错误解释已开功能、冲突使用迁移号，且实践项目与 v1 Case/Action 的对应关系未明确，不利于同一成果追踪。
- 建议：全量开源候选识别裁决保留；新迁移按当前序列分配；明确一个实践项目如何关联事项和产物。MITRE 用作选定场景的证据辅助，不以补全所有标签为首个成果的前提。
- 验收：一条真实候选的原文、项目、事项、执行结果、经验能互相追溯；未审定标签不冒充结论。

#### RA-11 · P2 · 产品页面暴露大量开发诊断信息，关键阅读和操作优先级偏低

- 证据：CaseDetail 展示 `allowed_actions`、`revision`、“走查 3 路径”、`content_hash`；SignalPanel 空态解释 D1 验收；摘要正文 11px、状态 10px；Case 知识区在证据/判断之前，且多层边框卡片嵌套。
- 影响：用户需要先理解实现术语才能判断下一步，信息密集但工作重点不清晰。
- 建议：默认显示问题、证据、结论、下一步、阻塞原因与产物；ID/hash/revision 移入可展开审计详情；稳定列表和阅读栏优先。保留现有字体/主题体系，先修动线与状态，再做尺寸和排版微调。
- 验收：桌面和窄屏逐页检查阅读、键盘焦点、返回路径、长标题和错误态。此次仅源码诊断，未做截图视觉验收。

#### RA-12 · P2 · 文档权威、台账编号和测试口径仍会制造下一轮漂移

- 证据：根规则同时声明权威 PRD 和权威旧 spec；PROJECT 仍含旧架构数字/旧 gate/旧生命周期；DEV_LOG 有两个 DEV-0179；早期报告仍使用历史断言。NAV4 测试按源码第一条匹配检查路由，并不验证所有事项可达。
- 影响：越积累过程文档，越容易把旧缺口误作当前事实，或把静态守卫通过误作业务验收。
- 建议：产品决策只在权威 PRD 更新，详细技术契约保留引用关系和有效性说明；历史报告不回改成“当时就正确”，只追加更正；新记录从全文件最大编号递增。后续独立验收需沿用户旅程而非重复实现者的断言。
- 处理：本轮使用 DEV-0221、CHECK-0003 并在旧报告顶部声明更正优先级；既有重复编号未静默重排。

### 13.5 三维审查

#### 逻辑一致性

| 检查项 | 结果 | 结论 |
|---|---|---|
| 数据流闭环 | 发现问题 | 热点/信号/事项/经验有局部桥接，SK-04 前端和 v1 执行链仍断；RA-05/06/07 |
| 操作流覆盖 | 发现问题 | 阻塞队列缺常规入口，无 CVE 任务不能自然生成判断；RA-03/04 |
| 架构支撑 | 部分成立 | 现有栈能支撑单人研究；外部模型与不出域承诺、计划与隔离保证冲突；RA-01/02 |
| 优先级一致 | 发现问题 | F0/F3 依赖及已交付能力重复排期；RA-09 |
| 数据模型完整 | 发现问题 | 通用研究与 CVE/Action 强制输入不匹配；实践项目到事项关系待定义；RA-04/10 |

#### 批判性审查

| 挑战维度 | 结果 | 结论 |
|---|---|---|
| 用户行为 | 发现问题 | 没有证据证明用户愿意逐张卡维护所有对象和诊断状态，应围绕一次成果减少重复输入 |
| 过度工程 | 发现问题 | 全量标签、服务网格和全能执行器不应都阻断第一个研究成果；系统自检属于后台保障 |
| 技术可行性 | 发现问题 | cwd/env 不能独立保证进程约束；本地 B/S 不能单独保证数据不出站 |
| 十倍规模 | 待测且有瓶颈候选 | 召回全读 published 正文、Case 最多逐条读取 50 个 reuse receipt、总览最多 8 次聚合；未做性能实测，不虚报容量 |
| 更简单替代 | 有可用候选 | 研究结论先闭环；人工回执完成实践；索引/模板/既有 API 优先，是否引检索库由效果决定 |

#### 第一性原理

| 问题 | 回答 | 结果 |
|---|---|---|
| 核心价值是什么 | 帮安全人员把值得关注的问题变成有依据、可验证、可复用的工作成果 | 方向成立，首个岗位成果待确认 |
| 每个模块都服务它吗 | 采集、证据、事项、产物、经验直接服务；图谱、工具管理、系统健康应按需支撑 | 发现范围/默认入口偏差 |
| 只留三个功能是什么 | 重点问题筛选；事项内判断与成果；经验检索与复用 | 建议作为 MVP 取舍标准，未代替 owner 裁决 |

### 13.6 四菜单体验建议（D，待裁决）

| 菜单 | 用户进入时要回答的问题 | 默认内容建议 | 保留为辅助内容 |
|---|---|---|---|
| 资讯 | 今天什么值得跟进，依据是什么 | 重点摘要、来源/新鲜度、跟进或关联已有事项 | 全量 Feed、频道过滤、采集诊断 |
| 知识 | 有没有能用于当前问题的经验 | 检索、适用条件、历史成果、待复查清单 | 导入/加工/编译、图谱、演示画布 |
| 行动 | 哪些工作需要我推进，缺什么 | 完整事项队列、阻塞原因、审阅/验收、实践项目入口 | 复习、普通待办、工具健康 |
| 设置 | 如何定义方向、资料边界和运行成本 | 关注方向、模型/同步范围、预算、备份与异常 | 运维详情和扩展配置 |

不新增主导航，不恢复旧壳，不机械套用营销式大标题、背景图、动效或图标换库。对安全工作台，状态准确、证据可读、操作连续比视觉装饰更优先。

### 13.7 建议交付顺序与验收（D，待裁决）

| 顺序 | 最小交付成果 | 利用已有实现 | 仍需补齐 | 退出证据 |
|---|---|---|---|---|
| S0 事实与任务基线 | 确定主岗位、一个真实研究任务和一个实践任务 | 本轮审查、原 owner 裁决、已有来源 | 首岗位回答、输入/预期成果定义、矛盾设计复议 | 输入资料与人工预期成果可检查 |
| S1 研究工作可日用 | 一条资讯变成可关闭的有据结论，再沉淀经验 | intake、摘要、Case、判断、发布、关闭、采用 | 队列可达、摘要承接、选定场景输入、SK-04 前端、研究型经验契约 | 浏览器从首页到结论/经验，不粘贴 ID、不伪造 Action |
| S2 人工实践闭环 | 一个实践任务有真实结果和验收 | CodeGarden、Action、Artifact 校验与采用记录 | 人工终态/附件登记、项目与事项关联、失败与完成区分 | 文件可打开、hash 可验证、操作者/结果可追溯 |
| S3 受控自动执行 | 用已审批计划自动完成一个受限任务 | dsh/pi 桥、run_orchestrator、观测与产物服务 | v1 Run 消费、强制边界、超时/取消/重试、真实 vendor 验证 | 真执行与产物；越界不能发生，失败不能报完成 |
| S4 效果提升 | 第二个独立事项真正受益于既有经验 | interest、adoption/outcome、MITRE 基础、FTS | 条件/过期校验、按效果选标签联动、基于测量优化检索 | 采用及结果记录、人工工作耗时对照 |

这不是全面重建，也不是取消已经批准的 MITRE/CodeGarden 工作。它建议以首个工作成果安排依赖，避免把所有扩展完工当作日用前提。未在目标岗位确认前承诺工期。

建议指标需先采基线，目标值待裁决：

| 指标 | 计算口径 | 防止误读 |
|---|---|---|
| 重点有效率 | 抽样重点中，用户认为值得跟进的条目数 / 已评条目数 | 同时记录忽略原因，避免只抽感兴趣域 |
| 任务完成耗时 | 同类任务从输入可用到人工接受成果的中位耗时 | 与人工基线比较，不从 token 数推算节省时间 |
| 可辩护结论率 | 有可访问来源、适用条件和未知项的关键结论数 / 评审结论数 | 引用存在不等于来源支持该结论，需要人工核验 |
| 有效复用率 | 后续独立事项中采用且记录有效结果的次数 / 适用候选被评估次数 | 推荐、展示、自引用和仅点击不计有效复用 |
| 可感知失败率 | 测试故障中准确呈现原因和下一步的数量 / 注入故障数量 | HTTP 200 或空列表不是成功证据 |

### 13.8 新版九章 PRD 的具体修订入口

本表为后续修订清单，不是已经确认的新版 PRD。

| 章节 | 应补的内容 |
|---|---|
| 1 产品概述与目标 | 一句话成果定位，最多 3 个核心目标；系统健康为保障条件 |
| 2 用户画像与场景 | 主岗位、真实输入、3~5 个用户故事、使用频率；区分组织影响与一般研究 |
| 3 功能模块 | 四菜单职责、保留/按需/延期映射、能力输入输出；不以现有页面数量定义范围 |
| 4 系统架构 | 保留当前栈；明确业务记录、正文、索引、运行与同步边界 |
| 5 业务流 | 研究完成、执行完成、人工实践、失败取消、经验复用各自条件 |
| 6 操作流 | 早间筛选、事项推进、验收复盘、周期复查；每步有入口与下一步 |
| 7 数据模型 | Subject/Material/Signal/Case 等所有权，实践项目关联，经验条件和结果，避免多套完成状态 |
| 8 优先级与里程碑 | 参考 S0~S4，按真实成果验收；已有能力不重排为从零实现 |
| 9 风险与缓解 | 外部推理边界、执行约束、资料真实性、失败恢复、使用负担与容量测量 |

### 13.9 本轮验证与边界

后端命令（项目自带虚拟环境；conftest 在模块导入前隔离三库/wiki/日志并限制生产路径）：

```bash
.venv/bin/python -m pytest backend/tests/test_v1_ingest_bridge.py backend/tests/test_c08_artifact_cas_wiki_caseclose.py backend/tests/test_c12_knowledge_adoption.py backend/tests/test_run_orchestrator.py backend/tests/test_backup_service.py --tb=short -q
```

结果：**51 passed，1 条 Starlette/httpx 弃用警告**。shell 中 `python` 不存在、系统 python3 无 pytest，改用已有 `.venv/bin/python` 成功，未安装新依赖。

前端命令（工作目录 frontend）：

```bash
npx vitest run src/components/sentinel/PriorityDigestCard.test.tsx src/components/v1/__tests__/c10_mutation_wiring.test.tsx src/components/v1/__tests__/c11_aggregate_and_sse.test.tsx src/routes/__tests__/nav4_shell.test.tsx src/api/__tests__/v1_url_builder.test.ts src/components/v1/panels/SignalPanel.test.tsx
```

结果：**6 文件 / 76 passed**。有现存 act、React Router future flag、Node localStorage 警告，未当成零警告。前端组件用测试数据/模拟 API，不证明真实模型或生产执行可用。

文档验证：本轮相关内容的 37 个本地链接均存在，12 个 RA 发现与唯一 DEV-0221/CHECK-0003 已检查；限定本轮路径的 `git diff --check` 通过。全工作树检查仅报告既有 `PROGRESS.md:34` 行尾空白，本轮未修改该文件。

未做：全量 pytest/vitest、生产数据库盘点、真实采集或模型出稿、工具执行、浏览器截图/移动端走查、远端 CI 查询、备份恢复演练。没有声称已实现的代码缺口被本轮修好，也没有评定全系统验收 PASS。

### 13.10 本轮交付与继续条件

- **已实现**：更正权威 PRD 的过期事实；完成三维审查、四菜单体验诊断、逐项源码证据和建议验收顺序；追加 DEV/CHECK 记录。owner 可从本文 §13.4 检查每个问题的影响和证据。
- **未实现**：新版九章 PRD 定稿、UI/执行器/知识链路修复、真实工作验收。前者等待主岗位等需求逐轮澄清，后者属于后续开发和独立验收；不把审查建议混写成既成能力。
- **需补充考虑和增强**：真实资料的对外推理限制、无 CVE 任务、研究型复盘、失败与取消结案语义、知识过期/条件验证、完整队列及历史数据关联、生产恢复和容量基线。

prd-iterative 的需求摘要确认与九章 PRD 定稿尚未完成，因此不执行 project-brain 的“初始化 PROJECT.md”步骤，不重置现有项目生命周期。事实调查已完成，继续时从主岗位问题的回答接上，避免重复询问既有架构约束。

## 14. 批判性复审：四类安全工作是否能共用当前 PRD

### 14.1 总体判定

**产品方向成立，范围定义不成立。** “安全研究与实践、企业安全运营、金融合规、安全管理”不是一个同质用户场景，而是四组不同的输入、证据、权限、完成标准和责任边界。当前 PRD 把它们都归入“单人安全从业者”，会掩盖关键差异，导致同一套 Case/Action/Knowledge 契约对部分工作失真。

当前 PRD 可以作为平台能力说明，不能作为四类工作的共同 MVP。必须先规定一个共享内核和岗位模板边界，否则会出现“每类都能创建事项，但没有一类能稳定交付”的结果。

### 14.2 四类工作的不可混同之处

| 工作类型 | 主要问题 | 证据形态 | 完成标准 | 当前缺口 |
|---|---|---|---|---|
| 安全研究与实践 | 这个技术/工具/漏洞如何工作，是否值得复现 | 公开资料、实验记录、脚本、截图 | 结论可复现，限制和反例明确 | Action 强制 CVE/执行计划过窄 |
| 企业安全运营 | 本组织是否受影响，先做什么，谁负责 | 资产上下文、检测结果、处置记录、时间线 | 责任、状态、影响和后续动作可追溯 | 缺资产上下文和责任分派模型 |
| 金融合规 | 要求是什么，本组织如何证明符合 | 条款、控制项、制度、审计证据 | 条款到控制、证据、缺口、整改闭环 | Judgment/Knowledge 未建条款和控制映射 |
| 安全管理 | 如何排优先级、投入资源、跟踪风险 | 风险登记、指标、例外、决策记录 | 决策依据、责任人、期限和复盘可追溯 | 四菜单无管理视图和组织决策字段 |

### 14.3 对当前 PRD 的六个批判

1. **用户画像偷换概念**：单人部署不等于单一岗位。企业运营和合规工作即使只有一个操作者，也需要责任人、资产/控制范围和审计读者等关系模型。
2. **“Case 是统一容器”缺少最小字段证明**：同一 `question/goal/scope` 无法表达实验复现、资产影响、法规条款和管理决策四种完成语义。继续堆可选字段会形成空字段模型。
3. **“Action 可执行”风险过高**：研究实践可接受本机实验；企业运营可能触及生产资产；金融合规通常需要审计留痕而不是命令执行。统一自动执行器会把低风险和高风险场景错误地放进同一信任等级。
4. **“知识复利”被过度泛化**：研究经验、运营处置手册、合规控制证据和管理决策模板的有效期、适用条件和读者不同。仅靠关键词召回会返回语义相近但责任边界错误的知识。
5. **成功指标不可横向合并**：研究看复现成功与结论质量，运营看发现到处置时延，合规看证据覆盖率，管理看风险决策闭环。一个“Case 关闭率”会奖励错误的快速关闭。
6. **四菜单只是信息架构，不是岗位策略**：资讯/知识/行动/设置可以共享导航，但不能证明四类工作共享同一首页排序、同一摘要、同一审批和同一知识入口。

### 14.4 第一性原理结论

- 核心价值应定义为：**把安全人员面对的一个具体问题，转化为可核对、可负责、可复用的成果**。
- 共享内核只需要保证：来源/材料、事项、证据、结论、行动、产物、复盘、引用关系和审计记录的可追溯性。
- 岗位差异应通过模板和校验表达：研究模板、运营模板、合规模板、管理模板；不应复制四套壳或四套本体。
- 自动执行不是所有岗位的共同 MVP。合规和管理优先需要证据整理与审批，研究实践才适合从只读实验开始，运营执行必须另有资产和变更授权。

### 14.5 对 MVP 的批判性建议（待 owner 确认）

建议把 MVP 定义为**一个共享事项内核 + 四类模板只读/人工闭环**：

| 层级 | 应进入 MVP | 不应作为 MVP 前置 |
|---|---|---|
| 共享内核 | 材料/证据引用、事项状态、结论与未知、人工成果、复盘记录 | 全量 MITRE、CodeGarden 服务网格、任意工具自动执行 |
| 研究实践模板 | 资料→问题→实验/人工结果→可复现经验 | 先要求 CVE 编号或 pi 自动执行 |
| 企业运营模板 | 资产/影响/责任/期限→人工处置记录 | 没有资产上下文却承诺“本组织已排查” |
| 金融合规模板 | 条款→控制→证据→缺口→整改事项 | 仅用普通 Knowledge 代替条款映射 |
| 安全管理模板 | 风险→决策→责任→期限→复盘 | 用 Case 关闭率代表管理成效 |

### 14.6 必须新增的反例验收

在新版 PRD 定稿前，至少要用四个真实或脱敏案例分别验证：

1. 一个无 CVE 的安全工具/技术研究，能形成可复现经验；
2. 一个企业资产影响判断，能区分“未知”与“未受影响”；
3. 一个金融控制项检查，能追溯条款、证据和整改；
4. 一个安全管理决策，能记录责任、期限、例外和复盘。

任一案例需要伪造字段、跨页面复制正文、把失败标为完成或无法指出证据来源，都说明共享契约仍不合理。该结论是批判性审查结果，不代表这些模板已经实现。

### 14.7 已确认裁决：自定义流程的安全底线

用户已确认：自定义事项类型允许完整配置业务流程和规则，但保留不可关闭的系统安全约束。该裁决纳入 v0.8.6 上游设计：

| 可由用户配置 | 系统不可关闭 |
|---|---|
| 类型、字段、状态、步骤、审批角色、输出模板、提醒和 AI 建议 | 外部执行授权、工作目录/资产/网络范围、凭据隔离、资料出站策略、审计追加写、失败/取消真实性、超时/资源上限、审批时规则快照 |

AI 配置助手可以生成和修改左侧业务规则，但其输出必须经过系统校验，不能修改右侧底线。此裁决解决了“完整自定义”与“平台安全责任”之间的边界问题；具体策略字段、默认值和拒绝原因属于 v0.8.6 后续章节待设计内容。
