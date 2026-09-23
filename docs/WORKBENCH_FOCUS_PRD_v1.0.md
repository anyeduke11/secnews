# 已废止

> 本文档已被单一权威 PRD 取代: [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md) (DEV-0179 收敛纪律)。以下内容仅作历史参考, 路由/接口一致性以 [`v0.8.5/V0.8.5_PLAN.md`](v0.8.5/V0.8.5_PLAN.md) 为唯一权威 spec。

# 安全从业者 AI 工作台聚焦方案（Workbench Focus PRD v1.0）

- 日期：2026-09-12；状态：**已裁决立项**（开发目标与任务分解见 [`WORKBENCH_FOCUS_DEV_PLAN.md`](WORKBENCH_FOCUS_DEV_PLAN.md)）
- 上游裁决：2026-09-12 owner 两连裁决——①「安全研究/标讯跟踪双视角切换」方案**否决不开发**；②工作台**专注安全从业者**单动线。
- 本文职责：定义"内容相关性门禁 + 实践域兴趣体系"的产品口径、分期范围与验收标准。路由/接口一致性仍以 [`v0.8.5/V0.8.5_PLAN.md`](v0.8.5/V0.8.5_PLAN.md) 为唯一权威 spec；本文与其冲突时以 spec 为准。

---

## 0. 背景与裁决记录

知识复利评估（2026-09-11 全仓知识图谱分析 + 对话评审）结论：资讯→决策→执行的复利**机制**已闭环（SK-04 复盘→知识、SK-05 复用收据 `/api/v1/knowledge/{id}/reuse`、SK-06 每日复查 job、`/api/kl/compounding` 指标），但**复利未滚动**——缺真实日活流量，且资讯消费缺内容相关性分层。本 PRD 只解决其中"内容相关性"一环：让每天流过工作台的资讯按安全从业者的实践方向分层，把"信息太多"变成**排序问题**，把"怕漏"交给既有 catchup / 质量门禁兜底。

裁决记录（防回摆，含被否决方案）：

| # | 裁决 | 内容 | 理由 |
|---|------|------|------|
| R1 | **否决** | 安全研究/标讯跟踪双视角切换（前端视角轴 + 后端双业务流 + 双画像） | 标讯是低频业务机会线，不是日活动线；为此加视角轴、双判断服务、双画像的常驻复杂度不划算 |
| R2' | **剔除（2026-09-12 追加裁决，取代初版 R2"维持现状"）** | 标讯功能从工作台剔除：`/bid-alert` 路由 + BidAlertPage 组件 + 壳菜单入口 + Feed bid 分类档 + 分类展示枚举全部移除；资讯流默认 `exclude_category=bid`。后端 `/api/bid-alert/*` 与 bid 采集器**暂保留**（数据层不动，是否停采另裁决） | owner 追加裁决"剔除和安全从业者 AI 工作台中标讯相关的功能"——低频业务线不应占据日活动线注意力 |
| R3 | **聚焦立项** | 本 PRD：安全从业者 AI 工作台的内容相关性门禁/实践域兴趣体系 | 直接服务日活动线与知识复利，是复利评估指出的 P0 缺口 |

## 1. 问题定义

质量门禁（`backend/quality/pipeline.py` 12 道）回答的是"这条信息是不是**好的**"（去重/时效/URL/作者核验），不回答"**对你**是否有用"。现状的相关性能力只有两个粒度，且都不在"实践域"层级：

| 粒度 | 载体 | 局限 |
|------|------|------|
| 源级 | `Category` 8 大领域（`backend/domain/enums.py`：ai/ai_security/security/finance/startup/bid/github/tech），采集时定死 | 粒度过粗：`security` 一个桶装不下"漏洞研究"和"等保合规"的区别 |
| 关键词级 | info_filter Layer 2 deny/allow（通用词表 + InfoFilterCard 前端） | 天生适合管**噪音**（硬规则），不适合表达**兴趣**（软偏好） |

缺的中间层 = **实践域词表 + 兴趣画像 + 打分接线**。`backend/services/auto_classifier.py` 已有三级规则打标（`TAG_DOMAIN_MAP` 标签映射 → `TITLE_DOMAIN_RULES` 标题关键词 → `URL_DOMAIN_MAP` 来源 URL），并在采集/知识链路消费（直接消费：`backend/scheduler/jobs/collect.py`、`backend/scheduler/jobs/knowledge.py`、`backend/api/knowledge.py`、`backend/compiler.py`；`backend/scheduler/jobs/digest.py` 经 compiler 间接）——只差把领域词表细化到实践域、把打标结果接到兴趣排序上。

## 2. 产品口径

1. **两道门禁正交**：噪音门禁（info_filter，硬规则，deny/allow）× 相关性门禁（本 PRD，软偏好，打分加权）。互不替代、互不耦合。
2. **降权不删**：兴趣未命中的条目降权进库不推送；搜索、catchup、补采永远可达。防漏兜底（catchup 断点补采 / recency 门禁 archive 放行 / admission_log 拒绝样本可回溯审计）维持不变；"每周例行拒绝样本人工审计"为本方案 P1 新建机制，非既有能力。
3. **主动线**：每日优先级摘要（SK-01，按兴趣域分区）+ digest job 待复习推送（复利驱动器②，每日 08:00 SSE review_due）。Feed 降级为档案抽查入口。
4. **单一画像**：本 PRD 只做单用户兴趣画像（settings.kv 一份），不做多画像/多视角/时段自动切换。
5. **画像可解释**：每条摘要/排序结果可回溯"因为命中了哪个实践域/哪个关键词"，不让用户对黑盒排序。

## 3. 分期范围

### P0 —— 实践域词表 + 兴趣选择器 + Feed 接线（本期）

| # | 交付 | 说明 |
|---|------|------|
| P0.1 | 实践域词表 | `auto_classifier` 新增二级实践域：企业安全建设 / 漏洞研究 / 威胁狩猎 / 应急响应 / AI 安全 / 应用安全 / 云与数据安全 / 合规监管（8 域起步，词表数据驱动可运营）；新增 `classify_practice_domain()`，`classify_item`/`batch_classify` 透出，**不改 `Category` 枚举** |
| P0.2 | 实践域评测语料 | **口径修正（审计 P1-2，待 owner 追认）**：新增 20 条带真值域的评测条目（入仓 fixture，纯合成标题），与词表同源——作用是**回归护栏**（词表改动后 --check 必须 100%），不是无偏准确率评估；无偏人评属 P1 运营机制。原"标注集 60→80"按 60 条本地 admission 标注（不入仓）+ 20 条评测语料 = 总量 80 记账，**关闭 v1.0 T00 悬置裁决"标注集 60-80"** |
| P0.3 | 兴趣画像 | settings.kv `interest.practice_domains`（数组）+ `GET/PATCH /api/settings/interests`（沿用 llm provider 的 kv + audit_log 先例）；前端 Settings 新增"我的方向"多选卡 |
| P0.4 | Feed 接线 | 资讯流查询时即时打标（纯函数，零 schema 变更）；兴趣命中 → 页内加权置顶；未命中 → 降权不删；每条回传 `practice_domain` + 顶层 `interest_domains` 供徽标展示 |
| P0.5 | SK-01 摘要分区 | **范围修正（审计 P1-3，待 owner 追认）**：后端聚合分区已交付（top_items 附加 practice_domain + practice_partitions 分组 + interest_domains 回显）；**前端分区渲染顺延 P1**——SK-01 在 v0.8.5 壳无活的前端消费面（无 API 端点），"优先级摘要卡上首页"本就是 P1 动线任务，届时一并接线 |

### P1 —— 标签统一 + 动线强化

- v0 feed 与 v1 admission 的标签词表统一为一套实践域词表（v1 侧 8 维 label 启发式扩实践域维度），杜绝两套词表漂移；
- 每日优先级摘要成为首页默认动线（SentinelHomePage 资料层第一区块）；
- 词表运营机制：每周 admission_log 拒绝样本审计 → 词表 PR（人工在环，规则先行不上模型）。

### P2 —— 行为反馈闭环

- 点击 / deep_read / 收藏行为微调兴趣域权重（attention 5 维评分为基础）；
- 兴趣画像漂移检测（提示"你最近看的和勾选的不一致"）；
- 语义/向量检索**另立方案**，不在本 goal 内。

## 4. 非目标（明确排除）

- 标讯视角、双视角切换、时段自动切换（R1/R2 裁决）；
- v1 九领域对象契约变更（contracts.md 不动，本 PRD 全部能力走 v0 层）；
- 向量/语义检索、LLM 内容分类（规则词表先行，效果不足再立项）；
- info_filter 引擎与 gate 语义变更（兴趣过滤在 feed 排序层实现，不动 `feature_gates.toml` 13 个 gate）。

## 5. 红线与约束

- `ai_hub` 调用链（`gateway._try_order` / `service._resolve_provider`）**不动**——本 PRD 全程无 LLM 新调用；
- **零新路由**：不新增一级入口；Settings/Feed 均为既有页内区块（v0.8.5 spec §5 硬规则）；
- `backend/services/` 新增代码遵守依赖方向（禁 `import backend.api`）与 `generate_meta.py` 数字同步门；
- i18n 双语（zh-CN/en-US）随 UI 同步交付。

## 6. 验收标准（DoD 摘要，细则见 DEV_PLAN）

1. `npx tsc --noEmit` 0 错、`npx vitest run` 全绿（新增选择器/接线测试）、`pytest backend/tests/` 0 回归（classifier/词表/端点新测试全绿）；
2. `python scripts/generate_meta.py --check` 通过（services/routers 数字与 ARCHITECTURE.md 一致）；
3. 兴趣未勾选时 Feed 行为与现状一致（**口径修正（审计 P1-2）**：响应结构一致——除新增增量字段 `practice_domain`/`interest_domains` 外，且无画像时排序与旧版相同；"逐字节一致"表述废弃）；
4. 每条摘要可解释命中域；
5. **实现与验证分离**：收尾由独立 agent 做功能验收 + 代码审计（`code-reviewer`），实现会话不得自评 PASS；审计发现 P0 级问题必须修复后复验。
