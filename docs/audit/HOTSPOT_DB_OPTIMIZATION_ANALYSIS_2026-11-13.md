# hotspot.db 体积优化方案 — 深度复盘与架构级养料分级

> **日期**: 2026-11-13
> **类型**: 架构级优化方案（复盘 + 分析 + 实施方案）
> **关联**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`](../v0.8.8/V0.8.8_REFACTOR_PRD.md) §4.17 R-17（P2.5）/ [`docs/audit/DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md`](DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md)（热冷分层设计）
> **目标重述**: **DB 缩小不是目标。目标是更健壮、更轻量地将「资讯」转为「知识」，将「知识 wiki」转为「人机可执行的养料」。体积下降是养料分级的副产品。**

---

## 0. 一句话结论

当前热层 163.6 MB 的 46% 来自三项**不是"人机即时消费养料"**的对象：FTS 倒排索引（34.41 MB，膨胀 14.8x）、admission_log 原文（11 MB 冷审计数据）、wiki_events 账本（19.84 MB 含索引）。真正的养料（hotspots / v1_signals / v1_materials / v1_evidence_receipts）仅占 14%。本方案以**养料分级**替代体积压缩：让养料留 DB、账与原文按 C-4 wiki-first 哲学归位 md，配合 FTS 索引瘦身与分词器治理，P0+P1 落地后热层可降至约 **90 MB（−45%）**，且检索能力不降级、养料完整保留。

---

## 1. 实测诊断：热层 163.6 MB 的构成与"养料"分级

### 1.1 完整体积分布（`dbstat`，2026-11-13 生产实测）

| 表 / 索引 | 体积 | 占比 | 行数 | 角色判定 |
|---|---|---|---|---|
| `hotspots_fts_data` | **34.41 MB** | 21% | 6532 | 资讯检索倒排索引，**膨胀 14.8x**（源 summary 仅 373 B/行） |
| `admission_log` | **20.71 MB** | 13% | 15099 | 准入审计，`raw_material_json` 原文 762 B/行 ≈ 11 MB（**原文是冷审计数据**） |
| `wiki_events` | 9.96 MB | 6% | 67493 | 审计账（sink 37317 + kl_transition 23207）+ 运行流（**账查询是冷路径**） |
| `idx_we_wiki_path` | 4.08 MB | 3% | — | wiki_events 反查索引 |
| `idx_we_kind_ts` | 3.24 MB | 2% | — | wiki_events 分类查询索引 |
| `idx_we_db_ref` | 2.56 MB | 2% | — | wiki_events 反查索引 |
| `hotspots` | 6.67 MB | 4% | 6522 | 资讯工作集（30 天窗）✅ **养料** |
| `v1_materials` | 6.57 MB | 4% | 7541 | 证据链引用层，**与 hotspots 重叠 2945 行**（冗余） |
| `v1_signals` | 5.61 MB | 3% | 7520 | 信号工作集 ✅ **养料** |
| `llm_cache` | 5.28 MB | 3% | 17906 | LLM 响应缓存，有 TTL（**衰减是否生效待核**） |
| `v1_evidence_receipts` | 4.59 MB | 3% | 15221 | 证据回执 ✅ **养料** |
| `llm_usage_log` | 5.62 MB | 3% | 28047 | LLM 用量日志（30 天窗已截） |
| `security_edges` + `ux_security_edge` | 5.81 MB | 4% | 18070 | 安全图谱（工作集） |
| `job_runs` | 3.27 MB | 2% | 20326 | 运行日志（20k 行环截） |
| `ai_scores` + `idx_ai_scores_hotspot` | 4.79 MB | 3% | 25241 | 知识打分（30 天窗） |
| `audit_log` 等其余 | ~10 MB | 6% | — | 审计日志 / 台账等 |
| **合计** | **163.6 MB** | — | — | — |

### 1.2 养料分级

| 级别 | 对象 | 体积 | 职责 | 归属 |
|---|---|---|---|---|
| **L1 即时养料** | `hotspots` · `v1_signals` · `v1_materials` · `v1_evidence_receipts` | ~23.4 MB (14%) | 人机即时消费：资讯浏览、信号队列、证据回执 | **留 DB**（热工作集） |
| **L2 工作集索引** | `hotspots_fts`（瘦身后）· `v1_*` 索引 | 见 §3 方案 A | 支撑 L1 的检索 | **留 DB**，瘦身优化 |
| **L3 审计账** | `wiki_events`（sink/kl_transition 账） | ~10 MB | 可由 md 重建的追溯链 | **下沉 md**（C-4 哲学） |
| **L4 冷审计原文** | `admission_log.raw_material_json` | ~11 MB | quarantine 原文审计 | **下沉 md**（C-4 哲学） |
| **L5 运行日志** | `job_runs` · `llm_usage_log` · `llm_cache` | ~14 MB | 短期滚动 | **留 DB**，环截 + TTL |

**核心发现**：L3+L4+L5 合计约 35 MB，加上 FTS 膨胀 28 MB，这 **63 MB（38%）是本方案可优化的目标空间**，且都不在"养料"范畴。

### 1.3 FTS 膨胀根因（重点）

- `hotspots_fts` DDL：`fts5(id UNINDEXED, title, summary, content='', tokenize='unicode61')`
- 源数据：`hotspots` 6532 行，`summary` 平均 373 B/行，`title` 0.32 MB。
- 索引：34.41 MB，**每行索引占用 5524 B，相对 summary 膨胀 14.8x**。
- 根因：`unicode61` 分词器对中文连续字符的切分策略导致倒排词元数膨胀。**这是分词器固有成本，非数据冗余**——索引内容（title+summary）总共仅 2.57 MB，倒排结构膨胀了 13 倍。

---

## 2. 执行困难与阻碍深度复盘

本次「db 转热库、wiki 转冷库」的执行中，暴露的阻碍不是操作难度，而是**架构方向与当前实现的深层冲突**。按阻碍程度排序：

### 阻碍 1：FTS5 contentless 触发器锁死（最大结构性阻碍）

**现象**：`hotspots_fts` 是 `content=''` 的 contentless FTS5，DELETE/UPDATE 被禁，必须走 migration 078 的触发器（`hotspots_ai/au/ad`）。

**影响**：
- FTS 结构变更（改索引列、换分词器）**无法在运行中调整**，必须停服迁移 + 全量重建索引；
- C2.3b 删 37317 行时，触发器逐行带旧值删除，批量删除性能依赖触发器效率（实测 1.7s 可接受，但规模再大时是瓶颈）；
- 本次未能实施 FTS 优化的直接原因：**先要评估所有 `MATCH` 消费点、再设计触发器迁移、再写独立重建脚本**，三重约束叠加导致 FTS 优化被推迟。

**消费点（实测）**：`search_service._fts_search_entity`（L154/172）、`hotspot_repo`（L416/496/634）、`chunk_service._search_fts`（L165）。均为资讯全文检索入口，**需逐一确认是否依赖 summary 列关键词**。

### 阻碍 2：wiki_events 双保留规则与体积目标自相矛盾

**现象**：C2.2 owner 裁决「保留 sink/rebuild + 全部带 wiki_path/db_ref 的行」。实测生产 67493 行**全部**带 wiki_path → 可删集合为 0 → wiki_events 实际不参与截断。

**根因**：**账本的"追溯链"需求与"热层体积"需求在此表上不可兼得**。当前靠「账留在 DB 支撑反查端点 `/api/wiki/trace`」维持，但账本身不是养料，是"账的索引"。

### 阻碍 3：冷层 md 无查询能力，账无法下沉

**现象**：`feed/` md 是纯文件，无索引。`trace_by_wiki_path` / `trace_by_db_ref` 反查依赖 DB 的 wiki_events 账。

**根因**：要让账下沉到 md，**必须先建 md 的检索/反查能力**。`feed/` 的行级 `<!--hsc:{json}-->` 已可解析，但无 SQL 级索引，`/api/wiki/trace` 端点无法直接扫 md 定位记录。**这是账下沉的前置缺失**，导致 C2.2/C2.3b 只能维持"账留 DB、md 留冷层"的双轨，无法真正收敛。

### 阻碍 4：ai_scores 双语义字段导致口径不可行

**现象**：`ai_scores.hotspot_id` 是「hotspot / knowledge item」双语义字段，生产实测存 `kl-*`（6704 个唯一值），与 `hotspots.id` 交集 0。

**根因**：C2.2 的「随 hotspots 同窗删」口径在数据上不可行，owner 改裁决为 `scored_at` 30 天窗。说明**字段语义未统一时，关联删除的口径设计会落空**，必须改为时间窗等不依赖语义关联的口径。

### 阻碍 5：WAL 与 VACUUM 的运行时冲突

**现象**：C2.2 首次生产执行暴露——WAL 模式下 VACUUM 把整库写入 WAL，服务持有 WAL 连接时 `checkpoint(TRUNCATE)` 无法截断 → 总占用 399 MB > 截断前 364 MB，净收益为负。

**根因**：**空间回收需要独占锁，而服务常驻**。这是 SQLite 单机架构的固有约束，已修复（VACUUM 后补 checkpoint + 停服截断），但每次空间回收都需停服窗口，影响健壮性。

### 阻碍根因总结

当前架构处于「**DB 为真源 + md 为投影**」向「**md 为真源 + DB 为热工作集**」的**过渡态**。两个方向的约束交叉在同一批表上：

- DB 侧：FTS 依赖（资讯检索）、账本依赖（反查端点）、原文依赖（准入审计）；
- md 侧：C-4 wiki-first 哲学（md 为唯一真相源）。

每次优化都要在「保留 DB 能力」与「符合 C-4 哲学」之间妥协，**这是体积目标未达成的深层原因，不是操作失误**。本方案的核心思路是：**用 md 的能力补齐来解锁 DB 侧依赖，让账与原文能真正下沉，从而打破过渡态的双轨锁定**。

---

## 3. 架构优化方案：以「养料分级」替代「体积压缩」

**总原则**：DB 只留「人机即时消费的养料 L1 + 必要的工作集索引 L2 + 短期滚动日志 L5」；所有「账 L3、冷审计原文 L4」归冷层 wiki；md 升级为可机读反查的养料库。

### 方案 A（P0，收益最大）：FTS 索引瘦身 + 分词器治理（预计 −28 ~ −48 MB）

#### A1. 索引列瘦身：只索引 title，summary 退出 FTS

| 项 | 现状 | 改后 |
|---|---|---|
| FTS 列 | `title, summary` | 仅 `title` |
| 源字节 | title 0.32 MB + summary 2.25 MB | title 0.32 MB |
| 索引体积（估） | 34.41 MB（膨胀 14.8x） | ~1.6 MB（膨胀 5x） |
| **收益** | — | **−32.8 MB** |

**决策依据**：资讯检索的核心锚点是标题。摘要的关键词检索需求：
- 若 `MATCH` 消费点**不依赖摘要关键词** → 直接移除 summary 索引；
- 若**依赖** → 摘要搜索降级为热层 `hotspots.summary` 的 `LIKE` 查询，或冷层 md 全文检索兜底。

**前置**：审计 `search_service` / `hotspot_repo` / `chunk_service` 的 MATCH 消费点，确认摘要关键词检索的实际使用频率（见 §5 裁决项 1）。

#### A2. 分词器评估：unicode61 → trigram

| 项 | 现状 | 评估方向 |
|---|---|---|
| `tokenize` | `unicode61` | `trigram`（FTS5 原生支持） |
| 中文膨胀 | 14.8x | 预期降至 5x 以下 |
| **收益**（若 A1+A2 组合） | — | 索引体积再降 50%，**再 −0.8 MB** |

**做法**：在副本库实测两种分词器的索引体积与查询召回，再决策。trigram 对中文部分匹配友好，但词元数更低。

#### A3. 触发器迁移预案（克服阻碍 1）

FTS 结构变更须停服，流程：
1. 新建新 FTS 表（新列 / 新分词器）；
2. 全量重建索引（从 `hotspots` 表读 title/summary 插入）；
3. 切换触发器（新表 `hotspots_ai/au/ad` 指向新 FTS，旧触发器移除）；
4. 删除旧 FTS 表。

需独立迁移脚本 + 回滚路径，**作为独立子项（C2.6）交付**，不混在 C2.3b 内。

### 方案 B（P1）：wiki_events 账目下沉（预计 −9.8 MB）

#### B1. 账（sink / kl_transition）下沉到 wiki md

| 账类 | 行数 | 现状 | 改后 |
|---|---|---|---|
| `sink` | 37317 | 留 DB | **下沉**：`feed/{yyyy-mm}.md` 已有全列记录，账可由 md 重建，DB 仅留近 7 天最近账用于快速反查 |
| `kl_transition` | 23207 | 留 DB | **下沉**：对应 wiki md 的 `lifecycle` 字段流转，账可由 md 重建 |
| 运行流（`agent_write`/`sync_item`/`kl_error`） | ~11968 | 留 DB | **保留**：工作集，按时间窗截断 |

**收益**：wiki_events 从 67493 行降至约 1.7 万运行流行，体积 9.96 MB → ~2.5 MB；3 个索引裁 2 个（`idx_we_wiki_path` / `idx_we_db_ref` 反查改由 md 承载，仅留 `idx_we_kind_ts`），**−9.8 MB**。

#### B2. 反查端点冷热路由（克服阻碍 3，前置必做）

`/api/wiki/trace`（`wiki_tools.py:158`）：
- `trace_by_wiki_path` / `trace_by_db_ref`：**先查 DB 近期账（7 天），未命中时扫 `feed/` + `llm-wiki-2.0/items/` md 的行级 JSON**。
- 保证账下沉后反查链不丢，这是账下沉的**前置能力**。

### 方案 C（P1）：admission_log 原文外移（预计 −15.7 MB）

| 项 | 现状 | 改后 |
|---|---|---|
| `raw_material_json` | 762 B/行 × 15099 ≈ 11 MB（留 DB） | **外移**到 `llm-wiki-2.0/admission/{yyyy-mm}/{hash}.md` |
| DB 元数据 | 全文 20.71 MB | 仅元数据（`body_hash`/`verdict`/`reason`/`matched_rule_id`）≈ 340 B/行 → 5 MB |
| **收益** | — | **−15.7 MB** |

**前置**：`v1_admission_service` / `v1_ingest_bridge` / `v1_signal_bridge` 读取方改冷热路由——元数据查 DB，原文按需读 md。

**注意**：需裁决是否改变 DEV-0344「保留 quarantine 原文审计」的语义（原文从 DB 迁到 md，审计能力不丢，但存储位置变更）。

### 方案 D（P2）：v1_materials 去重（预计 −3 MB）

- 现状：v1_materials 7541 行，与 hotspots 重叠 2945 行，存 `content_hash` + `content_length` + `content_ref`（无 content 列，是引用层）。
- 做法：重叠部分的 `content_ref` 指向 `hotspots` 的 id，消除重复的 hash/length 存储。
- **收益**：**−3 MB**（收益有限，优先级低）。

### 方案 E（P2）：llm_cache TTL 治理（预计 −2 MB）

- 现状：17906 行 5.28 MB，有 `ttl_seconds` 字段。**需先核查 TTL 清理是否生效**。
- 若未生效：补清理逻辑；若已生效：维持。
- **收益**：**−2 MB**。

### 方案 F（健壮性，非体积）：FTS 重建管道独立化

- 现状：FTS 同步完全依赖触发器逐行 DML，大批量删行时逐行执行。
- 做法：`rebuild_hot_index.py --rebuild-fts` 独立路径，不依赖触发器，批量重建 FTS 索引。
- **收益**：**健壮性 + 性能上限**（不直接减体积），支撑"更健壮"目标。

---

## 4. 预期收益与优先级

| 方案 | 收益 | 优先级 | 前置 / 依赖 |
|---|---|---|---|
| **A1 FTS 只索引 title** | **−32.8 MB** | **P0** | 裁决：MATCH 消费点是否依赖摘要 |
| **A2 分词器 trigram 评估** | 再 −0.8 MB | P0（评估） | 副本库实测 |
| **B1 wiki_events 账下沉** | **−9.8 MB** | P1 | **B2 md 反查能力（阻碍 3）** |
| **C admission_log 原文外移** | **−15.7 MB** | P1 | 读取方冷热路由 + 裁决 |
| D v1_materials 去重 | −3 MB | P2 | — |
| E llm_cache TTL | −2 MB | P2 | 核查 TTL 清理 |
| F FTS 重建独立化 | 健壮性 | P1 | — |

**组合收益**：
- **P0 落地**：热层 163.6 → ~130 MB（−20%）
- **P0+P1 落地**：热层 163.6 → **~90 MB（−45%）**
- 且 **养料（L1）完整保留、检索能力不降级、账与原文按 C-4 哲学归位 md**——体积下降是养料分级的副产品，不是目的。

---

## 5. 裁决请求

本方案中三项需 owner 裁决后才可实施：

| # | 裁决项 | 选项 | 影响 |
|---|---|---|---|
| **1** | **FTS 是否保留 summary 索引** | A. 移除 summary 索引（仅 title）· B. 保留 summary 但换 trigram 分词器 · C. 摘要搜索降级 LIKE | 决定方案 A1 的收益（−32.8 MB）能否落地 |
| **2** | **admission_log 原文外移** | A. 外移到 md（C-4 哲学，审计能力不丢）· B. 保留 DB（放弃 −15.7 MB） | 决定方案 C 是否实施 |
| **3** | **wiki_events 账下沉的保留窗口** | A. DB 仅留 7 天近期账 · B. DB 不留账，完全靠 md 反查 | 决定方案 B1 的实现细节与反查性能 |

## 6. 实施建议

建议按以下顺序实施（每阶段独立 commit + 副本库实测 + 生产首跑复核，遵循 DEV-0349 的 F-2 生产首跑复核纪律）：

1. **C2.6a FTS 消费点审计**（只读，无改动）：审计 `MATCH` 消费点是否依赖 summary，产出裁决依据。
2. **C2.6b FTS 瘦身 + 分词器治理**（停服迁移）：A1 + A2，独立迁移脚本 + 回滚路径。
3. **C2.6c md 反查能力**（B2 前置）：`/api/wiki/trace` 冷热路由 + feed md 行级 JSON 反查。
4. **C2.6d wiki_events 账下沉**（B1）：sink/kl_transition 账下沉 + 反查端点验证。
5. **C2.6e admission_log 原文外移**（C）：原文迁 md + 读取方冷热路由。
6. **C2.6f 健壮性收尾**（F）：FTS 重建独立化 + llm_cache TTL 核查。

每阶段遵循 DEV-0349 三条优化纪律（F-1 时间锚定 / F-2 生产首跑复核 / F-3 目标预演）。

---

## 附录：实测数据来源

- 体积分布：`PRAGMA dbstat` 分表统计（`backend/hotspot.db`，只读连接）
- FTS 健康：`hotspots_fts` 行数 = `hotspots` 行数（6532 = 6532，触发器无残留）
- wiki_events 构成：`SELECT kind, COUNT(*) FROM wiki_events GROUP BY kind`
- admission_log 字段：`PRAGMA table_info(admission_log)` + `AVG(length(raw_material_json))`
- v1_materials 重叠：`SELECT COUNT(*) FROM v1_materials m WHERE m.url IN (SELECT url FROM hotspots)`
- FTS 消费点：`grep -rn "MATCH.*hotspots_fts" backend/`
