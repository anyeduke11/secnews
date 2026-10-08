# 已废止（superseded）

> **本文档已被取代**：权威产品文档 = [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](../HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md)；0.8.6 版本族详细文档 = [`docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`](../HOTSPOT_V0.8.6_AI_NATIVE_PRD.md)。本文仅作历史设计留痕，**不作为当前事实源**（取代依据见权威 PRD 头部「取代」名单 + `docs/audit/PRD_ALIGNMENT_AUDIT_2026-10-02.md`）。

---

# mitre ATT&CK 实例化标签体系设计（v3 · 已批准）

- 日期：2026-09-13（v3，按 owner 全面裁决更新）
- 状态：**全部开放问题已确认（owner 2026-09-13）** — v2 方向 + 词表覆盖面/抽取-人审流程/L1 数据源/技战法卡位置四项全部落定，可进入实施排期
- 现状地基：`backend/data/mitre/enterprise-attack.json`（46MB ATT&CK Enterprise 全量）已就位；`security/mitre_attack.py` 加载器 + `attack_techniques`/`attack_cwe_map` 表已建但**零数据**（D18"图谱是死种子"）

---

## 1. 核心理念：MITRE 实例化

抽象的 ATT&CK 框架（14 战术 / 600+ 技术）对一线用户的学习成本极高。**实例化 = 把抽象技战法落到具体安全对象上**：

```
抽象层（MITRE 官方）:  T1486 数据加密勒索 ← 谁看得懂？
                          ↑ 实例化（本设计）
具体层（用户的世界）:  "LockBit 勒索事件" = 初始访问(T1078) → 执行(T1204)
                       → 提权(T1068) → 防御规避(T1490) → 影响(T1486)
```

用户看一个 CVE、一类安全事件、一份应急响应预案时，**直接看到它涉及的技战法**——理解安全事件的同时自然理解 MITRE 框架，双向降低学习成本。标签是手段，实例化是本质。

## 2. 三类标签对象（实例化的三个落点）

### L1 漏洞实例化（CVE → 利用战术标签）

- **做什么**：每个漏洞条目关联"被利用时所涉技战法"——利用方式（T1203 异常执行/T1068 提权）、入口（T1190 面向公众应用）、后渗透路径
- **数据来源**：`attack_cwe_map` 桥（CWE→ATT&CK 官方映射，随 enterprise-attack.json 就位）+ **NVD 权威源**作为 CVE 语料主干，与 P1-5 联动排期
- **展示位**：CVE/漏洞条目的"战术标签卡"、Subject 360 视图；技战法卡作为**知识层资产**入库（v1_knowledge），被判断层调用
- **诚实约束**：NVD 接入排期未启动前 L1 仅覆盖存量；建议把 L1 启动时点与 P1-5 已有可对接的 NVD 增量流挂钩

### L2 安全事件类型实例化（事件类型 → 典型技战法链）★ 主推

- **做什么**：建立安全事件类型词表（**通用 + 金融行业特有**），每类事件类型结构化其**典型技战法链**（战术序列 + 代表技术 + 真实案例引用）
- **词表覆盖面（v3 确认）**：
  - 通用类：勒索软件、钓鱼社工、Web 应用入侵、供应链投毒、暴力破解、内部威胁、云配置泄露、AI 模型投毒（8 类）
  - **金融行业特有**（owner 2026-09-13 加）：反诈、数据泄露（含客户 PII 流转）、监管通报（人行/银保监/网信办口径）（3 类）
  - **合计 11 类**
- **数据来源（v3 确认）**：**LLM 从公开事件报告结构化抽取 + owner 人审落库**——LLM 只生成候选，人审是必经步骤（详见 §7 抽审规约）
- **承载容器**：security taxonomy 新 entity_type（`event_type`），security_entities/taxonomy 表已存在（当前 3 行测试数据，需清洗重播）
- **用户价值**：这是三类中**用户感知最直接**的——资讯流里出现某类事件时，一键看到"这类事件通常怎么发生、关键技战术是什么"

### L3 应急响应实例化（响应手册 → 对抗战术映射）

- **做什么**：应急响应的动作/预案关联其所"对抗"的战术——检测类动作映射"能检测哪些 technique"、遏制类动作映射"针对哪些 technique"、恢复类映射"事件后的验证清单"
- **诚实约束**：**系统当前没有应急响应/预案对象**（第一性原理 §5.5 领域能力缺失之一）。本期方案：以"事件类型的响应知识条目"（v1_knowledge，带 review_at 复查纪律）承载，即 L3 = L2 事件类型的响应侧知识；独立 incident 对象属 P2-3 领域能力补齐，不在本期
- **用户价值**：应急响应从"凭经验"变"对照技战法清单"——事件发生时按 technique 查检测缺口

### 衍生：资讯打标（L2 的自然延伸）

- 资讯条目若命中事件类型/CVE，继承其实例化标签（不做独立的资讯级 ATT&CK NLP 打标，避免误标面扩大）

## 3. 基础设施前提：M1 图谱点火（所有标签场景的地基）

- **做什么**：跑通 `load_attack_data()` 将 techniques/tactics 落 `attack_techniques`；补 `security_edges` 写入路径（technique↔tactic 隶属、CVE↔technique 经 cwe_map）；`_load_compliance_edges()` 硬编码空列表与 `iter_builtin()` 合规种子一并接通
- **结果**：图谱页/分析页首次显示真实 ATT&CK 结构；标签体系的 FK 落点就位
- **成本**：1~2 天（加载器与表都在，主要是接断线）

## 4. 数据模型（最小集）

| 表 | 动作 | 说明 |
|---|---|---|
| attack_techniques / attack_tactics（或单表 + type 列） | 落数据（M1） | 官方全量，静态字典 |
| attack_cwe_map | 落数据（M1） | L1 的桥 |
| security_entities / taxonomy | 清洗测试数据 + 新增 event_type 实体（L2） | 11 类（8 通用 + 3 金融）每类一行 |
| **event_technique_map**（新表） | L2/L3 核心：`(event_type_id, technique_id, stage, note, owner_audit_chain)` | 事件类型×技战法多对多，stage 记录在杀伤链中的位置 |
| **event_technique_candidates**（新表，MP-2 自带） | LLM 抽取候选池 | `(event_type_id, technique_id, stage, confidence, evidence_quote, source_report_id, owner_status)` |
| CVE 侧 | 复用 attack_cwe_map 关联查询（L1），不加新表 | |
| v1_knowledge 复用 | L3 响应知识条目承载（带 review_at） | |
| **knowledge_technique_ref**（新表，MP-4） | L3 响应↔技战法关联 | 响应条目"能对抗/检测哪些 technique" |
| **v1_judgments 扩 1 列**（MP-4） | 判断层↔技战法引用 | `attack_technique_refs TEXT`（JSON 数组，judgment 上下文装配用） |

标签查询统一走一个 service（`attack_label_service`：给对象 id 返回结构化技战法链；扩展接口含 `list_knowledge_for_techniques`，MP-4 用），前端一张"技战法卡"组件三处复用（CVE 卡/事件类型卡/响应卡）。

## 5. 实施分期

| 期 | 内容 | 验收 | 工作量 |
|---|---|---|---|
| **MP-1** | **M1 图谱点火** | 图谱页显示真实 ATT&CK 结构；三个死视图复活；FK 落点就位 | **1~2 天** |
| **MP-2** | **L2 事件类型词表（11 类 = 8 通用 + 3 金融）+ LLM 抽取 + owner 人审规约 + 实例化标签 + 技战法卡** | 任一事件类型可看典型技战法链；金融行业三类纳入；抽审记录可追溯 | **3~4 天** |
| **MP-3** | **L1 漏洞实例化（与 P1-5 联动：NVD 接入+CVE→technique 标注）+ 资讯继承标签** | CVE 详情带战术标签；与 P1-5 排期挂钩 | **2~3 天** |
| **MP-4** | **L3 应急响应知识条目 + 知识↔判断层双向关联 + 与 CodeGarden 实践桥（"该战术有什么工具可练"）** | 事件类型页带响应知识与判断层调用入口 | **2~3 天** |

MP-2 是用户价值最高的一期（事件类型是用户日常语言）。
MP-4 涉及知识↔判断层双向关联（详见 §8）。

---

## 6. 开放问题状态（已全部确认）

| # | 问题 | 状态 | 决议 |
|---|---|---|---|
| 1 | 事件类型词表覆盖面 | **已确认** | **加金融行业特有**：反诈 / 数据泄露 / 监管通报（与通用 8 类并列，11 类全集） |
| 2 | 词表数据来源 | **已确认** | **LLM 抽取 → owner 人审落库**，详见 §7 抽审规约 |
| 3 | CVE 语料联动 | **已确认** | **L1 漏洞实例化绑 CVE，NVD 为权威源**，与 P1-5 联动排期 |
| 4 | 技战法卡位置 | **已确认** | **技战法卡放知识层（v1_knowledge 实体），判断层做调用**，两边做关联设计，详见 §8 |

## 7. LLM 抽取 → owner 人审规约（MP-2 实施细则）

**目的**：用 LLM 批量从公开事件报告抽取事件类型→技战法候选，owner 在落库前逐条人审。LLM 不直接入库，保证数据可信与责任链清晰。

**7.1 输入（输入侧）**

- 公开事件报告语料库：复用现有 `data/security/incidents/`（如已存在）+ 按事件类型从公开报告（MITRE Case Studies / Verizon DBIR / CrowdStrike 案例库 / 金融行业：央行支付结算司、银行业协会、银保监通报）按主题补抓
- 每份报告保留：`source_url` / `fetched_at` / `event_class_hint`（基于报告原始分类的初判，不作终判）/ `report_md` 原文片段
- 预算：MP-2 阶段每类事件类型至少 5 份报告（共 11 类 × 5 = 55+ 份），覆盖近 3 年

**7.2 LLM 抽取（候选侧）**

- 单条 prompt：给报告原文 + ATT&CK technique 字典（来自 M1 已加载的 attack_techniques），输出结构化候选：

  ```json
  {
    "event_type_id": "<已落 event_type 的 id>",
    "techniques": [
      {
        "id": "T1078",
        "stage": "initial_access|execution|persistence|privilege_escalation|defense_evasion|credential_access|discovery|lateral_movement|collection|exfiltration|impact",
        "confidence": 0.0~1.0,
        "evidence_quote": "≤120 字原文片段",
        "rationale": "≤80 字理由"
      }
    ]
  }
  ```

- 强约束：
  ①每条 candidate 必须 `id` 在官方 ATT&CK 字典中存在（M1 已落 attack_techniques 提供 FK 校验）
  ②`evidence_quote` 必须能在原文中逐字找到（程序化校验：抽取后跑 substring 匹配，失败标 `auto_reject_reason='quote_not_found'`）
  ③`confidence` < 0.5 的不入候选
- 落候选池：每条抽取结果落 `event_technique_candidates`（新表，MP-2 自带）：`(id, event_type_id, technique_id, stage, confidence, evidence_quote, rationale, source_report_id, llm_model, llm_run_at, owner_status='pending')`

**7.3 owner 人审（人工侧，MP-2 配套工具）**

- **入口**：`/admin/event-technique-review`（走 admin 入口，未来或开放给运营），按 event_type 分组、按 stage 排序
- **审核动作**（每条 candidate 三态）：
  - `approve` → 直接落 `event_technique_map`（带 `approved_by='owner'` / `approved_at`，**保留对 candidate 的引用作审计追溯链**）
  - `edit` → 改 technique/stage/note 后落（保留原 candidate 作审计，编辑版本同步入 `event_technique_map` 的 `owner_audit_chain` JSON 字段）
  - `reject` → 标 `owner_status='rejected'`，写 `reject_reason`
- **批量便利**：`approve_all_for_event_type`（当一类事件的所有 candidate 都置信度高，owner 一键批），但每条仍记录审计
- **进度指标**：`pending_total` / `approved_total` / `rejected_total` 按 event_type 维度展示，催办机制
- **追溯链**：每条最终 `event_technique_map` 行可回溯到 candidate → candidate 可回溯到 report → report 可回溯到 source_url。**任何技战法在事件类型上的关联都能证明出处**

**7.4 不入 LLM 抽取的边界**

- 词表本体的初版 11 类由 owner 直接给 schema 与定义（避免 LLM 命名漂移）；LLM 只生成"类内技战法候选"
- 金融行业三类的初次抽取语料只取**脱敏后的公开通报**（监管通报本身公开，反诈案例库来自公安部公开宣传），不接 owner 客户内部数据

**7.5 抽取-人审节奏建议**

- MP-2 启动后第一周：先完成 3 类高价值事件（如勒索/钓鱼/Web 入侵）的端到端抽取-人审闭环，验证流程无误
- 第二周：扩展到其余 5 通用类 + 启动金融三类的语料补抓（监管通报优先，反诈次之，数据泄露语料最难收，列第三批）
- MP-2 收口条件：11 类全覆盖，每类 ≥3 条已审定的 `event_technique_map` 行（最低质量门槛）

## 8. 知识层 ↔ 判断层双向关联设计（MP-4 重点）

**核心理念**（owner 2026-09-13 裁决）：**技战法卡放知识层（v1_knowledge），判断层做调用**，两边做关联设计。

**8.1 关联方向（谁存→谁查）**

- **方向 A：知识层 → 技战法**（MP-4 新增 `knowledge_technique_ref`）：v1_knowledge 行可关联 N 个 ATT&CK technique（响应条目常需"对抗 T1078/T1110"等）；写在知识侧，由 knowledge_service 调用 attack_label_service 渲染
- **方向 B：判断层 → 知识层**（MP-4 通过 `v1_judgments.attack_technique_refs` + judgment 上下文装配）：JudgmentService 生成判断时，**显式声明需要哪些技战法作锚点**——自动通过 attack_label_service 拉取"哪些知识条目引用了这些 technique"，拼装为 prompt 上下文片段

**8.2 数据模型补充**

```sql
-- v1_judgments 表加 1 列（与现有 draft/published/cas 等列并存）
ALTER TABLE v1_judgments ADD COLUMN attack_technique_refs TEXT;  -- JSON 数组，e.g. ["T1078","T1190"]

-- 已有 knowledge_technique_ref 表（MP-4 落地）
CREATE TABLE knowledge_technique_ref (
    knowledge_id TEXT NOT NULL,        -- v1_knowledge.id
    technique_id TEXT NOT NULL,        -- attack_techniques.attack_id (Txxxx)
    relation_type TEXT NOT NULL,       -- 'addresses'|'detects'|'mitigates' (L3 响应条目用)
    PRIMARY KEY (knowledge_id, technique_id, relation_type)
);
```

**8.3 judgment 上下文装配流程（MP-4 实现）**

```
JudgmentContextBuilder.build(judgment)
  1. 读 judgment.attack_technique_refs（如有）
  2. attack_label_service.list_knowledge_for_techniques(technique_ids)
     → 走 knowledge_technique_ref JOIN v1_knowledge WHERE status='published'
  3. 把"相关响应知识条目"作为 prompt context 片段（独立 section，标题"## 相关响应知识"）
  4. 返回最终 prompt 给 LLM
```

**8.4 反向（知识更新触发判断失效）（MP-4 配套）**

- 知识条目发布/废弃/修订时，**通过 SSE 事件 `v1.knowledge.published` 等**通知到前端（已有 v1 SSE 通道）
- 判断层**不自动重生成已发布判断**（避免覆盖 owner 已审定的输出）；只在前端清单/详情页标注"该判断引用的响应知识已更新"，由 owner 决定是否重审
- 与 v1 已有 status 流转 / CAS 不变量兼容（判断的 published 状态不被动摇）

**8.5 复用与边界**

- 不动 v1_judgments 既有字段，**只加 1 列**（向后兼容，老数据 attack_technique_refs=NULL 行为不变）
- 不动 v1_knowledge 主结构，**只加 1 表**（knowledge_technique_ref）
- attack_label_service 复用 MP-2 已建的 `event_technique_map` 查询路径（同一 service 多语义入口）

## 9. 同步事项

- `docs/FEATURE_DECOMPOSITION_2026-09-12.md` §5 裁决记录更新为"mitre v3 全部开放问题已关闭"
- `PROGRESS.md` 活跃段加 MP-1~4 待开工状态（不立即执行，待 owner 令下）
- 与 P1-5（NVD 接入）负责人协调 MP-3 启动时点；MP-2 抽取语料补抓可并行，不阻塞 MP-1
- DEV_LOG.md 追加 DEV-0214：mitre v3 设计稿定稿（4 开放问题全关）+ §7 抽审规约 + §8 知识↔判断层双向关联设计