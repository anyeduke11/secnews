# Hotspot 安全人员 AI 工作台 PRD（单一权威版本）

> **日期**: 2026-09-14  
> **状态**: 既有产品方向保留；2026-09-14 二次复审已更正事实基线，新用户定位与分期调整仍待逐轮澄清  
> **真相源**: 当前工作树代码 + 可追溯验证记录；过程文档须核对日期和后续修复，不能直接作为当前运行事实  
> **取代**: `docs/v0.8.5/V0.8.5_PLAN.md`（路由/接口事实已更新，旧文档标注 superseded）、`docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md`、`docs/WORKBENCH_FOCUS_PRD_v1.0.md`、`docs/DESIGN_P10_EXECUTOR_2026-09-13.md`、`docs/DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md`、`docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md`、`docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md`

---

## 阅读前提：2026-09-14 二次复审

本轮对应 DEV-0221 / CHECK-0003。完整证据、三维审查、体验诊断和待裁决建议见 [对齐审计报告 §13](audit/PRD_ALIGNMENT_AUDIT_2026-09-14.md#13-二次复审安全人员工作成果与当前代码对齐)。

- 已核对当前工作树（基于 `7c6b3d23a6bd563267059207f727be8d671e38a6`，包含本轮开始前已有修改）；后端定向测试 51 项、前端定向测试 76 项通过。没有进行生产数据库盘点、真实模型调用、浏览器验收或全量测试。
- 下文数据库行数、备份日期和全量测试数字是初稿的历史记录，**本轮未复证，不能当作当前生产事实或验收凭据**。尤其不能由 Run 表零行推断没有执行代码，由缺省路径不存在推断生产库丢失。
- 已纠正：采集任务“未注册”、SK-01“无首页/API”、Case“只读”、WARM/COLD“仍用 copy2 备份”、前端“仍用裸 fetch”、复用“未计真实采用”等过期结论。
- 实质缺口仍包括：v1 Action 的真实执行消费、四菜单内完整事项队列可达性、非 CVE 场景输入、摘要降级可见性、知识适用条件与真实成果验收。文档更正不代表这些代码问题已修复。
- 本文仍是唯一产品入口。详细设计中的已批准选择继续保留，但其技术可行性和验收冲突须显式记录；本轮建议不自动成为新裁决。

## 第 1 章 · 产品概述与核心飞轮

### 1.0 v0.8.6 产品裁决增量

- 四类安全工作共用“资讯 → 知识 → 行动 → 结果验证 → 经验沉淀 → 复用”路径。
- 事项按资讯和工作类型生成标准模板；用户可以创建自定义事项类型。
- 自定义类型可由用户完整配置业务流程和规则，AI 提供结构、字段、步骤、门禁、审批和输出模板建议。
- **不可关闭的系统安全底线**：外部执行授权、执行范围限制、凭据保护、资料出站控制、审计留痕、失败/取消真实性、资源与时间上限、审批时规则快照和版本追溯。自定义业务规则不得绕过这些底线。
- 该底线是平台约束，不代表本轮已经完成全部执行器和出站控制实现；实现与验证仍须按审计记录分开验收。

### 1.1 一句话定位

**面向安全从业者的单人本地 AI 工作台**：SecNews 资讯聚合 + 知识复利 + 安全实践域执行，运行在用户自有机器上。**本地运行不等于数据不出域**：配置外部模型或 WebDAV 同步时，相关内容可离开本机；离线模式、资料分级与外部推理限制不能视为已实现承诺。

### 1.2 核心目标

| # | 目标 | 可量化指标 |
|---|---|---|
| **G1** | **感知效率** | 每日端到端：一个真实源从抓取到可被 Case 立项，失败/陈旧/部分成功可辨别 |
| **G2** | **研判可辩护性** | 每条 Judgment 带证据引用；同 case 同一 claim_type 同时只 1 个 published |
| **G3** | **行动可执行性** | 每条 Action 经审批可执行；产出 Artifact 可验证；Case 可关闭 |
| **G4** | **知识复利** | 第二个同类 Case 自动浮现知识 + 1 条真实采用回执 |
| **G5** | **系统可信度** | 零静默失败；AI 降级诚实声明；备份可恢复 |

### 1.3 飞轮模型

```
感知（资料）→ 研判（判断）→ 行动（执行）→ 沉淀（知识）→ 复利（复用）→ 更快/更准的感知
     ↓              ↓             ↓             ↓             ↓
  真实源信号     证据 Judgment   审批 Run      条件化 Knowledge  自动召回 SK-05
  v1_signals    引用/反证/未知   Artifact      review_at 复查   adoption 回执
```

**飞轮不转的三种死法**：
1. 感知无有效供给（采集任务虽已注册，实际源可用性、准入结果与新鲜度仍须运行证据）
2. 研判无产物（AI 降级为 mock、Judgment 不引用证据）
3. 行动无闭环（v1_runs 永远 queued、Artifact 造不出、Case 无法关闭）

---

## 第 2 章 · 当前状态诚实报告

> **口径**: 实现状态按二次复审核对；数据库行数等数字保留初稿记录，未经本轮复证。代码存在、隔离测试通过、真实工作验收是三个不同等级。

### 2.1 壳层与导航

| 能力 | 状态 | 说明 |
|---|---|---|
| **NAV4 四菜单** | ✅ 已落地 | 资讯 / 知识 / 行动 / 设置；`SentinelShell` 唯一壳 |
| **SentinelLayout 三层路由** | ⚠️ 部分退役 | `/` 资料层、`/action` 行动层、`/cases/:id` 深链 存活；`/judge` 和 `/judge/graph` 已重定向，`SentinelJudgePage` 组件存在但不可达 |
| **PageLayout 工具页** | ✅ 53 路由 | 全部 lazy 加载，通过 `menuOf()` 自动归属四菜单 |
| **SecNewsShell** | 已拆挂且工作树已删除旧文件 | 6 视图直挂 PageLayout；该删除在本轮开始前已存在 |
| **UTILITY_GROUPS** | ✅ 已删除 | 17 项更多菜单已物理删除 |
| **主题模式** | ✅ 3 态 | light / dark / paper（暖米黄纸底 + 衬线字体） |

**当前关键不一致**：旧 spec 的 `layer=action`、`/cases→/action` 已在本轮开始前回写，勿重复列为待修。真正的动线缺口是 `CaseQueuePanel` 只在已被 `/judge→/` 重定向遮蔽的旧页面挂载；行动页总览仅取前 8 个 open/in_progress 事项，不包含 blocked，不能替代完整事项队列。

### 2.2 v1.0 域对象（9 对象 + 3 receipt）

| 对象 | 迁移 | Service | API | 数据 | 状态 |
|---|---|---|---|---|---|
| Subject | ✅ 096 | ✅ | — | 1 行 | 基础就绪 |
| Material | ✅ 096 | ✅ | — | 6 行 | 基础就绪 |
| Signal | ✅ 096 | ✅ | GET | 5 行 | **只读，无写端点** |
| Case | ✅ 098 | ✅ | 查询/写入/关联/聚合 | 5 行（历史） | 已有立项/关闭；研究型可无 Action 关闭，执行型受产物等守卫约束 |
| Judgment | ✅ 100 | ✅ | 4 端点 | 1 行 | 可生成/发布 |
| Action | ✅ 101 | ✅ | 6 端点 | 1 行 | 可生成/审批/启动/取消 |
| Run | ✅ 101 | ✅ | 2 端点 | **0 行** | **永远 queued，无执行体** |
| Artifact | ✅ 101 | ✅ | 6 端点 | **0 行** | 可 verify/accept/reject，但无产物可登记 |
| Knowledge | ✅ 102 | ✅ | 7 端点 | 1 行 | 可发布/复查/采用 |
| evidence_receipts | ✅ 096 | ✅ | — | 20 行 | 幂等提交正常 |
| v1_knowledge_revisions | ✅ 102 | ✅ | — | 2 行 | append-only 正常 |
| v1_knowledge_adoptions | ✅ 102 | ✅ | — | 1 行 | 真实采用回执 |

**关联表说明**：初稿记载 `v1_case_judgments` (0)、`v1_case_actions` (0)，本轮未重新查询；两个 repo 均有 `link_to_case` 写路径。需核对具体数据来源与调用，不能以历史空表作为“无关联能力”的证据。

### 2.3 数据层

| 组件 | 状态 | 说明 |
|---|---|---|
| **HOT 库** (`hotspot.db`) | ✅ 14,503 hotspots + v1 对象 + wiki FTS | schema_version=126，正常 |
| **WARM 库** (`hotspot-warm.db`) | 生效路径待运行核验 | 缺省路径与运行时环境可不同；FTS 是检索索引，不等于业务知识表，不证明 WARM 完整或丢失 |
| **COLD 库** (`hotspot-cold.db`) | ✅ 存在 | audit_log 等归档 |
| **Backup** | 代码已有修复；本轮定向测试通过 | `_snapshot_db` 使用 SQLite backup API，侧库有 manifest + sha256；当前生产覆盖、新鲜度和恢复能力需独立演练 |
| **Wiki-first** | ✅ 7,734 FTS 条目 | `wiki_items_fts` 在 HOT 库中；`llm-wiki-2.0/` md 真源 |
| **Schema 真相源** | ⚠️ 隐式 | 启动期逐条跑 119 个 migration SQL；无独立 schema 版本快照 |
| **跨库事务** | ⚠️ 不原子 | WAL 模式下跨 ATTACH 事务不原子（已知限制） |

### 2.4 AI 能力

| 能力 | 状态 | 说明 |
|---|---|---|
| **ai_hub** | ✅ 四级链 | env → settings.kv → router → yaml；5 providers；断路器 + provider health |
| **dsh** | ⚠️ 受管子进程 | ProcessSupervisor + bridge；真 vendor 未实测；mock 降级可用 |
| **pi** | ⚠️ agent_bridge | stdio JSON-RPC 协议已实测对齐 0.84.4；流式 UI 未接 |
| **SK-01** daily-priority-intel | 后端/API/首页已接线 | `/api/digests/priority` + `PriorityDigestCard` 已渲染兴趣分区；摘要缺少原文/事项动作且未展示响应 mode |
| **SK-02** cve-impact-brief | 生成/发布代码路径存在 | generate → draft → publish；真实模型与来源支撑质量未由本轮验收 |
| **SK-03** inspection-materials | ✅ 生成 | 生成/审批/执行；**执行体 P1-0 待落地** |
| **SK-04** action-retrospective | 后端生成 API 存在；事项前端未接线 | `generateKnowledge` 客户端存在但无组件调用；CaseDetail 只有经验展示/采用，不能声称浏览器内复盘闭环 |
| **SK-05** reuse-experience | ✅ 自动召回 | `auto_recall_for_case`；已产生 adoption 回执 |
| **SK-06** knowledge-review-due | ✅ job | Daily 04:00 Shanghai；case blocker 机制 |

> **2026-09-18 管线 LLM 能力补齐（方案 B，三 gate 默认关）**：pi 成为 ai_hub 第 5 种 provider type（`pi -p --mode json` 子进程，prompt 走 stdin，NDJSON 解析与 agent_bridge 共享 `ai_hub/pi_transport.py`，认证由 pi 自管）；新增三项采集管线能力 — 语义门禁（`info_filter_gate` 规则 neutral 时 LLM verdict-only 判别，gate `semantic_filter`，失败 fail-open 保留）、智能分类增援（`auto_classifier` 纯规则 miss 时 LLM 补 domain，gate `ai_classify`，domain 词表严格校验）、NER 实体抽取（t1 打分成功后实体落 `knowledge_items.entities`，gate `pipeline_ner`，迁移 119）。gate 关闭时行为与现状一致；ai_hub 红线不破（管线 LLM 单出口走 gateway）。Spec: `docs/superpowers/specs/2026-09-18-pipeline-llm-pi-provider-design.md`。
>
> **2026-09-27 pi 升主力引擎（owner 裁决"pi 取代原来的 aihub"）**：`llm.yaml` `default_provider: pi` + `fallback_order` pi 带头（ollama/sensenova/qwen/openai 降兜底不删除，pi 失效时无害兜底）；`_call_provider_chat` 补 pi additive 分支（messages 经 `serialize_messages_to_prompt` 序列化单轮 prompt，max_tokens/temperature 为 http 语义不下传）。既有 `_try_order`/`_resolve_provider`/场景重排零触碰（红线纪律同方案 B）；router tier 对 light 任务（如 summary）仍按既有策略分流，不因主力化改变。实弹修正：pi models 留空 = 不下传 `--model` 用 pi 默认上游（裸名 `claude-sonnet-4-5` 在 pi 0.87.1 跨 provider 歧义且无已认证项 → rc=1）。实弹验收：score 首链 `provider=pi ok=1`（14.1s）+ chat 分支 15.5s 真回复 + pi 瞬时失败由 fallback 兜住（usage log 如实记录）。Spec: `docs/superpowers/specs/2026-09-27-pi-primary-engine-design.md`。
>
> **2026-09-27 首页四阅读模式重定义（owner 裁决，DEV-0236 P1 + DEV-0237 P2）**：四按钮语义从纯前端渲染切换升级为各自后端语义 — **全量**（原简报：当轮收录全部资讯）/ **精选**（新功能：`pick_service` 多信号合成 pick_score = quality_score + 关注域 boost ×25 + 收藏源 +10 + 时效衰减，每轮采集后 Top-30 落 `hotspots.pick_score` 列（迁移 129），视图 `GET /api/hotspots/picked` 按 pick_score DESC）/ **深度**（精读：summary≥200 字或标题命中分析类词表的候选 + 用户收藏自选）/ **告警**（收窄为"需用户执行动作"的落地资讯：4 规则词表筛 → pi 复核「是否需读者执行动作」(action_hint: patch/investigate/monitor/respond) → `alert_events` 落库 → 首页真告警列表 4 分类 tab + 未读徽标 + 已读/解决；fail-open: LLM 失败时 ≥2 强信号候选放行）。假告警（前端取最高分单条）撤除；`/api/alerts/v2` 加 rule_type/scope 过滤零新增端点。实弹：pi 复核正确拒绝 4 条评论类误中候选 + 确认真告警并输出高质量理由；pick 评分 7d 回看 evaluated=1000/picked=30。Spec: `docs/superpowers/specs/2026-09-27-four-modes-redefine-design.md`。
>
> **2026-10-01 拒收日志人话化 + 迁设置运维区（DEV-0238）**：`quality_rejection_log.reason` 的机器 flag（如 `content_hash_duplicate`）对用户不可读 — 落地为**双层解释**：前端词典兜底（`rejectionReasons.ts` 10 flag 全映射中文短语，零 LLM 恒可用）+ 后端 LLM 批量人话（`rejection_explain_service` 单次 `generate(task="rejection_explain")` 回填 `explain` 列（迁移 130），IS NULL 幂等、失败保持 NULL 下轮重试、每轮 LIMIT 200，采集尾部第 3 个异常隔离 tick 挂点）。拒收日志页从 `/quality` 校对室收缩迁出，以 `RejectionLogCard` 落位 `/settings?cat=ops` 运维区第 4 卡（explain 优先显示 + 词典 flag 恒显）；`/quality/rejection` 重定向兼容。Spec: `docs/superpowers/specs/2026-10-01-rejection-explain-design.md`。

### 2.5 MITRE ATT&CK 标签体系

| 期 | 内容 | 状态 |
|---|---|---|
| **MP-1** 图谱点火 | attack_techniques (244 条) + attack_cwe_map (714 条) + security_edges (17,616 条) | ✅ 已落地 |
| **MP-2** 事件类型 | 11 类词表 + 5 表迁移 + 4 service + 6 API + 25 语料 | ✅ 基础设施已落地；**候选池待 owner 人审** |
| **MP-3** L1 漏洞绑 CVE | CVE→technique 标注 + NVD 接入 | ❌ 未启动 |
| **MP-4** L3 响应 + 双向关联 | `knowledge_technique_ref` 表 + `attack_label_service.get_knowledge_for_techniques()` | ⚠️ Stub（返回空列表）；表未建 |

### 2.6 已批准设计待落地清单

| 设计 | 批准日期 | 实施状态 |
|---|---|---|
| **P1-0 执行器** | 2026-09-13 | v1 Run 创建桥已存在，真实消费/终态执行未落；迁移无 `plan_json`/`boundary_hash`/`executor` 列 |
| **CodeGarden 安全实践域** | 2026-09-13 | ⚠️ 部分：practice_domain 分类已落；`cg_projects.practice_domain` 列 + S1 开源信号提取未落地 |
| **MITRE MP-3 L1 漏洞** | 2026-09-13 | ❌ 未启动 |
| **MITRE MP-4 L3 响应** | 2026-09-13 | ⚠️ Stub |
| **Workbench Focus** | 2026-09-12 | 优先摘要前端分区、兴趣引擎和域词表已落；工作流与效果验收仍须补齐 |

### 2.7 B0-B7 业务闭环整改进度

| 整改进度 | 状态 | 说明 |
|---|---|---|
| **R01** 证据持久化 | ✅ 已修 | `_insert_subject/material/signal` 真实 INSERT |
| **R02** 生产调度器接线 | 代码已接线 | `v1_signal_intake_tick` 已注册并调用桥；本轮桥测试通过，持续真实供给未验收 |
| **R03** 失败后游标推进 | ✅ 已修 | `items_committed > 0` 才 advance |
| **R04** Worker 真实 dispatch | ✅ 已修 | `_c07_r04_skill_dispatcher` 传入 |
| **R05** Mock 协议移除 | ✅ 已修 | `_VALID_RUN_PROTOCOLS` 不含 mock |
| **R06** Live trace 仍用 mock | 历史结论待复核 | 本轮未运行真实 vendor trace，不据旧记录直接认定当前实现或效果 |
| **R07** Async 边界 | ✅ 已修 | `asyncio.run` 包裹 |
| **R08** Artifact 正文持久化 | ✅ 已修 | 文件存在性 + hash 校验 |
| **R09** Artifact CAS | ✅ 已修 | revision + old_status 原子比较 |
| **R10** Wiki 路径一致性 | ⚠️ 部分 | 证据服务改善；WikiFs 未复核 |
| **R11** 旧数据迁移 | ✅ 已修 | stable mapping + ULID |
| **R12** WARM/COLD 备份 | 代码已修 | `backup_side_dbs` 调 SQLite backup API；不能将恢复阶段的 copy2 误认作在线备份 |
| **R13** 前端双问号 URL | 本轮定向测试通过 | URL builder 7 项通过；不等于所有页面已浏览器验收 |
| **R14** 工作台只读 | 旧结论已失效 | CaseDetail 已有审批/启动/取消/验证/验收/拒绝/关闭；完整队列和编辑/归档覆盖另审 |
| **R15** Skill 契约 | ⚠️ 部分 | dispatcher 已修；schema 问题未复核 |
| **R16** 复用计数诚实 | 已有 adoption 计数；本轮测试通过 | 真实采用与来源引用已分离；生产有效复用效果未验证 |
| **R17** Case 可关闭 | 已有分类守卫；本轮测试通过 | 研究型无需 Action；执行型需终态/无活跃 Run/产物/发布判断，不能简化为终态或产物 |
| **R18** SSE 可靠性 | 前端已接线；本轮定向测试通过 | 统一 realtime 注册与 Case 精准失效存在；生产断网恢复未验收 |
| **R19** 契约一致性 | ⚠️ 未复核 | |
| **R20** 发布台账 | ⚠️ 部分 | ruff/version 声称已修 |

---

## 第 3 章 · 核心飞轮诊断（第一性原理更新）

> **基线**: 2026-09-11 FIRST_PRINCIPLES_ANALYSIS 的三根根因；以下用 2026-09-14 代码事实更新诊断。

### 3.1 双本体论问题：是否已收敛？

**2026-09-11 诊断**：同一批资讯在库里同时存在三套身份（hotspots / wiki-first md + warm.knowledge_items / v1_materials），互不相认。

**2026-09-14 更新**：

| 身份 | 行数 | 状态 |
|---|---|---|
| `hotspots` | 14,503 | 仍是主要资讯源，但已标注 `bid` 类剔除 |
| `v1_materials` | 6 | 新证据身份，但数据量极少 |
| `v1_signals` | 5 | 受管信号流，已接通 SK-01 |
| `wiki_items_fts` | 7,734 | FTS 嵌入 HOT 库；知识复利的"已沉淀"侧 |

**结论**：三套身份**仍共存**，当前存在部分桥接：
- `v1_ingest_bridge.py` 编排 RSS → SourcePipeline → admission → v1_materials + v1_signals（D1 点火）
- `auto_recall_for_case` 读取 Case 标题/问题，匹配 `v1_knowledge` 中已发布正文；不直接搜索全部 wiki 或 hotspots。
- **当前缺口**：首页热点、受管信号、wiki 文档与 v1 经验之间的用户动线和 ID 关联没有全面贯通证明；采集注册不等于持续有效供给。

**诚实结论**：旧采集与 v1 intake 并存。后者已注册，不能再归因于“未接线”；也不能由少量跨 Case 复用测试推断全量历史知识已被召回。

### 3.2 能力方向问题：技能是分析还是自检？

**2026-09-11 诊断**：20 个内置 skill 中 14 个（70%）是系统自我体检。

**2026-09-14 更新**：

| 类别 | 数量 | 占比 | 内容 |
|---|---|---|---|
| operations | 8 | 40% | 信源巡检、top 事件、API 健康、迁移一致性、安全扫描、数据清理、备份校验、FTS 检查 |
| compliance | 6 | 30% | 合规检查、质量门禁 |
| analysis | 4 | 20% | 实际安全分析动作（CVE、事件分析等） |
| report | 2 | 10% | 报告生成 |

加上 6 个 v1 技能（SK-01~SK-06），总技能数 = 26。

**结论**：系统自我体检占比从 70% 降至 **54%（14/26）**，改善但仍是多数。v1.0 六项能力（SK-01~SK-06）的前端消费面**部分接通**：
- SK-02 (cve-impact-brief) / SK-03 (inspection-materials)：前端已接线 CaseDetail；SK-04 生成经验尚无组件调用，不能与前两者合并标为已接线。
- SK-05 (reuse-experience)：自动召回已落地，前端 CaseDetail 召回区块
- SK-06 (knowledge-review-due)：job 55 运行，case blocker 机制
- SK-01 (daily-priority-intel)：后端/API/首页分区已存在；需补原文、事项承接与降级状态展示。

**计数使用限制**：以上技能比例沿用初稿分类，未逐技能复核。“合规”不能直接等同于系统自检；判断产品聚焦程度应看岗位任务是否完成和维护负担，不能只凭 Skill 个数。

### 3.3 数据层可靠性：备份、Schema、跨库事务

**2026-09-11 诊断**：
1. 无 schema 真相源（启动期逐条跑 106 个 SQL）
2. 写路由隐式（显式 `warm.` 写入全仓 0 处）
3. WAL 模式下跨库事务不原子
4. `backend/backups/` 无全量快照，增量全 0 字节

**2026-09-14 更新**：

| 维度 | 2026-09-11 | 2026-09-14 | 改善？ |
|---|---|---|---|
| **备份** | 无全量快照，增量 0 字节 | 当前代码已有 SQLite backup + manifest + sha256，定向测试通过 | 实现已改；生产恢复须演练 |
| **Schema 真相源** | 启动期逐条跑 106 SQL | `knowledge_items_table()` 单一真相源（`db.py:124`）；migration 117 编号连续 | ⚠️ 改善但不完整 |
| **写路由** | 显式 `warm.` 写入全仓 0 处 | 已引入 `knowledge_items_table()` accessor；DEV-0210 记录裸读收敛 | 不能用字面 warm. 数量推断无路由 |
| **跨库事务** | WAL 跨 ATTACH 不原子 | 未变化（已知限制） | ⚠️ 已知风险 |
| **WARM 库文件** | 历史称存在 899MB | 当前生效路径及覆盖未独立核验 | 待验证，不判定恶化 |

**待验证事项**：运行进程的有效 HOT/WARM/COLD 路径、各库必备表、备份 manifest 覆盖及隔离恢复。`backup_side_dbs` 对不存在的侧库会跳过，需与“本部署应有哪些库”对账；FTS 条目不能替代业务库完整性证据。本轮未访问生产数据，也不建议按缺省路径自动重建数据库。

### 3.4 前端数据层与用户可见状态

**2026-09-11 诊断**：25 处 setInterval/15 文件，无 react-query/swr。

**2026-09-14 更新**：
- `setInterval`/`setTimeout` 调用：76 处（含测试 + Toast 等 UI 延迟）
- DEV-0199~0203 已收敛域客户端与请求工具，DEV-0211 已迁移 Sentinel 的 SSE 失效注册；当前核心链使用 `lib/api` / 域 API / `realtime.ts`。
- SSE 刷新自激循环已修（DEV-0167）
- **react-query/swr 仍未引入**

**结论**：未使用 react-query/swr 本身不是缺陷。应评估在途竞态、错误保留、缓存新鲜度和用户操作成本，再决定是否引库。首页摘要虽有 mode 字段，当前组件不显示降级原因，属于实际体验缺口。

### 3.5 代码质量

| 指标 | 2026-09-11 | 2026-09-14 | 改善？ |
|---|---|---|---|
| **pytest** | 3,740 | 历史 PROGRESS 为 4,598 passed / 9 skipped；本轮仅定向 51 passed | 不声称全量零 skip |
| **vitest** | 425 | 496 | ✅ |
| **tsc** | 0 | 0 | ✅ |
| **ruff** | 166 预存错 | 触碰文件 0 错 | ✅ |
| **except Exception** | 320 处 | 431 处宽泛 + 741 处具体 | ⚠️ 总量增加（新增代码） |
| **架构数字** | 85r/141s | **86r/145s** | ✅ 同步 |
| **Migrations** | ~107 | **117** | ✅ |
| **CI** | 历史未真跑 | 本轮未查询远端 CI | 当前状态未知 |

---

## 第 4 章 · 分期路线图（以飞轮为线索）

> **原则**：先闭环再加速；每个 F 期的退出条件是**真实数据**证明该环节可用。以下保留原分期框架并纠正已失效任务；F0 要求产物而完整执行器位于 F3 存在依赖歧义，建议分开研究闭环与执行闭环，见审计 §13.7。新排序待裁决，不直接作为已批准开发清单。

| 期 | 飞轮环节 | 内容 | 前置 | 退出条件 |
|---|---|---|---|---|
| **F0** | 全部 | B0-B7 业务闭环整改 + P1-0a 止血 | 无 | Case 可关闭 / Artifact 可产出 / Junction 表可填充 |
| **F1** | 感知 | 验证已注册 intake 的真实供给、新鲜度与事项承接 | F0 | 一个真实源端到端可追溯（采集→准入→v1_signal→Case） |
| **F2** | 研判 | D2 真实出稿（dsh/pi 出稿链路接通）+ Judgment 引用/反证完整 UI | F1 | 浏览器内完成 补证→判断→发布 |
| **F3** | 行动 | P1-0 执行器（边界协议→pi 执行→Artifact 自动登记）+ SK-03 完整接线 | F2 | 一条 Action 浏览器内走完审批→执行→产物 |
| **F4** | 沉淀 | SK-04 复盘 + Knowledge 发布/复查 + MP-2/3/4 标签体系 | F3 | 一个 Case 产出可复用知识 + 事件类型标签 |
| **F5** | 复利 | 已有召回/采用/摘要基础上的适用条件、结果与真实重复使用验证 | F4 | 第二个独立 Case 自动浮现适用知识 + adoption + 实际结果记录 |

### F0 详细任务（业务闭环整改）

| 任务 | 优先级 | 来源 | 说明 |
|---|---|---|---|
| F0-1 | P0 | R06 | 先复核 live trace 与实际 vendor 路径，再修确认的缺口；不得仅凭历史 mock 记录重建 SDK 集成 |
| F0-2 | P0 | R12 | 对已实现 SQLite backup 的覆盖、新鲜度与隔离恢复做验收，不重复开发 |
| F0-3 | P0 | R14 | 修复完整事项队列可达性，复核编辑/归档覆盖；关闭等 mutation 已存在 |
| F0-4 | P0 | P1-0a | v1_runs 加 `plan_json`/`boundary_hash`/`executor` 列；人工回执通道 |
| F0-5 | P1 | R02 | 验收已注册 SourcePipeline 的真实供给与错误状态呈现 |
| F0-6 | P1 | R17 | 复议执行器设计中“终态 run 或 accepted artifact”：会允许失败运行冒充完成；当前研究/执行型守卫须保留事实区分 |
| F0-7 | P1 | R16 | 在已有 adoption 计数上验证跨事项适用性与使用结果，不重复开发计数 |
| F0-8 | P1 | R18 | SSE 端到端可靠性（outbox + 前端消费） |
| F0-9 | P1 | R13 | URL builder 定向测试已通过，后续随真实用户旅程检查链接 |
| F0-10 | P2 | R10 | WikiFs 路径一致性复核 |
| F0-11 | P2 | R19 | HTTP 契约对齐（OpenAPI spec + 前端类型） |
| F0-12 | P2 | R20 | 发布台账 vs quality gate 一致性 |

---

## 第 5 章 · 已批准设计待落地清单

### 5.1 P1-0 执行器（4 期）

| 期 | 内容 | 工作量 | 依赖 |
|---|---|---|---|
| **P1-0a 止血** | 人工回执通道 + v1_runs 列扩展 | 1-2 天 | F0-4 |
| **P1-0b 边界协议** | ExecutionPlan schema + dsh prompt + 审批 API/UI | 3-4 天 | P1-0a |
| **P1-0c pi 执行** | enforce 编译 + pi 派发 + 事件回传 + Artifact 登记 | 4-5 天 | P1-0b |
| **P1-0d 加固** | sandbox-exec 降权 + 资源上限 + 越界告警 | 2-3 天 | P1-0c |

**不做的**：shell=True、workspace 外写、交互式输入、凭据传递。

### 5.2 CodeGarden 安全实践域（4 期）

| 期 | 内容 | 工作量 |
|---|---|---|
| **CP-1** | S1 全量开源信号提取（9,872 条实跑）+ 候选池端点 | 2-3 天 |
| **CP-2** | S2 立项四阶段 + 行动侧入口 | 2-3 天 |
| **CP-3** | S3 产物沉淀 + 知识联动 | 2-3 天 |
| **CP-4** | S4 工具台账 + phase2b 删除裁决 | 1-2 天 |

### 5.3 MITRE ATT&CK MP-3 / MP-4

| 期 | 内容 | 工作量 | 依赖 |
|---|---|---|---|
| **MP-3** | L1 漏洞实例化（NVD 接入 + CVE→technique 标注）+ 资讯继承标签 | 2-3 天 | P1-5 联动 |
| **MP-4** | `knowledge_technique_ref` 表 + L3 响应知识 + 判断层双向关联 | 3-4 天 | MP-2 完成 |

---

## 第 6 章 · 架构现状（代码事实）

### 6.1 后端

| 指标 | 数值 | 说明 |
|---|---|---|
| **Routers** | 100 | AST 反推 (generate_meta --check 维护, 2026-10-08); 含聚合 router |
| **Services** | 159 | 13 包 + v1 域服务 (2026-10-08) |
| **Migrations** | 133 | 缺号 066-069 为历史编号空洞 (informational, 勿改名) |
| **Jobs** | 58 | APScheduler (2026-10-08) |
| **Collectors** | 14 | SSRF 防护走 url_safety; 14 号为 arXiv 论文单源 (category=paper, 2026-09-26) |
| **Feature Gates** | 16 | 开 15 / 关 1 (mcp；管线 LLM 三 gate semantic_filter / ai_classify / pipeline_ner 2026-09-19 开闸, env HOTSPOT_FEATURE_GATES 可应急回关) |
| **Tests** | 5,281 passed | 全量 pytest (2026-10-08, 9 skipped); 数字随提交滚动, 以最近 DEV_LOG 为准 |
| **MCP Tools** | 23 | 16 读 + 7 写 (v0.8.7 P3-B +4 只读: list_proposals/runs/artifacts/cases) |

### 6.2 前端

| 指标 | 数值 | 说明 |
|---|---|---|
| **Routes** | 53 | 全 lazy |
| **Components** | ~284 | 18 组件域 |
| **Tests** | 496 | Vitest + jsdom |
| **i18n keys** | 120+ | zh-CN / en-US |
| **Theme modes** | 3 | light / dark / paper |

### 6.3 数据

| 组件 | 状态 |
|---|---|
| SQLite HOT/WARM/COLD | 三库架构仍在；本轮未核验当前生产文件、数量和有效路径 |
| Wiki-first | 7,734 FTS 条目嵌入 HOT 库；`llm-wiki-2.0/` md 真源 |
| WebDAV | 同步能力，出站范围需与本地优先定位对齐；与采集停启不是同一件事 |

### 6.4 AI

| 组件 | 状态 |
|---|---|
| ai_hub | 四级链 + 5 providers + 断路器 |
| dsh | 受管子进程（mock/ai_hub 降级链） |
| pi | agent_bridge stdio JSON-RPC（协议对齐 0.84.4） |

---

## 第 7 章 · 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解措施 | 状态 |
|---|---|---|---|---|---|
| **R1** | 缺当前远端 CI 证据 | 待核验 | 高 | 发布前取得对应提交的 CI 结果 | 本轮未查询 |
| **R2** | dsh/pi 真 vendor 未实测 | 中 | 高 | F0-1 接真 SDK + live trace 去 mock | 待排期 |
| **R3** | 有效库路径与备份覆盖未经本轮验证 | 待核验 | 高 | 只读核对生效配置并在隔离环境恢复，不直接重建生产库 | 待验证 |
| **R4** | owner 人审是关键路径瓶颈 | 高 | 中 | MP-2 11 类事件类型分 2-3 天；金融三类递进 | 进行中 |
| **R5** | 错误/降级状态未完整呈现 | 中 | 中 | 检查摘要 mode、新鲜度和可重试入口；是否引库由测量决定 | 已有源码证据 |
| **R6** | 跨库事务不原子 | 中 | 中 | v1 域对象尽量在 HOT 库；WARM 只读引用 | 已知限制 |
| **R7** | 320→431 处宽泛 except Exception | 中 | 中 | error_classifier 缺（D-a，未选） | 待排期 |
| **R8** | 生产后端绑 127.0.0.1（前端代理绕过） | 低 | 高 | dev 环境已修；生产独立部署 | 已缓解 |
| **R9** | 3800 行旧 knowledge_items 未迁移 | 低 | 中 | T16 遗留；需授权 + 备份前置 | 待授权 |

---

## 第 8 章 · 旧文档索引

> **使用规则**: 以下文档已被本文档取代或 superseded。引用时请指向本文档；如需原文，按路径查找。

| 文档 | 状态 | 说明 |
|---|---|---|
| `docs/v0.8.5/V0.8.5_PLAN.md` | ⚠️ 部分 superseded | 路由/接口事实已更新；§5 修订注③④ 仍有效但建议以本文档为准 |
| `docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md` | ❌ Superseded | 被本文档取代 |
| `docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md` | ❌ Superseded | 被本文档取代 |
| `docs/v1.0/REVIEW_2026-09-07.md` | 📋 只读审计 | R01-R20 历史证据保留；修复状态见本文 §2.7 |
| `docs/WORKBENCH_FOCUS_PRD_v1.0.md` | ❌ Superseded | 内容已并入本文 §2.6 + §5.1 |
| `docs/DESIGN_P10_EXECUTOR_2026-09-13.md` | 📋 已批准未落地 | 设计有效；实施状态见本文 §5.1 |
| `docs/DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md` | 📋 已批准未落地 | 设计有效；实施状态见本文 §5.2 |
| `docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md` | 📋 已批准未落地 | 设计有效；实施状态见本文 §5.3 |
| `docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md` | ❌ Superseded | 三根根因已更新为本文 §3 |
| `docs/PLAN_MP2_EVENT_TYPE_2026-09-13.md` | 📋 部分实施 | MP-2 基础设施已落地；候选池待人审 |
| `docs/v1.0/V1.0.1_V0.8_UI_CONVERGENCE_PLAN.md` | ❌ Superseded | 被 v0.8.5 反向收敛取代 |
| `docs/v1.0/V1.0.0_UI_UX_SPEC.md` | ❌ Superseded | 四入口条款被取代 |

---

## 附录 A：审计方法

本次 PRD 基于以下审计活动：

1. **前端路由审计**：对照 V0.8.5_PLAN.md §5，逐条比对 `frontend/src/routes/index.tsx` 实际注册路由 + `SentinelShell.tsx` menuOf() 映射 + `nav4_shell.test.tsx` 断言
2. **后端 API 审计**：统计 `backend/main.py` 实际 `include_router` 调用 + 逐端点 grep 验证
3. **v1.0 域对象审计**：migrations 目录计数 + `v1_0_models.py` 字段检查 + dev 数据库实际行数查询
4. **B0-B7 整改审计**：逐 finding 定位 REVIEW_2026-09-07.md 提及的文件，核对当前代码是否已修复
5. **设计落地审计**：P1-0 / CodeGarden / MITRE 设计文档承诺 vs 代码实际存在性（grep + 文件系统检查）
6. **飞轮诊断**：用 2026-09-14 代码事实更新 2026-09-11 FIRST_PRINCIPLES_ANALYSIS 的三根根因

---

## 附录 B：关键代码事实速查

> 下表为初稿快照，数字未在本轮全量复证，不应抄入发布说明；当前确认范围见文首与审计 §13.9。技能、架构数量应由各自注册源统计，业务成效需真实使用记录。

| 维度 | 数值 | 来源 |
|---|---|---|
| Routers | 86 | `backend/api/_registry.py` |
| Services | 145 | `backend/services/` `*_service.py` |
| Migrations | 117 | `backend/repository/migrations/*.sql` |
| Jobs | 51 | `backend/scheduler/jobs/` |
| Frontend routes | 53 | `frontend/src/routes/index.tsx` |
| Frontend tests | 496 | Vitest |
| Backend tests | 4,598 | pytest |
| Builtin skills | 20 | `builtin.py` (8 ops + 6 comp + 4 analysis + 2 report) |
| v1 skills | 6 | `v1_skills.py` (SK-01~SK-06) |
| Total skills | 26 | BUILTIN 单例 |
| HOT hotspots | 14,503 | `backend/hotspot.db` |
| v1_materials | 6 | `backend/hotspot.db` |
| v1_signals | 5 | `backend/hotspot.db` |
| wiki FTS | 7,734 | `backend/hotspot.db` |
| v1_runs | 0 | `backend/hotspot.db` |
| v1_artifacts | 0 | `backend/hotspot.db` |
| attack_techniques | 244 | `backend/hotspot.db` |
| event_types | 5 | `backend/hotspot.db` |
| Backups (latest) | 2026-09-12 | `backend/backups/backup-manifest-20260912_200000.json` |

---

# v0.8.6 正式版产品需求文档（2026-09-15 九章版 · 路线已被 AI Native 修订取代）

> 发布日期：2026-09-15　|　状态：**产品语义基线保留，路线图（本段 §8 F0–F5）已被取代**
> **2026-10-02 owner 裁决**：0.8.6 实现路线由《v0.8.6 AI Native 改造 PRD》取代（见下方「v0.8.6-A」摘要与 `docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`）。本段第 1–7 章的产品语义（四类岗位事项、证据链、成果验收、知识复利）作为长期产品方向保留，后续版本（0.8.7+）设计时继续有效；本段 §8 的 F0–F5 分期不再执行，其未竟项已被 AI Native 版的 P0–P2 与 0.8.7 候选表收编。
> 本章为历史产品定义；上文审计和历史快照用于追溯，不作为当前实现状态证明。

## 第1章 产品概述与目标

### 1.1 产品定位

Hotspot 是面向安全从业者的本地优先 AI 工作台，将经过门禁的安全资讯转化为可负责、可核验、可复用的工作成果。

### 1.2 核心目标

1. **提高感知到行动的转化率**：资讯经过质量与内容门禁后，能被映射为合适的标准或自定义事项。
2. **提高成果可信度**：判断、执行和合规结论均带证据、责任人、规则版本和结果状态。
3. **形成经验复利**：完成事项的条件化经验可在后续同类事项中被召回，并记录真实采用结果。

### 1.3 成功指标

- 资讯门禁结果可解释，误收、误拒均可追踪。
- 事项建立必须由用户确认，AI 不得直接创建或授权。
- 研究、运营、合规、管理四类事项均能产生各自定义的可验收成果。
- 执行型事项的成功、失败、取消、超时与人工介入状态真实可区分。
- 知识复用必须有采用回执，不能以召回次数代替有效复用。

## 第2章 用户画像与场景

### 2.1 用户

首期用户为独立安全研究员、安全运营人员、金融安全/合规人员和安全管理者。产品先支持单用户本地部署；组织协作、租户隔离和跨组织共享不纳入本版本承诺。

### 2.2 核心场景

- **安全研究与实践**：作为研究员，我希望从技术或开源工具资讯建立研究事项，以便完成验证、复现和经验沉淀。
- **企业安全运营**：作为运营人员，我希望从漏洞和情报预警建立处置事项，以便关联资产、分派责任并验证修复结果。
- **金融合规**：作为合规人员，我希望从监管资讯建立评估或整改事项，以便形成控制项、证据包和可审计结论。
- **安全管理**：作为管理者，我希望从风险趋势建立决策事项，以便比较方案、记录审批依据和跟踪决策后果。
- **经验复用**：作为任一用户，我希望系统在新事项中提示适用经验，以便减少重复判断并记录是否有效采用。

### 2.3 使用节奏

资讯浏览和门禁结果为日常操作；事项处理按事件或项目发生；知识复查按到期时间自动提醒；备份和健康检查由系统周期性执行。

## 第3章 功能模块设计

### 3.1 模块总览

`资讯门禁 → 类型识别 → 事项工作台 → 证据与成果 → 知识复用 → 设置与治理`。四菜单只提供导航，模块通过统一事项 ID、证据引用和版本号联动。

### 3.2 功能清单

| 模块 | 功能 | 输入/输出 | 优先级 |
|---|---|---|---|
| 资讯门禁 | 质量门禁、内容门禁、规则筛选、拒绝原因 | 采集资讯 → admission 结果 | P0 |
| 类型识别 | 漏洞、情报、技术、开源、合规、管理等分类；AI 推荐和预填 | 资讯 → 事项草案 | P0 |
| 标准事项 | 漏洞治理、研究实践、情报响应、合规整改、管理决策模板 | 用户确认 → Case/Action | P0 |
| 自定义事项 | 字段、状态、步骤、规则、审批、输出模板、提醒可配置 | 配置 → 版本化流程 | P0 |
| 事项执行 | 判断、审批、执行计划、Run、Artifact、人工回执 | Action → 可验收成果 | P0/P1 |
| CodeGarden | 开源候选、research/setup/exercise/retro 阶段 | 项目 → 实践产物 | P1 |
| 知识复用 | 条件化经验、复查、采用回执 | 成果 → Knowledge | P0 |
| 设置治理 | AI 提供商、数据分级、出站策略、策略版本、审计 | 配置 → 生效策略 | P0 |

### 3.3 依赖关系

没有通过门禁的资讯不能推荐事项；没有用户确认的草案不能成为 Case；没有证据或规定成果的事项不能宣称完成；执行器只能消费审批时冻结的策略快照。

### 3.4 设置页能力（2026-09-22 IA 重构落账，DEV-0227）

设置页 = 用户对系统可持久化偏好的低频写入口，纯配置心智（只读监控/数据浏览/一次性动作不混入）。侧栏 **7 cat / 5 组**：`overview`（总览）· `general`（通用：主题/模式/刷新/兴趣画像/能力开关）· `models`（模型配置唯一入口：Provider/密钥/模型池/三场景）· `collection`（采集与管线）· `network`（代理）· `connectivity`（同步/MCP/密钥状态）· `ops`（维护/导出/dsh 启停）。

接口消费：GET `/api/settings/features`（16 gate 单源）、GET/PUT `/api/settings/mcp/*`（ungated 开关 + 配置）、GET/PUT `/api/settings/feature-gates*`（TOML 写入 + audit，env 覆盖 409）、GET/PATCH `/api/settings/auto-intake`（自动入管配置 + 今日已入管数，2026-09-26 DEV-0231，collection 分区设置卡消费）、settings kv 读写走 `SettingsService` 前缀契约（`collection./llm./interest./quality./feature./feature-gates./state./secrets.oauth_allowlist`，未注册前缀 fail-loud）。`webhook.secret` 已迁加密存储不入明文 KV；跨端 sync bundle 仅打包 config namespace（`settings_sync_allowed` 白名单）。详见 `docs/audit/PRD_ALIGNMENT_AUDIT_2026-09-23.md`。

## 第4章 系统架构设计

### 4.1 架构

React/Vite 前端通过 FastAPI 领域 API 访问 SQLite HOT/WARM/COLD 数据层；Markdown wiki 保存知识正文；调度器负责采集、门禁、复查和备份；ai_hub 负责模型路由；dsh 生成执行计划，pi 在后端强制边界内运行。

### 4.2 数据分层

- HOT：当前资讯、事项、证据、知识索引。
- WARM：可恢复的历史业务数据，必须纳入备份和恢复演练。
- COLD：审计和归档数据。
- Wiki：知识正文的 Markdown 真源，数据库保存索引和引用。

### 4.3 外部依赖

外部资讯源、模型提供商、WebDAV 和执行环境均视为潜在出站边界。资料分级、允许目标、凭据隔离和失败可见性由平台策略控制。

## 第5章 业务流分析

### 5.1 资讯到事项

`采集 → 质量门禁 → 内容门禁 → 标题/正文规则筛选 → AI 推荐/预填 → 用户选择与修改 → 建立事项`。

### 5.2 事项到成果

`事项建档 → 补充范围与责任 → 形成 Judgment 或 Action → 审批 → 执行/人工处理 → Artifact 或证据包 → 验收 → 关闭`。

### 5.3 成果到知识

`验收成果 → 生成知识草稿 → 补充适用条件/限制 → 发布 → 到期复查 → 后续事项召回 → 用户确认采用或拒绝并记录原因`。

### 5.4 异常流

门禁失败、AI 不可用、执行计划生成失败、越界、超时、取消、证据不足和备份失败都必须保留真实状态、失败原因和重试边界；不得自动伪造成功或关闭事项。

## 第6章 操作流分析

### 6.1 日常流

用户查看门禁后的资讯摘要，选择需要处理的类型，确认 AI 预填内容，进入事项队列，处理待办并验收成果。

### 6.2 周期流

系统按计划执行资讯采集、知识复查提醒、事项逾期检查、工具台账检查和数据库备份；用户定期查看未完成、阻塞和待复核事项。

### 6.3 配置流

用户创建或修改自定义事项类型，AI 提供建议；系统校验不可关闭安全约束，生成策略版本；新事项在创建和审批时记录对应版本快照。

## 第7章 数据模型设计

核心实体包括：`Material`（原始资料）、`Signal`（门禁后信号）、`Case`（事项容器）、`Judgment`（有证据判断）、`Action`（待执行行动）、`Run`（执行记录）、`Artifact`（成果）、`Knowledge`（条件化经验）、`EvidenceReceipt`（证据回执）、`WorkflowType`（标准或自定义类型）、`PolicyVersion`（安全策略版本）。

关系路径为：`Material 1—N Signal 1—N Case 1—N Judgment/Action 1—N Run 1—N Artifact → Knowledge`；所有关键关系保留来源、责任人、时间、状态和版本信息。

## 第8章 开发优先级与里程碑

| 阶段 | 交付重点 | 验收 |
|---|---|---|
| F0 基础可信 | 事项队列可达、失败状态、人工回执、生产调度接线 | 一条事项可真实进入处理和关闭判定 |
| F1 资讯转事项 | 门禁、类型模板、AI 预填、用户确认 | 五类资讯各完成一次建项 |
| F2 成果闭环 | ExecutionPlan、审批、Run、Artifact、证据验收 | 只读研究事项完成真实执行闭环 |
| F3 四类工作 | 运营、合规、管理模板与差异化验收 | 四类反例事项分别走通 |
| F4 实践复利 | CodeGarden 四阶段、知识复查、采用回执 | 一个开源实践产出并被后续事项采用 |
| F5 治理加固 | 出站控制、策略快照、资源限制、恢复演练 | 越界、超时、出站和恢复演练通过 |

阶段顺序允许并行开发，但 F2 之前不得宣称“自动执行闭环”，F5 之前不得宣称“数据绝不出域”。

## 第9章 风险与缓解

| 风险 | 概率/影响 | 缓解 |
|---|---|---|
| 四类工作被压成同一模板 | 高/高 | 共享事项内核，使用岗位模板和独立完成标准 |
| AI 推荐误导或越权建项 | 中/高 | 门禁可解释、用户确认、不可自动创建 |
| 执行隔离不足 | 中/高 | 后端 enforce、范围白名单、凭据隔离、资源上限、审计 |
| 研究/运营/合规成果无法统一验收 | 高/高 | 按类型定义 Artifact、证据包和关闭条件 |
| 本地运行导致错误的数据安全假设 | 中/高 | 资料分级、出站策略、提供商可见状态和策略快照 |
| 知识召回但无实际价值 | 中/中 | 强制采用回执、复查和拒绝原因 |
| CodeGarden 范围膨胀 | 中/中 | 仅作为实践事项域，删除与实践无关的服务网格能力 |
| 数据备份或跨库事务不可靠 | 中/高 | 统一备份清单、恢复演练、记录跨库非原子限制 |

## 三维审查结论

**逻辑一致性**：通过条件为门禁、事项、成果、知识和策略版本均有明确输入输出；当前代码仍存在 Run 消费、Artifact 产出和完整队列缺口，列入 F0/F2。

**批判性审查**：发现四类岗位的信任等级、成果标准和使用频率不能统一；已在模板、权限和指标中拆分。CodeGarden 和全能执行器均不得成为所有场景的强制前置。

**第一性原理审查**：核心价值是“把值得关注的安全资讯变成可负责、可核验、可复用的工作成果”。若功能不能改善发现、证明、行动或复用，应降级或删除。

## 变更记录

- v0.8.6：基于需求摘要确认、专题方案比较和 2026-09-14 审计结论形成正式九章版本。
- 2026-09-16 (DEV-0183, UI 重构 Phase 4)：新增 5 视图路由——资料库前厅 `/knowledge/khub`、编目室 `/knowledge/library`、通稿审核 `/action/events`（MP-2 真实端点全接入）、清样深读 `/reader/:id`（wiki 阅读 + 批注占位）、校对室 `/quality`（`/quality/rejection` 升格子标签并重定向兼容）。未实现后端缺口（hub-stats 聚合 / 编目清单 / 批注）双登记于代码 TODO 与 `docs/UNIMPLEMENTED.md` 台账，前端不展示伪造数据。
- 2026-09-16 (DEV-0184, UI 重构 Phase 5)：无限画布 paradigm 接入两视图——共享 `InfiniteCanvas` 组件（拖拽平移 / ctrl+⌘ 滚轮光标锚定缩放 / 触控板横滚平移 / 双击重置 / 缩放控件 / 点阵网格，全 token 随主题翻转）；`/knowledge/canvas` 升级双模式（DOM 画布默认 + ECharts demo 降级保留），`/knowledge/graph` 增加画布模式开关（SVG 直排保留为默认降级）。纯前端，无新增路由与端点。
- 2026-09-16 (DEV-0185, UI 重构收尾批方案设计)：五阶段全部遗留项成文 `docs/UI_REFACTOR_FOLLOWUP_PLAN_2026-09-16.md`（批次 A 快赢修整 / B 页面编辑化收尾 / C 后端缺口接线 / D 裁决项，约 5–7 工作日）。核查代码后修正 UNIMPLEMENTED 台账两处事实：编目室复用既有 `GET /api/knowledge/items`（不建新表）；批注复用既有 `annotations` 表（migration 027，仅缺薄 API，不写 wiki md）。真实后端缺口仅剩 hub-stats 聚合端点一项。
- **2026-10-08 (v0.8.7 · P2 收口 + P3 交付回流，KPI 口径裁决)**：①**P2 收口 (DEV-0286)**：G1/G2/G3 + M1-M4 全链闭环——gate-detect 失败 446/446 全显式 outcome（「失败必可见」成立）、E8 补列、JudgePage 归零、SK-04 提案化（人主律落地）、t24 正式观测达标。**结构性发现定案**：信号转化率 15-30% 带与有意义质量门槛不可兼得（7d 桥评分中位 2.5 + 行业对标），带表述退场。②**v0.8.7 P3 五工单交付 (DEV-0289~0292)**：**C KPI 口径切换**——主指标改「分诊时延 (signal→case P50/P90) + artifact 产出率 (done 且有产物)」，signals/hotspots 比率降级为参考值，经 `GET /api/ops/kpi` 可查（本文件及《AI Native PRD》§1.4 已同步改写）；**D** gate 限频预算 config 化（6→20/60s）；**E** HOT db 巡检阈值校准 300MB（137MB 全有效零膨胀取证）；**B** MCP 只读导出 ×4（19→23，外部 agent 只读观测，人主律边界——不产提案）；**F** 语义过滤 post-ingest 化（采集热路径零 LLM，tick 尾补偿判别，reject → 隐藏+flag 可回溯）。③**量化目标修订**：v0.8.6-A 之「signals 13→≥120」流量目标随口径切换降级为参考（signals 实测已 3392/7d 远超原目标，质量问题非流量问题）；30 天主指标待观测窗（t0=2026-10-08 12:03）后按分诊时延/artifact 产出率重设基线。④**运维加固 (DEV-0293/0294)**：单实例守卫（pgid 锁+端口探活双检，run.py 启动闸）；拓扑定案 dev 即生产（8000 后端 + 8898 vite dev）。详见 `docs/PLAN_P3_2026-10-07.md` + DEV_LOG。
- **2026-10-10 (DEV-0311 · 资讯赞/踩 → 推荐优化 v1)**：资讯卡片（头条/次级/快讯三挂载点）新增赞/踩按钮，点击即入兴趣引擎（`like` +2.0 / `dislike` −1.5，`POST /api/interest/signals`）。reaction 为**状态型信号**（区别于 view/dwell 等累计型）：互斥切换 + 可取消，`DELETE /api/interest/reactions/{item_id}` 取消、`GET /api/interest/reactions?days=90` 回读 UI 状态。**三项裁决**：D1 单管道（扩兴趣引擎，不另建推荐通道）；D2 双向归一（正/负各自除本侧 max → b∈[−1,1]）+ 乘子 clamp [0.45, 1.30]；D3 互斥切换 + 可取消（同键取消/异键切换）。兼容铁律：无信号时全域乘子恒定 → feed 排序退化原序（= 现状），既有排序断言保持。前端 fail-safe：回读失败（gate 关闭/端点 404）时隐藏按钮组，不渲染死键。**同日补强 (DEV-0313)**：域归因三层化（hotspot tags → 标题关键词 → category 兜底，security 类目裸条不再静默丢弃 reaction，近期实测覆盖 8%→15%）；非安全类目维持 no-domain 语义（不入权重）。**同日第三批 (DEV-0314)**：reaction 被丢弃时如实回滚 + 提示（不装成功）；首页 view/favorite 行为埋点接线（此前行为信号仅有点赞）；非安全内容偏好通道完成设计留档（三案候选，未实现，待裁决）。**次日 (2026-10-11, DEV-0315)**：A(噪音抑制)+B(显式开关) 整合落地——设置「内容偏好」按内容类目 / 全部来源设三级偏好（加强/默认/减弱），驱动 feed 排序第二轴（与实践域正交）；只升降不删（条目永远可达），无配置时排序退化原序；`GET/PATCH /api/settings/content-preferences`（存储 `interest.content_preferences`；实现自 `settings.py` 拆出为 `api/content_preferences_api.py`，routers 100→101）。**同日 AI 化 (DEV-0316)**：内容偏好转三层——统计自动学习（近 30d 赞/踩/浏览/收藏按类目/来源聚合净分自动加强/减弱，零配置默认生效，5min TTL）+ LLM 优化建议（`GET /api/interest/content-prefs/recommendations`，采纳才写入手动层，人主律）+ 手动设置折叠为高级选项（手动 key 级覆盖自动）；设置卡默认不再铺 200+ 按钮。**同日 (DEV-0317)**：/maint 健康卡契约漂移修复——四项指标 (数据库大小/表数/碎片率/可清理行) 自 DEV-0178 建页起恒显「—」(前端类型凭想象与 `maintenance_service` 真实响应全不匹配 + 三层静默兜底掩盖 + 页面零测试)；修正为按后端权威契约呈现 (`size_mb`/空闲页 `freelist_pages`/`fragmentation_pct` 直读/`quality_check_logs.older_than_7_days`)，接口失败改显式错误态 (监控 fail-loud 纪律)，新增契约测试锁真实响应形状。**同日 (DEV-0318)**：清理功能验证发现**每周 telemetry_window 清理 job 自 v0.5 分层迁移起从未真实执行**（`db_diet` 存在性检查 `sqlite_master` 只覆盖 main，WARM 表全误判 table_not_found → 每周空转且 status ok；quality_check_logs 积压 53.8 万行）；修复 = 跨 schema 存在性检查 + CLI 补 ATTACH + maintenance 写端点 `asyncio.to_thread` + /maint 清理卡想象契约改调 `/cleanup-quality-logs?days=N&dry_run=false`（与 /settings 同形态，默认 7 天对齐健康卡口径）；生产实弹归档 538,002 行至 COLD 表（可追溯 90 天）、主表降至 45,657、健康卡「可清理行」闭环归零，三处契约测试锁真实形状。**同日 (DEV-0319)**：清理 job 层告警收口——`telemetry_window_job` 非零 skip 不再静默，写 `observability_alerts`（全表 skip=critical / 部分=warn）+ SSE breach + dispatcher（复用 v0.7 Batch ④ 基建，cooldown 1 天，告警失败不拖垮周日链）；`table_not_found` 且 warm.db 未建视为单库起步合法态豁免。
- **2026-10-02 (v0.8.6-A · AI Native 修订，owner 定稿)**：0.8.6 实现路线由《[`docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`](HOTSPOT_V0.8.6_AI_NATIVE_PRD.md)》（draft4，11 章）取代本文件 2026-09-15 九章版之 §8 路线。要点：**换主干**（Run 证据账本：proposal→审批→Run→Artifact，Agent 产出提案、人负责审批）+ **F0 止血 14 项**（E1 档位 model 真生效/S1 鉴权全入口/S2 迁移器幂等/E19 warm 索引/E4 misfire/DEFAULT_SCORE 删除/E2 egress 全覆盖/E13 门禁策略统一等）+ **AI Native 四轴**（owner 全选：Agent 优先循环/模型驱动管线/全界面副驾/对话式命令栏）+ 0.8.7 候选表 9 项（C1 except 分级治理[高] 领衔）。量化目标 30 天：v1_runs 0→≥10、artifacts 0→≥5、signals 13→≥120、三类静默失败 100% 显式。裁决：D1 主干优先/D2 含执行+产物/D3 保守冻结/D4 维持中文/D5 先修竞态/D6 长期单用户/D7 全入口覆盖。输入=`docs/audit/FIRST_PRINCIPLES_REDESIGN_2026-10-02.md`（六根因/19 证据/S1-S3）+ 复审修正；留痕=`docs/audit/PRD_ALIGNMENT_AUDIT_2026-10-02.md`。
