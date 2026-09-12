# hotspot 功能拆解与解耦方案（高内聚低耦合）

- 日期：2026-09-12
- 状态：**执行中** — Batch 1 已落地（DEV-0191），Batch 2~5 待 owner 裁决排期
- 定位：`docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md` §5.7「SSE 下沉」+ §6 D14（分层名存实亡）的**执行方案**；不替代 `docs/v0.8.5/V0.8.5_PLAN.md`（唯一实现 spec），不动三层壳 / 导航 / 视觉 token，全部变化在壳背后
- 方法：数字全部为本轮实测（3 个只读调研 pass + 主会话复核），与第一性原理分析 §3/附录 A 数字交叉一致处不重复取证

---

## 0. 摘要（一屏）

**一句话**：85 个 router 已经按功能分文件注册（`backend/api/_registry.py`）——"每个功能独立 API 接口"的**骨架**是存在的；真正的债不是"没拆"，而是**四类耦合**让边界名存实亡：

| # | 耦合类型 | 实测规模 | 状态 |
|---|---|---|---|
| ① | **反向依赖** services/scheduler → api | 8 处，根因单一：`publish_event` 住在 `api/events.py` | ✅ **今日清零**（Batch 1，守卫已上线） |
| ② | **层穿透**：api 直连 SQL / services 绕过 repo | api 层 `get_connection()` 50 次/21 文件；services 层 239 次/75 文件 | Batch 2/3 |
| ③ | **上帝模块**：单文件多域混杂 | `api/knowledge.py` 711 行/46 handler（超规格 4.7 倍）；`collection_service` 1071 行；`sync_bundle` 1033 行；`knowledge_service` 902 行横跨 5 域 | Batch 2/4 |
| ④ | **环**：模块级 + 域级 | `action_service ↔ run_service`（惰性 import 掩盖）；知识域 ↔ ai_hub 包（`ai_hub/write_back.py:81` 反调 knowledge_sync） | Batch 4（ai_hub 侧需裁决） |

**方案 = 5 条机械规则 + 5 批拆解**。核心思路：不新建任何一级入口，把"独立性"从**文件级**（已有）下沉到**规则级**——每条规则都有对应的机器断言（守卫测试 / grep 门 / CI step），让"高内聚低耦合"成为可验收状态而非口号。

---

## 1. 功能拆解总表（域 → API → service → repo → 表 → gate → 前端）

> 内聚度定义：✓ 高 = router/service/repo/表/前端五件套齐且无跨域 import；◐ 中 = 有上帝模块或部分表缺 repo；✗ 低 = 多重病灶叠加。
> "无 repo 表" = 该表由 service 层裸 SQL 直写（写路径不唯一，违反 R2）。

### 1.1 业务域

| # | 域 | API 路由（文件 → prefix） | service | repository | 核心表 | gate | 前端 | 内聚度 |
|---|---|---|---|---|---|---|---|---|
| 1 | **资讯采集** | hotspots / sources(581 行) / refresh / catchup(352) / categories / history / trends / interest_api | collection_service(1071)、catchup_service(659)、collect_validator(606)、source_health_machine | hotspot_repo(1070)、source_scheduler_repo、source_stats_repo、custom_source_repo、catchup_repo×2、trend_repo、crawl_url_check_repo | hotspots(WARM 隐式)、crawler_sources/runs、**raw_items†、collection_runs†**、catchup_*、interest_signals | secnews、interest_engine | secnews/、sentinel 壳 | ◐ |
| 2 | **知识库 v0**（kl/wiki） | **knowledge.py(711 行/46 handler)**、knowledge_chunks_api、knowledge_imported、wiki_tools、kl_metrics/rollback/compounding/planning/pipeline | **knowledge_service(902，横跨 dsh/ai_hub/evidence/migrate 四域)**、knowledge_sync(被 13 文件依赖)、compiler(661)、kl_state_machine、triggers/t1~t5 | **knowledge_repo(853/47 方法)**、kl_dead_letter_repo、wiki_event_repo | knowledge_*(WARM)、wiki_events、llm-wiki-2.0/*.md | secnews | knowledge/、secnews/knowledge | ✗ |
| 3 | **v1 证据引擎** | case_api(429)、judgment_api、action_api、run_api、artifact_api、knowledge_api(v1)、v1_signals_api、legacy_migrate×3 | case/judgment/action/run/artifact/knowledge/signal/v1_evidence/v1_admission/legacy_migrate 各自独立 | case/judgment/action/run/artifact/v1_knowledge_repo | v1_* 20+ 表 | 无（core） | v1/ | ✓（但 **v1_subjects/materials/signals/receipts、admission_*† 直写**） |
| 4 | **安全图谱** | security、compliance、cve_analytics | security/* 包 | security_repo | security_*、attack_*†、compliance_*† | security_graph | security/ | ✓ |
| 5 | **技能/agent** | skills、skill_registry_api×3、skill_builder_api、trigger_webhook_api | skill_registry(1639)、skill_runner(1132)、trigger_gate(1109)、playbook_engine(1452)、skill_eval(833)、agent_loop(965)、agent_memory(737) | skills_repo | skills、**skill_runs†、user_skills†、trigger_tickets†、kl_queue†、playbook_*†、loop_checkpoints†** | skill_registry、user_skills、trigger_gate | skills/ | ◐ |
| 6 | **告警** | alerts(v1)、alert_api(v2) | alert_service、alert_engine | alerts_repo、source_alert_repo | alert_* | feature_alert(v1) | （消费面少） | ✓ |
| 7 | **CRM** | crm_customers/opportunities/stats_api | 轻服务层 | crm_customer_repo、crm_opportunity_repo | crm_* | crm | crm/ | ✓ |
| 8 | **CodeGarden** | codegarden(463)、codegarden_ops(533)、codegarden_phase14 | codegarden_*_service ×6（scanner 619 / service 686…） | codegarden_repo×4（511/411/349/334） | cg_*（**cg_drift_assessments†**） | codegarden、codegarden_phase2b | codegarden/ | ✓ |
| 9 | **观测/质量** | observability_router(550)、observability_audit_api、health(369)、quality(382)、maintenance | observability*、cost_monitor | quality_repo | api_events†、job_runs†、agent_runs†、quality_check_logs(WARM 4.7M 行) | 无（基础设施） | secnews/observability | ◐ |
| 10 | **设置/密钥/同步** | settings(303)、secrets(556)、sync(363)、llm_status、image、mode、cache | **secrets_service(931)、sync_bundle(1033)** | secrets_repo、settings_repo、encryption_keys_repo、sync_*×3 | settings、llm_secrets、encryption_keys、sync_* | sync | settings/、secrets/、sync/ | ✗ |
| 11 | **个人工作流** | todos(331)、favorites(296)、annotations、reviews、tags、extract、deep_read、digests、recommend、search、content、export、reports、weekly_report、attention_events_api | 各自独立 service（extract/review/deep_read/digest/recommend/search/export/weekly_report…） | todo(616)/favorite/tags/reviews/annotations/deepread/digest/feedback_repo | todos、favorites、sm2_reviews、annotations、tags、deep_reads、digests、**attention_events†(零写入方)** | 部分旧 feature flag | 散布多目录 | ◐（search_service 运行时探测表名） |
| 12 | **AI 桥接**（横切） | llm_status、image、dsh_api、dsh_control_api、agents_api、mcp×5 | **ai_hub 包(3708 行，被 19 文件 import — 红线禁动)**、dsh(1077)、agent_bridge | — | agent_runs†、llm_usage_log†、llm_cache† | dsh、mcp | QualitySettings 等 | 红线（未裁决不动） |
| 13 | **SSE 事件**（基础设施） | events.py（瘦身后 ~110 行，仅 SSE 端点） | **core/events.py（总线，今日下沉）** | outbox_repo | v1_outbox | 无 | useSSE ×6 消费 | ✓ **今日修复** |

† = 无 repo、由 service 层裸 SQL 直写的表（R2 违规清单，Batch 3 处理）。

### 1.2 横切基础设施（不属于任何业务域，禁止业务反向依赖）

| 模块 | 职责 | 消费方 |
|---|---|---|
| `backend/core/events.py`（新） | 进程内 SSE 事件总线（publish_event / subscribe） | api/events.py + 全部 services/scheduler 发布点 |
| `backend/core/routers.py` | core router 白名单 + 扩展防重叠断言 | main.py |
| `backend/repository/db.py` | 连接 + ATTACH 三库 + 迁移 runner | 全部 repo（写路径应经 repo，见 R2） |
| `backend/exceptions.py` / `logging_config.py` / `observability.py` | 错误契约 / 日志 / 观测 | 全仓 |
| `backend/utils/url_safety.py`、`utils/concurrency.py` | SSRF 防护 / 全局限流 | 出站点、采集 |

### 1.3 前端域客户端现状（解耦的另一端）

| 层 | 现状 | 问题 |
|---|---|---|
| 传输层 `lib/api.ts` | apiFetch/getJSON/postJSON（4 导出，14 文件采用） | 无业务语义，采用率低 |
| 域客户端 `api/v1.ts` | 38 个函数，仅覆盖 /api/v1/* + skill-registry/v1 | 唯一成型样板，但只服务 v1 域 |
| **裸 fetch** | **280 次 / 106 文件**（15 个 hook 占 59 次） | `/api/knowledge/items` 被 **6 文件**、`/api/hotspots` 被 **5 文件**重复调用 |
| 服务端状态 | 无 react-query/SWR；唯一数据 context 是心跳条 PipeContext | 同端点多处拉取、无失效层（DEV-0167 根因） |
| SSE | useSSE（types 过滤）+ 两套失效实现（sentinel 节流重拉 / v1 精确失效） | 统一客户端时应把"事件→按端点失效"做成一等能力 |

---

## 2. 耦合病灶清单（实测，P0/P1/P2 分级）

| 级 | 病灶 | 证据 | 归属批次 |
|---|---|---|---|
| **P0** | services/scheduler → api 反向依赖 ×8 | compiler.py:545、collection_service.py:286、outbox_dispatcher.py:56、alert_service.py:189、jobs/digest.py:16、jobs/maintenance.py:541,677、jobs/_runtime.py:45（全为 publish_event） | ✅ Batch 1 已清零 |
| **P0** | `api/knowledge.py` 711 行 / 46 handler | 规格上限 150 行，超 4.7 倍；router 内混 items/chunks/search/stats/import 多资源 | Batch 2 |
| **P1** | api 层直连 SQL：50 次 get_connection / 21 文件 | `conn.execute(` 60 次；违反"数据访问只有 repository 一层" | Batch 2 |
| **P1** | services 绕过 repo：239 次 / 75 文件 | 重灾区 sync_bundle(15)、maintenance_service(41 execute)、knowledge_service(18)、collection_service(11) | Batch 3 |
| **P1** | 写路径不唯一：~25 张表无 repo（† 清单） | raw_items、collection_runs、skill_runs、trigger_tickets、kl_queue、v1_subjects/materials/signals/receipts、admission_*、api_events、agent_runs… | Batch 3 |
| **P1** | `action_service ↔ run_service` 硬环 | action_service.py:313 / run_service.py:93 双向惰性 import | Batch 4 |
| **P1** | 知识域 ↔ ai_hub 域级环 | knowledge_service→ai_hub.prompts/service；ai_hub/write_back.py:81→knowledge_sync | Batch 4（**ai_hub 侧需裁决**） |
| **P1** | 上帝服务：collection_service 1071 / sync_bundle 1033 / secrets_service 931 / knowledge_service 902 | knowledge_service 单文件 import dsh_adapter、ai_hub、v1_evidence、legacy_migrate 四域 | Batch 4 |
| **P2** | `search_service.py:43-49` 运行时探测表名 | `"warm.knowledge_items" if "warm" in attached else ...` — 写路由"靠环境" | Batch 3 附带 |
| **P2** | config 三处真相 | pydantic 43 字段 / api/settings.py 写 KV / main.py:57-63 DB 覆盖 1 键 | Batch 5 |
| **P2** | 前端 280 裸 fetch / 36 端点被 ≥2 文件重复调用 | 见 §1.3 | Batch 5 |
| **P2** | `data/migrations/` 副本腐化（停在 070，缺 44 个） | 无单一 schema 真相源（D12 关联） | 建议并入 P0-0 止血批 |

---

## 3. 解耦规则（R1~R6，全部机械可断言）

| 规则 | 内容 | 断言方式 | 状态 |
|---|---|---|---|
| **R1** | services / scheduler / collectors / repository 四层**禁止 import `backend.api`**；基础设施一律下沉 `backend/core/` | `backend/tests/test_layering_guard.py`（AST 全量扫描，注释/文档不误报） | ✅ **今日上线** |
| **R2** | **一表一 repo 一 writer**：任何表要么有唯一 repo，要么在豁免清单显式登记（清单入本文档并随批收缩） | 守卫测试：扫 services 层 `INSERT INTO <table>`，对照 repo 注册表 + 豁免清单 | Batch 3 落地 |
| **R3** | router ≤150 行（既有规格）且 **0 直连 SQL** | 守卫测试：api 层文件行数 + `get_connection|conn.execute` 归零断言 | Batch 2 落地 |
| **R4** | 域内零环（import 级） | 守卫测试：AST 构建 services 依赖图，SCC 检测 | Batch 4 落地 |
| **R5** | 前端**同一端点唯一 hook owner**：每个后端端点只允许一个 hook/域客户端函数持有 fetch，组件只消费 | lint 约定 + 域客户端覆盖率断言（裸 fetch 单调下降） | Batch 5 落地 |
| **R6** | **ai_hub 红线**：不动 `gateway._try_order` / `service._resolve_provider` 调用链（AGENTS.md 既有裁决）；ai_hub 包内部拆分（含 write_back 外移）须 owner 显式授权 | 既有约定，本方案不触碰 | 待裁决 |

---

## 4. 五批路线图

> 排序原则：**先立规则（守卫），再做重构**——每批结束时该批对应的守卫上线，防止回潮。所有批次均要求：pytest 全量 0 回归 + `generate_meta.py --check` + 触碰文件 ruff 0 错 + git 显式 pathspec 小步提交。

### Batch 1（✅ 2026-09-12 已落地，DEV-0191）：SSE 事件总线下沉

| 项 | 内容 |
|---|---|
| 动作 | 新建 `backend/core/events.py`（订阅池 + publish_event + subscribe/unsubscribe）；`api/events.py` 瘦身为纯 SSE 端点（HTTP + outbox 重放）；9 个发布点改 import；3 个测试改打桩位置；新增 `test_layering_guard.py`（R1 断言） |
| 效果 | **8 处 services→api 反向依赖清零**；R1 从"文档约定"变为"机器断言"；api/events.py 122→~110 行且不再被业务层 import |
| 验收 | 定向 51 用例通过（含新守卫 2 条）；`generate_meta --check` OK（85/127/57/13 不变）；ruff 触碰文件 0 错；全量回归结果见 DEV_LOG DEV-0191 |
| 风险 | 日志从 stdlib logging 换 loguru（debug 级，符合全仓规则）；SSE payload/重放语义逐行照搬，行为不变 |

### Batch 2：API 层收口（预计 2~3 天）

1. **拆 `api/knowledge.py`（711 行 → 按资源 4~5 个子 router）**：items / chunks / concepts+graph / stats+import 各自成文件，`prefix` 与全部 URL **不变**（前端零感知），`_registry.py` 挂载点不变。拆完该文件族全部 ≤150 行。
2. **api 层直连 SQL 清零（50 处/21 文件）**：每处下沉到对应 service 或 repo；observability_router(550 行) 是最大单点，顺带拆分。
3. **R3 守卫上线**：api 层行数 + 零 get_connection 断言（存量清零后开启，一次性还清）。
- 验收：`GET /api/knowledge/*` 等 URL 行为逐条等价（契约测试先行）；api 层 `get_connection` 命中 = 0。

### Batch 3：services 绕 repo 收敛 + 无 repo 表补齐（预计 3~5 天，可选两档）

- **档 A（冻结增量，推荐先行）**：新代码/新表强制走 repo（R2 守卫以"豁免清单"模式上线——存量命中白名单，新表不在白名单即失败）；`data/migrations/` 腐化副本删除或同步。
- **档 B（全量还清 239 处）**：按域分小批下沉，顺序 = 重灾区优先：maintenance_service(41) → sync_bundle(15) → knowledge_service(18) → collection_service(11) → trigger_gate/queue(11) → 其余；同时给 † 清单 ~25 张表补 repo（v1_* 四表优先——它们是证据引擎的写路径）。
- 附带：`search_service` 运行时探测表名改为显式声明（消"写路由靠环境"）。
- 验收：R2 守卫豁免清单单调收缩至 0（档 B），或冻结清单入档（档 A）。

### Batch 4：解环 + 上帝服务拆分（预计 3~5 天）

1. **action↔run 解环**：提取共享编排接口（如 `run_orchestrator`），action_service 不再 import run_service；R4 环检测守卫上线。⚠️ 时序上应与第一性原理 **P1-0 执行器**（run 永远 queued 的产品决策）合并考虑——执行器形状定了再动这两个文件，避免二次重构。
2. **knowledge_service(902) 拆分**：按既有 import 边界切四块——dsh 适配 / ai 深读改写 / v1 evidence 桥 / legacy migrate，各自独立模块，knowledge_service 只留编排。
3. **collection_service(1071) 拆分**：采集编排 / 去重与准入 / 源健康状态机三块（source_health_machine 已是独立 import，物理搬出即可）。
4. **ai_hub write_back 外移**（解知识↔ai_hub 域级环）——**R6 红线内，需 owner 显式授权**。

### Batch 5：前端域客户端收敛（预计 1 周）

1. 在 `lib/api.ts` 之上建域客户端：`api/hotspots.ts`、`api/knowledge.ts`、`api/sources.ts`、`api/codegarden.ts`（样板 = 现成 `api/v1.ts` 38 函数模式）。
2. 15 个裸 fetch hook 换域客户端 + 端点常量化（组件零改动即可完成大头）。
3. 立 R5"同一端点唯一 hook owner"：`/api/knowledge/items` 6 文件→1、`/api/hotspots` 5 文件→1。
4. SSE 失效统一：把 v1 的精确失效（useSSEAggregateInvalidate）与 sentinel 的节流重拉收敛为"事件→按端点失效"一等能力，防第三套实现。
- 验收：裸 fetch 计数单调下降（守卫脚本报告基线 280→目标 <100）；重复端点调用归零。

---

## 5. 需 owner 裁决

1. **与 P0-0 止血批的排序**：第一性原理 §0.1 的七个 P0（RCE / 备份空产出 / 明文密钥…）与本方案正交但更紧急。**建议 P0-0 先行**，本方案 Batch 2+ 在其后排期（Batch 1 因风险极低已先落地）。
2. **ai_hub 包拆分**（R6 红线）：write_back 外移可解知识域↔ai_hub 域级环，但触碰红线包结构，需显式授权。
3. **Batch 3 档 A（冻结增量）vs 档 B（全量还清 239 处）**：第一性原理 §7 倾向冻结；本方案给两档，档 A 半天可上线守卫、档 B 需 3~5 天。
4. **WARM/COLD 显式前缀策略**（D12 关联）：retention.json(103 表) 是温度层真相源，但写语句 0 显式前缀。建议与 P0-0 备份批合并处理（同一批停机窗口），不单独排期。
5. **CodeGarden / CRM 冻结范围**：两域内聚度已是 ✓ 高（无耦合债），但全 0 数据（第一性原理 D19）。本方案不拆不动；是否按减法清单移出核心动线属产品决策。

---

## 6. 与既有治理的关系（不变项）

- Feature Gates / `core.include`/`core.exclude` / scoped AGENTS.md / CI 分类门：**全部沿用**，本方案只加守卫不改门槛。
- 三层壳 / 路由表 / SSE 契约（C11 R18 outbox 双源）：**不变**（Batch 1 已验证 payload 逐行照搬）。
- `generate_meta.py` 数字门：Batch 1 后 85/127/57/13 不变；后续批次若新增 service/repo 文件须同步 ARCHITECTURE.md。
- 实现与验证分离：每批先写守卫/契约测试，实现侧不自评 PASS，验证结果记 DEV_LOG。
