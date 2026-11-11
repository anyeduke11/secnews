# PRD 对齐审计 — v0.8.8 P1 裁决表

> **依据**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`](../v0.8.8/V0.8.8_REFACTOR_PRD.md) §8.1「P1 裁决」行
> **日期**: 2026-11-11 ｜ **阶段**: P1（裁决）｜ **执行树**: `8bb960b` + 未提交工作区（R-13/R-15 已落地，DEV-0332/0333/0334）
> **性质**: **只裁决，不删除**。本文不含任何代码或 spec 变更。
> **退出条件**: **用户逐项批准**（PRD §8.1 明文：未批准不得进 P3）
> **证据源**: `P0_R06_SERVICE_ORPHANS_2026-11-10.md` / `P0_R07_JOB_INVENTORY_2026-11-10.md` / `P0_R08_COLLECTOR_INVENTORY_2026-11-10.md` / `P0_R09_FRONTEND_API_MAP_2026-11-10.md` / `P0_BASELINE_METRICS_2026-11-10.md` + 本轮只读复核（SQL 实查 + 代码逐行核验）

---

## 0. 口径定义与总览

### 0.1 四类口径（本文首次定义 — PRD §8.1 只列名未释义）

| 类 | 定义（判定问句） | 处置方向 |
|---|---|---|
| **闭环必需** | 删掉后「资讯 → Signal → Case → Claim → Run → Artifact → Knowledge」主链**断链**，或产出**无任何消费面** | 保留。仅允许修复缺陷，不允许退役 |
| **加速** | 不断链，但直接提升闭环的**速度 / 命中率 / 质量**（质量门禁、去重、源信誉、URL 校验、采集节奏、语义过滤） | 保留并优化。可下线其中的**无效实现**（≠ 下线能力） |
| **支撑** | 服务闭环但**不产出业务价值**：观测、诊断、运维、缓存、导出、迁移、配置、同步 | 保留，标注「非闭环必需」。仅在「确认无消费方」时按 B 档下线 |
| **孤立** | **无消费方**：孤儿 service / 死源 collector / 死封装 / 死组件 / 零调用端点 | A 档物理删除 / B 档 410 / C 档保留被消费方 |

### 0.2 计数总览

| 类 | 项数 | 其中建议删除 | 其中建议保留 |
|---|---:|---:|---:|
| 闭环必需 | 37（job）+ 主链 collector 子集 | 0 | 全部 |
| 加速 | 14 质量门禁 + 8 采集层议题 | 0（下线无效实现另计） | 全部 |
| 支撑 | 3 legacy 迁移 + 1 观测端点 + 67 端点中的运维子集 | 0（本轮） | 全部 |
| 孤立 | **4 service + 3 router + 4 死源 + 24 死封装 + 13 孤儿组件 + 67 零调用端点** | 见 §1 逐项 | — |

> **计数口径提醒**：PRD §2.2 写 router=101，当前树实测 **100**（R-13 已删 `todos` router）。本文一律用 **100**，并在 §5.4 提出 M-2 回写。

### 0.3 裁决档位与执行要求（沿用 PRD §3.3.1 / §6.1）

| 档 | 适用 | 执行要求 |
|---|---|---|
| **A 确证孤儿** | 全仓 0 生产 import / 0 生产调用 | 允许物理删除，**一项一 commit** |
| **B 疑似孤儿** | 有弱证据但无法排除反射/运维手工调用 | 响应体加 `410 Gone` + `deprecated_since` / `replacement` / `sunset_date`，观察一版 |
| **C 重复能力** | 能力重叠但仍有消费方 | 保留被消费方，删除副本 |

---

## 1. 孤立类逐项裁决

### 1.1 R-01 退役 `trends` 路由

| 项 | 内容 |
|---|---|
| **裁决** | **A 档 · 整链删除**（router + `trend_service.py`） |
| **证据（复核后强化）** | ① `backend/api/trends.py` 全仓唯一 import 方是 `_registry_core.py` 注册行；② `frontend/src` 对 `trend` 的命中**仅为类型残留** `TrendPoint`(`types/index.ts:68`) / `TrendResponse`(`types/index.ts:99`) 与被注释代码，**无任何活动调用点**；③ `scheduler.py:150-151` 明示独立 job `trend_rebuild` 已在 v1.8 R3 收敛进 collect_all，**无 job 调用**；④ `backend/repository/trend_repo.py:129` 的 `/api/trends` 命中**只是 docstring 文本**，不构成消费 |
| **推翻项** | P0_R09 主表行 1044 判「🟢 勿动（有内部消费）」**证据不成立** —— 该"内部消费"是注释，不是调用。R-01 结论恢复有效 |
| **附带发现（需单独批准）** | `collection_service.py:121` 注入 `TrendRepository`、`:187` 在 `collect_all` post-ingest 链调用 `rebuild_trend_and_log` 写 `trend_snapshots`。删 `trend_service` 后，若 `trend_snapshots` 无其他读取方，该写入即**纯浪费计算**（每轮采集都付）。**P1 未完成对 `trend_snapshots` 读取面的穷举**，故不并入 R-01，单列为 P1-01b |
| **前端残留** | `TrendPoint` / `TrendResponse` 类型随 R-01 同 commit 删除（无引用） |
| **回滚** | 单 commit revert |

### 1.2 R-02 退役 `categories` 路由

| 项 | 内容 |
|---|---|
| **裁决** | **A 档 · 仅删 router 文件 + 注册行**；`hotspot_repo.count_by_category` 与 `hotspot_service` 相关方法**保留** |
| **证据** | ① 前端分类元数据用本地常量 `CATEGORIES`(`types/index.ts:248`)；② 分类计数走 `/api/hotspots` 的 `category_counts`；③ P0_R09 主表 #34 判「仅测试」→ 无前端调用；④ `count_by_category` 另有 `hotspot_service` / `health_query_service` 消费者（PRD 已声明） |
| **前置校验（P3 执行时）** | `grep` 确认 `backend/api/mcp_*.py` 无 `/api/categories` 暴露（PRD §4.2 技术约束） |
| **保留断言（验收）** | 删后 `GET /api/hotspots` 的 `category_counts` 6 分类齐全 + `test_count_by_category` 全绿 + `CATEGORIES` 常量零改动 |
| **回滚** | 单 commit revert |

### 1.3 R-03 退役 `weekly_report` 路由 —— **裁决与 PRD 原文冲突，建议修订**

| 项 | 内容 |
|---|---|
| **PRD 原文** | 删 router，**保留** `weekly_report_service.py` 与 `digest.py` 调度链（§4.3 需求 / 验收②「digest job 仍正常执行，日志可见 `take_daily_snapshot` 计数」） |
| **P0_R07 §6 #1 提出的冲突** | R-03 保留 job 41，则 job 42 的唯一消费链仍在，`weekly_reports` 表不能因「无前端调用」判死 |
| **本轮实证** | ① 写入链：job 41 `daily_snapshot_job` → `WeeklyReportService.take_daily_snapshot` → `trend_daily_snapshots`（warm DB，175 行）；job 42 `weekly_report_job` → `generate_report` → `weekly_reports`（warm DB **仅 3 行**，最新 `week_start=2026-11-02`，本周 2026-11-09 **未生成**）；② **唯一读取面 = `backend/api/weekly_report.py` 的 5 个端点**，前端 0 调用（P0_R09 #…「零调用」）；③ 删掉该 router 后，两张表变成**只写不读**，job 41/42 每轮仍付出 SQL 与计算成本 |
| **推荐裁决** | **修订 R-03 为「整链下线」**：`api/weekly_report.py` + `weekly_report_service.py` + `digest.py::daily_snapshot_job`/`weekly_report_job` + scheduler 注册行 + `trend_daily_snapshots` / `weekly_reports` 两表（表可延后一版再 DROP，先停写） |
| **为何不能只删 router** | PRD 的「保留 service」前提是「service 另有消费方」。实测 service 的**唯一出口就是被删的 router**，唯一入口是 job 41/42 —— 删 router 后 service 成为「job 写给自己看」的死循环，属 §3.3.1 的 **C 档（重复/空转能力）**，不是「保留」 |
| **保留风险（需用户确认）** | `trend_daily_snapshots` 是否被 `/api/reports/monthly/overview` 或 `weekly_report_overview_service` 读取？**待证**（P1-03b）。若有读，则降级为「删 router + 保留 job 41」 |
| **回滚** | 两项一 commit（router+service / job+调度），可分别 revert |

### 1.4 R-06 服务层孤儿（161 → 4 项确证）

R-06 判定：孤儿 **1**（0.6%）/ 单消费者 22 / 多消费者 101 / UNKNOWN 37。阈值「孤儿 ≤ 5」通过。本轮对 4 个**仅测试消费**项逐个复核（`user_skills` 表实查 = **0 行**，故 `skill_builder/validate.py` 的动态导入面为空，R-06 局限 #2 解除）：

| # | service | 行数 | 生产 import | 复核结论 | 档位 |
|---|---|---:|---|---|---|
| S-1 | `backend/services/crawler_seed.py` | 194 | 0（仅自身 docstring + docs 文本） | 现役种子脚本是 `backend/scripts/seed_crawler_sources.py`，本文件是被取代的旧实现 | **A** |
| S-2 | `backend/services/cost_monitor.py` | — | 0 | 能力已被 `ai_hub/usage.py` 吸收（自身即委托 ai_hub 记账） | **A** |
| S-3 | `backend/services/feedback_analyzer.py` | — | 0 | `user_memory_service.py:26` / `user_memory_repo.py:26` 仅把字符串 `"feedback_analyzer"` 当 `source` **字段默认值**，非 import | **A** |
| S-4 | `backend/services/codegarden_scanner_service.py` | 619 | 0 | gate 开启的 job 33 `cg_service_scan` 用的是 `codegarden_service_service.scan_local_services`，后者内部**不 import** 本文件 → 排除「gate 表象」误判 | **A** |

**共同前置**：4 项均有仅测试引用。A 档物理删除 = **service + 其专属测试同 commit 删除**。若任一项的用户认为测试承载了「意图契约」需保留，则该项降级 **C**（保留）—— 请在批准表中逐项勾选。

### 1.5 R-09 前端层 —— **含 3 处假阳性纠正**

#### 1.5.1 假阳性纠正（必须回写 R-09 报告）

| # | R-09 原判 | 实测 | 证据 | 结论 |
|---|---|---|---|---|
| F-1 | `GET /api/reports/monthly/available` 零调用 | **有消费** | `MonthlyReport.tsx:15` 字面常量 + `/report` 页面可达（`SentinelShell.tsx` action 菜单 chip「报告 /report」） | **不可删** |
| F-2 | `GET /api/reports/weekly/available` 零调用 | **有消费** | `WeeklyReport.tsx:15` 同上 | **不可删** |
| F-3 | `GET /api/trends` 🟢 勿动（有内部消费） | **零调用** | `trend_repo.py:129` 仅 docstring | **可删**（并入 R-01） |

**根因**：R-09 的路径 B 只扫 `frontend/src/api/*.ts` 封装层，对组件内 `getJSON('/api/...')` 的**字面量直调存在漏检**。修复建议：R-09 报告补一段「组件内直调补充扫描」，或在报告头部加更正注，明确此 3 项以本文为准。

#### 1.5.2 死封装 / 孤儿组件（P0_R09 §7）

| 项 | 数量 | 说明 | 建议 |
|---|---:|---|---|
| §7.1 死封装 | 24 | `frontend/src/api/*.ts` 有导出函数，组件无调用 | 不属 P3 授权范围（§8.1 P3 仅 R-01~R-05）。建议新增 **R-16** 并在 P4.5 前端重构时随 R-15 一并清理 |
| §7.2 孤儿组件 | 13 | 其中 `editorial` 8 个为整组未挂载 | 同上，随 R-15 清理；**删前须跑 `npx tsc --noEmit` + `vitest run`**，防止动态 import 漏检 |

#### 1.5.3 §6.1「四项全未命中」67 端点

| 模块组 | 端点数 | 建议 |
|---|---:|---|
| `codegarden`（projects 全套 / lifecycle / archive / restore / sync / timeline / upstream） | 12 | **不动**。gate=codegarden 关闭时整族 404；开启时高频脚本可能消费，需 P2 消融 |
| `codegarden_ops`（dependencies / playbooks run / resources / services logs·metrics·restart） | 6 | 同上 |
| `knowledge_obsidian` / `knowledge_plans` / `knowledge_skills` / `knowledge_classify_api` / `kl_pipeline_api` 等 | 14 | **不动**。知识域手工/批处理入口，风险高于收益 |
| `reports`（daily / monthly / daily·monthly overview 之外的 4 项） | 4 | **仅确认 available 两项有消费**（F-1/F-2）；其余 2 项（`/api/reports/daily`、`/api/reports/monthly`）**待 P2 消融** |
| `skill_builder_api` / `tech_stack` / `security` / `cache` / `maintenance` / `observability` / `run_ledger` / `alerts` / `reviews` / `export` / `digests` / `content` 等 | 31 | **不动**。多为运维/调试/内部链路入口，符合 §6.1「运维手工端点保留并标注 docstring」 |

> **明确立场**：P3 **只**执行 R-01/R-02/R-03/R-05 的删除。67 端点中的其余项**不得**在 P3 顺手删除 —— ① R-09 自身定位是盘点（§4.9 回滚「纯盘点，无代码变更」）；② 每个删除候选须先过 §7.4 消融矩阵「关掉后零失败 + 零观测变化」。

---

## 2. 加速类（保留 + 优化，不退役）

| # | 项 | 证据 | 裁决 |
|---|---|---|---|
| A-1 | 14 质量门禁 | `backend/quality/*_gate.py`；P0_R08 显示 Startup 39 条被 `semantic_reject` 隐藏、GitHub 19 条全 `mismatch` | **保留**。门禁是 Feed 质量的唯一闸口 |
| A-2 | `AuthorVerificationGate` source 归一缺陷 | `GitHubCollector` 19/19 `mismatch` → Feed 产出 **0**；`SemanticScholar` 30/30 `unreachable` → Feed 0 | **修复**（非退役）。属加速类缺陷，P4 处理或单列需求 |
| A-3 | 同 category 重复抓取 | `base.py:375-441` 按 category 装载 registry 源；7 日重复 145 条；仅 `paper_sources.py:98-111` 有 per-collector 隔离 | **修复**。方案 A（隔离逻辑上提 `BaseCollector`，影响 19 collector，须同步 `source_coverage` 基线）优于方案 B（装配层传 `only_source`，覆盖不到单源路径） |
| A-4 | `source_coverage` 基线 | R-08 验收③ | **保留 + 随任何 collector 变更同步** |
| A-5 | 采集节奏 / post-ingest 链 | `collection_service.py` collect_all 尾部 | **保留** |
| A-6 | 语义过滤 / 兴趣引擎 | gate 默认开（`semantic_filter` / `interest_engine`） | **保留** |
| A-7 | `paper` 类 4 collector（7 日 169 条） | 首页 Feed **无 `paper` 频道** → 产出不进主链 | **待选** C1（推荐：`/knowledge` 独立区块，零后端改动，`types/index.ts:248` 已有 paper 标签）/ C2（首页加频道）/ C3（维持） |
| A-8 | `AISecurityCollector` 0 产出 | 7 日 0 / 30 日 1；6 个类常量源中 4 个失效 | **不下线**。建议把可用源登记进 `crawler_sources` 的 `ai_security` 分类 |

---

## 3. 支撑类（保留，标注「非闭环必需」）

| # | 项 | 证据 | 裁决 |
|---|---|---|---|
| U-1 | R-04 `GET /api/observability/audit` | **PRD 前提有误**：`observability_records` 表**根本不存在**。该端点实际读 `audit_log`（9,348 行），近 30 天 **6,906 行活跃写入**：`llm_breaker.transition` 6,738（最新 2026-11-10T16:31Z）/ `dsh.adapter.exit_criteria_triggered` 132 / `v1_evidence.entity_insert_failed` 16 | **按 R-04 (a) 保留**，作为诊断入口。须回写 PRD §4.4 表名事实 |
| U-2 | R-05 `legacy_migrate_api` | 前端 0 引用；迁移类端点可能被 `docs/RUNBOOK.md` 手工调用 | **保留**，docstring 标注「运维手工入口，勿删」（PRD 验收③已要求）。若 RUNBOOK 确认无引用 → 可降 B 档 |
| U-3 | R-05 `legacy_items_migrate_api` | 同上 | 同上 |
| U-4 | R-05 `legacy_migrate_v1_api` | 同上；实查 `v1_legacy_mapping` / `v1_legacy_promote_log` **均 0 行** | **待定**：表空 → 有可能已停用。建议 RUNBOOK 核验后再定 A/B |
| U-5 | 观测 / 指标 / 缓存 / 维护 / 导出端点 | P0_R09 判「零调用」或「仅文档」 | **保留**。符合 §6.1 运维端点条款；不占 P3 授权 |
| U-6 | `/api/reports/*`（daily / monthly / weekly 的 overview 与 available） | `SentinelShell.tsx` action 菜单「报告 /report」可达；`ReportPage` 组合三组件 | **保留**。闭环的「产出可读」节点，但归支撑而非闭环必需 |

---

## 4. 闭环必需（引用 P0 结论，不重复展开）

| 来源 | 结论 | 本文处置 |
|---|---|---|
| P0_R07 §5 | 闭环必需 **是 37 / 否 18 / 待裁 4**（#11, 14, 24, 56） | 37 项全部保留；4 项待裁见 P1-15 |
| P0_R08 §3 主表 | `AICollector` 273 条（7 日 87.5%）、`Arxiv` 156、`Reddit` 71、`SecurityCollector` 70、`Startup` 49 等为主链供料 | 保留 |
| P0_R08 §6.2 | 死源候选 4：`HFDailyPapersCollector`（registry `enabled=0` / `status='retired'`）、`HNCollector`（主库 `hn%` **0 行**）、`OSSInsightCollector`（末条 2026-09-07）、`TelegramCollector`（末条 2026-09-25） | 见 P1-12 |

> **说明**：本文不复述 37 项 job 与 19 collector 全表 —— 明细在 `P0_R07` §3-§5 与 `P0_R08` §3，作为本文附件的证据表可直接引用。

---

## 5. 显式冲突与 spec 修订提议（**须用户裁决**）

### 5.1 冲突 C-A：R-03 与 job 41/42

- **冲突**：PRD 要求「删 router、保留 job 41/42」；实证表明 router 是该链**唯一读取面**，保留 job 即保留空转。
- **提议**：修订 R-03 为整链下线（详见 §1.3），同步改 §4.3 需求与验收②、§5.2 M-8 口径。
- **未决子项**：`trend_daily_snapshots` 是否有第三方读取方（P1-03b，需 grep `trend_daily_snapshots` 全仓）。

### 5.2 冲突 C-B：R-04 前提失效

- **冲突**：PRD §4.4 指定「先查 `observability_records` 表」，该表不存在。
- **提议**：把 §4.4 技术约束改为「查 `audit_log` 近 30 天写入」，结论 (a) 保留。**M-2 少 1 个名额**。

### 5.3 冲突 C-C：R-09 假阳性

- **冲突**：67 个「零调用」中至少 2 个（reports available）被组件内字面量直调；1 个（trends）被误判为「有内部消费」。
- **提议**：R-09 报告加更正注 + 扫描口径补「组件内直调」；删除决策以本文 §1.5.1 为准。

### 5.4 冲突 C-D：M-2 目标 ≤96 不可达

| 口径 | 计算 | 结果 |
|---|---|---|
| PRD 原式 | 101 − R-01 − R-02 − R-03 − R-13 = 96 | **前提失效**（R-04 保留 + R-13 已生效使基线变 100） |
| 实测推演 | 100 − R-01 − R-02 − R-03 = **97** | 距 ≤96 差 1 |
| 若 R-05 三项全下线 | 97 − 3 = **94** | 优于原目标 |

**候选方案**：

- **(i) 修订 M-2 为 ≤ 97**（推荐）：明确「R-04 经证据推翻原假设转保留」「基线由 101 修正为 100」，相对降幅 3%，且不引入新删除风险。
- **(ii) 推进 R-05 全下线 → ≤ 94**：需 RUNBOOK/ADMIN_MANUAL 核验通过、且 U-4 表空可作旁证。收益更大，但触及运维链路。
- **(iii) 补删 1 个整 router**：经核查 **无现成候选** —— 67 零调用端点中没有「整 router 全端点零调用」的剩余 router（`categories`/`weekly_report`/`trends` 已计入）。若强行凑数须新增需求并走 P2 消融，**不建议**。

### 5.5 冲突 C-E：P3 授权范围不足

- **冲突**：§8.1 P3 只授权 R-01~R-05 + R-13/R-14。但孤立类中 **4 个 service、24 死封装、13 孤儿组件**无对应需求编号。
- **提议**：新增 **R-16「孤立资产清理」**（service + 前端死封装/孤儿组件），排期建议 **P4.5 随 R-15**；否则这些确证孤儿将永久滞留。

---

## 6. 待用户逐项批准清单

> 勾选方式：批准 / 拒绝 / 降级（写明降为哪档）。**未获批准的项目，P3 不得执行。**
> **本表为裁决记录；批准结果与最终执行口径见 §6.1**（2026-11-11 已批复，18 项全批准 + 3 项修订）。

| 编号 | 裁决 | 档位 | 一句话理由 | 建议 |
|---|---|---|---|---|
| **P1-01a** | 删除 `api/trends.py` + 注册行 + `trend_service.py` + 前端 `TrendPoint`/`TrendResponse` 类型 | A | 全仓零消费，P0_R09「有内部消费」为 docstring 误判 | 批准 |
| **P1-01b** | 是否同步摘除 `collect_all` post-ingest 的 `rebuild_trend_and_log` 与 `TrendRepository` 注入 | A | 删 service 后 `trend_snapshots` 若无人读即为每轮空转；**读取面待穷举** | 先补证再定 |
| **P1-02** | 删除 `api/categories.py` + 注册行（保留 `count_by_category`） | A | 前端用本地 `CATEGORIES`，分类计数走 `/api/hotspots` | 批准 |
| **P1-03a** | 修订 R-03 为「整链下线」：router + service + job 41/42 + 调度注册 | A（修订 spec） | router 是该链唯一读取面，保留 job = 空转 | 批准（推荐） |
| **P1-03b** | 两张表 `weekly_reports` / `trend_daily_snapshots` 停写 / DROP 时机 | — | 需先 grep 全仓确认无第三方读取 | 先补证 |
| **P1-04** | R-04 `observability/audit` **保留**为诊断入口 | 保留 | `audit_log` 30 天 6,906 行活跃写入 | 批准 |
| **P1-05** | R-05 三项：U-2/U-3 保留并标注 docstring；U-4 待 RUNBOOK 核验 | 保留（U-4 待定） | 迁移端点属运维手工入口 | 批准 U-2/U-3，U-4 先核验 |
| **P1-06** | 删除 `services/crawler_seed.py`（+ 专属测试） | A | 0 生产 import，已被 `scripts/seed_crawler_sources.py` 取代 | 批准 |
| **P1-07** | 删除 `services/cost_monitor.py` + `services/feedback_analyzer.py`（+ 测试） | A | 0 生产 import；能力已由 `ai_hub/usage.py` 吸收 / 仅剩字段默认值字符串 | 批准 |
| **P1-08** | 删除 `services/codegarden_scanner_service.py`（619 行，+ 测试） | A | job 33 用的是 `codegarden_service_service`，不 import 本文件 | 批准 |
| **P1-09** | 回写 R-09 三处假阳性（reports available ×2 → 有消费；trends → 零调用） | 文档 | 组件内字面量直调被封装层扫描漏检 | 批准 |
| **P1-10** | R-09 §6.1 其余 65 端点：**P3 不删**，留 P2 消融 | 保留 | §7.4 要求「关掉后零失败 + 零观测变化」才可下删除结论 | 批准 |
| **P1-11** | 24 死封装 + 13 孤儿组件：新增 R-16，排期 P4.5 随 R-15 | A（新需求） | P3 授权不含前端死代码 | 批准新增 R-16 |
| **P1-12** | 死源：`HFDailyPapers` 下线（回滚=删 `collection_service.py:117` 一行）；`HN` 先补 `tech:HackerNews` 观察 2 周；`OSSInsight` / `Telegram` 观察 | 混合 | HN 是配置缺失不是能力失效，直接删会永久失去源 | 批准 |
| **P1-13** | 重复抓取：采用方案 A（隔离逻辑上提 `BaseCollector`） | 加速（修复） | 7 日重复 145 条；方案 B 覆盖不到单源路径 | 批准 |
| **P1-14** | `paper` 类处置：**C1**（`/knowledge` 独立区块） | 加速 | 169 条 7 日产出不进 Feed；C1 零后端改动 | 批准 C1 |
| **P1-15** | R-07 待裁 4 项（#11 `source_health_check` / #14 / #24 / #56） | 待裁 | P0_R07 §5 未定 | 需逐项讨论 |
| **P1-16** | M-2 目标：方案 (i) 修订为 ≤ 97 | spec 修订 | R-04 保留 + 基线 100 使 ≤96 不可达；方案 (ii) 需 R-05 全下线 | 批准 (i) |
| **P1-17** | R-14 退役泳道页 `/garden` | A | 用户在三点式重构中未点名；PRD §8.1 P3 已列，需显式授权 | 待确认 |
| **P1-18** | R-13 待办域：PRD 要求 B 档（410 + 观察一版），但当前已物理删除 | **偏差** | 见下方风险提示 | 需确认 |

### ⚠ 需单独提示的两项偏差

1. **R-13 已按 A 档物理删除**（DEV-0332），而 PRD §6.1 明文要求待办域走 **B 档（410 + `deprecated_since`/`replacement`/`sunset_date`，观察一版）**。当前 `/api/todos` 直接 404。请确认：接受偏差（单机自用无外部集成，410 无意义）还是补回 410 垫片一版。
2. **R-15 三项未验收**：三主题人工走查（light/dark/paper）、M-4 ≤ 733,501 B 复测。P4.5 门禁依赖此项。

---

### 6.1 批准结果与补证闭环（2026-11-11）

> **批准结论**：**18 项全部批准**（P1-01a ~ P1-18），其中 **3 项按用户指令修订**。本节为最终执行口径；与 §6「建议」列冲突时**以本节为准**。
> **唯一保留项**：**P1-17（R-14 退役 `/garden`）** —— §6 建议列为「待确认」而非「批准」，故「按建议批准」不构成该页的删除授权；P3 动手前须再获一句显式确认（见 §6.1.3）。

#### 6.1.1 三项修订

| 编号 | §6 原建议 | 用户批准口径 | 影响面 |
|---|---|---|---|
| **P1-03a** | 修订 R-03 为「整链下线」：router + service + job 41/42 + 调度注册 | **批准整链下线**；补充：`trend_daily_snapshots` / `weekly_reports` **两表停写保留、不 DROP**（遵 X-6 先例） | PRD §4.3 需求与验收全改写 |
| **P1-16** | M-2 方案 (i) 修订为 **≤ 97** | **批准 ≤ 97**；口径 `100 − R-01 − R-02 − R-03 = 97`（R-04 保留不计，R-13 已生效使基线为 100） | PRD §5.2 M-2 行 |
| **P1-18** | R-13 已 A 档物理删除，需确认「接受 404 偏差」或「补回 410」 | **不接受 404 偏差 → 补回 410 垫片**：`/api/todos*` 返回 `410 Gone`，响应体含 `deprecated_since` / `replacement=/action` / `sunset_date`，归 **P3** 执行 | PRD §4.13 补「410 垫片」子项，与 PRD §6.1 兼容策略对齐 |

#### 6.1.2 三项补证结论（P1-01b / P1-03b / P1-05-U-4，全部闭环）

**P1-01b — `trend_snapshots` 读取面穷举 → 无第三方读取方**

| 面 | 命中 | 说明 |
|---|---|---|
| 写入 | `backend/repository/trend_repo.py:171` `INSERT INTO trend_snapshots`（`:102` `DELETE` 清表） | — |
| 读取 | 仅 `backend/repository/trend_repo.py:220` `FROM trend_snapshots` | 唯一查询方法 |
| 读取链 | `trend_repo.py:220` → `TrendService` → `backend/api/trends.py`（R-01 待删） | **链尾即 R-01** |
| 触发写 | `backend/services/collection_service.py:121` 注入 `TrendRepository`；`:187` `rebuild_trend_and_log(...)` | post-ingest 空转源 |
| 非读取命中 | `scripts/retention.json:1095`（保留策略 truncate 配置）/ `backend/domain/models.py:99`（docstring）/ `docs/DIAGRAMS.md:429` / `docs/archived/*` | 均非消费方 |
| 测试断言 | `backend/tests/test_e2e_collect.py:173-206`、`backend/tests/test_collection_service.py:226-236`（均断言 192 行） | **P3 摘写链后必红，须同 commit 修改** |

→ **P1-01b 批准**：R-01 同 commit 摘除 `collection_service.py:121` 注入与 `:187` 调用，并同步改上述两处测试断言。

**P1-03b — `trend_daily_snapshots` / `weekly_reports` 读取面穷举 → 无第三方读取方**

| 表 | 写 | 读 | 唯一出口 |
|---|---|---|---|
| `trend_daily_snapshots` | `backend/repository/weekly_report_repo.py:103` `INSERT` | `:121` `SELECT ... WHERE snapshot_date >= ?`（`get_range`） | `weekly_report_service.py:103` `generate_report`（= job 42 组装步） |
| `weekly_reports` | `backend/repository/weekly_report_repo.py:26` `INSERT` | `:70` / `:78` / `:86` `SELECT * FROM weekly_reports` | `backend/api/weekly_report.py` 5 端点（前端 0 调用） |

非读取命中：`scripts/retention.json:1084` / `:1172`（保留策略配置）、`docs/demos/NAV4_IA_DEMO.html:256`（演示文案）、`docs/POST_R2_ENHANCEMENTS_DESIGN_2026-09-12.md:64-76`（仅讨论 `bid_summary` 列，非表消费）、`migrations/017_weekly_report.sql` / `114_drop_dead_columns.sql`（建表/注释）。

→ **P1-03b 批准（整链成立）**：整链下线后两表成为只写不读，故按用户指令**停写保留、不 DROP**。

**P1-05（U-4）— `legacy_migrate_v1_api` 运维契约核验 → 保留**

| 检查 | 结果 |
|---|---|
| `docs/RUNBOOK.md` / `docs/ADMIN_MANUAL.md` | `legacy` / `weekly-report` / `todos` 三关键词 **均 0 命中** |
| 锁期契约登记 | `docs/v1.0/c13-switchback-runbook.md:38-44` 登记 5 端点与锁期行为；`test_c13_legacy_migrate_v1_api.py` 6/6 锁定 |
| 待授权生产动作 | `docs/v0.8.5/ACCEPTANCE.md:38` D4「生产 853 行 warm 迁移为授权运维任务（C13 工具链就绪：run/mapping/promote + 备份前置）」→ **未完成** |
| 活跃 job | `P0_R07_JOB_INVENTORY_2026-11-10.md:110` / `:173` job 58 `legacy_promote_due`、job 59 `legacy_migrate_resume` 直读 `v1_legacy_mapping` / `v1_legacy_promote_log` |
| 服务消费者 | `P0_R06_SERVICE_ORPHANS_2026-11-10.md:188` `services/legacy_migrate_v1.py` 24 消费者（api + 2 jobs + 3 services + tests + 3 scripts） |

→ **U-4 保留**（不降 A/B 档）：依据 = C13 回滚 runbook 仍为现行契约 + ACCEPTANCE D4 生产迁移未完成 + job 58/59 活跃；docstring 标注「运维手工入口，勿删」。

#### 6.1.3 局限关闭与未采纳方案

- §7.2 局限 **#2**（三表读取面未穷举）→ **关闭**，见 §6.1.2 三张表逐面清单。
- §7.2 局限 **#5**（两表在 warm DB）→ **转为 P3 执行前置**：停写验收须先确认调度器实际连接的库路径，否则验收误判（不影响本裁决）。
- §5.4 C-D 候选方案 **(ii) 推进 R-05 全下线 → ≤94** / **(iii) 补删 1 个整 router** → **均不采纳**，M-2 定版 **≤ 97**。
- §6「⚠ 偏差 1」（R-13 404）→ **已裁决补回 410 垫片**，不再列为偏差。
- **P1-17（R-14 `/garden`）→ 未获删除授权**：§6 建议列原文为「待确认」，本轮「按建议批准」不含该项。技术面结论不变（`/garden` 为只读泳道投影页，无写入链，重定向 `/action` 可单 commit revert），但**执行前须显式确认**；未确认则 P3 跳过该项，不影响 M-2 ≤ 97 口径（R-14 不涉及 router 增减）。

---

## 7. 证据来源与局限

### 7.1 证据来源

| 类型 | 来源 |
|---|---|
| 代码 | 逐行读取：`api/trends.py` 注册面、`api/reports.py`（91 行全量）、`api/weekly_report.py`、`scheduler/jobs/digest.py`（60 行全量）、`scheduler/scheduler.py:144-162`、`services/collection_service.py:121,187`、`scheduler/jobs/codegarden.py:30-70`、`SentinelShell.tsx:155-236`、`components/report/*.tsx` |
| 数据（只读 SQL） | `user_skills`=0；`weekly_reports`=3（最新 2026-11-02）；`trend_daily_snapshots`=175；`audit_log` 30 天 6,906 行按 action 分组；`v1_legacy_mapping`/`v1_legacy_promote_log`=0；`source_stats` 中 `hn%`=0 |
| 盘点附件 | `P0_R06` / `P0_R07` / `P0_R08` / `P0_R09` / `P0_BASELINE_METRICS`（均 2026-11-10） |
| 架构数字 | `python scripts/generate_meta.py --check` → routers **100** / services **161** / jobs **59** / collectors **19** / core_routers **68** |

### 7.2 局限（本文结论的适用边界）

1. **R-09 扫描口径缺陷**：仅覆盖 `frontend/src/api/*.ts` 封装层 + 组件内字面量 fetch，**未覆盖**动态拼接 URL、`window.location` 跳转、以及后端渲染的链接。§1.5.3 的 65 项「不删」部分是**保守保留**而非「确证有用」。
2. **`trend_snapshots` / `trend_daily_snapshots` / `weekly_reports` 的读取面未穷举**（grep 限于 `backend/` + `frontend/src/`，未覆盖 `scripts/` 与外部工具）→ P1-01b/P1-03b 标「先补证」。**✅ 2026-11-11 已补证关闭**（含 `scripts/` 与 `docs/` 全扫，见 §6.1.2）。
3. **P0_R06 在非干净树上采集**（R-13/R-15 未提交改动在位）；4 项 service 结论已用本轮独立 grep 复核，未受该局限影响。
4. **M-6 基线变异度 1.94×**（三轮 979.54 / 1,364.46 / 1,898.41 s），仅可作粗粒度不劣化门。
5. **`weekly_reports` / `trend_daily_snapshots` 位于 warm DB 而非主库** —— P3 执行时须确认调度器实际连接的库路径，否则「停写」验收会误判。

---

## 8. 下一步

1. ~~用户逐项批复 §6 清单（P1-01a ~ P1-18）。~~ **✅ 2026-11-11 已全部批准**（18/18，含 3 项修订，见 §6.1）。
2. ~~批复后：回写 spec（§4.3 / §4.4 / §5.2 / §8.1），在 DEV_LOG 记一条 **DEV-0335**。~~ **✅ 已回写** `V0.8.8_REFACTOR_PRD.md`（exec.4）并记 DEV-0335。
3. ~~补证 P1-01b / P1-03b / P1-05(U-4) 三项后，方可进入 **P2 消融**。~~ **✅ 三项已闭环**（§6.1.2），具备进入 P2 条件；**P2 启动仍待用户指令**。
4. **本文不含任何删除动作；P3 执行需用户另行启动指令。**