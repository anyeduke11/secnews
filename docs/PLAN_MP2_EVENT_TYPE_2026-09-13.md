# MP-2 安全事件类型实例化 · 正式执行方案

- 日期：2026-09-13（立项方案）
- 上游：`docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md` v3（已批准）
- 状态：**待 owner 令开工**（方案定稿，编排/抽审/验收/边界全部明确）
- 总工作量：**3~4 天**（多 agent 并行执行；owner 人审为关键路径瓶颈）

---

## 0. 一句话目标

为 **11 类安全事件类型**（8 通用 + 3 金融特有）建立结构化"典型技战法链"，**LLM 批量抽取 + owner 人审落库**，前端展示技战法卡（CVE 卡/事件类型卡/响应卡三处复用，MP-2 先做事件类型卡）。本期完成 **L2 安全事件类型实例化**（MP-2），L1 漏洞实例化（MP-3）与 L3 应急响应（MP-4）后续期。

---

## 1. 输入与前置依赖

### 1.1 强前置（必须先完成）

- **M1 图谱点火**（MP-1，1~2 天）：attack_techniques 表已落数据，提供 FK 校验目标
- **event_type 实体播种**：security_entities 表新增 11 行（owner 直接提供 schema 与定义，**不走 LLM**——避免命名漂移）

### 1.2 输入侧：公开事件报告语料

- **预算**：每类事件类型 ≥5 份 = **11 类 × 5 = 55+ 份**（MP-2 收口条件：每类 ≥3 条已审定 `event_technique_map` 行 = 33+ 条终态数据）
- **来源策略**：

  | 来源类别 | 适用事件类型 | 备注 |
  |---|---|---|
  | MITRE Case Studies | 通用类优先 | 结构化最好，覆盖广 |
  | Verizon DBIR | 通用类 | 年度报告，事实库权威 |
  | CrowdStrike 案例库 | 通用类 + 金融类 | 勒索/钓鱼/内部威胁样本多 |
  | 央行支付结算司通报 | 反诈 / 数据泄露 | 国内权威，结构化 |
  | 银行业协会通报 | 反诈 / 数据泄露 / 监管通报 | 行业自律，案例丰富 |
  | 银保监 / 网信办公开通报 | 监管通报 | 口径明确 |
  | 公安部公开宣传（反诈） | 反诈 | 公众教育素材，语料相对松散 |
  | 金融行业公开事件报告 | 数据泄露 | 语料最稀，优先级最低 |

- **每份报告保留字段**：`source_url` / `fetched_at` / `event_class_hint`（基于报告原始分类的初判，不作终判）/ `report_md` 原文片段
- **存储**：`data/security/incidents/`（如目录不存在，本方案建）

### 1.3 词表本体（owner 直接给，11 类）

| # | 类别 | 名称（中/英） | 行业 | 难度 | 优先级 |
|---|---|---|---|---|---|
| 1 | 通用 | 勒索软件 / Ransomware | 通用 | 中 | 高 |
| 2 | 通用 | 钓鱼社工 / Phishing & Social Engineering | 通用 | 中 | 高 |
| 3 | 通用 | Web 应用入侵 / Web Application Compromise | 通用 | 中 | 高 |
| 4 | 通用 | 供应链投毒 / Supply Chain Compromise | 通用 | 高（语料稀） | 中 |
| 5 | 通用 | 暴力破解 / Brute Force & Credential Stuffing | 通用 | 低 | 中 |
| 6 | 通用 | 内部威胁 / Insider Threat | 通用 | 高（事件少） | 中 |
| 7 | 通用 | 云配置泄露 / Cloud Misconfiguration | 通用 | 中 | 中 |
| 8 | 通用 | AI 模型投毒 / AI Model Poisoning | 通用 | 高（新领域） | 低 |
| 9 | **金融** | 反诈 / Anti-Fraud | 金融 | 中 | **金融第 1 批**（监管通报优先） |
| 10 | **金融** | 数据泄露（含客户 PII 流转）/ Data Breach | 金融 | 高 | **金融第 2 批**（银行业协会 + 央行） |
| 11 | **金融** | 监管通报 / Regulatory Disclosure | 金融 | 中（口径明确） | **金融第 3 批**（监管口径本身公开） |

**owner 提交词表格式**（建议一次性给齐 11 类）：

```json
{
  "id": "evt_ransomware",
  "name_zh": "勒索软件",
  "name_en": "Ransomware",
  "industry": "general",
  "definition": "攻击者通过加密受害者文件或锁定系统访问权限，索取赎金的恶意行为",
  "scope_note": "包含初始入侵→加密→勒索三个阶段；不含纯数据窃取无加密的勒索事件",
  "owner_initial_techniques_hint": ["T1486", "T1490", "T1566"]  // 可选，owner 初判
}
```

---

## 2. 编排：多 agent 并行（owner 决策 2026-09-13）

### 2.1 并行结构（5 agent 组）

11 类事件类型按"通用 8 + 金融 3"分两个域，并行执行：

```
                ┌─ [Agent-A] 通用 8 类（5 类高优先级：勒索/钓鱼/Web 入侵/供应链/云泄露）  ─┐
[主会话协调] ─┼─ [Agent-B] 通用 8 类（3 类次优先级：爆破/内部威胁/AI 模型投毒）       ─┤
                │                                                                       │
                ├─ [Agent-C] 金融 3 类（反诈 - 监管通报优先）                            ─┤
                ├─ [Agent-D] 金融 3 类（数据泄露 - 央行/银行业协会）                  ─┤
                └─ [Agent-E] 金融 3 类（监管通报 - 银保监/网信办口径）                 ─┘
```

- **5 个 agent 同时启动**（突破历史的 2-agent 并发上限：本任务在 5 个**独立 worktree** 内执行，每个 worktree 互不阻塞）
- **worktree 隔离规则**：
  - 主 worktree（hotspot main）保留接收 owner 人审结果与最终合入
  - 子 worktree：5 个独立 branch（`feat/mp2-agent-{A,B,C,D,E}-2026-09-13`），互不干扰
  - 每个子 worktree 跑独立 dev_data 库（隔离根）+ 独立 fixture
- **每个 agent 输出**：
  - 自己负责类的 `event_technique_candidates` 行（owner_status='pending'）
  - 自审脚本生成的候选质量报告（覆盖率/置信度分布/evidence_quote 通过率）
  - **不直接写 `event_technique_map`**（owner 人审是必经步骤）

### 2.2 owner 人审的关键路径编排

| 时段 | 5 agent 在做什么 | owner 在做什么 |
|---|---|---|
| T+0 ~ T+0.5 天 | 各自独立抽取（每类 5+ 报告）→ 落 `event_technique_candidates` (pending) | **空闲 / 准备人审工具培训** |
| T+0.5 ~ T+1 天 | 各自补抽取低置信度 + 自审 | **第一批 3 类人审**（agent-A 的勒索/钓鱼/Web 入侵，验证流程） |
| T+1 ~ T+2 天 | 剩余通用类 5 类抽取（agent-A 续 + agent-B 启动） | **第一批人审通过后**，批量审第二批 5 类通用 |
| T+2 ~ T+3 天 | 金融 3 类抽取（agent-C/D/E 并行） | **金融三类人审**（按优先级：监管通报 → 反诈 → 数据泄露） |
| T+3 ~ T+3.5 天 | 各自代码合入主分支 | **最终验收**：进度指标 / 追溯链 / 金融语料边界复核 |

**owner 人审是瓶颈**：5 agent 抽取并行可压缩 1~1.5 天工期，但 owner 人审吞吐决定收口时间。建议：

- 第一批 3 类（agent-A 的高优先级）端到端验证人审流程无误，再批量审后续
- 每类事件类型 owner 用时 ~30 分钟（5~8 条候选）
- 总 owner 人审预算：**11 类 × 30 分钟 ≈ 5.5 小时**，分 2~3 天完成

### 2.3 金融行业语料三阶（owner 决策 2026-09-13）

按"语料可得性 + 抽取质量"递进：

| 阶 | 类别 | 来源 | 语料可得性 | LLM 抽取难度 | 启动时点 |
|---|---|---|---|---|---|
| **第 1 批** | 监管通报 | 银保监 / 网信办 / 央行口径本身 | 高（结构化） | 低（口径明确） | T+2 天启动（agent-E） |
| **第 2 批** | 反诈 | 公安部公开宣传 + 银行业协会 | 中（语料相对松散） | 中 | T+2 天启动（agent-C） |
| **第 3 批** | 数据泄露 | 央行支付结算司 + 银行业协会 + 公开事件 | 低（语料最稀） | 高（描述常脱敏） | T+2.5 天启动（agent-D） |

**第 3 批数据泄露的特殊处理**：

- 抽取语料上限：3 类事件报告中**实际命中"客户 PII 流转"案例**的才入池
- 若 5+ 份报告抽取不到 ≥3 条有效候选，**触发降级方案**：
  - 备选语料：公开行业研究（Verizon DBIR 金融分册 / 普华永道金融安全报告）
  - 若仍不足，**接受该类 `event_technique_map` < 3 条审定**（在 MP-2 收口报告中如实标注，**不降级事件类型本身**）
- 不为追求数字拉低候选质量门槛（conf≥0.5 阈值不降）

---

## 3. 数据模型与代码侧

### 3.1 数据模型（迁移 `data/migrations/117_mp2_event_technique.sql`）

```sql
-- 1. event_type 实体（owner 直接播种，不走 LLM）
INSERT INTO security_entities (entity_type, entity_id, display_name_zh, display_name_en, definition, scope_note, industry, status, created_by, created_at)
VALUES
('event_type', 'evt_ransomware', '勒索软件', 'Ransomware', '...', '...', 'general', 'active', 'owner', strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('event_type', 'evt_phishing', '钓鱼社工', 'Phishing & Social Engineering', '...', '...', 'general', 'active', 'owner', strftime('%Y-%m-%dT%H:%M:%fZ','now')),
-- ... 共 11 行
;

-- 2. event_technique_candidates 候选池（LLM 抽取落库，owner 审）
CREATE TABLE event_technique_candidates (
    id TEXT PRIMARY KEY,                    -- ULID
    event_type_id TEXT NOT NULL,            -- 关联 security_entities.entity_id
    technique_id TEXT NOT NULL,             -- ATT&CK Txxxx
    stage TEXT NOT NULL,                    -- initial_access | execution | ...
    confidence REAL NOT NULL,               -- 0.0~1.0
    evidence_quote TEXT NOT NULL,           -- ≤120 字原文片段
    rationale TEXT,                         -- ≤80 字理由
    source_report_id TEXT NOT NULL,         -- 关联 incident_reports
    llm_model TEXT NOT NULL,                -- e.g. 'gpt-4o-2024-08-06'
    llm_run_at TEXT NOT NULL,
    owner_status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | edited | rejected
    owner_action_at TEXT,
    owner_action_by TEXT DEFAULT 'owner',
    reject_reason TEXT,
    auto_reject_reason TEXT,                -- 程序化校验失败原因
    UNIQUE (event_type_id, technique_id, stage, source_report_id)  -- 同源报告同位置只一条
);
CREATE INDEX idx_etc_event_type ON event_technique_candidates(event_type_id);
CREATE INDEX idx_etc_owner_status ON event_technique_candidates(owner_status);
CREATE INDEX idx_etc_technique ON event_technique_candidates(technique_id);

-- 3. event_technique_map 终态（owner 审定落库）
CREATE TABLE event_technique_map (
    id TEXT PRIMARY KEY,                    -- ULID
    event_type_id TEXT NOT NULL,
    technique_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    note TEXT,                              -- owner 可编辑
    candidate_id TEXT,                      -- 追溯链：来源 candidate
    source_report_id TEXT,                  -- 追溯链：来源报告
    approved_at TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT 'owner',
    owner_audit_chain TEXT,                 -- JSON：[{ts, action, by, prev_status, note}]
    UNIQUE (event_type_id, technique_id, stage)  -- 同 event_type 同 stage 同一 technique 只一条
);
CREATE INDEX idx_etm_event_type ON event_technique_map(event_type_id);
CREATE INDEX idx_etm_technique ON event_technique_map(technique_id);

-- 4. incident_reports 报告语料库
CREATE TABLE incident_reports (
    id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    event_class_hint TEXT,
    report_md TEXT NOT NULL,
    checksum TEXT NOT NULL,                 -- 报告原文 sha256
    UNIQUE (source_url)
);

-- 5. FK 约束（attack_techniques 必须在 M1 已落数据）
-- 通过 service 层 enforce（不引外键依赖，迁移解耦）
```

### 3.2 service 层

| 模块 | 文件 | 职责 |
|---|---|---|
| `IncidentReportService` | `backend/services/mp2/incident_report_service.py` | 报告语料管理：抓取 / 校验 / 去重 / 列表 |
| `EventTechniqueExtractService` | `backend/services/mp2/event_technique_extract_service.py` | LLM 抽取：候选生成 / 程序化校验（FK / evidence_quote substring / confidence）/ 落候选池 |
| `EventTechniqueReviewService` | `backend/services/mp2/event_technique_review_service.py` | owner 审核三态：approve / edit / reject + 批量便利 + 进度指标 |
| `AttackLabelService` | `backend/services/mp2/attack_label_service.py` | 多语义入口：`get_for_event_type(event_type_id) → [technique_chains]` + MP-4 用的 `list_knowledge_for_techniques(technique_ids)` 留 stub |

### 3.3 repo 层

| 模块 | 文件 | 职责 |
|---|---|---|
| `EventTechniqueCandidateRepo` | `backend/repository/event_technique_candidate_repo.py` | 候选池 CRUD（含按 status 过滤） |
| `EventTechniqueMapRepo` | `backend/repository/event_technique_map_repo.py` | 终态 CRUD |
| `IncidentReportRepo` | `backend/repository/incident_report_repo.py` | 报告 CRUD + checksum 去重 |
| `SecurityEntityRepo`（扩展） | `backend/repository/security_entity_repo.py` | event_type 实体的 list/get（已有则扩展，无则新建） |

### 3.4 API 层（薄）

- `GET /api/mp2/event-types` — 11 类清单
- `GET /api/mp2/event-types/{id}/technique-chain` — 技战法链（渲染用，按 stage 排序）
- `POST /api/mp2/admin/event-technique-review/{candidate_id}` — owner 审核三态（仅 owner token）
- `GET /api/mp2/admin/event-technique-review/queue` — owner 待审队列（按 event_type 分组）
- `GET /api/mp2/admin/event-technique-review/progress` — 进度指标
- `POST /api/mp2/admin/event-technique-review/batch-approve` — 批量便利

**审计要求**：所有 admin 端点写 audit_log（actor=owner / target_type=candidate / action=approve|edit|reject|batch_approve）

### 3.5 前端

- `frontend/src/components/mp2/EventTypeCard.tsx` — 技战法卡（按 stage 时间线展示）
- `frontend/src/components/mp2/EventTypeReviewPage.tsx` — owner 人审 UI（按 event_type 分组，按 stage 排序，三态按钮 + 批量便利 + 进度条）
- `frontend/src/hooks/mp2/useEventTypeTechniqueChain.ts` — 拉取 + 缓存（5min TTL，与 SSE 失效对接）
- 路由注册：`/admin/event-technique-review`（admin 入口，与现有 `/admin/*` 同款权限）
- **不做**：事件类型管理页（owner 直接种子进库，不开放 CRUD）；候选编辑页（owner 编辑通过 service API 在 UI 内联完成）

### 3.6 守卫测试

| 守卫 | 内容 |
|---|---|
| `test_mp2_fk_guard` | candidate.technique_id 必须存在于 attack_techniques 表 |
| `test_mp2_evidence_quote_guard` | candidate.evidence_quote 必须在 source_report.report_md 中 substring 命中 |
| `test_mp2_confidence_threshold_guard` | confidence<0.5 不入候选池（service 层 enforce + 守卫反向断言） |
| `test_mp2_owner_only_guard` | admin review API 必须 owner_token（无 token 403） |
| `test_mp2_audit_log_guard` | 三态审核 + 批量便利必须落 audit_log |

---

## 4. 端到端流程（每个 agent 跑一遍）

```
Step 1 词表播种（owner 一次性提供 11 类 JSON, 主会话灌库）

Step 2 报告语料入库（5 agent 并行, 每个 agent 负责自己类）
  2.1 从来源策略清单中按类挑选 5+ 公开报告
  2.2 抓取原文 + 落 incident_reports（含 checksum 去重）
  2.3 自检：每类至少 3 份报告有完整 report_md

Step 3 LLM 抽取（5 agent 并行）
  3.1 拼 prompt：报告原文 + ATT&CK technique 字典（M1 已落）
  3.2 LLM 输出结构化候选
  3.3 程序化校验：FK 存在 + evidence_quote substring 命中 + confidence≥0.5
  3.4 校验通过落 event_technique_candidates (pending)；失败落 auto_reject_reason

Step 4 自审脚本（每个 agent 跑）
  4.1 每类生成"候选质量报告"：覆盖率（覆盖 ATT&CK tactic 几个）/ 置信度分布 / evidence_quote 通过率
  4.2 低覆盖率类（<5 个 tactic 覆盖）触发补抽

Step 5 owner 人审（主会话, owner 在前端 UI）
  5.1 打开 /admin/event-technique-review
  5.2 按 event_type 分组浏览候选
  5.3 三态审核：approve / edit / reject
  5.4 通过的 candidate 落 event_technique_map（含 candidate_id / source_report_id 追溯链）
  5.5 第一批 3 类（勒索/钓鱼/Web 入侵）端到端验证流程无误后，owner 批量审后续

Step 6 数据合入（主会话）
  6.1 5 个 worktree 各自产出 commit
  6.2 主 worktree 按顺序 merge：A → B → C → D → E（每个 merge 后跑 pytest 全量 + meta --check）
  6.3 不 push 远端（owner 禁令维持）
```

---

## 5. 验收与边界

### 5.1 验收门（MP-2 收口条件）

| 维度 | 条件 |
|---|---|
| **数据完整性** | 11 类全覆盖；每类 ≥3 条已审定 `event_technique_map` 行（第 3 批数据泄露如实标注） |
| **抽审追溯** | 每条 `event_technique_map` 可回溯到 candidate → candidate 可回溯到 report → report 可回溯到 source_url |
| **API 可用** | `GET /api/mp2/event-types/{id}/technique-chain` 返回结构化链；admin review 5 端点全部通 |
| **前端可交互** | `/admin/event-technique-review` 路由可访问；技战法卡组件渲染 11 类事件类型 |
| **守卫全绿** | 6 个新守卫测试全部通过 |
| **测试** | pytest 基线 4600 + MP-2 新增 ≥50 用例（11 类×3-5 候选场景） = ≥4650 / 0 fail |
| **meta --check** | 数字同步：services +5（mp2 域 5 服务）+ routers +1（mp2 域 6 端点）+ migrations +1（117）|
| **P0=0 / P1≤2** | code-reviewer 独立审计（与实现分离） |

### 5.2 边界（不变项）

- **不动**：v0.8.5 三层壳 / 导航 / 视觉 token；ai_hub 调用链与包结构；CRM 删除决策；R1~R4 守卫
- **不复用**：现有 security/* 域（本次新建 mp2 子域，避免污染主域；MP-4 时再决定是否合并）
- **不实现**：事件类型管理 CRUD（owner 直接种子）/ LLM 抽取侧的配置管理（临时 prompt 即可，MP-3 再固化）/ 候选编辑的版本控制（仅 owner 一次审核，不支持反复回退）
- **金融行业边界**：仅取**脱敏后的公开通报**（监管通报本身公开、反诈案例库来自公安部公开宣传），**不接 owner 客户内部数据**（反复强调，audit_log 必落 actor=owner 标识外部分类）

### 5.3 风险与降级

| 风险 | 触发条件 | 降级方案 |
|---|---|---|
| LLM 抽取质量不达标（confidence<0.5 占比 >50%） | 任一类 | ① 切换更便宜的 LLM 重抽 ② 增加同源报告数量 ③ owner 给定 `owner_initial_techniques_hint` 引导 |
| owner 人审吞吐瓶颈 | owner 工作繁忙 | ① 启用批量便利（按 tactic 分组批） ② 延长工期至 5 天 ③ owner 委派代理（agent 接受 owner 授权 token） |
| 金融三类语料稀 | 数据泄露 < 5 份有效报告 | 见 §2.3 第 3 批降级方案（备选语料 + 接受不足 3 条审定） |
| 5 agent 并行冲突 | 子 worktree 合并时冲突 | ① 不同 agent 写不同 event_type 物理隔离（UNIQUE constraint 兜底） ② 共享文件改动序列化（attack_label_service / 迁移文件） |
| 程序化校验误报 | evidence_quote substring 漏掉 unicode 边界 | 改用 fuzz substring（normalized form C）+ 自定义白名单符号 |

---

## 6. 同步事项

- `docs/FEATURE_DECOMPOSITION_2026-09-12.md` §5 裁决区追加 "MP-2 方案立项" 记录
- `PROGRESS.md` 活跃段加 MP-2 待开工状态
- DEV_LOG.md 追加 DEV-0215: MP-2 方案落账
- MP-1 与 MP-2 抽取语料可并行启动（候选池写库需 M1 已落 attack_techniques，词表播种需 M1 完成 event_type 实体表结构）
- 与 MP-4 负责人协调 attack_label_service 多语义入口预留（list_knowledge_for_techniques stub）

---

## 7. 后续期衔接

- **MP-3（L1 漏洞实例化）**：依赖 P1-5 NVD 接入；event_technique_map 不动（L2 专用），MP-3 走 attack_cwe_map 关联查询
- **MP-4（L3 应急响应 + 双向关联）**：复用本方案的 `event_technique_map` 与 attack_label_service，新增 `knowledge_technique_ref` 表 + `v1_judgments.attack_technique_refs` 列
- **MP-2 收口报告**：落 `.ua/tmp/mp2-event-type-code-audit-report.md`（沿用 batch 报告惯例）