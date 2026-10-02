# Hotspot AI Native 设计

> **日期**: 2026-10-02
> **基线 commit**: `18dd6f3`
> **性质**: 设计文档 (决策前)；是 [FIRST_PRINCIPLES_REDESIGN_2026-10-02.md](FIRST_PRINCIPLES_REDESIGN_2026-10-02.md) 的补充卷，专攻 AI 层
> **前置结论**: 主分析确立三条律 —— `L1 溯源律` / `L2 可证伪律` / `L3 人主律`。本文给出 AI 层如何在这三条律下成为**结构**而非**外挂**

---

## 0. 摘要

**核心判断**：当前系统的 AI 是**事后的加速器**，不是**结构本身**。即便在"采集打标、摘要、分类、拒绝原因"这些**旁路**上，也有相当一部分**从未真正接通**（§2.5 勘误）；而在真正卡住用户的**研判与行动**环节，AI 各只覆盖 2 条 skill 路径，且全部止步于 `draft` / `planned`。

**最刺眼的一个事实**（§2.5 D1）：`ai_classify` gate 在 `feature_gates.toml:38` **声明为 `true`（已开闸）**、在 `extensions/__init__.py:61` **已登记**、并有 `test_ai_classify.py` **测试通过** —— 但它的唯一消费点 `classify_item_with_ai` **没有任何生产调用方**。**该能力自 2026-09-19 "开闸"以来没有处理过任何一条资讯。**

**关键发现**：这个系统**已经无意中做对过** AI Native 的样子，而且 —— 更关键 —— **"提案"实体在代码里已经存在了，只是只在一条 skill 路径上使用，其余场景全部绕过它**：

| # | 已有的正确模式 | 位置 | 为什么是对的 |
|---|--------------|------|------------|
| P1 | AI 输出**强制 schema 化**，含 `claim_type`/`confidence`/`evidence_refs`/`unknowns` | `ai_hub/prompts.py:411-448` (`parse_cve_impact_brief_response`) | 每个字段都是可审计的 |
| P2 | 知识生成**强制条件化**：`prerequisites` 非空 + `counter_examples` + `review_at` + **证据哈希与库中比对** | `services/knowledge_ai.py:40-63` | 经验带适用条件与失效期，哈希防篡改 |
| P3 | 规则优先 → AI 增援 → **结果必须在白名单内才采纳** → 失败退回原结果 | `services/auto_classifier.py:586-615` | 设计正确，AI 永不越权 —— **但当前无生产调用方（§2.5 D1）** |
| P4 | **完整的提案表已经存在** | `event_technique_candidates`（migration 117） | 见下方 schema —— 这就是 Proposal 的雏形 |
| P5 | 领域类型系统**已内置不确定性字段** | `domain/v1_0_models.py:320-343` (`Judgment`) | `evidence_refs` min_length=1 / `counter_evidence_refs` / `unknowns` / `status=draft` |

**P4 是最重磅的发现。** 生产库里 `event_technique_candidates` 的 schema 已经是一张完整的提案表：

```
id | event_type_id | technique_id | stage | confidence | evidence_quote | rationale
   | source_report_id | llm_model | llm_run_at
   | owner_status('pending') | owner_action_at | owner_action_by('owner') | reject_reason | auto_reject_reason
```

**它同时具备**：证据（`evidence_quote`）、理由（`rationale`）、置信度（`confidence`）、模型溯源（`llm_model` + `llm_run_at`）、人工决策生命周期（`owner_status` = pending / 决策时间 / 决策人 / **拒绝理由**）。

**而它的生产行数是 0，`audit_log_mp2_review` 也是 0 行。** 写它的 `event_technique_extract_service.extract_for_report` 只在 MP-2 事件类型流程里被调用（PRD §2.5 记载"候选池待 owner 人审"）。

**所以 AI Native 的结论要再收紧一层**：

> 不是"要新建一个 Proposal 实体"，也不是"要把 4 个局部模式一般化" ——
> 而是 **Proposal 的 schema 与生命周期已经在仓里躺了两个月且零使用**。
> 要做的是：**把它提升为平台唯一的 AI 产出通道**，并让所有 AI 输出都必须经过它。

这也解释了为什么"AI 在研判与行动环节几乎空白"：不是缺能力，是**缺一条所有 AI 输出都必须走的通道** —— 于是每条 AI 路径各自造轮子，或干脆不造（直接写字段、直接返回文本）。


**一句话设计**：

> AI 的唯一一等产出物是 **Proposal (提案)** —— 一个**带证据引用、置信度、未知项、模型与提示版本**的**草稿态**领域对象。AI **永不**直接写事实、**永不**宣称完成；每个提案都有 run record；人的采纳/拒绝/修改**连同理由**沉淀为训练信号与审计证据。

---

## 1. AI Native 是什么意思 (第一性原理定义)

先用反例定义。**"AI 加装 (AI-added)"** vs **"AI 原生 (AI-native)"**：

| 维度 | AI 加装 (现状) | AI 原生 (目标) |
|------|--------------|--------------|
| 位置 | AI 在某个函数内部被调用 | AI 是流程中的一个**实体**，有生命周期和账本 |
| 产出 | 一段文本 / 一个枚举值 | 一个**类型化的领域对象**（草案） |
| 证据 | 无 | `evidence_refs` 强制 ≥1，哈希校验 |
| 不确定性 | 无（默认值冒充确定） | `confidence` + `unknowns` + `counter_evidence_refs` 是**必填** |
| 失败 | 静默降级，回落默认值 | 显式 `failed`，不缓存、不冒充成功 |
| 所有权 | AI 的输出直接落库 | 只有人的采纳才使其成为事实 (`L3 人主律`) |
| 可追溯 | 无从知道哪个 prompt / 哪个模型 | `proposal` 记录 model + prompt_version + cost + 输入快照 |
| 改进 | 无反馈回路 | 人的采纳/拒绝/**修改 diff** 是训练与评估信号 |
| 主动性 | 人问才答 | 有**观察循环**，主动浮现应当注意的事 |

**判据 (AI Native 五问)** —— 任何号称 AI 原生的能力必须全部通过：

| # | 判据 | 不通过的含义 |
|---|------|-------------|
| **AN1** | 产出是**类型化草案**而非裸文本吗？ | 不可审计、不可组合 |
| **AN2** | 是否**强制**带证据引用 + 置信度 + 未知项？ | 不可辩护，违反 `L1` |
| **AN3** | 失败是否**显式**且**不冒充成功**？ | 违反 `L2`，污染账本 |
| **AN4** | 是否**必须经人采纳**才成为事实？ | 违反 `L3`，责任链断裂 |
| **AN5** | 是否有 **run record + prompt_version + 成本**？ | 不可复现、不可改进、成本失控 |

---

## 2. 现状诊断 (AI 层专项)

### 2.1 AI 在哪、不在哪

| 业务阶段 | AI 覆盖 | 证据 |
|---------|--------|------|
| 采集 / collection | ❌ **打标 AI 未接通**（纯规则在跑） | `classify_item_with_ai` **零调用方**（§2.5 D1）；生产是规则 `batch_classify`（`jobs/collect.py:83` 等） |
| 门禁 / gating | ⚠️ 语义判别在跑，但**破坏性 + fail-open** | `semantic_filter`（`info_filter_gate.py:163`）判定后**直接丢弃条目**；失败时 `tasks.py:131` fail-open 放行；NER 实体 ✅ `pipeline_ner` |
| 承接 / intake | ❌ **AI 缺席** | `case_service` / `signal_service` / `auto_intake_service` / `v1_admission_service` **零 ai_hub 引用**；最近的是事后 `rejection_explain` |
| **研判 / judgment** | ⚠️ 有，但**仅 SK-02 一条路径** | `judgment_service.py:261→279` → `v1_judgments` status=**draft** |
| **行动 / action** | ⚠️ 有，但**仅 SK-03 一条路径** | `action_service.py:191→206` → `v1_actions` status=**planned** |
| **执行 / run** | ❌ **AI 缺席且无执行体** | `run_service.py` 只有 create/list/get，**无状态转移写入方**；`v1_runs` 只写 'queued'（`:149`）；`worker_pump.py:44` 明确不写 v1_runs |
| 产物 / artifact | ❌ **AI 缺席** | `artifact_service.py` **零 ai_hub 引用** |
| 沉淀 / knowledge | ⚠️ 仅 SK-04 路径，但校验最强 | `knowledge_ai.py:112→127` → `v1_knowledge` status=**draft** |
| 复用 / reuse | ❌ **AI 缺席** | `knowledge_reuse.py` **零 ai_hub 引用**；召回是 SQL/关键词（`:302`） |

**修正后的结论 (比初稿更严格)**：

1. AI 在**维持系统自动运转**上很勤奋，在**帮助用户完成一次可辩护的判断**上几乎空白；
2. 即使在有 AI 的环节，**全部止步于 `draft` / `planned`**，且**执行与产物两环完全没有 AI**；
3. 更关键的是 —— **采集打标 AI 与承接环节 AI 根本不存在**，所以"AI 在旁路工作"这个说法本身也偏乐观：旁路里有一部分（D1/D2）**也从未接通**。

**唯一具备完整"证据 + 置信度 + 强制人审理由"的实现是 `event_technique_candidates` 那条路径**（§8 表），而它 0 行数据。


### 2.2 AI 层的八条结构性缺口

| # | 缺口 | 证据 | 违反判据 |
|---|------|------|---------|
| **A1** | **没有"提案"这个实体** —— AI 输出直接成为字段值或文本，没有生命周期、没有账本 | `llm_usage_log` 记的是**调用**不是**产出**（`ai_hub/usage.py`） | AN1 |
| **A2** | **prompt 不是版本化代码** —— 全仓仅 `DEEP_READ_PROFILE_VERSION="v3"` 一处版本常量，且只存在 deep_read blob 内；`llm_usage_log` **无 prompt_version 列** | `prompts.py:113`、`llm_usage_log` schema | AN5 |
| **A3** | **强制 schema 校验只覆盖 2/6 skill** —— 4 个 `parse_*_response` 有校验，5 处 ad-hoc 解析（`_parse_verdict_json` 把非 reject 全映射为 allow） | `prompts.py:411,531,657,777` vs `:71,80` / `tasks.py:47,73,98` | AN2 |
| **A4** | **失败冒充成功** —— `score` 解析失败回落 `DEFAULT_SCORE 5.0` 并缓存、记 `ok=True` | `prompts.py:71-77`、`gateway.py:270-278` | AN3 |
| **A5** | **AI 输出无可视溯源，且不可视是结构性的** —— 后端有完整的可观测层，前端**零消费** | 见 §2.3 专项 —— `observability_router.py:262-267` / `llm_status.py:30,70` 无任何前端调用点；`DigestCard` 渲染的简报 payload **连 provider/model 字段都没有**；`TokenLedger.tsx:12` 类型里有 `provider` 但从不渲染；`ModelPoolPanel.tsx:336` 的路由 chip **硬编码绿色 `st-chip ok`**，值却来自 `llm.yaml` 的**配置值**而非实时解析 | AN5 |
| **A6** | **无反馈回路 (三重机制全部空转)** —— 用户的采纳/拒绝/修改不留可用信号 | `feedback_analyzer.py:56` 的 docstring 声称"由 `feedback_service.submit_feedback` 异步触发"，**该调用不存在**；`agent_memory.PreferenceMiner.mine()` / `recall()` / `active_preferences` 均**无任何请求/触发/调度调用**；反馈 API 已注册 (`api/_registry.py:196-197`) 但**零前端调用点**；`FeedbackBar.tsx:31` 硬编码 `comment: ''` —— **连理由都没存** | 改进不可能 |
| **A7** | **降级不可见：治理仪表盘在主模型失效时说"一切正常"** —— breaker / health / fallback / degradation matrix 后端齐备，前端**零消费者** | `/api/observability/llm/health`、breaker reset、`llm/status` 的 scenario + observability 块**全部无前端调用**。用户能看到的唯一熔断是**代理**的（`ProxySettings.tsx:174,197-202` 显示"熔断 → 直连" + 剩余秒数）—— **同一 UI 范式早就存在，只是没给 LLM 建** | AN3 / AN5 |
| **A8** | **人审决策不存理由** —— 采纳/拒绝的理由被丢弃或硬编码 | `CaseDetail.tsx:267` 发布判断**无理由字段**；`rejectArtifact` 的理由**硬编码** `'人工拒绝 (UI 入口)'` (`:208`)；`PracticeDomainsCard.tsx:189` 显示了 AI 推荐理由但**不持久化**；批量通过只按 `min_confidence: 0.7` 阈值，**无逐条理由** | AN4 的边界条件 |

**A4 / A6 / A7 是本层最危险的三条**：

- **A4** 让账本说谎（模型拒绝 → 记为"评分 5.0 成功"）；
- **A6** 让系统永远不会变好（负样本全丢，连理由都没存）；
- **A7** 让**诊断本身不可信** —— 当主模型降级时，设置页仍显示绿色 "ok"，于是所有人（包括我）都会误判系统健康。

**A7 是"失败即沉默"根因 (R2) 在 AI 层的具体形态**，也是最容易修的：后端已备齐，只差前端接线。


### 2.3 降级与溯源不可见的实测清单

这一节单独成节，因为它是**最容易修、后果最重**的一条。

**后端已经建好了完整的可观测层**：

| 后端能力 | 位置 |
|---------|------|
| breaker 门控跳过 | `ai_hub/gateway.py:220-229` |
| provider 健康记账 | `gateway.py:234-237` |
| fallback 链 `_try_order` 逐任务迭代 | `gateway.py:168` → `:258,310,364,425,510` |
| 全 provider 失败状态 | `gateway.py:551` |
| 降级矩阵 (`scenario` / `t1_available` / `t3_available` / `fallback_order`) | `config/degradation_matrix.py:77-92` |
| provider 健康窗口 + breaker 快照 | `ai_hub/provider_health.py:299-303` |
| 健康 API + reset API | `api/observability_router.py:262-267`、`:272-277` |
| `llm/status` 的 scenario + observability 块 | `api/llm_status.py:30,70` |

**前端消费量：0。**

| 后端已暴露 | 前端调用点 |
|-----------|-----------|
| `/api/observability/llm/health` | **无** |
| breaker reset | **无** |
| `llm/status` → `observability` 块 (recent_calls / recent_errors / success_stats) | **无** —— `ModelsSettings.tsx:31-40` 只读 4 个字段 |
| `llm/status` → `scenario` 降级矩阵 | **无** |

**唯一可见的熔断器是代理的**：`settings/ProxySettings.tsx:174,197-202` 显示"熔断 → 直连" + 剩余秒数 + 连续失败次数。**同一 UI 范式早已存在，只是没给 LLM 建。**

**因此主模型失效时，用户只能靠副作用察觉**：DeepReadPage 报错框 (`:372-381`)、判读队列的 eval 错误行 (`SentinelJudgePage.tsx:417-418`)、简报降级为模板 + 警告 (`DigestCard.tsx:49-51`)、告警描述里冒出裸 token `llm_fail_open: N 强信号` (`backend/services/news_alert_service.py:103` → `NewsAlertList.tsx:74`)。

**他们不会知道**：某 provider 被跳过、是 fallback 答的、简报/告警/领域推荐分别由哪个模型产出、降级场景是否切换。设置页会继续显示同一个 `effective_provider` 和一颗绿色路由 chip。

**两处"结构上不可能溯源"**（比"没渲染"更严重）：

| 位置 | 问题 |
|------|------|
| `DigestCard.tsx:55` 渲染 LLM `summary_md` 并冠以"官方每日简报" | 简报 payload **不含 provider/model 任何字段** (`digest_service.py:301` ← `:123`) |
| `NewsAlertList.tsx:74` 渲染 `{a.description}` | 该字段是 `f"{reason} \| {summary}"` 拼接 (`news_alert_service.py:208`)；LLM 失败时 `reason` 变成裸内部 token，**当作文案无标注展示** |

**设计含义**：溯源不能靠"再加一个展示组件"，必须在**产出层就写入 provenance**（这正是 Proposal 账本要解决的），否则前端永远只能展示"渲染时恰好带过来的字段"。

### 2.4 已经做对但被埋没的五件事 (可直接一般化)

| 模式 | 位置 | 一般化后的形态 |
|------|------|--------------|
| schema 化判断 + 证据引用 | `parse_cve_impact_brief_response` | 所有 `Judgment` 提案的唯一入口 |
| 知识条件化 + 哈希校验 | `knowledge_ai._validate_evidence_hashes` | 所有 `Knowledge` 提案的硬门禁 |
| 规则优先 + AI 增援 + 白名单采纳 + fail-safe | `auto_classifier.classify_item_with_ai` | 平台级"AI 不得越权"的参考实现 —— **⚠️ 设计正确，但当前无生产调用方（见 §2.5）** |
| 领域类型已含不确定性字段 | `domain/v1_0_models.py:320-343` | `Proposal` 直接复用，无需新概念 |
| **提案表 + 人审生命周期已存在** | `event_technique_candidates` (migration 117) | **通用 Proposal 的 schema 基础**（详见 §8） |

**这五件事说明：承载实体、类型系统、校验契约、人审生命周期 —— 全都已经在了，缺的是"让所有 AI 输出都必须走这一条通道"的强制执行。**

### 2.5 勘误与新增：四项"已建成但无调用方"的 AI 能力

本节是对本文档早期判断的**自我更正**，来自 AI 调用点全量取证（对所有 `.py` / `.ts` / `.tsx` 做穷尽 grep）。

| # | 能力 | 声称状态 | 实测 |
|---|------|---------|------|
| **D1** | `auto_classifier.classify_item_with_ai`（`ai_classify` gate 的消费点） | `feature_gates.toml:38` **`ai_classify = true`（已开闸）**；`extensions/__init__.py:61` 已登记；`test_ai_classify.py` 有 43 行测试且通过 | **零生产调用方** —— 全仓仅 6 处引用，全部在测试与 `__all__` 里。生产走的是**纯规则** `batch_classify`（`jobs/collect.py:83`、`jobs/knowledge.py:33`、`knowledge_import.py:119`、`auto_intake_service.py:137`） |
| **D2** | `t3_link_to_structure._summarize_with_llm` | T3 阶段"LLM 摘要优先，失败回退截断" | **零调用方**（定义在 `:148`，只有测试调用）。T3 实际走 `_generate_summary` |
| **D3** | `feedback_analyzer.analyze_batch` | docstring 称"由 `feedback_service.submit_feedback` 异步触发" | **该调用不存在**；全仓无调用方 |
| **D4** | `agent_memory.PreferenceMiner.mine()` / `recall()` / `active_preferences` | 偏好挖掘与召回 | **无任何请求/触发/调度调用** |

**D1 是最严重的一条，因为它是一个"三元一致"的假象**：

```
gate 声明开启   (feature_gates.toml:38  ai_classify = true)
   +  扩展登记   (extensions/__init__.py:61)
   +  测试通过   (test_ai_classify.py 全绿)
   =  看起来完全通电的能力
   −  但没有调用方  →  实际从未运行过一次
```

**这说明该能力自 2026-09-19 "开闸"以来，没有处理过任何一条资讯。** 而 `feature_gates.toml` 的注释明确写着"gate 化须随消费点同时登记 (user_skills 先例)" —— 这个纪律在 `ai_classify` 上失效了：**登记了 gate，却没有验证消费点存在。**

#### 与 §6.1 的关系

§6.1 的"能力已建成，消费方为零"清单需要扩充为 **8 项**：

| 已建成 | 消费方 |
|--------|--------|
| LLM breaker / provider health / 降级矩阵 | 0 个前端调用点 |
| `feedback_service` / `feedback_analyzer` / `agent_memory` 三套反馈机制 | 0 个调用方 / 0 个前端调用点 |
| `event_technique_candidates` 提案表 + 人审 API | 0 行数据 |
| `ProxySettings` 熔断 UI 范式 | 只给了代理 |
| `TokenLedger` 类型里的 `provider` | 声明了但从不渲染 |
| 简报 / 告警 payload 的 provider/model | **字段不存在** |
| **`ai_classify` gate + 白名单校验 + 43 行测试** | **0 个生产调用方**（D1） |
| **T3 LLM 摘要** | **0 个调用方**（D2） |

#### 对全文结论的影响

**没有推翻，而是加强。** 原结论是"AI 是事后加速器，不在结构上"。现在还要加一句：

> **而且连"加速器"里也有一部分从未接通 —— 系统里有若干 AI 能力通过了 gate 声明、扩展登记和单元测试三重检查，却因为缺一个调用方而从未执行。**

这进一步支持 §6.1 的排序结论：**在任何新 AI 功能之前，先建立"声明即验证"的机制** —— 一个 gate 声明为 true 时，CI 必须能证明它的消费点存在（可执行、被调用），否则就该失败。


---

## 3. AI Native 目标架构

### 3.1 核心新增实体：Proposal (提案账本)

```
                    ┌─────────────────────────────────────────┐
   AI 观察/推理 ──→ │  Proposal (草案态领域对象)               │
                    │  ─────────────────────────────────────  │
                    │  id            ULID                     │
                    │  kind          judgment | action |       │
                    │                knowledge | case_draft |  │
                    │                classification | alert    │
                    │  payload       类型化 body (复用现有      │
                    │                Judgment/Action/Knowledge)│
                    │  evidence_refs ≥1 + hash 校验            │
                    │  counter_evidence_refs                   │
                    │  unknowns[]      显式未知项              │
                    │  confidence      low|medium|high|proved  │
                    │  provenance: {model, provider, prompt_id,│
                    │               prompt_version, run_id}    │
                    │  cost: {tokens, usd, latency_ms}         │
                    │  status  proposed | accepted | rejected  │
                    │          | superseded | expired          │
                    │  decided_by / decided_at / decision_note │
                    │  diff    (采纳时人改了什么)              │
                    └───────────────┬─────────────────────────┘
                                    │  人审
                    ┌───────────────┴─────────────────────────┐
                    │ accept → 物化为 fact (Judgment/Action/…) │
                    │ edit   → 物化 + 记录 diff (训练信号)      │
                    │ reject → 记录理由 (负样本)                │
                    └─────────────────────────────────────────┘
```

**三条不可违反的规则**：

1. **AI 只能写 `proposal` 表** —— 任何 AI 产出直接写业务事实表 = CI 门禁失败。
2. **`accept` 是唯一的事实化入口** —— 且必须记录 `decided_by`（单用户场景即 `owner`）与时间。
3. **`reject` 必须带理由** —— 理由进负样本，用于评估与后续 prompt 改进。

**复用而非新建**：`payload` 直接复用 `domain/v1_0_models.py` 的 `Judgment`/`Action`/`Knowledge`（它们已含 `confidence`/`evidence_refs`/`unknowns`/`status=draft`），`Proposal` 只加**溯源与决策**两个侧面。

### 3.2 上下文编译器 (Context Compiler)

当前 prompt 是把原始文本切片塞进去（`prompts.py:327` 的 `content[:budget]`），既无结构也**无注入防护**。

```
                 ┌────────────────────────────────────────┐
  请求 ────────→ │  Context Compiler                       │
                 │  1. 检索: 相关 Case / Knowledge /       │
                 │     Signal / chunk (语义 + 关键词)       │
                 │  2. 分级: 可信(内部账本) vs 不可信(采集正文)│
                 │  3. 编址: 每段带 {ref_id, hash, 来源层级} │
                 │  4. 预算: 按 token 预算分配, 记录取舍     │
                 │  5. 封装: 不可信内容用分隔符包裹 +        │
                 │     层级声明 (防注入)                     │
                 └────────────────┬───────────────────────┘
                                  ▼
                         Prompt (版本化, 可复现)
```

**产出**：一个 `ContextBundle`（含每段引用与哈希），**随 Proposal 一起存档**。这样"这条判断当时看到了什么"永远可复现 —— 这是 `L1 溯源律` 在 AI 层的落实。

### 3.3 工具契约 (Tool Contract)

`dsh` / `pi` / agent 类能力必须统一到**一个工具调用契约**：

```
Tool = {
  name, description,
  input_schema,          # JSON Schema, 强校验
  output_schema,         # 强校验
  scope,                 # 允许的副作用域 (read | write:<table> | exec)
  requires_approval,     # bool
  cost_estimate          # 时间/资源上限
}
```

**规则**：调用前校验输入、调用后校验输出、每次调用落 `run record`、越界即拒绝并审计。现状的 `dsh` 命令白名单（`dsh/supervisor.py:36-45`）是这条契约的一个手工特例，应一般化。

### 3.4 安全与治理不变量 (平台级, 不可被自定义规则绕过)

| # | 不变量 | 说明 |
|---|--------|------|
| **G1** | AI 只写 `proposal` | CI 门禁：AI 模块不得 import 业务事实 repo 的写方法 |
| **G2** | 出站单一出口 | 100% 凭据出站经 `gateway` + `check_credential_egress`（主分析 E2） |
| **G3** | 不可信内容分级 | 采集正文在 prompt 中必须标记为不可信层级 |
| **G4** | 输出 schema 强校验 | 校验失败 = `failed`，不得回落默认值（删除 `DEFAULT_SCORE`） |
| **G5** | prompt 版本化 | `prompt_id + prompt_version` 入 `llm_usage_log` 与 `proposal` |
| **G6** | 策略快照 | 审批时冻结 `policy_version`；执行只消费冻结快照 |
| **G7** | 成本可见且可阻断 | `cost_alert` 从只读变阻断；`on_exceeded: warn → block` |
| **G8** | 降级可见 | breaker / fallback / mock / gate fail-open 必须上抛到 UI |

### 3.5 评估层 (Eval) —— 让系统会变好

**这是当前完全缺失、也是 AI Native 与"AI 加装"最大的分野。**

```
            ┌─────────────────────────────────────────────┐
   黄金集 ──→│  Eval Harness                               │
 (人工标注)  │  · 每个提案类型一组黄金样本                  │
            │  · 指标: 证据引用正确率 / 幻觉率 /           │
            │          采纳率 / 修改率 / 拒绝率 / 成本      │
            │  · prompt 或模型变更 → 自动回归              │
            └──────────────┬──────────────────────────────┘
                           ▼
              人的决策记录 (accept/edit/reject + 理由)
                           ▼
              变成下一轮黄金集 / 负样本 / few-shot
```

**反馈闭环**：`reject` 的理由 + `edit` 的 diff 是**最高价值的信号** —— 它们精确指出 AI 错在哪。当前这些信号**全部丢弃**（A6）。

---

## 4. AI Native 功能清单

> 按"是否服务用户真实任务"排序。每条标注**新增/一般化**与依赖。

### 4.1 第一梯队 —— 主干上缺失的 AI (P0)

| # | 能力 | 形态 | 新/改 | 依赖 |
|---|------|------|-------|------|
| **AIN-1** | **证据支撑的判断提案** | 任意 domain 的 Case 上，AI 产出 schema 化 `Judgment` 草案：`claim + claim_type + confidence + evidence_refs(哈希校验) + counter_evidence_refs + unknowns`，落入 `proposal` 表，人审后物化 | **一般化** `parse_cve_impact_brief_response` + `judgment_service.create_with_dsh`（当前只服务 SK-02） | Proposal 账本 + Context Compiler |
| **AIN-2** | **反证搜索 (Devil's Advocate)** | 对一条已存在的 Judgment 提案，AI **专门寻找反证**并产出 `counter_evidence_refs` + "什么会推翻这个结论" | **新增** | 同上；这是安全判断的核心价值 |
| **AIN-3** | **行动方案提案** | 从 Judgment 产出 `Action` 草案：步骤 + 预期产物 + 成功判据 + 资源上限 + 边界，人审后成为 Action | **一般化** `parse_inspection_materials_response` | Proposal 账本 |
| **AIN-4** | **条件化经验提案** | Case 关闭后产出 `Knowledge` 草案：`prerequisites`(非空) + `counter_examples` + `review_at` + 证据哈希 | **一般化** `knowledge_ai._generate_parsed_draft`（当前只 SK-04） | 同上 |

**为什么这四条是第一梯队**：它们精确对应飞轮断裂的三处（研判无产物 / 行动无闭环 / 沉淀无复用），且**全部已有代码原型**，风险最低、杠杆最高。

### 4.2 第二梯队 —— 主动性与复利 (P1)

| # | 能力 | 形态 | 新/改 |
|---|------|------|-------|
| **AIN-5** | **观察循环 (Observer)** | 周期性 agent：扫描新 Signal / 未决 Case / 到期 Knowledge / 逾期 Action → 产出**提案**（不是动作）进 `proposal` 收件箱；单次预算受限、可静音、可解释"为什么现在提这个" | 新增（`agent_loop` 已有骨架） |
| **AIN-6** | **知识语义召回 + 适用性判断** | 新 Case 建立时，语义检索历史 Knowledge → AI 判断**是否适用**（含不适用理由）→ 提案"建议参考 + 为什么适用" | 改（现为关键词 `auto_recall_for_case`） |
| **AIN-7** | **证据缺口检测** | 对每条 Judgment 提案，AI 指出"要证明这个结论还缺什么证据"，产出 `unknowns` + 建议补证动作 | 新增 |
| **AIN-8** | **提案去重与冲突检测** | 同一 Case 内多条 Judgment 提案的冲突检测（`claim_type` 同槽位只允许 1 个 published 已有约束） | 改（约束已有，检测缺失） |

### 4.3 第三梯队 —— 治理与自我改进 (P1/P2)

| # | 能力 | 形态 | 新/改 |
|---|------|------|-------|
| **AIN-9** | **AI 决策账本 UI** | 每个 AI 产出的溯源卡：模型 / provider / prompt 版本 / 成本 / 延迟 / 上下文快照 / 置信度 / 降级状态。**修 `TokenLedger` 已声明但不渲染的 `provider`**；**把 `ModelPoolPanel.tsx:336` 硬编码的绿色 chip 改为实时解析结果** | 改 + 新增 |
| **AIN-10** | **降级与失败可见（最高性价比）** | breaker / fallback / mock / fail-open 全部上抛；"AI 现在不可用"是可见状态。**后端已备齐零消费**（§2.3）—— 直接复用 `ProxySettings.tsx:174,197-202` 的"熔断 → 直连 + 剩余秒数"范式，给 LLM 建同一块 | 改（**接线，不新建**；治 A7/R2） |
| **AIN-11** | **Eval Harness + 黄金集** | 每类提案的黄金样本 + 回归指标（证据正确率/幻觉率/采纳率/成本） | 新增 |
| **AIN-12** | **反馈闭环** | 采纳/拒绝/修改 diff 结构化落库 → 回归集 + few-shot 候选。**接线现有三处空转机制**（`feedback_service` / `feedback_analyzer` / `agent_memory`），并给 `FeedbackBar` 补理由字段 | 改（**接线，不新建**；治 A6） |
| **AIN-13** | **成本与限额治理** | 按提案类型/任务的成本看板 + `on_exceeded: block`；给 `TokenLedger` 补成本列 | 改（`cost_monitor` 现无引用） |
| **AIN-14** | **人工决策必须带理由** | 统一所有 accept/reject 的理由字段；替换 `CaseDetail.tsx:208` 的硬编码 `'人工拒绝 (UI 入口)'`；`PracticeDomainsCard` 的推荐理由持久化 | 改（治 A8） |
| **AIN-15** | **溯源写入产出层** | `DigestCard` / `NewsAlertList` 这类"结构上不可能溯源"的产出，在**落库时就写 provider/model/run_id**，而非靠前端凑字段 | 改（治 A5 结构性根因） |
| **AIN-16** | **"声明即验证" CI 门禁** | gate 声明为 `true` 时，CI 必须证明其**消费点存在且可达**（AST 调用图 + 入口可达性）；孤儿 gate / 孤儿能力直接失败。**直接治 D1 类"gate 开启但零调用方"的假象** | 新增（治 §2.5 元问题） |

### 4.4 明确**不做**的 (反 AI 泡沫)

| 不做 | 理由 |
|------|------|
| 让 AI 自动立项 / 自动关闭 Case | 违反 `L3 人主律`；PRD §1.3 已明示"事项建立必须由用户确认" |
| 让 AI 自动发布 Judgment / Knowledge | 责任链断裂；`status` 必须停在 draft |
| 无边界多轮自主 agent 循环 | 成本不可控、不可审计；观察循环必须单次预算受限 |
| 让 AI 直接执行动作（无审批） | 违反 PRD 不可关闭安全底线 |
| 用 AI 生成"看起来完整"的报告填空 | 幻觉进账本，比没有更糟 |
| 把 prompt 调优当产品迭代 | 无 eval 的 prompt 调优是掷骰子 |

---

## 5. 落地路线 (与主分析 F 期对齐)

| 期 | AI Native 任务 | 验收 (可验证) |
|----|--------------|-------------|
| **F0** | 删除 `DEFAULT_SCORE`；AI 失败显式 `failed`；`prompt_id+version` 入 `llm_usage_log` | 构造超时/拒绝用例 → 断言 `failed` 且 UI 可见；日志含 prompt_version |
| **F0** | **`AIN-10` 降级可见接线**（后端零消费，只接前端） + **`AIN-14` 决策理由字段** | 主模型失效时设置页**不再**显示绿色 ok；拒绝理由不再硬编码 |
| **F0** | **`AIN-16` 声明即验证门禁** —— 先对现有 gate 做一次全量审计，暴露所有"声明开启但零消费点"的项 | CI 能列出并阻断孤儿 gate；D1 类假象不再可能 |
| **F1** | **Proposal 账本** (迁移 + service + API)；**Context Compiler** MVP；`AIN-1` 判断提案端到端 | 一条真实资讯 → AI 判断提案 → 人审采纳 → `v1_judgments` 出现 1 行，且证据哈希可校验 |
| **F1** | `AIN-3` 行动提案 + `AIN-4` 经验提案 + **`AIN-15` 溯源写入产出层** | 同一 Case 走完判断→行动→知识，全程 proposal 可追溯；简报/告警 payload 自带 provider/model |
| **F2** | `AIN-9` 溯源 UI + `AIN-13` 成本阻断 | 任一提案可看到模型/prompt/成本/上下文；超额被阻断；`TokenLedger` 显示 provider 与成本 |
| **F2** | Tool Contract 统一 (`dsh`/`pi`/agent) | 所有工具调用有 input/output schema 校验 + run record |
| **F3** | `AIN-2` 反证搜索、`AIN-5` 观察循环、`AIN-6` 语义召回、`AIN-7` 证据缺口、`AIN-8` 冲突检测 | 各自黄金样本通过 |
| **F4** | `AIN-11` Eval Harness + `AIN-12` 反馈闭环（接线现有三处空转机制） | prompt/模型变更触发自动回归；采纳率/修改率可测 |

**关键排序理由**：

1. `Proposal 账本` 必须最先落地 —— 它是 `AIN-1..AIN-8` 的共同前置。**没有账本，做任何 AI 功能都只是再造一次 A1 缺口。**
2. `AIN-10`（降级可见）与 `AIN-14`（决策理由）**放在最前面，因为它们是纯接线/纯加字段，后端能力已 100% 具备**。用最小成本换回"系统诚实"这个前提 —— 否则后续所有度量都建立在不可信的仪表盘上。
3. `AIN-15`（溯源写入产出层）与提案账本同期做，因为**溯源必须在产出时写入，事后补不了**（§2.3 两处结构性缺失即为此）。

---

## 6. 度量 (怎么知道 AI Native 真的成了)

| 指标 | 定义 | 目标 |
|------|------|------|
| **提案采纳率** | accepted / (accepted+rejected) | 30 天内建立基线，之后逐期上升 |
| **提案修改率** | edited / accepted | 逐期下降（AI 越来越准） |
| **证据引用正确率** | 哈希校验通过且引用确支持 claim 的比例 | ≥95%（哈希部分可 100%） |
| **幻觉率** | 采纳后被人撤回/反证的比例 | 逐期下降 |
| **溯源完整率** | 有完整 provenance 的提案占比 | **100%**（硬门禁） |
| **降级可见率** | 降级事件中被 UI 呈现的比例 | **100%**（硬门禁） |
| **单提案成本** | usd / proposal | 有基线且不失控 |
| **主干转化率** | Signal → Case → Judgment → Artifact | 从 0.041% 提到可测量 |

> **度量前提**：在 `AIN-10`（降级可见）落地之前，**上述任何指标都不可信** —— 因为仪表盘会在主模型失效时显示绿色 "ok"。先修可见性，再测指标。

---

## 6.1 一个反直觉的结论：最低成本的最大收益是"接线"

本次审计最反复出现的模式是：**能力已建成，消费方为零。**

| 已建成 | 消费方 |
|--------|--------|
| LLM breaker / provider health / 降级矩阵 | **0 个前端调用点** |
| `feedback_service` + `feedback_analyzer` + `agent_memory` 三套反馈机制 | **0 个调用方 / 0 个前端调用点** |
| `event_technique_candidates` 提案表 + 人审 API（含强制拒绝理由） | **0 行数据** |
| `ProxySettings` 的熔断 UI 范式 | 只给了代理，**没给 LLM** |
| `TokenLedger` 类型里的 `provider` | **声明了但从不渲染** |
| 简报 / 告警 payload 的 provider/model | **字段根本不存在** |
| **`ai_classify` gate（声明开启）+ 白名单校验 + 43 行测试** | **0 个生产调用方**（§2.5 D1） |
| **T3 LLM 摘要**（`_summarize_with_llm`） | **0 个调用方**（§2.5 D2） |

所以这份设计的**性价比排序**与"做新功能"的直觉相反：

```
最高性价比  →  接线已有能力 (AIN-10 降级可见 / AIN-12 反馈闭环 / AIN-14 理由字段)
中         →  建立"声明即验证"门禁 (AIN-16) —— 防止再产生 D1 类假象
中         →  提升已有 schema (Proposal 表 = event_technique_candidates 一般化)
较低       →  补齐主干缺失 (AIN-1..AIN-4 判断/行动/经验提案)
最低       →  全新能力 (AIN-5 观察循环等)
```

**"AI Native" 在这个项目里的第一层含义，不是让 AI 更聪明，而是让已经建成的 AI 治理设施真正被使用 —— 并且让"声明了却没接通"这件事在 CI 里就无法通过。**


---

## 7. 风险与反证条件

| # | 风险 | 反证/缓解 |
|---|------|----------|
| 1 | Proposal 账本增加摩擦，用户嫌烦 | 若采纳率低且修改率高，说明提案质量不够 → 先修 prompt + eval，而非取消人审 |
| 2 | 单用户场景下"人审"变成自己审自己，形同虚设 | 人审的价值不在"第二个人"，而在**强迫显式化不确定性**（`unknowns`/`counter_evidence`）；若实测确认无价值，退化为"事后确认"而非"事前审批" |
| 3 | Context Compiler 与语义检索引入新的复杂度 | 先做**规则+关键词**版本，语义检索放 F3 |
| 4 | 观察循环变成噪声源 | 单次预算 + 可静音 + 必须给"为什么现在提"；噪声率高则先收紧触发条件 |
| 5 | 模型能力不足以产出合格证据引用 | 这条最可能成立 —— 若 30 天采纳率 <20%，应降级 AI 角色为"检索与整理"而非"判断建议" |

**最重要的一条反证**：如果实测显示"AI 的判断提案采纳率长期低于人工起草的收益"，那么正确的结论**不是**加大 AI 投入，而是把 AI 收缩到它确实强的地方（检索、归类、抽取、反证搜索），并明确产品定位从"AI 工作台"回到"证据账本 + 辅助工具"。**AI Native 不等于 AI 全能。**

---

## 8. 附：与既有资产的关系

| 既有资产 | 处置 |
|---------|------|
| `domain/v1_0_models.py` 的 `Judgment`/`Action`/`Knowledge` | **复用**为 proposal payload；不新建平行模型 |
| `ai_hub/prompts.py` 4 个 `parse_*_response` | **提升为通用校验契约** |
| `services/knowledge_ai.py` 的哈希校验 | **提升为所有提案的硬门禁** |
| `services/auto_classifier.py` 的"规则优先+白名单+fail-safe" | **作为平台参考实现**推广；但 `classify_item_with_ai` (D1) 需**接线或删除** —— 现在它是"gate 开着却从不运行"的样板 |
| `services/triggers/t3_link_to_structure.py:148` `_summarize_with_llm` | **接线或删除**（D2）—— 定义存在，零调用方，T3 实际走 `_generate_summary` |
| `feature_gates.toml` 16 个 gate | **全量审计一次消费点可达性**，剔除 D1 类孤儿 gate；把该检查纳入 CI（`AIN-16`） |
| `llm_usage_log` (1,062 行, 已有 provider/model/task/tokens/cost/latency/ok/config_source/key_source) | **扩列** `prompt_id`/`prompt_version`/`proposal_id`；已有数据是成本基线 |
| `services/agent_loop/` (965 行) / `agent_memory/` (737 行) | **候选承载** `AIN-5` 观察循环。`agent_memory` 的 `PreferenceMiner.mine()` / `recall()` / `active_preferences` 经核实**无任何请求/触发/调度调用**，`agent_preferences` 无消费者 —— 属"已建好但完全空转"，是 `AIN-12` 的直接骨架 |
| `services/skill_registry/` `skill_runner/` `trigger_gate/` (3,912 行) | 与 Proposal 关系需裁决：skill 是"AI 能力"还是"proposal 的触发器"？建议收敛为后者 |
| `frontend .../pipeline/TokenLedger.tsx` | **扩**为提案溯源与成本面板的载体：修 `:12` 已声明但从不渲染的 `provider`，补成本列 |
| `services/feedback_service.py` (`feedback_events` + 权重 + dsh bridge) | **接线**：其输出从不进 prompt —— 是 `AIN-12` 的另一半骨架 |
| `services/feedback_analyzer.py` (无运行期引用) | **激活或删除** —— docstring 声称"由 `feedback_service.submit_feedback` 异步触发"但**该调用不存在**；这是文档说谎的又一实例 |
| `frontend .../settings/ProxySettings.tsx:174,197-202` | **直接复用**其"熔断 → 直连 + 剩余秒数 + 连续失败次数"范式给 LLM 建同一块（`AIN-10`） |
| `frontend .../skills/FeedbackBar.tsx:31` | **补理由字段** —— 现硬编码 `comment: ''`，连负样本的理由都没存 |
| **`event_technique_candidates` (migration 117, 0 行)** | **提升为 Proposal 的 schema 基础** —— 已有的 `confidence`/`evidence_quote`/`rationale`/`llm_model`/`llm_run_at`/`owner_status`/`owner_action_at`/`owner_action_by`/`reject_reason` 全部复用；只补 `prompt_id`/`prompt_version`/`context_bundle`/`cost`/`payload_kind` |
| `audit_log_mp2_review` (0 行) | 合并进统一的提案决策审计 |
| `frontend .../events/EventsReviewPage.tsx:264-274` | **保留为参考实现** —— 它是全仓唯一"显示证据 + 置信度 + **强制拒绝理由**"的审查面，是正确的提案审查 UX 样板 |

### 关键结论：迁移策略是"提升"，不是"新建"

因为 P4 的 schema 已经存在，Proposal 账本的落地路径比预想短得多：

```
第 1 步  event_technique_candidates 的列 → 抽为通用 proposal 表 (migration)
第 2 步  event_technique_extract_service → 改为写通用表 (行为不变, 只是换表)
第 3 步  judgment / action / knowledge 三条既有 AI 路径 → 改为写通用表
第 4 步  加 CI 门禁: AI 模块不得直接写业务事实表
```

第 2 步是零行为变更的纯搬运，可立刻验证通用表设计是否正确；第 3 步才是把 AI 从旁路搬上主干。

