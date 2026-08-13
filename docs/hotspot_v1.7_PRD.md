# hotspot v1.7 PRD — 分析报告 + 新方案

> **作者**: MiniMax-M3
> **日期**: 2026-07-26
> **状态**: 草案（基于 v1.7 PRD 实施现状 + Horizon 借鉴 + 第一性原理）
> **关联**:
> - 上游文档: [hotspot_v1.7_PRD.md](./hotspot_v1.7_PRD.md)（2193 行，17 章）
> - 借鉴项目: <https://github.com/Thysrael/Horizon>
> - 落地基线: v1.7.6 Phase 7（MCP Server）+ v1.8（catchup）+ v1.9（checkpoint & validation）
>
> **命名说明**: v1.8 已被 catchup 阶段占用，v1.9 已被 checkpoint/validation 占用。下一个"大版本"命名为 **v1.7**。

---

## 目录

- [Part A · 分析报告](#part-a--分析报告)
  - [A.1 v1.7 PRD 实施数据审视](#a1-v17-prd-实施数据审视)
  - [A.2 v1.7 PRD 好的设计](#a2-v17-prd-好的设计)
  - [A.3 v1.7 PRD 不足与可砍](#a3-v17-prd-不足与可砍)
  - [A.4 Horizon 借鉴分析](#a4-horizon-借鉴分析)
  - [A.5 第一性原理审视](#a5-第一性原理审视)
  - [A.6 hotspot 中转系统定位](#a6-hotspot-中转系统定位)
- [Part B · v1.7 PRD 新方案](#part-b--v20-prd-新方案)
  - [B.0 产品战略审计（2026-07-27 团队产出）](#b0-产品战略审计2026-07-27-团队产出)
    - [B.0.1 TL;DR 与核心结论卡片](#b01-tldr-与核心结论卡片)
    - [B.0.2 三个产品目标（与 B.1.2 北极星指标对齐）](#b02-三个产品目标与-b12-北极星指标对齐)
    - [B.0.3 用户故事（5 个核心场景）](#b03-用户故事5-个核心场景)
    - [B.0.4 用户研究洞察（来自瑞思）](#b04-用户研究洞察来自瑞思)
    - [B.0.5 竞品对比（来自竞析）](#b05-竞品对比来自竞析)
    - [B.0.6 数据依据与北极星指标（来自数析）](#b06-数据依据与北极星指标来自数析)
    - [B.0.7 需求池（P0 × 8 / P1 × 9 / P2 × 7 = 24 条）](#b07-需求池p0--8--p1--9--p2--7--24-条)
    - [B.0.8 Non-goals（v1.7 明确不做什么）](#b08-non-goalsv20-明确不做什么)
    - [B.0.9 时间线与里程碑（来自路径）](#b09-时间线与里程碑来自路径)
    - [B.0.10 关键流程图与 UI 草图（战略视角统一视图）](#b010-关键流程图与-ui-草图战略视角统一视图)
  - [B.1 定位与目标](#b1-定位与目标)
  - [B.2 核心原则（精简化）](#b2-核心原则精简化)
  - [B.3 三层架构](#b3-三层架构)
  - [B.4 数据模型（最小化）](#b4-数据模型最小化)
  - [B.5 抓取层（Horizon 借鉴）](#b5-抓取层horizon-借鉴)
  - [B.6 知识层（KL 5 阶段 + 5 自动化触发器 + 资讯收藏聚合视图）](#b6-知识层kl-5-阶段--5-自动化触发器)
  - [B.7 MCP 集成（读独立 + 写副作用 + 失败恢复 + 规划引导）](#b7-mcp-集成读独立--写副作用--失败恢复--规划引导)
  - [B.8 复利机制（核心）](#b8-复利机制核心)
  - [B.9 不做清单（v1.7 明确放弃）](#b9-不做清单v20-明确放弃)
  - [B.9.5 用户旅程（v1.7 优秀设计保留）](#b95-用户旅程v17-优秀设计保留)
  - [B.9.6 API 设计（v1.7 endpoint 列表保留）](#b96-api-设计v17-endpoint-列表保留)
  - [B.9.7 调度器（v1.7 job 表保留 + 5 触发器新增）](#b97-调度器v17-job-表保留--5-触发器新增)
  - [B.9.8 前端组件与路由（v1.7 关键组件保留）](#b98-前端组件与路由v17-关键组件保留)
  - [B.9.9 跨端同步（v1.7 Sync Bundle 设计保留 + 8 表扩展）](#b99-跨端同步v17-sync-bundle-设计保留--8-表扩展)
  - [B.10 Phase 规划](#b10-phase-规划)
  - [B.11 验收标准](#b11-验收标准)
  - [B.11.5 测试策略（v1.7 完整保留 + 5 触发器专项测试）](#b115-测试策略v17-完整保留--5-触发器专项测试)
  - [B.11.6 迁移策略（v1.7 → v1.7）](#b116-迁移策略v17--v20)
  - [B.12 风险与对策](#b12-风险与对策)
  - [B.13 hotspot Hybrid AI 设计（Crawl4ai + 可选本地 LLM）](#b13-hotspot-hybrid-ai-设计crawl4ai--可选本地-llm)
- [附录 A · v1.7 → v1.7 决策变更总表](#附录-a--v17--v20-决策变更总表)
- [附录 B · Horizon scrapers 借鉴表](#附录-b--horizon-scrapers-借鉴表)
- [附录 C · 待确认问题清单（2026-07-27 战略审计）](#附录-c--待确认问题清单2026-07-27-战略审计)
- [附录 D · 行动清单（M1-M4 / D1-D46）](#附录-d--行动清单m1-m4--d1-d46)
- [附录 E · v1.7 PRD 实测对账与修复记录（2026-07-27 leader skill 产出）](#附录-e--v20-prd-实测对账与修复记录2026-07-27-leader-skill-产出)
- [附录 F · v1.7 PRD 修复任务书归档（2026-07-27，已完成）](#附录-f--v20-prd-修复任务书归档2026-07-27已完成)

---

# Part A · 分析报告

## A.1 v1.7 PRD 实施数据审视

### A.1.1 实施数据快照（2026-07-26）

| 指标 | 实际 | v1.7 PRD 目标 | 完成度 |
|---|---|---|---|
| `knowledge/items/*.md` | **4,127** | 无上限 | 持续累积 ✅ |
| `knowledge/concepts/*.md` | **97** | 持续扩展 | 已建立目录结构 ✅ |
| **应用了 `lifecycle` 字段的 items** | **4,147 / 4,147 = 100%** | 全部 items 应有生命周期 | ✅ 字段已建，但值命名与 v1.7 5 阶段不统一 |
| **应用 v1.7 5 阶段 (`kl:raw/refine/link/structure/publish`) 的 items** | **0 / 4,147 = 0%** | v1.7 起新写入 | ❌ **老数据全部用 v1.7 旧 3 阶段值**（见下）|
| **现存 lifecycle 实际取值分布** | `generate`: 74 / `signal`: 4,070 / `amplify:tagged`: 3 | v1.7 目标 5 阶段 | ❌ 与 v1.7 设计 100% 不一致，需 B.11.6 增加迁移 SQL |
| `knowledge/learning/tasks/pending/` | 0（已清空，Option A） | 不再活跃写入 | ✅ Option A 落地 |
| `tags` 表（多对多） | 已建表 | 替代 JSON 字段 | ✅ Phase 1 落地 |
| `sm2_reviews` 表 | 已建表 | SM-2 复习 | ✅ Phase 2 落地（数据稀疏）|
| `reading_states` 表 | 已建表 | 行为日志 | ✅ Phase 4 落地（数据稀疏）|
| `mcp_tool_registry` 表 | 13 tool 已 seed | Phase 7 13 tool | ✅ v1.7.6 完成 |
| `catchup_runs` / `catchup_checkpoints` | 已建表 | 断点续传 | ✅ v1.8/v1.9 完成 |
| `collect_validations` 表 | 已建表 | 4 类验证 | ✅ v1.9 完成 |
| **Codegarden 项目数** | 已有项目 | Phase 2b | ✅ |
| **Security Graph** (CVE/MITRE/合规) | 已建表 + graph | Phase 1-5 | ✅ |

### A.1.2 关键洞察

1. **采集层已经成熟**：4 类验证 + 24h checkpoint + 5min 防抖 + 46 源（其中 28 个活跃）已上线，**问题集中在"采回来之后怎么用"**
2. **知识库 4,147 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段（实际 100% 用 v1.7 旧 3 阶段值 `generate`/`signal`/`amplify:tagged`）** —— KL 五阶段是"应该实现但被遗忘的脚手架"
3. **MCP 是 13 tool 中**：`search_hotspots / search_knowledge / add_favorite / add_annotation / update_knowledge_item` 是核心，**`trigger_extract_tags` / `trigger_cubox_sync` / `create_alert_rule` / `mark_digest_read` 是低频工具**
4. **用户实际工作流**（基于 session memory）：
   - 早上开 dashboard 看热点
   - 感兴趣 → 收藏到 knowledge
   - 周末/晚间手动整理 → 写 SOUL / 提炼 concept
   - 写 code 时从 knowledge 检索 → 触发 Todo/Codegarden

---

## A.2 v1.7 PRD 好的设计

### A.2.1 架构层

| 设计 | 评价 | 保持/调整 |
|---|---|---|
| **MCP 协议 + 外部 AI Agent**（v1.7.6 Option A） | 移除内部 hotspot-agent 进程、LLM 推理下放给外部 agent、零状态耦合、依赖少、生态成熟 | ✅ **完全保持** |
| **OKF + LLM-Wiki 2.0 统一存储** | `.md` 文件为源数据、SQLite 为 KV 缓存 + 查询加速、Obsidian 可直读、AI Agent 可直写 | ✅ **完全保持** |
| **SAG 事件-实体模型吸收** | 事件 = 整个 .md / 实体 = concepts+tags+tech_stack / 查询时多表 JOIN = 动态超边 | ✅ **完全保持**（落地为 `item_entities` 表）|
| **本地优先、零外部依赖** | 单一工作站、单进程、SQLite WAL、Fernet 加密、APScheduler | ✅ **完全保持** |
| **协议优先而非运行时** | hotspot 不做智能体 runner，做数据 + 工具暴露 | ✅ **完全保持** |
| **KL 五阶段状态机**（`kl:raw/refine/link/structure/publish`）| v1.7 设计的 5 阶段是知识复利的基础设施，区分了"机器完成/AI Agent 完成/用户完成"的边界 | ✅ **完全保留**（落地为 `item_entities` + `knowledge_links` + lifecycle 字段，配合 5 个自动化触发器推进）|
| **认知链路 6+1 环节**（信号→注意→理解→关联→内化→决策→行动 + 复利）| hotspot 的灵魂 | ✅ 完整保留并加 5 触发器对应 |

### A.2.2 数据模型层

| 设计 | 评价 |
|---|---|
| `tags` 多对多 + `parent_id` 层级 | ✅ 极好，支持 ai-security → security 层级 |
| `hotspot_tags.confidence` | ✅ 自动提取置信度可校准 |
| `reading_states` opened_count + total_dwell_ms | ✅ 隐式学习数据基础 |
| `sm2_reviews` SM-2 完整字段 | ✅ 算法正确（但数据稀疏）|
| `annotations` entity_type + entity_id | ✅ 笔记空间支持任意实体 |
| `favorites.created_via` | ✅ 区分 UI/MCP/Agent 来源，统计友好 |
| `mcp_tool_registry` | ✅ Tool 元数据 + 启动 seeding |

### A.2.3 流程层

| 设计 | 评价 |
|---|---|
| **认知链路 6+1 环节**（信号→注意→理解→关联→内化→决策→行动 + 复利）| ✅ 链路完整性是真知灼见，是 hotspot 的"灵魂" |
| **Phase 5 内部 agent → Phase 7 删表** 的迭代 | ✅ 体现了"砍掉累赘"的勇气 |
| **断点续传** (catchup_checkpoints) | ✅ 单机场景下让"补抓"成为可中断的工程 |
| **结构化日志** (`log_collect_event`) | ✅ 让回放、统计、告警成为可能 |
| **4 类数据完整性验证** | ✅ source_regression / time_coverage_gap / category_anomaly / cross_source |

---

## A.3 v1.7 PRD 不足与可砍

### A.3.1 过度设计（应该砍或简化）— v1.7 适度裁剪

> **原则**: 砍掉 v1.7 中"未实施且无 KPI 价值"的设计；保留"未实施但价值明确"的设计为 v1.7 候选；保留"已实施且价值明确"的设计为必选。

| 设计 | 问题 | v1.7 处置 | 备注 |
|---|---|---|---|
| **KL 五阶段**（`kl:raw/refine/link/structure/publish`）| 实际 100% items 有 `lifecycle` 字段但 0% 用 v1.7 5 阶段（100% 用 v1.7 旧 3 阶段值 `generate`/`signal`/`amplify:tagged`）；5 阶段是知识复利的必要骨架 | **完全保留** + 加 5 个自动化触发器 + migration 046 强制命名迁移 | 不应简化 |
| **SAG 事件-实体模型**（`item_entities` 表 + chunks YAML 字段）| 实际未启用 chunks 字段；实体抽取依赖 LLM Agent，hotspot 本地无运行 | **完全保留**：`item_entities` 表 + chunks 字段 v1.7 引入（Hybrid AI 提供本地 LLM 支持）|
| **SAG 命名**（原 Signal-Amplify-Generate）| 与 Zleap-AI/SAG 命名冲突已改 KL，但文档/代码仍残留 | v1.7 全量清理引用 | |
| **kv_cache 表** | v1.7.6 评估后保留为可选，**但**实际无人维护 | **删除**（保留 schema 注释在 docs/）| |
| **6 种认知模式**（简报/扫描/深度/整理/复习/告警）| v1.7 5 个未实施；v1.7 凭借 Hybrid AI + chunks + attention_score 全部实施 | **v1.7 全部实施**（Phase 12 实施 4 种核心 + Phase 16 实施整理/复习；用户明确反对激进裁剪到 3 种）| 6 模式完整闭环 |
| **告警系统 M6** | 整套规则引擎设计未实施 | **保留设计 + 部分实施**：v1.7 实施 3 类基础规则（tech_stack 影响 / 关键 CVE / 标讯命中），v2.1 扩展 | 用户明确要求恢复 |
| **离线间隔摘要** | 设计但未实施 | **v1.7 实施**：catchup 失败恢复后自动生成"昨日未读补丁"摘要 | |
| **快速捕捉 Quick Capture** | 设计但未实施 | **推迟到 v2.2**（浏览器插件开发成本高）| |
| **注意力热图** | 设计但未实施 | **v1.7 引入**（基于 reading_states + LLM，详见 B.4.6）| |
| **决策日志** | 设计但未实施 | **不做**（概念模糊）| |
| **13 个 MCP tool 全量** | `trigger_extract_tags` `trigger_cubox_sync` `create_alert_rule` `mark_digest_read` 是低频/非必要 | **13 → 13**：5 读 + 4 保留 + 4 新增（score_item / enrich_concept / link_items / trigger_codegarden_drift）- 4 移除（trigger_extract_tags / mark_digest_read / create_alert_rule 推迟 / trigger_cubox_sync 改本地 job） | 数量不变，组成优化 |
| **Phase 6 Sync Bundle 扩展** | 4 表同步 schema 复杂 | **简化为 reading_states + favorites + tags + sm2_reviews 四表** | |
| **Phase 5 内部 agent 代码** | 已被 Phase 7 Option A 替代但代码未清干净 | v1.7 **必须清理 `/api/agent/*` deprecated 路由** | 落实 Option A |
| **`/api/agent/*` 路由** | CLAUDE.md 标记为 deprecated 但仍存在 | v1.7 移除 | 落实 Option A |

### A.3.2 缺失设计（v1.7 必须补）

| 缺失 | 原因 | v1.7 解决方案 |
|---|---|---|
| **复利机制无落地** | 知识库 4,147 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段、无法证明复利 | 见 B.8 复利机制 |
| **抓取层没有跨源去重** | Horizon 有 dedup，hotspot 没有 | v1.7 加 LSH/simhash 跨源去重 |
| **没有 AI 评分** | Horizon 0-10 AI 评分；hotspot 仅靠源信任度 | v1.7 用外部 AI Agent 通过 MCP 评分（保持零本地 LLM）|
| **没有背景补全** | Horizon "为陌生概念补充背景" | v1.7 用外部 AI Agent 调 MCP 触发，缓存在 concept.md |
| **没有评论/讨论捕获** | Horizon 抓 HN/Reddit 评论 | v1.7 不做（single-user 不需要社区评论）|
| **没有 daily digest 自动生成** | 用户每天 50-200 篇无摘要 | v1.7 用外部 AI Agent 每日生成 .md 日报，存到 `knowledge/summaries/daily/` |
| **Codegarden 与 knowledge 联动弱** | Codegarden 项目的 tech_stack 应自动从 knowledge 推 | v1.7 加 `tech_stack_drift` 任务：知识库新概念→触发项目技术栈重评估 |
| **Security Graph 与 knowledge 隔离** | CVE/ATT&CK 节点在 security 库，相同概念在 knowledge 库重复 | v1.7 统一 entity 命名空间，security 节点引用 knowledge concepts |

### A.3.3 必要性审视（哪些章节是必需的？）

> **v1.7 章节保留原则**：保留 v1.7 全部 17 章骨架，但**精简内容**而非删除章节；保留所有"反映 hotspot 设计灵魂"的章节（用户旅程、6 种认知模式、告警系统设计）。

| 章节 | 必要性 | 理由 | v1.7 处置 |
|---|---|---|---|
| §0 版本概述 | ✅ 必 | 定位 + 原则 | 简化为 0.5 段 |
| §1 用户旅程 | ✅ 必 | 8 时段工作流是设计输入 | **保留完整**（去掉冗余截图描述）|
| §2 架构 | ✅ 必 | 决策树需要 | 简化为 1 图 + 1 表 |
| §3 数据模型 | ✅ 必 | 实现基线 | 保留 13 张表 + 4 张新表 |
| §4 API | ✅ 必 | 实现基线 | 保留 endpoint 列表 + 关键 schema |
| §5 MCP | ✅ 必 | v1.7 核心 | 完整保留 13 tool |
| §6 功能规格 | ✅ 必 | 6 种认知模式 + 复利机制描述 | **保留**（按 8 时段 × 6 模式组织）|
| §7 调度器 | ✅ 必 | 实现基线 | 保留表 + 新增 5 触发器 |
| §8 前端 | ✅ 必 | 实现基线 | 保留关键组件 + 路由 |
| §9 同步 | ✅ 必 | 实现基线 | 保留 4 表同步设计 |
| §10 迁移 | ✅ 必 | 每次重大升级必有 | 完整保留 |
| §11 测试 | ✅ 必 | 实现基线 | 保留核心指标 + 关键 case |
| §12 Phase | ✅ 必 | 实施计划 | 完整保留，8-14 Phase |
| §13 验收 | ✅ 必 | 量化标准 | 完整保留 |
| §14 风险 | ✅ 必 | 风险评估 | 保留 12-15 条 |
| §15 术语 | 🟡 收 inline | 散落到 inline 即可 | 移除独立章节，inline 解释 |
| §16 Phase 7 MCP 单独章节 | ✅ 必 | v1.7.6 重大决策 | 保留为 §5 的子章节 |

**v1.7 PRD 共 2193 行 → v1.7 PRD 当前 4087 行（+86%；因补全 KL 5 阶段 + 5 触发器 + Hybrid AI + Chunks/Attention + 资讯收藏聚合视图 + 规划引导 + 6 张新表 + 附录 E/F 审计归档等模块；远期可精简到 2500-3000 行）**

---

## A.4 Horizon 借鉴分析

### A.4.1 Horizon 核心架构（流程图）

```
config(信息源/阈值/模型/语言/分发)
  │
  ▼
fetch → dedup → score(AI) → enrich(背景) → summary(AI)
  │                                              │
  ▼                                              ▼
sources: RSS/HN/Reddit/TG/Twitter/GitHub/OpenBB   outputs: Pages/Email/Webhook/MCP
```

### A.4.2 关键借鉴点

| Horizon 设计 | hotspot v1.7 借鉴 | 收益 |
|---|---|---|
| **JSON 配置驱动**（信息源/阈值/模型/语言/分发）| hotspot 用 `proxy_config.json`，可扩展为 `pipeline_config.json`（sources/thresholds/outputs）| 单文件可版本化、可分享、零代码改配置 |
| **共享 `httpx.AsyncClient`** | hotspot 已有 `ProxySession`，但每个 collector 自建 → 提取为 `BackendSession` 注入 | 减少连接建立、降低反爬检测 |
| **`fetch(since)` 增量抓取接口** | hotspot 已有 24h checkpoint，但接口不统一 → 标准化 `BaseCollector.collect(since, until)` | 断点续传天然支持 |
| **可读 ID `{source}:{subtype}:{native_id}`** | hotspot 用 hash ID（`a1b2c3d4`）不可读 → 改为 `gh:release:abc123` / `hn:story:12345` | 调试、跨源去重、log 友好 |
| **跨源去重** | hotspot 无 → 加 simhash + URL canonicalize | 同一新闻 HN/RSS 抓两遍只入库一次 |
| **AI 评分 0-10** | hotspot 靠源信任度 → 引入 MCP `score_item(hotspot_id, score, reason)` 由外部 Agent 调 | 评分可解释、可学习 |
| **背景补全** | hotspot 无 → MCP `enrich_concept(concept_name)` 由外部 Agent 调，缓存到 concept.md | 陌生概念自动有背景 |
| **多输出 Pages/Email/Webhook** | hotspot 只有 Web UI → v2.1 扩展 | 单人场景 Web UI 优先，Email/Webhook 推迟 |
| **MCP 作为输出** | hotspot MCP 是核心协议 → 已有 | ✅ 领先 |
| **daily-run.sh** | hotspot 已有 APScheduler → 但 v1.7 加 daily_digest job | 自动化日报 |
| **url_security.py** | hotspot 已有 FinalUrlGate → 借鉴统一 SSRF/CSRF 防御 | 安全层 |
| **extractors/trafilatura.py** | hotspot 解析靠 regex/lxml → 引入 trafilatura 作为可选 extractor | 提取质量提升 |
| **统一 `models.ContentItem`** | hotspot 多 collector 多 model → 标准化为统一的 `RawItem` | 减少重复代码 |

### A.4.3 Horizon 的不足（不要学）

| 不足 | hotspot 优势 |
|---|---|
| 没有知识库沉淀（输出到 Pages/Email 后就丢）| ✅ hotspot 知识库是核心，**复利源** |
| AI 评分依赖云 LLM（Claude/GPT/Gemini）| ✅ hotspot 用用户已配的外部 AI Agent（本地/云/混合自由）|
| 无断点续传（每次 fetch(since) 全量）| ✅ v1.8 catchup + v1.9 checkpoint 已建 |
| 无数据完整性验证 | ✅ v1.9 4 类验证已建 |
| 无自动反爬恢复 | ✅ source_revival_service 已建 |
| 不支持多用户/多工作空间 | ✅ 单人本地优先，**这是 hotspot 的本** |
| 无 codegarden / security graph | ✅ hotspot 的双核心 |

### A.4.4 借鉴优先级

1. **P0**（v1.7 必做）：统一 `BackendSession` + 可读 ID + simhash 跨源去重
2. **P1**（v1.7 必做）：trafilatura 作为可选 extractor + AI 评分 MCP tool + 背景补全 MCP tool
3. **P2**（v1.7 必做）：JSON pipeline_config 化（最简版，4 个源示例）
4. **P3**（v2.1+）：Email/Webhook 输出、daily digest 自动生成

---

## A.5 第一性原理审视

### A.5.1 hotspot 的本质问题

> "**从信息到知识，再到知识复利的关键中转系统**"（用户原话）

拆解：
- **信息**：来自 46 个源的原始 feed（每天 200-500 条）
- **知识**：从信息中提炼的、可复用的概念（concepts）+ 实体（entities）+ 关联（relations）
- **复利**：知识库越大，**新信息进来时**的"判断"（这是不是新东西？和已有的 X 有关吗？）越快越准

### A.5.2 第一性原理拆解

**1. 采集不是瓶颈**
- 46 源已建立，200-500 条/天
- 真正缺的是"看完能用上"
- **结论**：v1.7 不应继续堆 source，应聚焦"采回来的 N 条如何进入知识库"

**2. 知识的本质是连接**
- 单一 concept 没价值，concept A → B → C 的网络才是复利
- v1.7 设计的"事件-实体"模型是正确方向，但**没落地**
- **结论**：v1.7 必须让 `item_entities` 表活起来

**3. 复利的关键在"读旧写新"**
- 用户每天产出 200-500 条信息，但知识库增长 0 条/天 = 复利断裂
- 4,147 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段 = 全部 items 都用错的旧 3 阶段值
- **结论**：v1.7 必须让"自动入库"成为默认，而不是"手动标记"

**4. MCP 是放大器，不是替代品**
- v1.7 设计：MCP 写 = 外部 AI Agent 主动调
- 实际：用户很少主动打开 AI Agent 调 MCP（需要"触发时刻"）
- **结论**：v1.7 应让"自动触发"成为常态（如：catchup 完成后自动调 MCP 评分 + 入库；用户收藏时自动调 MCP 提炼 concept）

**5. 单人本地优先是约束也是护城河**
- 约束：不能假设有云 LLM、有 Redis、有多用户
- 护城河：99% 的 SaaS 抓取工具（Feedly、Inoreader、NewsBlur）都是云服务，**本地优先是差异化**
- **结论**：v1.7 任何设计都要问"无外部依赖能跑吗？"

### A.5.3 复利系统的关键路径

```
信息采回 → (1) 自动去重 + 评分 → (2) 命中已有 concept? 
                                     │ 是 → 关联到已有 entity，更新 knowledge_items
                                     │ 否 → 新建 concept
                                     ▼
                                  (3) 自动写 .md + 触发 SOUL 更新
                                     │
                                     ▼
                                  (4) 复利可见：今天新进了 5 条，
                                      3 条与已有 concept 关联
```

**v1.7 没有 (1)(2)(3) 的自动化**，全靠手动。v1.7 必须打通。

---

## A.6 hotspot 中转系统定位

### A.6.1 一句话定位

> hotspot 是**单人的本地"信息→知识→复利"中转站**：把 46 源原始信息自动降噪、跨源去重、AI 评分、提炼概念、连接已有知识、让知识库每天自动增长，让用户的判断越来越快。

### A.6.2 与竞品对比

| 维度 | hotspot v1.7 | Horizon | Feedly | Notion AI | Obsidian + 插件 |
|---|---|---|---|---|---|
| 本地优先 | ✅ 单机单进程 | ❌ 云优先 | ❌ 云 | ❌ 云 | ✅ 但无抓取 |
| 多源抓取 | ✅ 46 源 | ✅ 7 源 | ✅ | ❌ 手动 | ❌ 手动 |
| AI 评分 | ✅ MCP 下放 | ✅ 云 LLM | ✅ 云 | ✅ 云 | ❌ |
| 知识库沉淀 | ✅ 4147+ items 持续增长 | ❌ 输出即丢 | ❌ 无 | ✅ 但无自动 | ✅ 但手动 |
| 知识复利 | ✅ 目标 v1.7 | ❌ | ❌ | ❌ | ❌ |
| 跨源去重 | ✅ simhash v1.7 | ✅ | ✅ | N/A | N/A |
| MCP 协议 | ✅ 13 tool | ✅ | ❌ | ❌ | ❌ |
| 配套子系统 | ✅ Codegarden + Security Graph | ❌ | ❌ | ✅ | ❌ |

**差异化**：hotspot 是**唯一**同时具备"本地优先 + 多源 + AI + 知识沉淀 + 复利 + MCP + 配套子系统（项目管理 + 安全图谱）"的系统。

### A.6.3 三大子系统的协同

```
SecNews (采集/聚合)
    │ 降噪 + 去重 + 评分后入库
    ▼
Knowledge (沉淀/复利)
    │ 提取的 concept 驱动
    ▼
CodeGarden (项目落地)
    │ tech_stack 漂移检测
    ▼
Security Graph (安全图谱)
    │ CVE/ATT&CK 节点引用 knowledge concepts
    ▼
(MCP 出口给外部 AI Agent)
```

v1.7 必须打通这 4 个环，让 1+1+1+1 > 4。

---

## B.0 产品战略审计（2026-07-27 团队产出）

> **来源**: `WorkBuddy/2026-07-27-10-11-21/deliverables/product-strategy/prd-hotspot-v2-2026-07-27.md`（产品战略团队 AI 协作产出）
> **参与成员**: 方向明（主理人/编排）、瑞思（用户研究员）、竞析（竞品分析师）、数析（数据分析师）、析客（需求分析师）、路径（路线图规划师）
> **性质**: 战略层审计结论，为 Part B 的设计章节提供需求侧/用户侧/竞品侧/数据侧的输入；设计实现细节仍以 Part B 的 B.1-B.13 章节为准。

### B.0.1 TL;DR 与核心结论卡片

**TL;DR（执行摘要，3-5 行）**:

- **核心目标**：hotspot v1.7 从"采集导向"转向"复利导向"——让每天 200–500 条新信息自动沉淀、复用、产生复利，而非继续堆采集源。
- **关键决策**：保留 KL 五阶段 + 引入 5 自动化触发器（T1–T5）强制推进生命周期；引入 simhash 跨源去重；MCP 叙事从"支持 MCP"升级为"AI Agent 可读写你的本地知识库"。
- **依据**：v1.7 采集层已成熟（46 源/28 活跃），但 4,147 条 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段（实际 100% 用 v1.7 旧 3 阶段 `generate`/`signal`/`amplify:tagged`）、知识库日增量≈0——瓶颈在消费端，不在采集端。
- **下一步**：以 M1（复利基础设施+闭环核心，P0 全部交付）为硬承诺里程碑，知识库日增量目标 ≥10/天、新信息复用率 ≥30%。

**核心结论卡片**:

| 项目 | 内容 |
|------|------|
| 推荐方案 | 建立"信息→知识→复利"自动闭环：simhash 去重 + 4 张新表 + T1/T2 触发器先发（P0），T3/T4/T5 与可视化渐进（P1），体验项后置（P2） |
| 优先级 | P0（must，8 条）/ P1（should，9 条）/ P2（could，7 条），共 24 条需求 |
| 预期影响 | 知识库日增量 ≈0 → ≥10/天；新信息复用率 ≈0% → ≥30%；v1.7 5 阶段 lifecycle 应用率 0% → migration 046 迁移后 100% |
| 资源需求 | 单人本地优先服务，46 天密集交付（设计目标）；M1 为硬承诺，M2–M4 设缓冲 |
| 风险等级 | 中（单人资源约束 + Horizon 开源逼近 + 本地 LLM 硬件门槛，均有缓释策略） |

### B.0.2 三个产品目标（与 B.1.2 北极星指标对齐）

从"复利导向"提炼三个彼此正交的产品目标，与北极星指标（知识库日增量 ≥10/天、新信息复用率 ≥30%、MCP P95 <500ms）对齐：

**目标①：建立"信息→知识→复利"自动闭环（复利飞轮）**
让每天 200–500 条新信息自动经过降噪、去重、评分、关联、结构化、发布，沉淀进本地知识库。直接对标本北极星"知识库日增量 ≥10/天"与"新信息复用率 ≥30%"，解决 100% items 用 v1.7 旧 3 阶段（应迁 v1.7 5 阶段）的核心断点。

**目标②：强化"本地优先 + 可自我读写"差异护城河（架构护城河）**
坚守 .md + SQLite 单进程本地优先、可 Obsidian 直读、数据主权与离线可用；以"MCP 写知识图谱的操作协议（score_item / enrich_concept / link_items）"区别于竞品的只读 MCP。对标本北极星"MCP tool P95 <500ms"与可读 ID 规范化，构成 Horizon / Feedly / Cubox 难以复制的蓝海。

**目标③：打通知识库与 Codegarden / Security Graph 双子系统联动（垂直纵深）**
知识提炼出的 tech_stack / CVE 实体自动触发 Codegarden 技术栈漂移评估与 Security Graph 双向同步，让三个子系统在单人工作流里互相喂养。这是竞品完全没有的纵深，也是付费验证的差异化锚点。

> 三者正交性：①是价值产出（知识是否增长），②是架构与差异化根基（谁不可替代），③是价值放大（知识是否联动其它系统）。互不为手段，各自独立可度量。

### B.0.3 用户故事（5 个核心场景）

- 作为安全从业者，我希望新信息入库后系统自动评分、去重、打标签，以便我打开 dashboard 时只看到值得关注的热点，而无需自己逐条筛选 200–500 条 feed。
- 作为研究者，我希望收藏一篇文章后系统自动把它关联到知识库里已有的 concept，以便知识的连接是"长出来"的而非我手动维护的。
- 作为告警响应者，我希望 08:15 出现 CVE/0-day 时能一键创建待办并评估技术栈影响，以便紧急响应不掉链子。
- 作为复盘者，我希望每天 17:00 看到"今日新增 N 条、提炼 M 个概念、建立 K 个关联"的复利可视化，以便清楚感知自己的知识是否在增长。
- 作为拖延型整理者，我希望系统在 dashboard 顶部用 KnowledgePlanningPanel 告诉我"现在该评分 10 条、复习 5 条、清理 3 条 stale 知识"，以便整理负担被切成一个个可执行的小动作。

### B.0.4 用户研究洞察（来自瑞思）

**核心用户画像**: hotspot v1.7 的核心用户是"以知识为生产力的单机安全从业者"——参考品牌 SecNews，典型画像为拥有约 10 年攻防演练与咨询经验的安全老兵，关注 AI 安全、网络安全、安全从业转型与安全规划建设运营。工作环境高度本地化：单机作业、无团队协作假设、强烈的数据隐私诉求，这与 v1.7"本地优先（.md + SQLite，Obsidian 可直读）"的架构天然契合。核心诉求经历了一次本质迁移——从"把 46 个源的信息采回来"转向"采回来的东西每天能自动沉淀、复用、并产生复利"。其真实工作流高度规律：早上看热点 → 收藏 → 周末/晚间手动整理写 SOUL、提炼 concept → 写代码时检索触发 Todo/Codegarden；这一链路目前在每个"→"处都依赖人工，是 v1.7 必须自动化的断点。

**核心痛点与未被满足需求**: 草案数据揭示三个结构性断点：① 复利断裂：4,147 个 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段（100% 用 v1.7 旧 3 阶段值 `generate`/`signal`/`amplify:tagged`）；② 知识库日增量≈0：每天 200–500 条新信息进来，能进入 knowledge/items/ 的几乎为零；③ 手动整理负担重：周末/晚间手动整理、写 SOUL、提炼 concept 全靠人，MCP 13 tool 中 4 个低频（缺触发时刻）。未被满足需求：用户要的不是更多源，而是"采回来的 N 条如何自动进入知识库"以及"知识的本质是连接"。

**对 v1.7 关键设计的用户价值验证**:

- KL 五阶段 + 5 自动化触发器 + migration 046 命名迁移：直接命中断点。T1 解决"卡在 raw"、T2 解决"连接靠手建"、T3/T4 把结构化+发布默认化、migration 046 把 v1.7 旧 3 阶段值统一到 v1.7 5 阶段。100% items 用 v1.7 旧 3 阶段不是阶段本身的问题，而是命名未统一 + 没有触发器——验证保留 5 阶段。
- 复利机制：把"新信息进来时系统能认出它与已有知识的关系"显性化为 L1/L2/L3 三层 + 断点检测，满足复盘者场景。
- KnowledgePlanningPanel：针对"手动整理负担重 + 缺乏触发时刻"，把整理切成优先级 1–5、可关闭、可观测的小动作，降低行动门槛。

**用户分层 / 分群建议**:
1. **重度研究者**（SecNews 原型）：概念提炼/知识图谱/双子系统联动，是复利机制主用户，应作北极星样本。
2. **轻量浏览/告警响应者**：T1 自动降噪+告警模式为主，对整理/复习需求弱，需零负担路径。
3. **规划驱动型拖延用户**：依赖规划引导 nudges，是提升 lifecycle 覆盖率的杠杆人群。

> 建议验收分别追踪"重度研究者知识库日增量"与"轻量浏览者 kl:raw→refine 自动化率"。

### B.0.5 竞品对比（来自竞析）

**竞品全景图**:

- **Horizon**（开源自托管）：AI 新闻雷达，把 HN/Reddit/RSS/Telegram/GitHub/OpenBB 揉成双语日报；目标＝想掌控来源与模型的自托管研究者。
- **Feedly**（云 SaaS）：RSS + Leo AI 情报平台，面向竞情/安全分析团队。
- **Inoreader**（云 SaaS）：RSS/社媒/YouTube/Newsletter 聚合 + Intelligence，面向重度订阅研究者。
- **Obsidian + 插件**（本地优先）：Markdown 双向链接知识库，面向个人知识管理（PKM）用户。
- **Notion AI**（云 SaaS）：块数据库式"第二大脑" + AI Agent/MCP，面向团队知识协作。
- **Cubox**（云 SaaS）：AI 稍后阅读助手，跨端收藏 + 全库问答 + 主题关联，面向中文深度阅读者。
- **Readwise Reader**（云 SaaS）：阅读 + 高亮 + 间隔重复 + Ghostreader AI，面向主动标注型读者。

**功能对比矩阵**:

| 维度 | hotspot | Horizon | Feedly | Inoreader | Obsidian | Notion | Cubox | Readwise |
|---|---|---|---|---|---|---|---|---|
| 本地优先 | ✅ | 部分 | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| 多源自动抓取 | ✅46 | ✅7 | ✅ | ✅ | ❌ | ❌ | 部分 | 部分 |
| AI 评分 | ✅MCP | ✅0-10 | ✅ | 部分 | 部分 | ✅ | ✅ | ✅ |
| 知识沉淀 | ✅ | ❌ | ❌ | 部分 | ✅ | ✅ | ✅ | ✅ |
| 知识复利 | ✅ | ❌ | ❌ | 部分 | 部分 | ❌ | 部分 | 部分 |
| 跨源去重 | ✅ | ✅ | ✅ | 部分 | N/A | N/A | 部分 | 部分 |
| MCP 协议 | ✅13 | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |
| 配套子系统 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

> 注：2025–2026 MCP 已成入场券，但竞品 MCP 多为读取/检索接口；唯 hotspot 的 MCP 是写入知识图谱的操作协议（score_item / enrich_concept / 建立 relation）。

**SWOT 分析**:

- **优势**: 唯一同时满足"本地优先+46源自动抓取+AI评分+持续增长知识库+知识复利+MCP知识写入+双子系统"，本地优先带来数据主权与离线可用，知识复利是真正飞轮。
- **劣势**: ①纯单人定位放弃最大付费市场；②本地优先抬高上手门槛；③Horizon 已开源且功能逼近；④MCP 不再稀缺，叙事需从"支持 MCP"升级为"MCP 写知识"。

**差异化机会**:

- **坚决强化（蓝海）**: ①知识复利引擎——把"读旧写新"做成默认自动（无人区）；②本地优先+46源自动抓取组合；③双子系统垂直纵深。
- **不必硬刚（红海）**: ①多端云同步体验（交给 Cubox/Readwise，hotspot 保本地可导出）；②团队协作与权限（主动放弃）；③通用阅读/标注 UI；④"支持 MCP"本身（已成标配）。

**行动建议**:

1. v1.7 优先级压在"知识复利自动闭环+跨源去重+AI评分 MCP 工具"，而非新增抓取源。
2. 对外叙事升级为"AI Agent 可读写你的本地知识库"。
3. 防守 Horizon：突出本地优先+知识沉淀+双子系统。
4. 提供到 Obsidian/Cubox/Readwise 的导出与只读桥。
5. 用 1–2 个垂直场景（安全研究/个人技术雷达）做付费验证，确认单人付费意愿后再决定是否开放轻量协作。

### B.0.6 数据依据与北极星指标（来自数析）

**当前指标基线（v1.7 实施快照，2026-07-26）**:

| 指标 | 实际 | 目标 | 完成度 |
|---|---|---|---|
| 知识库 items 累计 | 4,147 | 无上限 | ✅ |
| concepts 累计 | 97 | 持续扩展 | ✅ |
| 应用 lifecycle 字段 items | 4,147/4,147 = 100% | 100% | ✅ 字段已建 |
| 应用 v1.7 5 阶段 lifecycle items | 0/4,147 = 0% | 100%（迁移后）| ❌ 老数据全用 v1.7 旧 3 阶段 |
| lifecycle 实际取值分布 | generate: 74 / signal: 4,070 / amplify:tagged: 3 | 5 阶段全替换 | ❌ 与 v1.7 5 阶段 100% 不一致，需 migration 046 |
| 采集源 | 46（28 活跃） | — | ✅ 成熟 |
| MCP tool | 13（5 核心+8 低频） | — | ✅ |
| 知识库日增量 | ≈0 | ≥10/天 | ❌ |
| 新信息复用率 | ≈0% | ≥30% | ❌ |
| 跨源去重准确率 | 未实现 | ≥95% | ❌ |

> **关键缺口分析**: 采集层已成熟（46源/28活跃+全套验证防抖），但 4,147 条 100% 有 lifecycle 而 0% 用 v1.7 5 阶段（实际 100% 用 v1.7 旧 3 阶段值）。问题重心已从"采得回"转移到"采回来之后怎么用"。日增量≈0、复用率≈0 是这一断裂的量化结果。这构成 v1.7 从采集导向转向复利导向的唯一决策依据。

**北极星指标定义与测量**:

| 指标 | 定义 | 当前值 | 目标值 | 测量来源 |
|---|---|---|---|---|
| 知识库日增量 | 每日新发布 kl:publish items | ≈0 | ≥10/天 | knowledge_items 新增 + metrics:kl_transition{to=publish} |
| 新信息复用率 | 新信息中与已有 concept 关联比例 | ≈0% | ≥30% | T2 写 knowledge_links ÷ 新 items |
| MCP 调用 P95 | 13 tool 调用耗时 P95 | 保持预算 | <500ms | mcp_tool_registry 埋点 |
| 跨源去重准确率 | simhash Hamming<5 判同准确率 | 未实现 | ≥95% | content_fingerprints 抽样 |
| 评分后入库延迟 | T1 去重→评分→入库 | — | <5min | ingest_pipeline_logs |
| 收藏聚合视图 P95 | 合并响应 | — | <300ms | 服务层 merge 计时 |

**关键决策点数据支撑**:

1. **为何不再堆 source**: 采集已成熟，但 0% 用 v1.7 5 阶段、复利闭环未建立、日增量≈0，新增源边际收益趋零，瓶颈在消费端。
2. **为何引入 5 触发器 + migration 046**: v1.7 设计 KL 五阶段但没触发器 + 100% items 用 v1.7 旧 3 阶段值命名不一致，强制推进 + 命名迁移（migration 046）一并修复，把脚手架变可执行管线。
3. **为何 simhash 去重**: v1.7 抓取层无跨源去重，同新闻抓两遍污染知识库，simhash+Hamming<5 是达成≥95% 的前提。

### B.0.7 需求池（P0 × 8 / P1 × 9 / P2 × 7 = 24 条）

> 战略层需求清单；实施期 Phase 划分见 B.10。

| 编号 | 需求 | 优先级 | 验收标准 | 估算 |
|---|---|---|---|---|
| P0-1 | simhash 跨源去重 | P0 | 64-bit simhash + URL canonicalize + Hamming<5；1000 条样本去重准确率 ≥95%；评分后入库延迟 <5min | Phase 8 |
| P0-2 | 新增 4 张数据表 | P0 | content_fingerprints / ai_scores / item_entities / knowledge_links schema 校验通过、CRUD 全过；ai_scores 写入 P95 <500ms | Phase 8 |
| P0-3 | T1 触发器 raw→refine | P0 | 60s 调度；100 条样本 ≥95% 推进到 refine；评分<阈值自动 archive；失败指数退避 3 次入死信 | Phase 10 |
| P0-4 | T2 触发器 refine→link | P0 | 120s 调度；≥80% 找到 ≥1 关联 concept；Agent 未响应保留 pending_link 队列 | Phase 10 |
| P0-5 | AI 评分 MCP tool（score_item） | P0 | 外部 Agent 调通；score≥7 触发 T1、<5 自动 archive；P95 <500ms；一次调用完整+失败兜底 | Phase 8 |
| P0-6 | 知识库自动入库（日增量） | P0 | 30 天平均知识库日增量 ≥10 items/天；新信息复用率 ≥30% | Phase 10–12 |
| P0-7 | 可读 ID 规范化 | P0 | {source}:{subtype}:{native_id} 工厂；100% 旧 hash ID 可映射；MCP 13 tool 兼容不变 | Phase 10 |
| P0-8 | 遗留清理 | P0 | 删除 kv_cache 表、/api/agent 路由、4 个低频 MCP tool；迁移指南与 CHANGELOG 完整 | Phase 14 |
| P1-1 | T3/T4/T5 触发器 | P1 | T3(600s)关联≥3 的 100% 推进 structure；T4(1800s)score≥8 的 100% 发布；T5 回滚 100% 不丢用户编辑 | Phase 11 |
| P1-2 | 3 类基础告警 | P1 | tech_stack 影响 / 关键 CVE(CVSS≥9.0) / 标讯命中 三类规则可触发；AlertCenter Inbox 渲染 | Phase 11 |
| P1-3 | 资讯收藏聚合视图 | P1 | 5 数据源合并+去重+分页；P95 <300ms；5 类型筛选+搜索+时间+分页 e2e 8 用例通过 | Phase 8 |
| P1-4 | 复利仪表盘 | P1 | KnowledgeCompoundingDashboard 渲染日/周/月趋势 + top concepts + 断点告警（7 天无推进告警） | Phase 12 |
| P1-5 | 4 模式 UI（简报/扫描/深度/告警） | P1 | BriefingMode / ScanMode / DeepReadMode / AlertMode 渲染；简报含一句话摘要+3 篇关键文章+数据源状态 | Phase 12 |
| P1-6 | KnowledgePlanningPanel 规划引导 | P1 | 基于 reading_states+lifecycle+KL 状态生成优先级 1–5 动作；可关闭可观测；planning_action_check 10min job | Phase 12 |
| P1-7 | Hybrid AI（LLMService + Crawl4ai） | P1 | 多 provider（Ollama/Qwen/OpenAI）；Crawl4ai 4 源成功率 ≥80%；T1/T3 延迟降 ≥60%/40%；5 降级场景全过 | Phase 15 |
| P1-8 | 抓取层 6 个新 collector | P1 | hn / reddit / openbb / telegram / gdelt / ossinsight 各 5 用例通过；BackendSession 注入 + trafilatura fallback | Phase 10 |
| P1-9 | 子系统联动（drift / cve_sync） | P1 | tech_stack_drift 触发并评估；Security.cve_nodes 双向同步去重；跨域 entity 命名空间生效 | Phase 13 |
| P2-1 | 注意力热图 | P2 | 30 天×3 时段热图渲染；attention_score 5 维度加权；30min 聚合 job 写回 frontmatter | Phase 16 |
| P2-2 | 整理/复习（SM-2）模式 | P2 | OutboxMode + ReviewMode(SM-2) UI；sm2_reviews 卡片翻转入库、下次复习时间计算正确 | Phase 16 |
| P2-3 | chunks 字段 | P2 | knowledge_chunks 表 + chunks_meta 写回 .md frontmatter；chunk 级 FTS5 搜索返回 chunk_index | Phase 16 |
| P2-4 | Twitter / X 抓取 | P2 | 借鉴 Horizon twitter_playwright；推迟至 v2.1 | v2.1 |
| P2-5 | Email / Webhook 输出 | P2 | 单人 Web UI 优先，推迟至 v2.1 | v2.1 |
| P2-6 | Quick Capture 插件 | P2 | 浏览器插件开发成本高，推迟至 v2.2 | v2.2 |
| P2-7 | 向量化语义搜索 | P2 | 本地优先 FTS5 已够用，永久不做 | 不做 |

> **统计**: P0 ×8、P1 ×9、P2 ×7，共 24 条。P0 全部对应复利闭环核心与本地优先根基；P1 补齐闭环尾部、可视化、Hybrid AI 与双子系统联动；P2 为体验增强与明确推迟项。

### B.0.8 Non-goals（v1.7 明确不做什么）

1. **不做团队协作 / 多用户 / 权限体系**——坚守单人本地定位，主动放弃最大付费市场。
2. **不新增云端同步以替代 Cubox / Readwise**——仅保本地可导出与只读桥，多端体验交给云端竞品。
3. **不堆砌新增抓取源**——采集层已成熟（46 源 / 28 活跃），瓶颈在消费端，新增源边际收益趋零。
4. **不做内部 AI agent 进程**——已被 MCP 写协议（Option A）+ Hybrid AI 替代。
5. **不做向量数据库 / Embedding**——本地优先场景下 FTS5 全文检索已足够。
6. **不默认自动建立 knowledge_links（无需确认）**——v1.7 需 AI Agent 经 link_items 确认，错误链接伤害信任，v2.1 再自动化。
7. **不默认把 0–10 热点评分自动应用**——v1.7 评分先存待人工确认，用户对 AI 评分信任需累积，v2.1 再自动应用。
8. **评分未通过的信息不自动写 .md 进知识库**——仅 score ≥ 阈值才入库。
9. **Twitter / X 抓取推迟到 v2.1**——反爬强，先做 6 个新 collector。
10. **Quick Capture 浏览器插件推迟到 v2.2**——插件开发成本高，非复利核心。
11. **Email / Webhook 多输出推迟到 v2.1**——单人 Web UI 优先。
12. **决策日志永久不做**——概念模糊、无明确 KPI 价值，已确认砍除。

> 与 B.9 不做清单交叉引用：B.9 章节是 PRD 设计侧的实现级不做清单（12 条），本节是战略层的非目标清单（12 条），二者同源（均锚定"单人本地优先 + 复利闭环"）但视角不同。冲突时以 B.0.8 战略意图为准、B.9 设计落实。

### B.0.9 时间线与里程碑（来自路径）

> hotspot v1.7 为常驻本地优先服务，采用 46 天密集交付（设计目标，非承诺计划）。下表以"阶段"替代日历季度；若映射季度可视为相对时间（M1≈D1–18、M2≈D19–28、M3≈D29–34、M4≈D35–46），但实际以交付里程碑为准，不绑定日历。Phase 8–16 的具体周期见 B.10。

**里程碑归并（4 个交付阶段）**:

- **M1 复利基础设施 + 闭环核心（P0 must）**：打通"信息→知识→复利"主链路的数据与触发器地基，清遗留，达首轮可发布。
- **M2 闭环尾部 + 可视化 + 规划引导（P1 should）**：补全触发器尾部与告警，交付用户可见的复利仪表盘与规划引导。
- **M3 抓取现代化 + 子系统联动（P1 should）**：扩展数据源并打通双子系统联动。
- **M4 现代化增强 Hybrid AI + 体验闭环（P1/P2）**：引入可选 Hybrid AI，收口体验增强项。

**标准路线图表**:

| 阶段（相对时间） | 主题 | 关键交付（需求编号） | 负责人 | 风险 |
|---|---|---|---|---|
| M1（~D1–18） | 复利基础设施+闭环核心 | P0-1 simhash去重、P0-2 四张新表、P0-5 评分MCP、P0-3 T1、P0-4 T2、P0-6 知识库日增量(起始)、P0-7 可读ID、P0-8 遗留清理；附 P1-3 收藏聚合视图 | 主理人(全栈/后端主导) | 单人46天现实性；本地LLM门槛；清理迁移兼容性 |
| M2（~D19–28） | 闭环尾部+可视化+规划引导 | P1-1 T3/T4/T5触发器、P1-2 三类告警、P0-6 日增量(收尾)、P1-4 复利仪表盘、P1-5 四模式UI、P1-6 规划引导 | 主理人(全栈/前端主导) | UI工作量低估；覆盖率回升节奏 |
| M3（~D29–34） | 抓取现代化+子系统联动 | P1-8 抓取层6新collector、P1-9 tech_stack_drift/cve_sync联动 | 主理人(全栈/抓取层主导) | 源稳定性；联动数据质量 |
| M4（~D35–46） | Hybrid AI+体验闭环 | P1-7 LLMService+Crawl4ai、P2-1 注意力热图、P2-2 SM-2整理/复习、P2-3 chunks字段 | 主理人(全栈) | 本地LLM硬件门槛；体验项可延后至v2.1 |

> 注：Phase 10 按优先级拆分——P0-7(可读ID, must)并入 M1，P1-8(collector, should)并入 M3；单人串行排期下实际顺序为 M1→M2→M3→M4。

**优先级排序逻辑**:

- **P0（must）先发**：Phase 8/9、P0-7(Phase 10)、P0-8(Phase 14) 构成复利闭环核心，是差异化壁垒与价值地基，**必须**在 M1 内全部达到可发布。P0-8 清理虽排至 Phase 14 时段，但作为"首轮发布门禁"，不阻塞新功能开发。
- **P1（should）渐进、顺序可调**：草案 B.10.11 明示 P1 顺序可调整。强 should（T3/T4/T5+告警，闭环尾部）优先于纯可见价值（仪表盘/UI）；抓取现代化与子系统联动作扩展性补充置于 M3。
- **P2（could）严格后置或放弃**：Phase 16 体验项置 M4 末；Twitter/X(v2.1)、Email/Webhook(v2.1)、Quick Capture(v2.2) 明确推迟到后续版本；向量化语义搜索(P2-7) 永久不做，从路线图移除。

**关键里程碑节点**:

1. **M1 完成 = 复利闭环打通**：simhash 去重上线、T1/T2 运行、知识库日增量开始 **>0**、可读ID定调、遗留清理完成 → 首轮可独立发布。
2. **M2 完成 = 用户可见复利**：闭环尾部(T3/T4/T5+告警)收口，复利仪表盘与 KnowledgePlanningPanel 规划引导上线，价值可对外展示。
3. **M3 完成 = 抓取与联动现代化**：6 新 collector 接入，tech_stack_drift/cve_sync 双子系统联动打通。
4. **M4 完成 = 6 模式完整 + Hybrid AI 可选**：简报/扫描/深度/告警 + 收藏/规划 六模式齐备，Hybrid AI 在本地硬件达标时可选启用，注意力热图/SM-2 体验闭环收口。

**依赖关系与关键路径**:

- **关键路径**：P0-2 四张表 → P0-1 去重/P0-5 评分 → P0-3 T1 → P0-4 T2 → P0-6 日增量(Phase 10–12) → P1-1 T3/T4/T5 → P1-9 联动 → P1-7 Hybrid AI → P2 体验项。整链串行，是 46 天基线。
- **强前置**：T1/T2(P0-3/4) 是后续所有触发器(T3/T4/T5)与知识库日增量的前置，须 M1 内完成；P0-2 表结构是 P0-5/去重/实体链接的底座。
- **弱依赖/可并行**：P1-3 收藏视图、P1-8 collector 不阻塞主链，可在对应阶段早期并行；P0-8 清理独立于新功能，仅受"发布门禁"约束。

**风险标注**:

1. **单人资源约束**：46 天连续密集交付对单人是否现实存疑。建议 M1 为硬承诺，M2–M4 设渐进缓冲；M4 的 P2 体验项若延期可顺移至 v2.1，不破闭环。
2. **Horizon 开源逼近**：防守压力下 P0 复利闭环须先发建立壁垒；P2 体验项（热图/SM-2）后置，避免与开源正面竞争，聚焦差异化。
3. **本地 LLM 硬件门槛**：P0-5 评分 MCP 与 P1-7 Hybrid AI 依赖本地推理，低端设备可能无法运行 → 需提供云端降级/可选路径，不将本地 LLM 设为闭环硬依赖。
4. **覆盖率回升节奏**：P0-6 日增量 M1 即 >0，但达稳态生命周期覆盖率需数周爬坡，仪表盘指标应在 M2 即呈现"回升中"而非"已达标"。
5. **清理迁移风险**：P0-8 删低频 tool + 迁移指南须保证向后兼容，避免破坏既有自动化；建议 M1 末以灰度方式执行。

### B.0.10 关键流程图与 UI 草图（战略视角统一视图）

> 本节是审计报告 §7 流程图与 UI 草图的战略层摘要。详细设计在 B.6.1 (KL 状态机)、B.6.3 (5 触发器调度)、B.6.7 (KnowledgeFavoritesView)、B.9.5 (8 时段用户旅程与 6 模式 UI) 中展开。

**(a) 信息复利主链路（KL 五阶段状态机）** — 详见 B.6.1：

```
collect ──▶ dedup(simhash) ──▶ ai_score ──▶ ingest
                                         │
        T1 (60s, ≥95%)   raw ──────────▶ refine
                                         │
        T2 (120s, ≥80%)  refine ───────▶ link
                                         │
        T3 (600s, ≥70%)  link ─────────▶ structure
                                         │
        T4 (1800s, ≥50%) structure ────▶ publish  ──▶ 复利沉淀
                                         ▲
        T5 (用户回滚)     publish ◀──────┘  stale 标记 + 重跑 T1
```

**状态机不变量**：任何 `kl:publish` 必经历 T1–T4；任何 `kl:link` 必含 ≥1 个 `item_entity`。

**(b) 5 触发器调度架构** — 详见 B.6.3：

```
┌────────────────────────────────────────────────────┐
│  APScheduler（单进程，30 jobs 实测）                  │
│  T1 Interval 60s   T2 Interval 120s                 │
│  T3 Interval 600s  T4 Interval 1800s  (T5 无调度)   │
└───────────┬──────────┬──────────┬───────────────────┘
            ▼          ▼          ▼
      KLStateMachine（记录 lifecycle / 决定下一态 / 写 transition log）
            ▼          ▼          ▼
      RetryPolicy（指数退避 1/2/4/8/16s，3 次失败入死信，24h 重试 1 次）
            ▼          ▼          ▼
   metrics:kl_transition + pending_link 队列 + 死信表（可观测）
```

**(c) 关键 UI 组件 + Dashboard 草图** — 详见 B.9.5 / B.6.7：

| 组件 | 职责 |
|---|---|
| KnowledgeCompoundingDashboard | 今日新增 items / concepts / links + 30 天趋势 + 断点告警 |
| KnowledgeFavoritesView | 5 数据源收藏聚合（合并+去重+分页+筛选） |
| KnowledgePlanningPanel | 顶部规划引导：评分 N / 复习 M / 清理 K（优先级 1–5） |
| BriefingMode | 每日首次打开：一句话摘要 + 3 篇关键文章 + 数据源状态 |
| AlertCenter | 告警 Inbox + 红色横幅（CVE / tech_stack / 标讯） |
| KLTriggerBadge | 详情页 5 阶段进度条 + 当前 lifecycle 状态 |

```
┌─ Dashboard 顶部 ──────────────────────────────────┐
│ KnowledgePlanningPanel                             │
│  评分 10 ▸ 复习 5 ▸ 清理 3 stale      [全部展开]    │
├───────────────────────┬───────────────────────────┤
│ KnowledgeCompounding  │  KLTriggerBadge            │
│ Dashboard             │  raw→refine→link→struct   │
│  今日 +12 items       │  →publish [✓][✓][✓][ ][ ] │
│  今日 +3 concepts     │                           │
│  今日 +28 links       │  AlertCenter（红色横幅）  │
│  [ 30 天趋势图 ]      │  🔴 CVE-2026-XXXX CVSS 9.1│
└───────────────────────┴───────────────────────────┘
```

---

## B.1 定位与目标

### B.1.1 一句话

> **hotspot v1.7 = 单人本地"信息→知识→复利"中转站，46 源自动降噪、AI 评分、概念提炼、跨库连接，让知识库每天自动增长，配套 Codegarden + Security Graph 双子系统。**

### B.1.2 三个北极星指标

1. **知识库日增量** ≥ 10 items/天（当前 ≈ 0）
2. **新信息复用率** ≥ 30%（新信息中与已有 concept 关联的比例）
3. **MCP tool 调用 P95** < 500ms（保持 v1.7.6 性能预算）

---

## B.2 核心原则（精简化）

7 条 → 5 条：

1. **采集不是瓶颈，复利是** — 不再堆 source，聚焦"采回来怎么用"
2. **零状态耦合** — 任何数据可被外部 Agent 通过 MCP 重读
3. **本地优先，单进程单数据库** — SQLite WAL + APScheduler
4. **协议优先而非运行时** — MCP 是核心出口，不内置 AI
5. **可读 ID 优于 hash ID** — `gh:release:abc123` > `a1b2c3d4`

（砍掉：减少认知摩擦、自动化优先、在场不在野、渐进式个性化、外部 AI Agent 即协作者 — 这 5 条已隐含在上述 5 条中）

---

## B.3 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│  接入层  hotspot UI (React)         外部 AI Agent (MCP)     │
│          /  /knowledge /codegarden  /security                │
│          ↓ HTTP API                 ↓ MCP (stdio/SSE)        │
├──────────────────────────────────────────────────────────────┤
│  服务层  采集 (8 collectors + trafilatura + Crawl4ai)        │
│          去重 (simhash)                                       │
│          AI 评分 (本地 LLM / MCP → external Agent)            │
│          提炼 (本地 LLM NER / MCP → external Agent)            │
│          知识引擎 (KL 5 阶段 + 5 自动化触发器)                 │
│          规划引导 (KnowledgePlanningPanel)                    │
│          Codegarden / Security / Sync                         │
│          ↓                                                  │
├──────────────────────────────────────────────────────────────┤
│  数据层  SQLite WAL (71+ 表)         知识文件系统             │
│          + 58 services                knowledge/              │
│          + 41 routers                 ├─ items/*.md          │
│          + 13 MCP tools               ├─ concepts/*.md       │
│          + 30 schedulers              ├─ summaries/          │
│          + 22 quality gates           └─ learning/           │
└──────────────────────────────────────────────────────────────┘
```

**关键简化**：
- 砍掉内部 hotspot-agent 进程（已完成，v1.7.6）
- 砍掉 knowledge_tasks 异步队列（已完成，v1.7.6）
- 砍掉 KV 缓存层（保留 schema 注释）
- 6 种认知模式 + 规划引导全部保留，v1.7 实施
- 5 阶段 + 5 自动化触发器强制推进 lifecycle

---

## B.4 数据模型（最小化）

### B.4.1 保留的表（v1.7 已建）

| 表 | 用途 | v1.7 变化 |
|---|---|---|
| `hotspots` | 原始信息（采集去重后） | 改 ID 为可读 `{source}:{subtype}:{native_id}` |
| `favorites` | 收藏 | 保持 |
| `knowledge_items` | 知识条目（SQLite 索引）| **保持 + lifecycle 5 阶段字段 + 5 触发器驱动 + 新增 chunks/attention_score 字段** |
| `knowledge_concepts` | 概念 | 保持 |
| `tags` + `hotspot_tags` | 标签 | 保持 |
| `reading_states` | 阅读行为 | **强化**：自动写入 6 类事件（view/dwell/scroll/favorite/annotation/glance），删 mark_digest_read tool |
| `annotations` | 笔记 | 保持 |
| `sm2_reviews` | SM-2 复习 | **保持 + Phase 16 实施 SM-2 算法 + ReviewMode UI 触发** |
| `mcp_tool_registry` | **13 tool 保持**（5 读 + 4 保留 + 4 新增 - 4 移除 = 13） | 删 trigger_extract_tags / trigger_cubox_sync / create_alert_rule（推迟 v2.1）/ mark_digest_read |
| `catchup_runs` / `catchup_checkpoints` / `collect_validations` | 抓取流程 | 保持 |

### B.4.2 新增的表（v1.7）

> **总览**: v1.7 新增 6 张表（4 张核心 + 2 张可选/规划）。4 张核心：`content_fingerprints` / `ai_scores` / `item_entities` / `knowledge_links`；2 张扩展：`knowledge_chunks`（段落级引用）/ `planning_actions` + `planning_action_log`（规划引导）。

```sql
-- 1. 跨源去重（v1.7 必做）
CREATE TABLE content_fingerprints (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id   TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    simhash      BIGINT NOT NULL,           -- 64-bit simhash
    url_canonical TEXT NOT NULL,            -- 规范化 URL
    title_norm   TEXT NOT NULL,             -- 规范化标题
    created_at   TEXT NOT NULL,
    UNIQUE(hotspot_id)
);
CREATE INDEX idx_fp_simhash ON content_fingerprints(simhash);
CREATE INDEX idx_fp_url_canonical ON content_fingerprints(url_canonical);

-- 2. AI 评分（v1.7 必做）
CREATE TABLE ai_scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id  TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    score       REAL NOT NULL,           -- 0-10
    reason      TEXT,                    -- LLM 给的可解释理由
    scorer      TEXT,                    -- 'agent:claude-desktop' / 'agent:cursor' / 'rule'
    scored_at   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_ai_score ON ai_scores(hotspot_id, scored_at);

-- 3. 实体连接（v1.7 必做，SAG 吸收）
CREATE TABLE item_entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     TEXT NOT NULL,           -- knowledge_items.id
    entity_name TEXT NOT NULL,           -- prompt-injection
    entity_type TEXT NOT NULL,           -- concept/tool/vendor/person/cve/technique/standard/event
    confidence  REAL DEFAULT 1.0,
    source      TEXT,                    -- 'rule' / 'agent' / 'manual'
    created_at  TEXT NOT NULL,
    UNIQUE(item_id, entity_name, entity_type)
);
CREATE INDEX idx_entity_name ON item_entities(entity_name);
CREATE INDEX idx_item ON item_entities(item_id);

-- 4. 知识复用关联（v1.7 必做，复利核心）
CREATE TABLE knowledge_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_item_id    TEXT NOT NULL,
    to_item_id      TEXT NOT NULL,
    link_type       TEXT NOT NULL,       -- 'extends' / 'contradicts' / 'cites' / 'example-of'
    confidence      REAL DEFAULT 1.0,
    created_by      TEXT,                -- 'agent' / 'manual' / 'rule'
    created_at      TEXT NOT NULL,
    UNIQUE(from_item_id, to_item_id, link_type)
);
CREATE INDEX idx_link_to ON knowledge_links(to_item_id);

-- 5. 段落级引用（v1.7 必做，T3 触发器写，详见 B.4.5）
CREATE TABLE knowledge_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,           -- knowledge_items.id
    chunk_index     INTEGER NOT NULL,        -- 段落序号 0,1,2,...
    content         TEXT NOT NULL,           -- 段落原文（trafilatura 切分）
    content_hash    TEXT NOT NULL,           -- 段落 sha1，用于去重
    summary         TEXT,                    -- LLM 生成的段落摘要（T3 写）
    word_count      INTEGER NOT NULL,
    char_start      INTEGER,                 -- 原文偏移，便于跳转
    char_end        INTEGER,
    created_at      TEXT NOT NULL,
    UNIQUE(item_id, chunk_index)
);
CREATE INDEX idx_chunk_item ON knowledge_chunks(item_id);
CREATE INDEX idx_chunk_hash ON knowledge_chunks(content_hash);

-- 6. 规划引导（v1.7 必做，详见 B.7.5.2.1）
CREATE TABLE planning_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type     TEXT NOT NULL,           -- score_pending | review_due | clean_stale | enrich_concept | ...
    priority        INTEGER NOT NULL,        -- 0-100；由 priority_score() 公式计算
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | shown | accepted | dismissed | done | failed
    payload         TEXT NOT NULL,           -- JSON：动作参数（item_ids 列表 / params）
    target_user     TEXT,                    -- 单用户系统，预留扩展
    expires_at      TEXT,                    -- 动作失效时间
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_pa_status_priority ON planning_actions(status, priority DESC, created_at DESC);
CREATE INDEX idx_pa_type ON planning_actions(action_type);

CREATE TABLE planning_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER NOT NULL REFERENCES planning_actions(id) ON DELETE CASCADE,
    event           TEXT NOT NULL,           -- shown | accepted | dismissed | done | failed
    detail          TEXT,                    -- JSON：执行结果 / 失败原因
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_pa_log_action ON planning_action_log(action_id, created_at DESC);
```

### B.4.3 删除/简化的表

| 表/字段 | 处置 |
|---|---|
| `kv_cache` | **DROP**（保留 schema 注释在 docs/）|
| `knowledge_items.lifecycle` 5 阶段 | **完全保留**（v1.7 设计，v1.7 加 5 触发器强制推进）|
| `knowledge_items.chunks` YAML + SQLite | **v1.7 引入**（v1.7 设计，吸收 SAG 思想，详见 B.4.5）|
| `knowledge_items.attention_score` | **v1.7 新增字段**（基于 reading_states 聚合，详见 B.4.6）|
| `knowledge_chunks` SQLite 表 | **v1.7 新增**（chunk 索引，详见 B.4.5.3）|
| `feature_*` 13 flags | 简化为 5：`feature_mcp_server` / `feature_simhash_dedup` / `feature_ai_scoring` / `feature_chunks` / `feature_attention_heatmap` |
| 6 个 internal agent 表 | 已在 v1.7.6 删除，确认无残留 |
| Local LLM 配置文件 | **v1.7 新增** `config/llm.yaml`（详见 B.13）|

### B.4.4 知识库 .md 文件格式（v1.7 简化）

```yaml
---
id: "gh:release:abc123"
title: "LangChain 0.3 发布"
source: "hotspot"
source_url: "https://github.com/langchain-ai/langchain/releases/tag/v0.3"
ingested_at: "2026-07-26T..."
lifecycle: "kl:publish"                  # kl:raw | kl:refine | kl:link | kl:structure | kl:publish
news_type: "tool"                       # cve/vulnerability/technique/tool/paper/news/opinion
domain: "ai"
topic: "ai-coding"
difficulty: "intermediate"
tags: [ai-coding, langchain, agent]
tech_stack: [langchain, python]
concepts: [agent-loop-design, prompt-engineering]
score: 8.5                              # AI 评分
score_reason: "重大版本更新，含 breaking changes"  # 评分理由
related_items: [d4e5f6, g7h8i9]         # 通过 item_entities 计算
fingerprint: 1234567890                 # simhash
chunks: 4                               # v1.7 新增：chunk 总数（详见 B.4.5）
attention_score: 0.78                   # v1.7 新增：注意力评分（详见 B.4.6）
---

# LangChain 0.3 发布

... (内容)

## chunks_meta (v1.7 新增，可选)

> 当 `lifecycle >= kl:link` 时由 T3 触发器自动生成

```yaml
chunks_meta:
  - index: 0
    text_preview: "LangChain 0.3 在 agent loop 上做了重大改进..."
    char_start: 0
    char_end: 256
    entities: [langchain, agent-loop]
    summary: "v0.3 主打 agent loop 重构"
    score: 0.92
  - index: 1
    text_preview: "Breaking change: ToolMessage 字段重命名..."
    char_start: 256
    char_end: 512
    entities: [ToolMessage, breaking-change]
    summary: "Breaking changes 列表"
    score: 0.85
```

### B.4.5 chunks 字段（v1.7 引入，吸收 SAG 思想）

> **v1.7 引入 chunks**：v1.7 设计了但未实施，v1.7 决定引入。**为什么引入**：chunks 是 SOTA 检索架构的基础单元（参考 SAG），支持段落级精确引用、增量摘要、用户可点击跳转原文位置。

#### B.4.5.1 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `chunks` | integer | 否（仅 publish 阶段）| chunk 总数（自动从 body 计算）|
| `chunks_meta` | YAML 列表 | 否 | chunk 详细元数据（仅 llm_extracted=true 时）|

**chunks_meta 格式**:

```yaml
chunks_meta:
  - index: 0
    text_preview: "OpenAI 今天发布 GPT-5，性能提升 10x..."  # 前 100 字
    char_start: 0
    char_end: 256
    entities: [openai, gpt-5]  # chunk 级实体
    summary: "OpenAI 官方发布 GPT-5"  # chunk 摘要（LLM 生成）
    score: 0.95  # chunk 重要性
  - index: 1
    text_preview: "在 MMLU 基准测试中..."
    char_start: 256
    char_end: 512
    entities: [mmlu, benchmark]
    summary: "MMLU 基准测试结果"
    score: 0.72
```

#### B.4.5.2 chunks 生成机制

| 触发时机 | 生成方式 | 用途 |
|---------|---------|------|
| 抓取时 | trafilatura 段落切分 | 基础 chunk 索引 |
| T1 时 | 不生成 | - |
| T3 时 | 本地 LLM（或外部 MCP）摘要 | chunk 级摘要 |
| 用户展开 | 动态加载 | 阅读时高亮 |

#### B.4.5.3 SQLite 缓存（v1.7 新增表）

```sql
-- migration 046_v1.7_chunks.sql
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text_preview TEXT,
    summary TEXT,
    entities TEXT,  -- JSON 数组
    score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_id, chunk_index)
);
CREATE INDEX idx_chunks_item ON knowledge_chunks(item_id);
CREATE INDEX idx_chunks_entity ON knowledge_chunks(entities);
```

#### B.4.5.4 检索增强

chunks 字段启用后：
- **chunk 级 FTS5 搜索**：`search_knowledge` 返回带 `chunk_index` 的引用
- **chunk 级 entity JOIN**：`item_entities` 扩展为 `chunk_entities`
- **chunk 级引用**：在 UI 中点击引用可跳转到原文段落
- **chunk 级 RAG 上下文**：外部 Agent 调 MCP 时可按 chunk 取上下文

#### B.4.5.5 何时不生成 chunks

- `lifecycle < kl:link`（尚未结构化）
- 短文（< 200 字）→ 视为单 chunk
- 标讯、招标公告等结构化文本 → 保留元数据，chunks=0

#### B.4.5.6 与 SAG 的差异

| 维度 | SAG | hotspot v1.7 |
|------|-----|--------------|
| chunk 切分 | LLM-driven | 段落级（trafilatura）|
| 摘要 | LLM 全文 | chunk 级 LLM 摘要（按需）|
| 存储 | 独立 chunk DB | SQLite + YAML 双写 |
| 检索 | 向量 + entity | FTS5 + entity JOIN |
| 增量 | checkpoint | 天然（每 .md 独立）|

### B.4.6 attention_score 字段 + 注意力热图（v.2.0 引入）

> **v1.7 引入注意力评分**：基于 reading_states + 浏览时长 + 滚动深度 + 标签匹配 + 用户标记，构建 item 级别的"注意力分数"。

#### B.4.6.1 评分模型

```
attention_score(item) = 0~1，由以下加权：

1. 0.30 × reading_state.weight       (0/0.3/0.5/0.8 对应 unread/glanced/read/deep_read)
2. 0.25 × dwell_time_normalized      (0~1，归一化到 5min 上限)
3. 0.20 × scroll_depth_normalized    (0~1，0%=未滚, 100%=滚到底)
4. 0.15 × tag_match_score            (0~1，与用户 tech_stack 匹配度)
5. 0.10 × explicit_mark              (0/0.5/1.0 对应无/favorite/annotation)
```

**举例**：
- 一篇用户深度阅读 5min + 滚动到底 + 命中 tech_stack + 加了笔记的 item
- score = 0.30×0.8 + 0.25×1.0 + 0.20×1.0 + 0.15×0.9 + 0.10×1.0 = **0.875**

#### B.4.6.2 注意力热图 UI

**前端组件**: `AttentionHeatmap.tsx` (Phase 12 实施)

```
┌──────────────────────────────────────────────────┐
│  Attention Heatmap (近 30 天)                      │
│                                                    │
│  Mon  ░░▒▒▒▓▓▓██░░▒▒  ← 日期列                     │
│  Tue  ░▒▒▓▓██▒▒░░▒▒▒                              │
│  Wed  ▒▓██▓▒░░▒▒▓▓▓  ← 时间段（早/中/晚）           │
│  Thu  ▓████▓▒▒░░▒▒                                  │
│  ...                                                │
│                                                    │
│  ░ = 低 (0~0.2)   ▒ = 中低 (0.2~0.4)                │
│  ▓ = 中 (0.4~0.6)  █ = 高 (0.6~1.0)                │
└──────────────────────────────────────────────────┘
```

**热图交互**：
- 点击格子 → 弹出该时段读过的 items
- 颜色 = 平均 attention_score
- 排序：可按 category / tag / time 切换

#### B.4.6.3 数据采集

| 事件 | 触发 | 写表 | 字段 |
|------|------|------|------|
| `item_view` | 进入 item 详情 | reading_states | timestamp |
| `item_dwell` | 离开 item | reading_states | dwell_ms |
| `item_scroll` | 滚动（debounced 200ms）| reading_states | max_scroll_pct |
| `item_favorite` | 收藏 | favorites | mark=0.5 |
| `item_annotation` | 加笔记 | annotations | mark=1.0 |
| `item_glance` | 列表页停留 < 3s | reading_states | weight=0.3 |

#### B.4.6.4 注意力聚合任务

```python
# backend/scheduler/jobs.py 新增
scheduler.add_job(
    compute_attention_scores,
    IntervalTrigger(minutes=30),
    id='attention_aggregate',
    name='Attention Score Aggregation',
    max_instances=1
)

def compute_attention_scores():
    """每 30 分钟聚合一次 attention_score，写回 knowledge_items.frontmatter"""
    for item in get_recent_items(hours=24):
        score = calculate_attention_score(item)
        update_item_attention_score(item['id'], score)
```

#### B.4.6.5 热图应用场景

1. **简报模式**：根据 attention_score 排序 Top 5（用户可能想再读）
2. **整理模式**：按 attention_score 过滤未处理 items
3. **深度模式**：在右侧栏显示"相关 items 的 attention 对比"
4. **复利仪表盘**：attention_score 趋势图（高 attention items 增长曲线）

#### B.4.6.6 隐私考虑

- 注意力数据 100% 本地存储（不上传）
- 60 天后自动匿名化（保留 score，去除原始事件）
- 用户可一键删除 attention history

### B.4.7 资讯收藏聚合视图（不新增表，仅逻辑视图）

> **设计原则**: 资讯收藏聚合视图**不引入新物理表**，而是基于现有 `favorites` + `knowledge_items` 两表在**服务层 Python 侧 merge** 出一个逻辑视图。详见 B.6.7。

**为什么不做新表？**
1. 收藏的语义就是 favorites（"星标"），不能用另一张表替代
2. 知识条目已有 knowledge_items（含 Cubox / 书签 / 历史资讯导入）
3. 任何"导入"动作都已落地到 .md 文件 + SQLite 缓存，再做一张聚合表是冗余
4. v2.1 之后如需缓存，可新增 `imported_aggregator_cache`（仅快照用）

**逻辑视图的关键不变量**：
- 同 URL 在 favorites + knowledge_items 双写时，**favorites 胜出**
- origin 字段用于 UI 展示（favorite / cubox / bookmark / secnews_archive / secnews）
- 不修改原表 schema，不触发 migration

---

## B.5 抓取层（Horizon 借鉴）

### B.5.1 架构借鉴

**Horizon 的 6 步管线**:
```
fetch → dedup → score → enrich → summary → output
```

**hotspot v1.7 的 6 步管线**（保留 Horizon 设计 + 改造为本地优先）:
```
collect → dedup(simhash) → ai_score(MCP) → enrich(MCP) → ingest → digest(MCP)
```

### B.5.2 关键改造

| 改造 | 说明 |
|---|---|
| **统一 `BackendSession`** | 提取 `BackendSession` 类封装 `httpx.AsyncClient` + proxy + retry + rate-limit，每个 collector 注入（Horizon 模式）|
| **可读 ID 规范** | `{source}:{subtype}:{native_id}`，例如 `gh:release:abc123` / `hn:story:456` / `rss:item:789` |
| **统一 `BaseCollector`** | 强制接口 `async def collect(self, since: datetime, until: datetime) -> list[RawItem]` |
| **simhash 跨源去重** | 标题 + URL 规范化 → simhash 64-bit → Hamming distance < 5 视为同一条 |
| **trafilatura 作为可选 extractor** | 对反爬/JS 渲染失败的内容，fallback 用 trafilatura 提取正文 |
| **AI 评分通过 MCP 触发** | collector 完成后，写入 `pending_scoring` 状态；外部 AI Agent 通过 MCP 调 `score_item` 评分；cron 5min 检查超时 |
| **背景补全通过 MCP 触发** | 新出现的 concept 写入 `pending_enrich`；Agent 调 `enrich_concept` 补全；结果缓存到 `concepts/{name}.md` |
| **JSON pipeline_config** | 4 个示例源（hn/rss/github/reddit）+ 阈值（score>=7 才入知识库）+ 输出（web）|

### B.5.3 抓取层 schema

```python
# backend/collectors/base.py v1.7
class BaseCollector(ABC):
    source: str                       # 'github' / 'rss' / 'hn' / ...
    subtype: str                      # 'release' / 'story' / ...

    def __init__(self, session: BackendSession, config: dict):
        self.session = session        # 共享 httpx + proxy
        self.config = config          # 该 source 的子配置

    @abstractmethod
    async def fetch(self, since: datetime, until: datetime) -> list[RawItem]:
        """纯抓取，不做去重/评分/入库"""
        pass

    async def run(self, since, until) -> list[HotspotItem]:
        raw = await self.fetch(since, until)
        items = []
        for r in raw:
            item = make_hotspot(r, id=f"{self.source}:{self.subtype}:{r.native_id}")
            if not is_duplicate(item):           # simhash dedup
                items.append(item)
        return items
```

### B.5.4 抓取层 9 个 collector

| Collector | Source | Subtype | 状态 |
|---|---|---|---|
| HackerNews | `hn` | `story` / `comment` | v1.7 新增（借鉴 Horizon）|
| Reddit | `reddit` | `post` / `comment` | v1.7 新增 |
| RSS | `rss` | `item` | 已有 8 个，v1.7 标准化 |
| GitHub | `gh` | `release` / `trending` / `repo` | 已有 |
| OpenBB | `openbb` | `news` | v1.7 新增（金融）|
| Telegram | `tg` | `message` | v2.1 推迟（需 playwright + 反爬强；与 Twitter/X 同等复杂度）|
| Twitter/X | `x` | `tweet` | v2.1 推迟（反爬强）|
| GDELT | `gdelt` | `event` | v1.7 新增（安全事件）|
| OssInsight | `oss` | `repo` | v1.7 新增（开源洞察）|

**v1.7 新增 6 个 collector，借鉴 Horizon scrapers 实现**

---

## B.6 知识层（KL 5 阶段 + 5 自动化触发器 + 资讯收藏聚合视图）

> **本节是 v1.7 PRD 的核心**。v1.7 设计了 KL 5 阶段但**没有触发器** + 100% items 实际用 v1.7 旧 3 阶段值（命名不一致）。v1.7 通过 5 个自动化触发器强制推进 lifecycle + migration 046 强制命名迁移，配合认知链路 6+1 环节实现知识复利。

### B.6.1 KL 5 阶段定义（保留 v1.7 完整设计）

| 阶段 | 旧名 (SAG) | 含义 | 执行主体 | 自动化程度 |
|------|-----------|------|---------|----------|
| **`kl:raw`** | signal | 原始信号：刚采集，未处理 | 机器 | 100% 自动 |
| **`kl:refine`** | amplify:tagged | 已精炼：标签/实体提取完成 | 机器 + 规则 | 95% 自动，5% 兜底 |
| **`kl:link`** | amplify:linked | 已关联：概念图节点已创建 | AI Agent (MCP) | 80% 自动，20% 失败回退 |
| **`kl:structure`** | amplify:complete | 已结构化：信息完备，上下文完整 | AI Agent + 规则 | 70% 自动，30% 用户确认 |
| **`kl:publish`** | generate | 已发布：知识条目已生成到 `knowledge/items/`，可被外部 Agent 通过 MCP 读取 | 用户 + AI 辅助 | 50% 自动（auto 阈值触发），50% 用户手动 |

**为什么是 5 阶段而不是 3 阶段**：
- 5 阶段区分了"机器完成/AI Agent 完成/用户完成"的边界，是知识复利的必要骨架
- 简化为 3 阶段会让"提取 vs 关联"和"结构化 vs 发布"两种不同语义的转换混在一起，丢失设计语义
- 5 个触发器一一对应 5 个状态转换，可观测、可测试、可回滚
- 100% items 用 v1.7 旧 3 阶段值（应迁 v1.7 5 阶段）不是因为阶段太多，而是因为**命名未统一 + 没有触发器**——这是 v1.7 的真正问题

### B.6.2 5 个自动化触发器（v1.7 核心创新）

> **设计原则**：每个触发器明确**触发条件、执行主体、副作用、失败回退**四要素。

#### T1: `kl:raw → kl:refine`（机器自动）

| 维度 | 详情 |
|---|---|
| **触发条件** | 1) simhash 去重后入库（hotspot_id 唯一） 2) AI 评分 ≥ 阈值（默认 7.0）3) 自动 tag/实体提取完成 |
| **执行主体** | 机器（`backend/services/ingest_pipeline.py`）|
| **触发时机** | catchup 完成后批量触发；单条新信息入库后立即触发 |
| **副作用** | 1) 写 `ai_scores` 表 2) 写 `hotspot_tags` 关联 3) 更新 `hotspots.lifecycle = 'kl:refine'` 4) 写 `item_entities` 候选集（待 T2 确认）|
| **失败回退** | 评分失败：保留 `kl:raw`，5 分钟后重试 3 次后入死信；tag 提取失败：仅更新 lifecycle，不阻塞 |
| **自动化率** | 95%+ |
| **预期耗时** | 单条 < 100ms（评分 MCP 异步时 < 10ms）|
| **可观测** | `metrics:kl_transition{from=raw,to=refine}` 计数器 + `ingest_pipeline_logs` 表 |

```python
# T1 实现核心逻辑
async def trigger_t1_raw_to_refine(hotspot_id: str):
    # 1. 去重检查（simhash）
    if is_duplicate_simhash(hotspot_id):
        merge_into_existing(hotspot_id)
        return

    # 2. AI 评分（MCP 异步）
    score = await mcp_ai_score(hotspot_id)  # 外部 Agent 调用
    if score < SCORE_THRESHOLD:
        archive_hotspot(hotspot_id)
        return

    # 3. 自动 tag 提取
    tags = extract_tags_local(hotspot_id)  # 本地规则
    entities = extract_entities_local(hotspot_id)

    # 4. 推进 lifecycle
    update_lifecycle(hotspot_id, 'kl:refine')
    return TransitionResult(success=True, score=score, tags=tags, entities=entities)
```

#### T2: `kl:refine → kl:link`（AI Agent 主导）

| 维度 | 详情 |
|---|---|
| **触发条件** | 1) 已有 `item_entities` 候选集 2) 至少 1 个候选 entity 出现在已有 items 中 3) AI Agent 通过 MCP 确认关联 |
| **执行主体** | 外部 AI Agent（Cursor / Claude Desktop / Trae）通过 `link_items` MCP tool |
| **触发时机** | T1 完成 30 秒后批量触发；用户手动 review 也可触发 |
| **副作用** | 1) 写 `knowledge_links` 表 2) 更新 `hotspots.lifecycle = 'kl:link'` 3) 触发 concept graph 增量更新 |
| **失败回退** | Agent 30 分钟未响应：保留 `kl:refine`，标记 `pending_link` 状态；关联失败：保留当前状态，2 小时后重试 |
| **自动化率** | 80%（依赖 Agent 主动调用）|
| **预期耗时** | 取决于 Agent，用户可配置 P95 目标 |
| **可观测** | `metrics:kl_transition{from=refine,to=link}` + `pending_link` 队列长度 |

```python
# T2 实现核心逻辑
async def trigger_t2_refine_to_link(hotspot_id: str):
    # 1. 取出候选 entity
    entities = get_item_entities(hotspot_id)

    # 2. 查找已有相关 items
    related = find_related_items(entities, exclude_id=hotspot_id)
    if not related:
        # 没有匹配 concept，升级为新 concept
        create_new_concept_from_entities(entities)
        return TransitionResult(success=True, linked_count=0, new_concept=True)

    # 3. MCP 触发 AI Agent 确认关联
    await mcp_link_items(hotspot_id, related_items=related)

    # 4. Agent 调 link_items 后推进 lifecycle
    update_lifecycle(hotspot_id, 'kl:link')
    return TransitionResult(success=True, linked_count=len(related))
```

#### T3: `kl:link → kl:structure`（AI + 规则混合）

| 维度 | 详情 |
|---|---|
| **触发条件** | 1) 关联 items 数 ≥ 3（强关联证据）2) 标题 + 摘要 + 关键实体完整 3) 至少 1 个 tech_stack 或 cve 实体 4) 规则校验通过 |
| **执行主体** | 规则引擎（本地）+ AI Agent 辅助（标题摘要生成）|
| **触发时机** | T2 完成后每 10 分钟批量检查 |
| **副作用** | 1) 写 `summaries/{hotspot_id}.md` 摘要文件 2) **写 `knowledge_chunks` SQLite 表 + 更新 .md frontmatter `chunks_meta` 字段**（基于 LLM 批量 chunk 摘要，由 T3 触发而非单独的 Phase 任务）3) 更新 `hotspots.lifecycle = 'kl:structure'` 4) 触发 T4 候选 |
| **失败回退** | 关联不足 3：保留 `kl:link`，等待更多关联；摘要生成失败：标记 `pending_summary`，2 小时后重试 |
| **自动化率** | 70%（30% 需要用户确认）|
| **预期耗时** | 单条 < 5s（含 MCP 摘要生成）|
| **可观测** | `metrics:kl_transition{from=link,to=structure}` + 关联数分布直方图 |

```python
# T3 实现核心逻辑
def trigger_t3_link_to_structure(hotspot_id: str):
    # 1. 关联数检查
    link_count = count_knowledge_links(hotspot_id)
    if link_count < 3:
        return TransitionResult(success=False, reason='insufficient_links')

    # 2. 摘要生成（MCP 异步）
    summary = await mcp_generate_summary(hotspot_id)  # Agent 调用

    # 3. 规则校验
    if not validate_structure_completeness(hotspot_id):
        return TransitionResult(success=False, reason='incomplete')

    # 4. 写摘要文件 + chunk 摘要（v1.7 合并到 T3，由 LLMService 批量生成）
    write_summary_file(hotspot_id, summary)
    chunk_summaries = await llm_service.summarize_chunks(
        chunks=get_item_chunks(hotspot_id),
        batch_size=10
    )
    write_chunks_meta(hotspot_id, chunk_summaries)  # 写 .md frontmatter + SQLite

    # 5. 推进 lifecycle
    update_lifecycle(hotspot_id, 'kl:structure')
    return TransitionResult(success=True, link_count=link_count, summary=summary)
```

#### T4: `kl:structure → kl:publish`（用户 + AI 辅助）

| 维度 | 详情 |
|---|---|
| **触发条件** | 1) score ≥ PUBLISH_THRESHOLD（默认 8.0）2) lifecycle 处于 `kl:structure` 3) 24 小时内无结构变更 4) 用户确认（auto 模式可跳过）|
| **执行主体** | 用户（手动）或自动阈值（auto 模式）|
| **触发时机** | T3 完成后每 30 分钟批量检查；用户点击"发布到知识库"立即触发 |
| **副作用** | 1) 写 `knowledge/items/{id}.md` 完整条目 2) 同步到 `knowledge_items` SQLite 表 3) 更新 `lifecycle = 'kl:publish'` 4) 触发 SOUL profile 增量更新 5) 通知 codegarden drift 检测 |
| **失败回退** | 写入失败：标记 `pending_publish`；SOUL 更新失败：仅警告，不阻塞；codegarden 联动失败：仅警告 |
| **自动化率** | 50%（auto 模式下 80%）|
| **预期耗时** | 单条 < 200ms（含文件 I/O）|
| **可观测** | `metrics:kl_transition{from=structure,to=publish}` + 知识库日增量仪表盘 |

```python
# T4 实现核心逻辑
async def trigger_t4_structure_to_publish(hotspot_id: str, auto: bool = False):
    item = get_knowledge_item(hotspot_id)

    # 1. 阈值检查
    if item['score'] < PUBLISH_THRESHOLD and not auto:
        return TransitionResult(success=False, reason='low_score')

    # 2. 24h 内结构稳定检查
    if not is_structure_stable(hotspot_id, hours=24):
        return TransitionResult(success=False, reason='unstable')

    # 3. 写 .md 文件
    md_path = f"knowledge/items/{hotspot_id}.md"
    write_item_to_md(item, path=md_path)

    # 4. 同步 SQLite
    sync_item_to_db(item)

    # 5. 推进 lifecycle
    update_lifecycle(hotspot_id, 'kl:publish')

    # 6. 触发 SOUL 更新 + codegarden drift（非阻塞）
    asyncio.create_task(update_soul_profile(hotspot_id))
    asyncio.create_task(check_codegarden_drift(hotspot_id))

    return TransitionResult(success=True, md_path=md_path)
```

#### T5: `kl:publish → kl:refine`（用户回滚，例外触发器）

| 维度 | 详情 |
|---|---|
| **触发条件** | 用户主动编辑/回滚发布的知识条目；或检测到结构性问题（重复、错误）|
| **执行主体** | 用户（手动）|
| **触发时机** | UI 点击"重新精炼"；MCP `update_knowledge_item` 设 `lifecycle = 'kl:refine'` |
| **副作用** | 1) 保留 `knowledge/items/{id}.md` 但标记 `stale: true` 2) 更新 SQLite 3) 触发 T1 重新链路（保留 `item_entities`，重做 `knowledge_links`）|
| **失败回退** | 文件被外部修改：警告但允许；用户主动撤销：恢复 `kl:publish` |
| **自动化率** | 0%（用户主动）|
| **预期耗时** | 同步直返 < 50ms |
| **可观测** | `metrics:kl_transition{from=publish,to=refine}` + 回滚原因分布 |

```python
# T5 实现核心逻辑
async def trigger_t5_publish_to_refine(hotspot_id: str, reason: str):
    # 1. 备份当前 .md
    backup_path = backup_md_file(hotspot_id)

    # 2. 标记 stale
    mark_md_stale(hotspot_id, reason=reason)

    # 3. 更新 lifecycle
    update_lifecycle(hotspot_id, 'kl:refine')

    # 4. 触发 T1 重新链路
    asyncio.create_task(trigger_t1_raw_to_refine(hotspot_id))

    return TransitionResult(success=True, backup=backup_path, reason=reason)
```

### B.6.3 触发器调度架构

```
┌─────────────────────────────────────────────────────────────┐
│                   触发器调度器 (triggers/)                    │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │ T1 Scheduler │  │ T2 Scheduler │  │ T3 Scheduler │ ...    │
│  │  IntervalTrigger   │  IntervalTrigger   │  IntervalTrigger    │
│  │  seconds=60        │  seconds=120       │  seconds=600        │
│  └───────┬────┘  └───────┬────┘  └───────┬────┘             │
│          │               │               │                   │
│          ▼               ▼               ▼                   │
│  ┌──────────────────────────────────────────────────┐        │
│  │   状态机引擎 (KLStateMachine)                       │        │
│  │   - 记录当前 lifecycle                              │        │
│  │   - 决定下一个状态                                   │        │
│  │   - 调用对应 trigger 函数                            │        │
│  │   - 记录 transition log                            │        │
│  └──────────────────────────────────────────────────┘        │
│          │               │               │                   │
│          ▼               ▼               ▼                   │
│  ┌──────────────────────────────────────────────────┐        │
│  │   重试机制 (RetryPolicy)                            │        │
│  │   - 指数退避 (1s, 2s, 4s, 8s, 16s)                  │        │
│  │   - 3 次失败入死信队列                                │        │
│  │   - 死信 24h 后重试 1 次                            │        │
│  └──────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

**调度器配置（APScheduler 集成）**:

```python
# backend/scheduler/jobs.py v1.7
from apscheduler.triggers.interval import IntervalTrigger

# T1：每 60 秒检查新采集的 raw items
scheduler.add_job(
    trigger_t1_batch,
    IntervalTrigger(seconds=60),
    id='kl_trigger_t1',
    name='KL T1: raw → refine',
    max_instances=1
)

# T2：每 120 秒检查 refined 等待关联
scheduler.add_job(
    trigger_t2_batch,
    IntervalTrigger(seconds=120),
    id='kl_trigger_t2',
    name='KL T2: refine → link',
    max_instances=1
)

# T3：每 600 秒（10 分钟）检查 link 等待结构化
scheduler.add_job(
    trigger_t3_batch,
    IntervalTrigger(seconds=600),
    id='kl_trigger_t3',
    name='KL T3: link → structure',
    max_instances=1
)

# T4：每 1800 秒（30 分钟）检查 structure 等待发布
scheduler.add_job(
    trigger_t4_batch,
    IntervalTrigger(seconds=1800),
    id='kl_trigger_t4',
    name='KL T4: structure → publish',
    max_instances=1
)

# T5：用户主动触发，无 scheduler
```

### B.6.4 状态机不变量与可观测性

**不变量**:
- 任何 `kl:publish` 的 item 必须经历过 T1/T2/T3/T4 四个触发器
- 任何 `kl:link` 的 item 必须有至少 1 个 `item_entity` 关联
- 任何 `kl:structure` 的 item 必须有完整摘要文件
- T5 触发的 item 必须保留 `stale: true` 标记，避免重做覆盖用户编辑

**可观测性指标**:

| 指标 | 类型 | 目标 | 告警阈值 |
|------|------|------|---------|
| `kl_transition_total{from,to}` | Counter | - | - |
| `kl_pending_count{stage}` | Gauge | < 1000 | > 5000 告警 |
| `kl_t1_success_rate` | Gauge | > 95% | < 90% 告警 |
| `kl_t2_linked_count_avg` | Gauge | ≥ 3 | < 2 告警 |
| `kl_publish_daily_count` | Counter | ≥ 10 | < 5 告警 |
| `kl_compounding_ratio` | Gauge | ≥ 30% | < 20% 告警（核心 KPI）|

### B.6.5 失败回退与死信队列

| 触发器 | 失败类型 | 回退策略 | 死信条件 |
|--------|---------|---------|---------|
| T1 | 评分 MCP 超时 | 3 次指数退避后入死信 | 3 次失败入死信 |
| T1 | tag 提取失败 | 跳过 tag，仅更新 lifecycle | 不入死信（warning）|
| T2 | Agent 不响应 | 标记 `pending_link`，30min 后重试 | 5 次失败入死信 |
| T2 | 无相关 concept | 创建新 concept，强制推进 | 不入死信 |
| T3 | 关联数 < 3 | 保留 `kl:link`，不重试 | 不入死信（等关联）|
| T3 | 摘要生成失败 | 标记 `pending_summary`，2h 后重试 | 3 次失败入死信 |
| T4 | score < 阈值 | 保留 `kl:structure`，不重试 | 不入死信（等用户）|
| T4 | 文件写入失败 | 标记 `pending_publish`，立即重试 | 5 次失败入死信 |
| T5 | 文件备份失败 | 拒绝执行 | 不入死信（硬错误）|

### B.6.6 触发器与认知链路 6+1 环节映射

| 触发器 | 对应认知环节 | 用户感知 |
|--------|------------|---------|
| T1 | 提取 (Understanding) → 标签/实体 | "这条信息被打上了 3 个标签" |
| T2 | 关联 (Contextualization) | "这条与已有 5 个条目关联" |
| T3 | **结构化 (Structuring)** → 摘要 + chunk 拆分 | "这条生成了完整摘要 + 段落级引用" |
| T4 | 决策 (Decision) → 行动 (Action) | "这条已加入知识库，可被检索" |
| T5 | **反馈 (Feedback)** → 回退修正 | "我重新编辑了这条" |
| （持续）| 复利 (Compounding) | "知识库日增 12 条，关联率 35%" |

> **注**: T3 改用"结构化"而非"内化"——因为"内化"在 v1.7 设计中对应 SM-2 复习环节（Phase 16.11 ReviewMode）。T3 的"结构化"包含摘要生成 + chunk 拆分（chunks_meta + knowledge_chunks），是介于"关联"和"内化"之间的过渡环节。

### B.6.7 资讯收藏聚合视图（v1.7 新增模块）

> **背景**：v1.7 知识管理页面有 4 大领域（信息导入 / 处理数据 / 知识库编译 / 知识复利），但**缺少统一浏览所有"已导入资讯"的视图**。用户反馈"想在一个页面看全 Cubox/书签/收藏/历史资讯导入的全部条目，并能按名称/类型/时间筛选"。
>
> **约束**：不影响 4 大领域结构与流程，仅在「信息导入」页增加 1 个 action card → 点击进入新页面。

#### B.6.7.1 入口设计

```
/knowledge (KnowledgeTabs 4 大领域)
└─ /knowledge/import (KnowledgeImport, 已有 4 个 action card)
   └─ /knowledge/imported (KnowledgeFavoritesView) ← 新增第 5 个 action card 跳转
```

**入口位置**：在 KnowledgeImport 现有 4 个 action card 网格（`grid-cols-1 md:grid-cols-2`）下方，新增 1 个全宽第 5 个 card（`md:col-span-2`），符合"信息导入 → 浏览"子模块关系。

**入口 card 设计**：

```tsx
<div className="rounded-[var(--radius-md)] p-3.5 md:col-span-2" 
     style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
  <div className="flex items-center gap-2 mb-2">
    <span className="w-6 h-6 rounded-md flex items-center justify-center"
          style={{ background: 'color-mix(in srgb, var(--color-ai) 18%, transparent)',
                   color: 'var(--color-ai)' }}>
      <Icon size={12}>★</Icon>
    </span>
    <h4 className="text-xs font-bold">资讯收藏</h4>
    <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
      聚合所有已导入资讯
    </span>
  </div>
  <p className="text-[11px] mb-3" style={{ color: 'var(--text-secondary)' }}>
    统一展示来自 Cubox 同步、浏览器书签、UI 收藏、历史资讯导入的全部条目，
    支持按名称/类型/时间筛选 + 分页浏览。
  </p>
  <button onClick={() => navigate('/knowledge/imported')}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ color: 'var(--color-ai)' }}>
    查看资讯收藏 →
  </button>
</div>
```

#### B.6.7.2 数据源与去重策略

| 来源 | 物理表 | source 字段值 | 角色 |
|------|--------|------------|------|
| **UI 收藏** | `favorites` | category (ai/security/finance/startup/bid/github) | 主结果（favorited_at 较新，字段最完整）|
| **Cubox 同步** | `knowledge_items` | `source='cubox'` | 副结果（首次导入，可能未收藏）|
| **浏览器书签** | `knowledge_items` | `source='bookmark'` | 副结果 |
| **历史资讯导入** | `knowledge_items` | `source='secnews_archive'` | 副结果 |
| **收藏 promote** | `knowledge_items` | `source='secnews'` | 副结果（与 favorites URL 重叠）|

**去重原则**：同一 URL 在 favorites + knowledge_items 同时存在时，**favorites 胜出**。原因：
1. favorites 字段更完整（含 `created_via`、`favorited_at`）
2. UI 收藏代表用户主动选择，权重最高
3. knowledge_items 中 `source='secnews'` 的行是 favorites 的"派生物"（`sag_service.promote_favorite_to_knowledge` 自动创建）

**去重实现**（服务层 Python 侧 merge）：

```python
# backend/services/imported_aggregator.py
def list_imported(keyword, type_filter, since, until, limit, offset):
    # 1. 主查询: favorites 拿全字段
    fav_items = _query_favorites(keyword, type_filter, since, until, limit=limit+offset+100)
    fav_urls = {it['url'] for it in fav_items}

    # 2. 副查询: knowledge_items 排除已收藏 URL
    ki_items = _query_knowledge_items(
        sources=('cubox', 'bookmark', 'secnews', 'secnews_archive'),
        keyword=keyword, type_filter=type_filter,
        since=since, until=until,
        exclude_urls=fav_urls,  # ← 关键去重
        limit=limit+offset+100,
    )

    # 3. 标准化 schema → 合并 → 排序 → 切片
    merged = sorted(
        [_fav_to_dict(f) for f in fav_items] + [_ki_to_dict(k) for k in ki_items],
        key=lambda x: x['ingested_at'], reverse=True,
    )
    return {
        'items': merged[offset:offset+limit],
        'total': len(merged),
        'has_more': len(merged) > offset + limit,
    }
```

#### B.6.7.3 标准化 Schema (ImportedItem)

```python
class ImportedItem(TypedDict):
    id: str                # "fav:abc123" | "ki:def456"
    origin: str            # favorite | cubox | bookmark | secnews | secnews_archive
    title: str
    url: str
    category: str          # ai | security | github | bid | finance | startup | other
    type_label: str        # 科技/AI | 网络安全 | GitHub | 标讯 | 其他
    tags: list[str]        # 来自 favorites 或 knowledge_items.tags
    ingested_at: str       # ISO datetime
    summary: Optional[str] # 仅 knowledge_items 有
    lifecycle: Optional[str]  # 仅 knowledge_items 有 (kl:raw 等)
    created_via: Optional[str]  # ui | mcp | agent（仅 favorites）
```

**type → type_label 映射**：

| category | type_label | 含义 |
|----------|-----------|------|
| `ai` | 科技/AI | 科技/AI 资讯 |
| `security` | 网络安全 | CVE/漏洞/告警 |
| `github` | GitHub | 开源项目 |
| `bid` | 标讯 | 招标采购 |
| `finance` | 其他 | 金融/投资 |
| `startup` | 其他 | 独立开发/创业 |
| `other` | 其他 | 未分类 |

#### B.6.7.4 API 端点设计

```python
# backend/api/knowledge_imported.py
router = APIRouter(prefix="/api/knowledge/imported", tags=["knowledge-imported"])

@router.get("")
async def list_imported(
    keyword: Optional[str] = Query(None, max_length=200, description="按标题模糊搜索"),
    type:    Optional[str] = Query(None, regex="^(ai|security|github|bid|other|all)$"),
    since:   Optional[str] = Query(None, description="起始日期 ISO (YYYY-MM-DD 或 ISO8601)"),
    until:   Optional[str] = Query(None, description="结束日期 ISO"),
    limit:   int = Query(50, ge=1, le=200),
    offset:  int = Query(0, ge=0),
) -> dict:
    """聚合列表: favorites ∪ knowledge_items (按 URL 去重, favorites 优先)

    Response:
        {
          "items": [ImportedItem, ...],
          "total": 234,
          "has_more": true,
          "limit": 50,
          "offset": 0,
          "origin_breakdown": {
            "favorite": 180,
            "cubox": 30,
            "bookmark": 15,
            "secnews_archive": 9,
            "secnews": 0
          }
        }
    """
```

**与现有 endpoint 的关系**：
- `/api/favorites` (单表 favorites, 旧) → 仍保留，UI 收藏面板用
- `/api/knowledge/items` (单表 knowledge_items) → 仍保留，知识库列表用
- `/api/knowledge/imported` (聚合视图) → **新增**，本模块用

#### B.6.7.5 Repository 扩展（向后兼容）

```python
# backend/repository/favorite_repo.py - list() 方法扩展
def list(
    self,
    *,
    category: Optional[str] = None,
    keyword: Optional[str] = None,    # 新增
    since:    Optional[str] = None,   # 新增
    until:    Optional[str] = None,   # 新增
    limit:    int = 200,
) -> list[FavoriteItem]:
    """按收藏时间倒序. 全部参数可选, 向后兼容. category=None 查全部."""
```

```python
# backend/repository/knowledge_repo.py - list_items() 方法扩展
def list_items(
    self,
    *,
    domain:     Optional[str] = None,
    source:     Optional[str] = None,         # 单 source (已有)
    sources:    Optional[list[str]] = None,   # 新增: 多 source IN (...)
    keyword:    Optional[str] = None,         # 新增
    since:      Optional[str] = None,
    until:      Optional[str] = None,
    exclude_urls: Optional[list[str]] = None, # 新增
    limit:      int = 50,
    offset:     int = 0,
) -> list[KnowledgeItem]:
    """list_items 扩展. sources 优先级高于 source (向后兼容)."""
```

#### B.6.7.6 前端页面结构

```
┌─────────────────────────────────────────────────────────────────┐
│ 📥 资讯收藏                                       [重置] [导出] │
│ 聚合所有已导入资讯 · 共 234 条                                  │
├─────────────────────────────────────────────────────────────────┤
│ 搜索: [____________] 类型: [全部] [科技/AI] [网络安全] [GitHub] │
│ 时间: [____] 至 [____]    按 origin 分布: ★180 📦30 🔖15 🕘9 │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ ★ 某 AI 安全报告                          [★ 已收藏] [→]  │ │
│ │ tags: ai-security, llm, redteam · 2026-07-26 14:32         │ │
│ │ https://example.com/...                                     │ │
│ │ origin: favorite · category: ai · via: ui                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 📦 某 GitHub 工具 (Cubox 导入)              [☆ 收藏] [→]  │ │
│ │ tags: github, cli · 2026-07-25 09:15                       │ │
│ │ origin: cubox · category: github · kl:raw                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ... (更多)                                                     │
├─────────────────────────────────────────────────────────────────┤
│              [上一页] 第 2 / 5 页 [下一页]  跳转 [__]          │
└─────────────────────────────────────────────────────────────────┘
```

**核心交互**：
- 名称搜索：300ms debounce（参考 `useSearch.ts` 模式）
- 类型筛选：5 个 chips（全部 / 科技/AI / 网络安全 / GitHub / 标讯 / 其他），btn-ghost + active 底边下划线
- 时间筛选：两个 `<input type="date">`，until 含当天（`date(until, '+1 day')`）
- origin 分布条：实时显示各来源数量（按当前筛选结果重新统计）
- 收藏切换：点击 ☆ 调 `add_favorite` / `remove_favorite`，本地更新状态
- 翻页：上一页/下一页 + 跳转输入框

**复用现有组件**：
- `Icon` 共享组件
- `btn-ghost` / `tech-card` / `tech-input` / `tech-select` 通用样式类
- `EmptyState` 模式（favorites/FavoriteList.tsx L42-58）
- inline Toast 模式（KnowledgeImport L242-255）

#### B.6.7.7 性能与边界

| 边界 | 策略 |
|------|------|
| **数据规模** | 初期 < 5000 条，offset 分页可接受；> 5000 改为 cursor 分页（与 hotspots 一致）|
| **重复 URL** | 服务层 `exclude_urls` 过滤，favorites 优先 |
| **空表** | 全部 5 来源都为空时显示 EmptyState + 引导导入 |
| **LLM 标签** | 不调 LLM，纯 SQL LIKE 模糊搜索（性能保证）|
| **同步延迟** | Cubox 同步后 1-2min 内可见（knowledge_watcher 实时同步 .md → SQLite）|
| **移动端** | 列表 grid `lg:grid-cols-1`，类型 chips 横向滚动 |

#### B.6.7.8 与现有功能的关系

| 现有模块 | 关系 |
|----------|------|
| `favorites` API | 仍是 favorites 表的单表入口，本模块聚合数据源之一 |
| `knowledge_items` API | 仍是 knowledge_items 的单表入口，本模块聚合数据源之一 |
| 5 触发器 (T1-T5) | **不影响**：触发器只更新 `lifecycle`，不影响 imported 视图 |
| `unified_search` (033 migration) | **不影响**：本模块用 SQL LIKE，不走 FTS5 view |
| sync_bundle | 跨端同步时新增 `imported_aggregator_cache` 缓存表（v1.7 推迟到 v2.1）|

#### B.6.7.9 实施阶段

| Phase | 任务 | 工作量 |
|-------|------|--------|
| **Phase 8.9** | 后端 imported_aggregator service + API + repo 扩展 + 单测 | 1d |
| **Phase 8.10** | 前端 KnowledgeFavoritesView 组件 + useImported hook + 5th action card + 路由 + 组件测试 | 1.5d |
| **Phase 8.11** | 端到端验证：启动 dev → 5th card 跳转 → 5 类型筛选 + 名称搜索 + 时间范围 + 分页 | 0.5d |

**总计 3 天**（融入 Phase 8 信息导入子阶段，不新增 Phase）。

#### B.6.7.10 不做清单

| 不做 | 原因 | 推迟到 |
|------|------|--------|
| 向量化语义搜索 | 本地 FTS5/LIKE 够用 | v2.2 |
| 跨设备 imported 视图同步 | 跨端同步当前仅 4 表 | v2.1 |
| 批量操作（批量收藏/批量删除）| 单条已够用 | v2.1 |
| 导入来源过滤（只看 Cubox / 只看书签）| origin 分布条已显示 | 后续迭代 |

---

## B.7 MCP 集成（v1.7：读独立 + 写副作用 + 失败恢复 + 规划引导）

> **v1.7 核心变更**: v1.7.6 仅有"同步直返 + 零状态"的简单 tool 列表。v1.7 引入**"读独立 + 写副作用"混合模式**（基于"服务之间数据/流程是否关联，关联则联动"原则），并为每个写 tool 设计**失败恢复动作**。

### B.7.1 MCP 13 tool 清单 + 模式标记（v1.7 组成优化，数量不变）

> **模式标记约定**: `[A]` = 独立调用（无副作用）；`[B]` = 副作用（一次调用完整业务流程 + 失败兜底）

| 类别 | 模式 | Tool | 用途 | 关联服务 / 副作用 | 状态 |
|---|---|---|---|---|---|
| **读（5 个，纯独立）** | `[A]` | `search_hotspots` | 搜热点 | 仅读 hotspots 表 | ✅ v1.7.6 |
| | `[A]` | `get_hotspot` | 取详情 | 仅读 hotspots + 关联 | ✅ v1.7.6 |
| | `[A]` | `list_favorites` | 收藏列表 | 仅读 favorites | ✅ v1.7.6 |
| | `[A]` | `search_knowledge` | 知识库搜索 | FTS5 全文搜 + chunk 引用 | ✅ v1.7.6 + Phase 16.4 |
| | `[A]` | `get_personal_profile` | SOUL profile | soul_service 聚合 | ✅ v1.7.6 |
| **写 - 保留（4 个，副作用）** | `[B]` | `add_favorite` | 收藏 | **关联**: lifecycle / reading_states → 触发 T1（score_item + 标签提取）| ✅ v1.7.6 |
| | `[A]` | `remove_favorite` | 取消收藏 | 单纯删 favorites（保留 reading_states 历史）| ✅ v1.7.6 |
| | `[B]` | `add_annotation` | 加笔记 | **关联**: attention_score → mark=1.0，触发 30min 内 attention 聚合 | ✅ v1.7.6 |
| | `[B]` | `update_knowledge_item` | 改 lifecycle/fields | **关联**: lifecycle 字段值变化 → 触发对应 T1-T5 | ✅ v1.7.6 |
| **写 - 新增（4 个，副作用）** | `[B]` | `score_item` | AI 评分 | **关联**: ai_scores / ai_score ≥ 7 触发 T1 推进；score < 5 自动 archive | 🆕 v1.7 |
| | `[B]` | `enrich_concept` | 概念背景补全 | **关联**: concepts/{name}.md / item_entities 候选集 | 🆕 v1.7 |
| | `[B]` | `link_items` | 知识关联 | **关联**: knowledge_links / concept graph 增量更新 | 🆕 v1.7 |
| | `[B]` | `trigger_codegarden_drift` | 项目技术栈漂移检测 | **关联**: cg_projects.tech_stack 评估 / alerts | 🆕 v1.7 |
| **删除（v1.7 移除 4 个）** | - | ~~`trigger_extract_tags`~~ | 自动标签提取 | 改为 T1 触发器自动（Phase 10）| 移除 |
| | - | ~~`trigger_cubox_sync`~~ | 同步 | 保留为本地 cron job `cubox_sync` | 移除 |
| | - | ~~`create_alert_rule`~~ | 告警 | 推迟 v2.1（v1.7 内置 3 类基础规则）| 移除 |
| | - | ~~`mark_digest_read`~~ | 标记日报已读 | 改 reading_states 自动追踪 | 移除 |

**总计 13 tool 保持不变**：
- 6 独立 `[A]`（5 读 + remove_favorite）
- 7 副作用 `[B]`（4 保留写 + 4 新增写 = 8 个写 tool 中 7 个带副作用，remove_favorite 唯一独立写）
- 4 移除（trigger_extract_tags / trigger_cubox_sync / create_alert_rule / mark_digest_read）

### B.7.2 独立 vs 副作用 判定原则

> **核心原则**: 写 tool 是否带副作用，**取决于服务之间数据和流程是否关联**。关联 → 副作用联动；不关联 → 独立。

| 判定维度 | 独立 [A] | 副作用 [B] |
|---|---|---|
| **数据流** | 单表 CRUD，无跨表依赖 | 写表 A 必然需要改表 B（生命周期/外键/触发器）|
| **业务流** | 单一动作完成 | 一次动作需触发下游多个动作（lifecycle 推进、聚合更新、告警写入）|
| **回滚复杂度** | 单行 delete 可回滚 | 多表多 action 需补偿事务或死信队列 |
| **hotspot 场景** | 删除收藏、查询列表 | 收藏=触发 T1、评分=触发 T1、关联=触发概念图更新 |

**示例说明**:
- `add_favorite` [B]: 因为 favorites 表的写入必然需要 `reading_states` 记录 + `lifecycle` 推进到 `kl:refine`，三者数据流强关联 → 副作用联动
- `remove_favorite` [A]: 因为删除收藏是单纯 DELETE，reading_states 历史保留是**只读不写**，lifecycle 不回退 → 独立即可

### B.7.3 写 tool 失败恢复机制（"B 模式一次调用完整，调用失败有后手完成"）

> **设计目标**: 副作用失败不阻塞主调用返回；通过"后手"机制保证业务最终一致。

| Tool | 主调用（同步直返）| 失败场景 | 后手恢复动作 | 兜底时间 |
|---|---|---|---|---|
| `add_favorite` | 写 favorites + 返回 ID | T1 推进失败 | 标记 `pending_t1`，kl_trigger_t1 60s 重试 | 3 次失败入死信；kl_dead_letter_retry 每日 05:00 重试 |
| `add_annotation` | 写 annotations + 返回 ID | attention 聚合失败 | 写 reading_states 成功即可，聚合失败仅 warning（30min 兜底）| 不入死信 |
| `update_knowledge_item` | 更新字段 + 返回 item | T1-T5 触发失败 | 标记 `pending_kl`，对应触发器 60-1800s 重试 | 3 次失败入死信 |
| `score_item` | 写 ai_scores + 返回 score_id | T1 触发失败 / archive 失败 | 标记 `pending_t1`；archive 失败保留 kl:raw | 3 次失败入死信 |
| `enrich_concept` | 写 concept.md + 返回 path | item_entities 更新失败 | concept.md 写成功即可，item_entities 后台异步补 | 不入死信 |
| `link_items` | 写 knowledge_links + 返回 link_id | concept graph 更新失败 | 标记 `pending_graph_update`，下次 query 触发 rebuild | 不入死信 |
| `trigger_codegarden_drift` | 评估 + 返回 affected_projects | alerts 写入失败 | 评估结果写 cg_drift_log，alerts 后台异步补 | 不入死信 |

**通用恢复机制**:
```python
# 副作用失败的标准恢复模式（伪代码）
async def call_with_side_effects(tool_func, *args, **kwargs):
    try:
        result = await tool_func(*args, **kwargs)  # 主调用同步返回
        # 副作用异步触发（失败不影响主返回）
        asyncio.create_task(
            trigger_side_effects_safely(result, *args)
        )
        return result
    except SideEffectError as e:
        # 副作用失败 → 标记 pending，触发器兜底
        await mark_pending(e.pending_state, *args)
        log(f"Side effect {e.name} failed, marked pending: {e}")
        # 主调用仍返回成功
        return result_with_warning(result, side_effect_warning=str(e))
```

### B.7.4 MCP tool 设计原则

- **同步直返**（保持 v1.7.6 Option A）：所有 tool 同步返回，副作用异步触发
- **零状态**：hotspot 不维护 agent session
- **幂等**：写操作可重试不重复
- **版本化**：input_schema 加 `version` 字段
- **错误规范**：返回标准 `{success, error_code, error_message, data, side_effects_warn}` 格式
- **副作用可关闭**：每个 [B] tool 入参支持 `disable_side_effects: bool = false`
- **副作用可观测**：每个 [B] tool 写 `kl_transition_log` 表 + Prometheus 指标

### B.7.5 规划引导（v1.7 新增，13 个 tool 之外的常驻能力）

> **设计动机**: hotspot 是常驻服务，但用户的认知链 6+1 环节需要**主动引导**才能完成"从资讯到知识再到知识复利"的完整闭环。KnowledgePlanningPanel 充当"系统级的智能助手"。

#### B.7.5.1 规划动作（Planning Actions）

> **核心思想**: 系统基于"实时状态"生成"建议动作"，用户点击即可完成。**不是自动化**（用户有最终决定权），但**高度引导**（降低决策成本）。

| 规划动作 | 触发条件 | 关联 tool | 完成什么 |
|---|---|---|---|
| **「立即评分 5 条新信息」** | `hotspots.lifecycle = 'kl:raw'` 数 ≥ 5 | `score_item` × N | 推进 T1 |
| **「查看今日 top 3 概念」** | `compounding_metrics` 有新数据 | `search_knowledge` | 浏览知识库 |
| **「清理 7 条 stale 知识」** | `lifecycle = 'kl:publish' and last_modified > 30d` | `update_knowledge_item` (T5) | 触发 T5 重新精炼 |
| **「精炼 3 条 ref: 标签」** | `lifecycle = 'kl:refine'` 等待 T2 | 等待 T2 自动 + `enrich_concept` | 推进 T2 |
| **「复习 10 条 due today」** | `sm2_reviews.due_date = today` | `search_knowledge` | 进入 ReviewMode |
| **「收藏已读 3 条到知识库」** | `reading_states.weight = 'read'` 数 ≥ 3 且未 `add_favorite` | `add_favorite` | 推进 T1 |
| **「关联 2 条相关条目」** | `lifecycle = 'kl:refine'` 候选 entity 有 ≥ 2 个匹配 | `link_items` × N | 推进 T2 |
| **「生成今日日报」** | `daily_digest` 距上次 > 24h | `daily_digest` (本地 cron) | 知识沉淀 |
| **「技术栈漂移告警：fastapi 0.110 → 0.115」** | `cg_drift_log` 有新记录 | `trigger_codegarden_drift` | Codegarden 联动 |

#### B.7.5.2 规划动作数据结构

```yaml
# backend/services/planning_actions.py
PlanningAction:
  id: str                       # 唯一 ID
  category: str                 # "score" / "link" / "review" / "stale" / "drift"
  priority: int                 # 1-5，5 最高
  title: str                    # 用户看到的标题
  description: str              # 详细说明
  reason: str                   # 为什么建议这个动作
  estimated_time_seconds: int   # 预估完成时间
  related_ids: list[str]        # 关联的 hotspot_id / item_id
  tool_to_call: str             # 建议调用的 MCP tool
  tool_params: dict             # 预填参数
  cta_label: str                # 行动按钮文案（"立即评分" / "查看详情"）
  expires_at: str               # 过期时间
  created_at: str
```

#### B.7.5.2.1 SQLite 表设计（v1.7 新增）

```sql
-- migration 047_v1.7_planning_actions.sql
CREATE TABLE IF NOT EXISTS planning_actions (
    id              TEXT PRIMARY KEY,         -- uuid
    category        TEXT NOT NULL,            -- score | link | review | stale | drift | digest
    priority        INTEGER NOT NULL,         -- 1-5
    title           TEXT NOT NULL,
    description     TEXT,
    reason          TEXT,
    estimated_time_seconds INTEGER DEFAULT 60,
    related_ids     TEXT,                     -- JSON array
    tool_to_call    TEXT,                     -- MCP tool 名称
    tool_params     TEXT,                     -- JSON dict
    cta_label       TEXT,
    status          TEXT DEFAULT 'pending',   -- pending | shown | accepted | dismissed | done | expired
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_pa_status ON planning_actions(status);
CREATE INDEX idx_pa_priority ON planning_actions(priority DESC, created_at DESC);
CREATE INDEX idx_pa_category ON planning_actions(category, status);

-- 动作日志（去重 + 优化）
CREATE TABLE IF NOT EXISTS planning_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       TEXT NOT NULL,
    user_event      TEXT NOT NULL,            -- shown | clicked | dismissed | done | expired
    occurred_at     TEXT NOT NULL,
    UNIQUE(action_id, user_event, occurred_at)
);
CREATE INDEX idx_pal_action ON planning_action_log(action_id);
```

**字段映射**：
- `status='pending'` → 刚生成未推送
- `status='shown'` → 已通过 SSE 推送给前端
- `status='accepted'` → 用户点击 CTA，准备调用 tool
- `status='done'` → tool 调用完成
- `status='dismissed'` → 用户主动关闭（7 天内不再推荐同类）
- `status='expired'` → 超过 expires_at 自动失效

#### B.7.5.3 规划动作生成逻辑

```python
# backend/scheduler/jobs.py v1.7
def planning_action_check():
    """每 10 分钟生成一次规划动作"""
    actions = []
    
    # 1. 检查待评分（kl:raw 堆积）
    raw_count = count_hotspots_by_lifecycle('kl:raw')
    if raw_count >= 5:
        actions.append(PlanningAction(
            category="score",
            priority=4,
            title=f"立即评分 {min(raw_count, 10)} 条新信息",
            description=f"当前 {raw_count} 条新信息待评分，建议立即调 T1 推进 lifecycle",
            tool_to_call="score_item",
            tool_params={"batch": True, "limit": 10},
            cta_label="立即评分"
        ))
    
    # 2. 检查 stale 知识
    stale_items = find_stale_published_items(days=30)
    if len(stale_items) >= 3:
        actions.append(PlanningAction(
            category="stale",
            priority=2,
            title=f"清理 {len(stale_items)} 条 stale 知识",
            description="这些知识已 30 天未编辑，可能已过时",
            tool_to_call="update_knowledge_item",
            tool_params={"lifecycle": "kl:refine", "items": [i.id for i in stale_items]},
            cta_label="重新精炼"
        ))
    
    # 3. 检查今日复习
    due_reviews = count_due_sm2_reviews()
    if due_reviews >= 5:
        actions.append(PlanningAction(
            category="review",
            priority=3,
            title=f"复习 {due_reviews} 条 due today",
            description="SM-2 算法推荐今日复习",
            tool_to_call="search_knowledge",
            tool_params={"due_today": True, "limit": 10},
            cta_label="开始复习"
        ))
    
    # 4. 检查技术栈漂移
    drift_alerts = check_pending_drift_alerts()
    if drift_alerts:
        actions.append(PlanningAction(
            category="drift",
            priority=5,
            title=f"技术栈漂移：{drift_alerts[0].new_version}",
            description=drift_alerts[0].description,
            tool_to_call="trigger_codegarden_drift",
            tool_params={"project_id": drift_alerts[0].project_id},
            cta_label="查看影响"
        ))
    
    # 5. 写表 + SSE 推送前端
    save_planning_actions(actions)
    sse_push("planning_actions_updated", {"count": len(actions)})
```

#### B.7.5.4 KnowledgePlanningPanel UI

**位置**: dashboard 顶部（横幅） + 各模式页面右侧栏（侧边栏）

```
┌────────────────────────────────────────────────────────────┐
│ 📋 今日规划（4 个动作待处理）              [全部展开] [收起] │
├────────────────────────────────────────────────────────────┤
│ 🔥 [4] 立即评分 10 条新信息                                  │
│    当前 12 条新信息待评分，建议立即调 T1 推进 lifecycle        │
│    预估 30s                              [立即评分 →]      │
├────────────────────────────────────────────────────────────┤
│ 📚 [3] 复习 5 条 due today                                   │
│    SM-2 算法推荐今日复习                                    │
│    预估 5min                              [开始复习 →]      │
├────────────────────────────────────────────────────────────┤
│ 🗑️ [2] 清理 3 条 stale 知识                                 │
│    这些知识已 30 天未编辑                                    │
│    预估 1min                              [重新精炼 →]      │
├────────────────────────────────────────────────────────────┤
│ ⚠️ [5] 技术栈漂移：fastapi 0.110 → 0.115                    │
│    3 个项目可能受影响                                        │
│    预估 2min                              [查看影响 →]      │
└────────────────────────────────────────────────────────────┘
```

**交互**:
- 点击 [立即评分] → 自动调用 score_item，UI 显示进度，完成后刷新
- 点击 [查看详情] → 跳转到对应详情页
- 点击 [×] → 关闭该动作，下次不再推荐
- 点击 [全部展开] → 展开所有 9 类动作的完整列表
- 自动隐藏已完成的动作
- 新动作通过 SSE 实时推送（无需刷新页面）

#### B.7.5.5 规划动作的 5 条原则

1. **可执行而非抽象**：每个动作都能映射到一个 MCP tool 或本地操作
2. **优先级排序**：priority 1-5，5 最高（紧急）
3. **不重复**：同一动作不在 24h 内重复推荐
4. **可关闭**：用户点 × 后 7 天内不再推荐同类
5. **可观测**：所有动作记录到 `planning_action_log` 表，用于回放和优化

#### B.7.5.6 优先级评分公式

> **设计目标**：综合"业务紧急度"和"用户行为权重"得出最终排序，避免简单按 category 排序。

```
priority_score = base_priority × behavior_weight × freshness_weight

1. base_priority（业务紧急度，1-5）
   ┌──────────────────────────────────────────────────────────────┐
   │ 5 紧急：技术栈漂移 / 关键 CVE 命中 / 24h 内必死 review       │
   │ 4 高：  kl:raw 堆积 ≥ 5 / 复习 due ≥ 10                      │
   │ 3 中：  kl:refine 等待 T2 推进 / 新日报未生成                 │
   │ 2 低：  kl:publish stale ≥ 30d                               │
   │ 1 极低：纯优化建议（清理 ref 标签 / 重读 7d 旧 items）       │
   └──────────────────────────────────────────────────────────────┘

2. behavior_weight（用户行为权重，0.5-1.5）
   - 用户过往 7d 接受同类动作比例 ≥ 70% → 1.5
   - 30%-70% → 1.0
   - < 30% → 0.5（降权，避免刷屏）
   - 同类 dismissed 次数 ≥ 3（最近 7d）→ 0.3

3. freshness_weight（时效衰减，0.7-1.0）
   - created_at 距今 < 1h → 1.0
   - 1-6h → 0.95
   - 6-24h → 0.85
   - > 24h → 0.7
```

**SQL 查询（按 priority_score 倒序）**：

```sql
SELECT *,
    priority *
    CASE
        WHEN (SELECT COUNT(*) FROM planning_action_log pal
              WHERE pal.action_id LIKE pa.category || ':%'
                AND pal.user_event = 'clicked'
                AND pal.occurred_at > datetime('now', '-7 days'))
             >= (SELECT COUNT(*) FROM planning_action_log pal
                 WHERE pal.action_id LIKE pa.category || ':%'
                   AND pal.occurred_at > datetime('now', '-7 days')) * 0.7
        THEN 1.5
        WHEN (SELECT COUNT(*) FROM planning_action_log pal
              WHERE pal.action_id LIKE pa.category || ':%'
                AND pal.user_event = 'dismissed'
                AND pal.occurred_at > datetime('now', '-7 days')) >= 3
        THEN 0.3
        ELSE 1.0
    END *
    CASE
        WHEN julianday('now') - julianday(created_at) < 1.0/24  THEN 1.0
        WHEN julianday('now') - julianday(created_at) < 6.0/24  THEN 0.95
        WHEN julianday('now') - julianday(created_at) < 1.0      THEN 0.85
        ELSE 0.7
    END AS priority_score
FROM planning_actions pa
WHERE status IN ('pending', 'shown')
  AND expires_at > datetime('now')
ORDER BY priority_score DESC
LIMIT 10;
```

**前端渲染顺序**：
- 前端拿到前 10 条最高分动作
- 顶部放 1-2 条 "🔥 紧急"（priority=5）
- 中部放 2-3 条 "📋 建议"（priority=3-4）
- 底部放 1-2 条 "ℹ️ 信息"（priority=1-2）
- 全部展开模式按 category 分组展示

### B.7.6 MCP 协议层（v1.7.6 Option A 保持）

- **传输**：stdio（Claude Desktop / Trae）+ SSE（远程场景）
- **鉴权**：本地无鉴权（单用户），远程建议 Cloudflare Tunnel + 临时 token
- **JSON-RPC 2.0**：完全兼容 MCP 规范
- **OpenAPI → MCP 自动转换**：`fastapi-mcp` 库自动生成
- **Tool discovery**：`tools/list` 返回 13 tool 元数据 + 每个 tool 的 `mode: [A|B]` 标记
- **Tool call**：`tools/call` 同步直返结果（主结果）+ 副作用（异步触发 + 后手兜底）
- **Tool schema 增强**：每个 [B] tool 的 input_schema 含 `disable_side_effects: bool = false`

---

## B.8 复利机制（核心）

### B.8.1 复利的本质

> **新信息进入时，系统能"认出"它与已有知识的关系，并自动连接。**

理想情况下：4,147 items × 每天 200-500 条新信息 → 预计每天可产生 50-100 个 `knowledge_links` 关联。**实际值取决于 T2 触发器响应率**（依赖外部 AI Agent 接入 LLM 推理）+ AI 评分 ≥ 7 的 items 占比。初期保守估计 5-15 个/天，6 个月内逐步爬升到 30-50 个/天。

### B.8.2 三层复利

**L1 短期复利（1 天内）**
- 新信息 → simhash 去重 → 已有 items 自动合并
- AI 评分 → 自动写到 knowledge_items
- 自动提炼 tag → hot tag 推荐

**L2 中期复利（1 周内）**
- 新 concept → 写 `concepts/{name}.md`
- concept 关联到多个 items → `item_entities` 多对多
- 同 concept 的多个 items 自动形成"专题"

**L3 长期复利（1 个月+）**
- knowledge_links 自动建立"延伸/矛盾/引用/示例"关系
- knowledge graph 自动可视化
- SOUL profile 反映用户知识结构
- 新信息进入时，系统能预测"这属于 X 概念"（基于已有 item_entities）

### B.8.3 复利可视化

新增 1 个组件 `KnowledgeCompoundingDashboard`：
- 今日新增 items 数
- 今日新增 concept 数
- 今日建立 knowledge_links 数
- 30 天趋势图
- top concepts 列表（按关联 items 数排序）

### B.8.4 复利断点检测

- 若 7 天内 `ingested_at` 无新记录 → 系统告警
- 若 7 天内 `lifecycle` 没有 raw→refined 推进 → 系统告警
- 若 7 天内 `item_entities` 无新行 → 系统告警

### B.8.5 与三大子系统的复利联动

**Knowledge ↔ Codegarden**:
- knowledge 提炼的新 concept 含 tech_stack 字段
- 自动触发 codegarden 项目的 tech_stack 评估
- 新 tech → 自动列出受影响项目（MCP `trigger_codegarden_drift`）

**Knowledge ↔ Security Graph**:
- knowledge 的 CVE 节点（entity_type=cve）自动同步到 security.cve_nodes
- security 的 MITRE ATT&CK 节点引用 knowledge concepts
- 双向去重：`security.cve_nodes.cve_id = knowledge.item_entities[entity_name]`

---

## B.9 不做清单（v1.7 明确放弃，更保守）

> **v1.7 不做清单原则**: 优先保留 v1.7 优秀设计，仅明确放弃"长期未实施且无明显 KPI 价值"的设计；模糊价值的项目**保留为设计**而非直接砍。

| 不做 | 原因 | 处置 |
|---|---|---|
| 告警系统 M6 | ~~优先级低于复利~~ | **v1.7 实施 3 类基础规则**（tech_stack/CVE/标讯），v2.1 扩展 → 见 Phase 11.5-11.8 |
| 6 种认知模式 → 3 种 | ~~单人界面模式少~~ | **保留 6 种设计，v1.7 全部实施**（Hybrid AI + chunks + attention_score 支撑整理/复习模式）|
| 快速捕捉 Quick Capture | 浏览器插件开发成本高 | 推迟到 v2.2 |
| 注意力热图 | 数据稀疏（reading_states 数据不足）| **v1.7 引入**（reading_states + LLM 摘要 + 30 天数据即可使用，详见 B.4.6）|
| 决策日志 | 概念模糊 | 永久不做（已确认）|
| 离线间隔摘要 | ~~同质化功能~~ | **v1.7 实施**：catchup 失败恢复后自动生成补丁摘要 |
| Email / Webhook 多输出 | 单人 Web UI 优先 | 推迟到 v2.1 |
| Twitter/X 抓取 | 反爬强 | 推迟到 v2.1 (借鉴 Horizon twitter_playwright) |
| 向量数据库 / Embedding | 本地优先，FTS5 够用 | 永久不做（已确认）|
| 内部 hotspot-agent | 已被 Option A 替代 | 永久不做（已确认）|
| knowledge_tasks 队列 | 已被 Option A 替代 | 永久不做（已确认）|
| KV 缓存层 | 评估后保留为可选，v1.7 移除 | 永久不做（已确认）|
| `chunks` YAML 字段 | 本地无 LLM | **v1.7 引入**（Hybrid AI 模式下本地 LLM 可用，详见 B.4.5）|
| **热点 0-10 评分自动应用**：评分先存待人工确认，v2.1 再自动 | 第一性原理：用户对 AI 评分的信任需要累积 | v2.1 |
| **自动写 .md**（采集完成立即写 knowledge/items/）| 评分未通过的不应进入知识库 | 评分 ≥ 阈值才写 |
| **自动建立 knowledge_links**（无需用户确认）| 错误链接伤害信任 | v2.1 |
| **整理模式（Outbox）** | v1.7 设计未实施 | **v1.7 实施**（reading_states 累积 + LLM 摘要支持，详见 Phase 12）|
| **复习模式（SM-2）** | v1.7 设计未实施 | **v1.7 实施**（sm2_reviews 累积，详见 Phase 12）|

---

## B.9.5 用户旅程（v1.7 优秀设计保留）

> **保留 v1.7 8 时段工作流**：用户的真实工作流是设计的输入，不能因为"复杂"就删。

### 8 时段典型一天（IT 安全从业者）

```
08:00 - 开电脑，打开 dashboard
  |  (1) 态势感知
  |  * 数据源完整性指示器（绿/黄/红）         -> 复利仪表盘
  |  * 夜间告警汇总                          -> 告警模式
  |  * 每日简报（自动生成）                   -> 简报模式
  |  * 离线间隔摘要（若昨日未使用过）          -> 离线补丁
  |
08:15 - 紧急响应（若有 CVE / 0-day / 攻击事件）
  |  (2) 快速决策
  |  * PUSH 告警 -> 红色标记                  -> 告警模式
  |  * 技术栈影响分析                         -> Codegarden drift
  |  * 一键创建待办                           -> T4 触发器联动 Todo
  |
09:00 - 深度阅读（3-5 篇重点文章）
  |  (3) 知识摄入
  |  * 自动提取标签/概念/技术栈                -> T1 触发器
  |  * 上下文推荐（相关知识库条目）             -> T2 触发器
  |  * 笔记区（Markdown，关联文章）              -> 深度模式
  |  * 阅读状态追踪                           -> reading_states
  |
12:00 - 碎片浏览（GitHub / Twitter）
  |  (4) 快速捕捉
  |  * 一键保存 URL 到系统                    -> T1 触发
  |  * 自动打标签                             -> T1 触发
  |
13:00 - 交叉验证与关联分析
  |  (5) 知识验证
  |  * 统一搜索跨 5 层穿透                    -> search_knowledge
  |  * 概念图谱可视化                         -> knowledge graph
  |  * 同话题多源聚合                         -> T2 触发器
  |
15:00 - 行动落地
  |  (6) 知识->行动
  |  * 项目影响评估 -> Todo 创建               -> T2 + Codegarden drift
  |  * 发布/导出分析报告                      -> T4 触发器
  |
17:00 - 复盘与学习
  |  (7) 知识内化
  |  * 今日看了 N 篇文章，提取了 M 个概念      -> 复利仪表盘
  |  * 复习队列（最长未复习条目优先）          -> 复习模式（v2.1）
  |  * 今日精选（系统推荐最有价值条目）         -> 知识推荐
  |
17:30 - 规划明日
  |  (8) 准备
  |  * 设置告警规则                           -> 告警配置
  |  * 优先收件箱                             -> 整理模式（v2.1）
  |  * 明日简报预生成                         -> daily_digest job
  +------------------------------------------
```

### 6 种认知模式（v1.7 全部实施）

> **v1.7 全部实施 6 种认知模式**：基于 reading_states 数据积累 + LLM 摘要支持，整理/复习模式可落地。

| 模式 | 触发条件 | 界面 | 核心操作 | v1.7 状态 | Phase |
|------|---------|------|---------|----------|-------|
| **简报模式** | 每日首次打开 / 离线归来 | 一句话摘要+3 篇关键文章+数据源状态 | 扫一眼，点开感兴趣的 | ✅ | Phase 12 |
| **快速扫描模式** | 默认首页 | 分类+标签+时间筛选列表 | 快速浏览标题 | ✅ | Phase 12 |
| **深度阅读模式** | 点击一篇文章 | 文章全屏+右侧栏(推荐/笔记/影响/触发器状态/chunk 高亮) | 阅读、提取、笔记 | ✅ | Phase 12 |
| **整理模式（Outbox）** | 手动切换 / 浏览 1h 后自动建议 | 清单视图(未处理+待复习+待确认+按 attention_score 排序) | 批量处理 | ✅ | Phase 12 |
| **复习模式（SM-2）** | 复习队列非空时 | 卡片翻转(概念->自评->答案) | 回顾+评分 | ✅ | Phase 12 |
| **告警模式** | 新告警产生 | 红色横幅+告警中心 Inbox | 查看、标记、行动 | ✅ | Phase 11 |

### 与现有功能集成（v1.7）

| 现有模块 | v1.7 集成方式 |
|----------|--------------|
| **favorites** | 收藏即自动触发 T1 提取 + T2 关联 + T4 发布 |
| **todos** | 告警命中时自动创建 Todo，标记 source_article_id |
| **knowledge** | 提取的概念自动关联 knowledge_items，5 触发器驱动 |
| **codegarden** | tech_stack 桥接 cg_projects，告警影响分析 |
| **security_graph** | 关联的 CVE 实体注入知识推荐 |
| **sync_bundle** | reading_states + annotations + sm2_reviews 跨端同步（v1.7 简化为 4 表）|
| **weekly_report** | digest 作为周报输入素材 |
| **obsidian** | 直接读取 knowledge/items/ 目录，LLM-Wiki 2.0 格式 |
| **外部 AI Agent** | 通过 MCP 协议调 hotspot 13 个 tool，LLM 推理在 agent 侧 |

---

## B.9.6 API 设计（v1.7 endpoint 列表保留）

> **保留 v1.7 核心 endpoint**：API 是 hotspot 与外部（前端 + MCP + Agent）的契约，不能因为"重复"就删。

### 5 类 endpoint 概览

| 类别 | 数量 | 路径前缀 | 用途 |
|------|------|---------|------|
| **SecNews** | 12 | `/api/hotspots`, `/api/categories`, `/api/catchup/*` | 热点查询、分类、追抓 |
| **Knowledge** | 19 | `/api/knowledge/items`, `/api/knowledge/concepts`, `/api/knowledge/learning`, `/api/knowledge/content`, `/api/knowledge/summaries`, `/api/knowledge/imported` | 知识库 CRUD + 搜索 + 资讯收藏聚合视图 |
| **Codegarden** | 14 | `/api/codegarden/projects`, `/api/codegarden/phase2b/*` | 项目 + 服务网格 |
| **Security** | 8 | `/api/security/graph`, `/api/security/cve`, `/api/security/compliance` | 安全图谱 |
| **MCP** | 13 | `/mcp/tools/*` (或 stdio) | 13 个 MCP tool |
| **总** | **66** | | |

### 关键 endpoint（v1.7 必保留）

| Method | Path | 用途 | v1.7 变化 |
|--------|------|------|----------|
| GET | `/api/hotspots` | 列表查询 | 保持 + 可读 ID 支持 |
| GET | `/api/hotspots/{id}` | 详情 | 保持 + 包含 `lifecycle` |
| POST | `/api/catchup/run` | 追抓 | 保持 + 集成 T1 触发器 |
| GET | `/api/knowledge/items` | 知识列表 | 保持 + lifecycle 过滤 |
| GET | `/api/knowledge/items/{id}/triggers` | **v1.7 新增** 5 触发器状态 | 🆕 |
| POST | `/api/knowledge/items/{id}/transition` | **v1.7 新增** 手动触发 T1-T5 | 🆕 |
| GET | `/api/knowledge/imported` | **v1.7 新增** 资讯收藏聚合视图（favorites ∪ knowledge_items 去重）| 🆕 |
| GET | `/api/knowledge/compounding` | **v1.7 新增** 复利仪表盘数据 | 🆕 |
| GET | `/api/alerts` | **v1.7 新增** 告警列表 | 🆕 |
| POST | `/api/alerts/{id}/ack` | 告警确认 | 🆕 |
| GET | `/api/codegarden/phase2b/services` | 服务列表 | 保持 |
| POST | `/api/codegarden/phase2b/services/{id}/restart` | 重启 | 保持 |
| GET | `/api/security/graph` | 安全图谱 | 保持 + Knowledge 联动 |
| GET | `/mcp/tools/{tool_name}` | MCP tool 调用 | 保持 + 4 新 tool |
| GET | `/api/soul` | SOUL profile | 保持 + 5 触发器增量更新 |
| GET | `/api/metrics/kl` | **v1.7 新增** 触发器指标 | 🆕 |

**`/api/knowledge/imported` vs `/api/favorites` 分工**:
- `/api/favorites`：**只看 favorites 表**（最严格"已收藏"语义），导出 xlsx 用
- `/api/knowledge/imported`：**聚合视图**（favorites ∪ knowledge_items），含时间/类型/名称筛选，用于"看看我导入了什么"的全景视图
- 前端 KnowledgeImport 页面"资讯收藏"卡片 → 调 `/api/knowledge/imported`
- 前端 HotspotCard ⭐ 按钮 → 调 `/api/favorites`

### v1.7 移除的 endpoint

| Method | Path | 原因 |
|--------|------|------|
| GET/POST | `/api/agent/*` | Option A 落实，删除 8 个路由 |
| GET | `/api/kv_cache/*` | kv_cache 表删除，路由一并清理 |
| POST | `/api/knowledge/tasks/*` | knowledge_tasks 队列删除 |

### API 设计原则（v1.7 保留）

1. **错误响应统一**：`{"detail": {"message": "...", "missing": "github_token"}}`
2. **同步直返**：所有 endpoint 同步返回，不引入异步任务（Phase 7 Option A 原则）
3. **idempotent**：写操作可重试不重复
4. **OpenAPI 文档自动生成**：FastAPI 自带 `/docs`
5. **Pydantic 严格校验**：所有 request body 走 Pydantic model
6. **错误码语义化**：404/403/409/400/500 严格区分
7. **CORS 白名单**：仅允许本地前端端口（8898）

---

## B.9.7 调度器（v1.7 job 表保留 + 5 触发器新增）

> **v1.7 新增 9 个 job**：T1/T2/T3/T4 四个 IntervalTrigger + T5 主动触发。

### APScheduler 任务清单（v1.7 = 30 jobs）

| Job ID | 名称 | 触发器 | 周期 | v1.7 状态 |
|--------|------|--------|------|----------|
| `catchup_run` | 追抓资讯 | CronTrigger | 每 6h | ✅ 已有 |
| `collect_validate` | 数据完整性验证 | CronTrigger | 每日 04:00 | ✅ v1.9 |
| `source_revival_check` | 源复活检测 | IntervalTrigger | 每日 03:00 | ✅ v1.9 |
| `trending_score` | 趋势评分 | IntervalTrigger | 1h | ✅ 已有 |
| `sync_bundle` | 跨端同步 | IntervalTrigger | 6h | ✅ 已有 |
| `knowledge_watcher` | 知识库监听 | Watchdog | 实时 | ✅ 已有 |
| `security_mitre_sync` | MITRE 同步 | CronTrigger | 每周日 02:00 | ✅ 已有 |
| `security_nvd_sync` | NVD 同步 | CronTrigger | 每日 02:00 | ✅ 已有 |
| `cg_service_scan` | 服务扫描 | IntervalTrigger | 5min | ✅ Phase 2b |
| `cg_event_process` | 事件处理 | IntervalTrigger | 60s | ✅ Phase 2b |
| `db_maintenance` | DB 维护 | CronTrigger | 每周一 03:00 | ✅ 已有 |
| `cubox_sync` | Cubox 同步 | CronTrigger | 每日 01:00 | ✅ 已有 |
| `collect_validations_cleanup` | 验证日志归档 | CronTrigger | 每日 04:00 | ✅ v1.9 |
| `sse_keepalive` | SSE 心跳 | IntervalTrigger | 30s | ✅ Phase 6 |
| `mcp_health_check` | MCP 健康检查 | IntervalTrigger | 60s | ✅ v1.7.6 |
| `kl_trigger_t1` | **T1 触发器** | IntervalTrigger | 60s | 🆕 Phase 10 |
| `kl_trigger_t2` | **T2 触发器** | IntervalTrigger | 120s | 🆕 Phase 10 |
| `kl_trigger_t3` | **T3 触发器** | IntervalTrigger | 600s | 🆕 Phase 11 |
| `kl_trigger_t4` | **T4 触发器** | IntervalTrigger | 1800s | 🆕 Phase 11 |
| `kl_dead_letter_retry` | 死信重试 | CronTrigger | 每日 05:00 | 🆕 Phase 10 |
| `daily_digest` | 每日简报生成 | CronTrigger | 每日 08:00 | 🆕 Phase 12 |
| `compounding_metrics` | 复利指标聚合 | IntervalTrigger | 5min | 🆕 Phase 12 |
| `attention_aggregate` | 注意力分数聚合 | IntervalTrigger | 30min | 🆕 Phase 16 |
| `planning_action_check` | 规划动作检查 | IntervalTrigger | 10min | 🆕 Phase 12 |

**总计 24 个 job**（v1.7 15 个 + v1.7 新增 9 个：4 触发器（kl_trigger_t1/t2/t3/t4）+ dead_letter_retry + daily_digest + compounding_metrics + attention_aggregate + planning_action_check）

> **实施灵活度说明**: 13 tool 是设计目标，**实施顺序可根据用户实际需求调整**。Phase 8-16 表的周期是"设计目标"，不是"固定计划"。hotspot 是常驻服务，用户可在任意 Phase 启动 v1.7 部分能力，剩余能力渐进式补齐。

### 调度器设计原则（v1.7 保留）

1. **单进程**：SQLite WAL 限制 WORKERS=1
2. **max_instances=1**：所有 job 禁止并发执行
3. **misfire_grace_time=300s**：错过 5 分钟内可补跑
4. **coalesce=True**：错过的多次触发合并为 1 次
5. **持久化**：jobstore 用 SQLite
6. **监控**：每个 job 写 `job_runs` 表，记录 start/end/duration/status

---

## B.9.8 前端组件与路由（v1.7 关键组件保留）

> **v1.7 新增 4 模式 UI + 复利仪表盘 + 触发器状态可视化**。

### 关键路由（v1.7 完整保留 v1.7）

| 路径 | 组件 | 用途 | v1.7 状态 |
|------|------|------|----------|
| `/` | `HotspotPage` | 首页（扫描模式）| ✅ 保持 |
| `/knowledge` | `KnowledgePage` | 知识库列表 | ✅ 保持 |
| `/knowledge/items/:id` | `KnowledgeItemDetail` | 知识详情 | ✅ + 触发器状态条 |
| `/knowledge/imported` | `KnowledgeFavoritesView` | **v1.7 新增** 资讯收藏聚合视图（5 类型筛选 + 名称搜索 + 时间范围 + 分页）| 🆕 Phase 8 |
| `/knowledge/compounding` | `KnowledgeCompoundingDashboard` | **v1.7 新增** 复利仪表盘 | 🆕 Phase 12 |
| `/knowledge/briefing` | `BriefingMode` | **v1.7 新增** 简报模式 | 🆕 Phase 12 |
| `/knowledge/scan` | `ScanMode` | **v1.7 新增** 扫描模式 | 🆕 Phase 12 |
| `/knowledge/deep` | `DeepReadMode` | **v1.7 新增** 深度阅读 | 🆕 Phase 12 |
| `/alerts` | `AlertCenter` | **v1.7 新增** 告警中心 | 🆕 Phase 11 |
| `/codegarden` | `CodegardenPage` | 项目管理 | ✅ 保持 |
| `/codegarden/phase2b` | `CodegardenPhase2bPage` | 服务网格/资源中枢/联动 | ✅ 保持 |
| `/security` | `SecurityPage` | 安全图谱 | ✅ 保持 |
| `/sync` | `SyncPage` | 跨端同步 | ✅ 保持 |
| `/secrets` | `SecretsPage` | 密钥管理 | ✅ 保持 |
| `/settings` | `SettingsPage` | 设置 | ✅ 保持 |

### v1.7 关键组件（新增）

| 组件 | 路径 | 用途 |
|------|------|------|
| `KnowledgeCompoundingDashboard` | `components/knowledge/` | 复利可视化：日/周/月趋势 + top concepts + 断点告警 |
| `KnowledgeFavoritesView` | `components/knowledge/` | **v1.7 新增** 资讯收藏聚合视图：5 类型筛选 + 名称搜索 + 时间范围 + 分页 + origin 分布 |
| `BriefingMode` | `components/knowledge/modes/` | 简报模式：一句话摘要 + 3 篇关键文章 + 数据源状态 |
| `ScanMode` | `components/knowledge/modes/` | 扫描模式：分类 + 标签 + 时间筛选列表 |
| `DeepReadMode` | `components/knowledge/modes/` | 深度模式：文章全屏 + 右侧栏 + 触发器状态 |
| `AlertCenter` | `components/alerts/` | 告警 Inbox + 红色横幅 + 告警历史 |
| `KLTriggerBadge` | `components/knowledge/` | 5 阶段进度条（reusable 组件）|
| `LifecycleFilter` | `components/knowledge/` | 按 lifecycle 过滤 items |

### 前端技术栈（保持 v1.7）

- **框架**：React 18 + Vite 5 + TypeScript
- **样式**：Tailwind 3 + CSS Variables (theme)
- **状态**：React Context + useState/useReducer（无 Redux）
- **图表**：echarts-for-react + recharts
- **测试**：Vitest + jsdom
- **类型检查**：`tsc --noEmit`
- **构建**：`vite build`

### 前端设计原则（v1.7 保留）

1. **共享 Icon**：`Icon.tsx` 统一所有图标（避免 11 处重复定义）
2. **深色/浅色主题**：`ThemeContext` 在 `App.tsx`
3. **响应式**：优先 1280+ 桌面，移动端渐进适配
4. **类型安全**：所有 props 走 TypeScript interface
5. **可访问性**：aria-label、keyboard navigation
6. **无路由库**：用 `react-router-dom` v6

---

## B.9.9 跨端同步（v1.7 Sync Bundle 设计保留 + 8 表扩展）

> **v1.7 同步表扩展**: 在 v1.7 4 表核心（reading_states + favorites + tags + sm2_reviews）基础上，**新增 4 表**（lifecycle / knowledge_links / ai_scores / item_entities）共 **8 表同步**。

### 同步包设计

```
config-YYYY-MM-DD.zip
├── envelope.json      (Fernet 密文)
└── manifest.json      (明文元数据)
```

- **文件名 ASCII 强制**（坚果云 WebDAV quirk）
- **zip 容器**：便于传输与解压
- **Fernet 加密**：PBKDF2 派生密钥，envelope format

### 同步表清单（v1.7 共 8 表）

| 表 | 同步方向 | 冲突解决 | 频率 |
|---|---------|---------|------|
| `reading_states` | 双向 | last-write-wins | 6h |
| `favorites` | 双向 | add-only（去重）| 6h |
| `tags` | 双向 | add-only（去重）| 6h |
| `sm2_reviews` | 双向 | last-write-wins | 6h |
| `knowledge_items.lifecycle` | 双向 | 设备本地状态优先 | 6h |
| `knowledge_links` | 双向 | 设备本地状态优先 | 6h |
| `ai_scores` | 单向（上推）| latest 优先 | 6h |
| `item_entities` | 单向（上推）| latest 优先 | 6h |

**v1.7 新增 4 表同步**：lifecycle / knowledge_links / ai_scores / item_entities（设备本地状态优先）

### 同步实现（v1.7 拆分 3 文件保留）

```
sync_service.py  →  Orchestration: push/pull/bidirectional (371 lines)
sync_merge.py    →  3-way merge engine: MergeResult, three_way_merge() (246 lines)
sync_bundle.py   →  Serialization: build_bundle, encrypt/decrypt (400 lines)
```

### 3-way merge 原则（v1.7 保留）

1. **base/local/remote**：每个 entity 保留 base + local + remote 三方
2. **record-level alignment**：按 ID 对齐 records
3. **field-level last-write-wins**：每字段独立比较 timestamp
4. **冲突检测**：base==local≠remote 标记 conflict，让用户处理
5. **不自动覆盖**：本地状态（lifecycle）优先，避免跨端覆盖

---

---

## B.10 Phase 规划

### B.10.1 总览（10 个 Phase，~46 天）

> **与 B.10.12 一致**：10 个 Phase（v1.7 的 9 个 + 预置 v1.9 标准化 1 个）总计 ~46 天。Phase 9 为 v1.9 已完成基线，详见 phase9_changelog.md。Phase 16/17 详见 B.10.10 / B.10.11。

| Phase | 名称 | 周期 | 模块 | 5 触发器对应 | 状态 |
|---|---|---|---|---|---|
| **8** | 复利基础设施 + 资讯收藏聚合 | ~6 天 | simhash 去重 + ai_scores/item_entities/knowledge_links 表 + 4 个新 MCP tool + **资讯收藏聚合视图（B.6.7）**| T1 基础设施 | 🆕 v1.7 |
| **9** | **资讯抓取流程标准化** | **~4 天** | **断点续传（catchup_checkpoints）+ 4 类数据完整性验证（collect_validations）+ 结构化事件日志** | **抓取可靠性** | **✅ v1.9 已完成** |
| **10** | T1/T2 触发器实施 | ~4 天 | T1 (raw→refine) + T2 (refine→link) + 状态机引擎 | T1, T2 | 🆕 v1.7 |
| **11** | 抓取层现代化 | ~5 天 | BackendSession + 可读 ID + trafilatura + 6 个新 collector | T1 数据源 | 🆕 v1.7 |
| **12** | T3/T4/T5 触发器 + 告警系统 | ~6 天 | T3/T4/T5 + 3 类基础告警规则（tech_stack/CVE/标讯） | T3, T4, T5 | 🆕 v1.7 |
| **13** | 复利可视化 + 4/6 模式 + 规划引导 | ~4 天 | KnowledgeCompoundingDashboard + 简报/扫描/深度/告警 4 模式 UI + KnowledgePlanningPanel | T4 验证 | 🆕 v1.7 |
| **14** | 子系统联动 | ~3 天 | tech_stack_drift + cve_knowledge_sync + 跨域 entity 命名空间 | T2 联动 | 🆕 v1.7 |
| **15** | 清理 + 文档 + 迁移 | ~5 天 | 删 kv_cache / /api/agent / 4 MCP tool / 迁移指南 / 用户文档 | T5 兜底 | 🆕 v1.7 |
| **16** | **Hybrid AI（Crawl4ai + 本地 LLM + 外部 Agent 并存）** | **~6 天** | **LLMService 多 provider + Crawl4ai 4 源迁移 + 5 种降级场景**（详见 B.10.10）| 性能提升 | 🆕 v1.7 |
| **17** | **Chunks + Attention Heatmap + 6 模式完整** | **~7 天** | **chunks 表 + 热图 + 整理/复习模式**（详见 B.10.11）| 复利闭环 | 🆕 v1.7 |

**总预估**: ~46 天（v1.7 的 28 天 → v1.7 46 天，**+64%**；5 阶段 + 5 触发器 + 告警恢复 + 4 模式 UI + Hybrid AI + chunks/attention + 6 模式完整 + 规划引导是核心增量）

> **详细周期分配**: 6 + 4 + 5 + 6 + 4 + 3 + 5 + 6 + 7 = 46 天（v1.7 Phase 8 + 10–17，不包含 v1.9 Phase 9 已完成基线；与 B.10.12 总览一致）。

### B.10.2 Phase 8：复利基础设施

| 任务 | 详情 | 验收 |
|---|---|---|
| **8.1 数据迁移** | `migration 043_v1.7_fingerprints_scores.sql`：新增 `content_fingerprints / ai_scores / item_entities / knowledge_links` 4 表 | schema 校验通过 |
| **8.2 simhash 实现** | `backend/services/simhash.py`：64-bit simhash + Hamming distance + URL canonicalize | 1000 条样本去重准确率 ≥ 95% |
| **8.3 去重集成** | `backend/services/collection_service.py`：collect() 后立即去重 | 单元测试 5 用例通过 |
| **8.4 AI 评分 MCP tool** | `backend/api/mcp_phase8.py`：`score_item(hotspot_id, score, reason, scorer)` | 外部 Agent 调通 |
| **8.5 背景补全 MCP tool** | `enrich_concept(concept_name, content, source)` → 写 `concepts/{name}.md` | 缓存命中 ≥ 80% |
| **8.6 知识关联 MCP tool** | `link_items(from_id, to_id, link_type, confidence)` → 写 `knowledge_links` | idempotency 测试通过 |
| **8.7 codegarden drift MCP tool** | `trigger_codegarden_drift(project_id)` → tech_stack 评估 | 评估延迟 < 200ms |
| **8.8 tests** | `test_simhash / test_mcp_phase8 / test_fingerprint` 等 | 4 表 CRUD + 13 tool 通过 MCP 调用 |
| **8.9 资讯收藏聚合后端** | `backend/services/imported_aggregator.py` + `backend/api/knowledge_imported.py` + `favorite_repo.list`/`knowledge_repo.list_items` 扩展 | API 返回聚合去重结果 |
| **8.10 资讯收藏聚合前端** | `KnowledgeFavoritesView.tsx` + `useImported.ts` + 5th action card + 路由 | 5 类型筛选 + 搜索 + 时间 + 分页 |
| **8.11 资讯收藏聚合 e2e** | 启动 dev → 5th card 跳转 → 全流程验证 | e2e 8 用例通过 |

### B.10.3 Phase 10：T1/T2 触发器实施

| 任务 | 详情 | 触发器 |
|---|---|---|
| **10.1 状态机引擎** | `backend/services/kl_state_machine.py`：KLStateMachine 类 + 不变量检查 | 基础设施 |
| **10.2 T1 实施** | `backend/services/triggers/t1_raw_to_refine.py`：60s 调度 + simhash 去重 + 评分 + tag 提取 | **T1** |
| **10.3 T2 实施** | `backend/services/triggers/t2_refine_to_link.py`：120s 调度 + entity 查找 + MCP link_items 触发 | **T2** |
| **10.4 调度器注册** | `backend/scheduler/jobs.py` 注册 kl_trigger_t1 / kl_trigger_t2 | 调度 |
| **10.5 重试 + 死信** | `backend/services/retry_policy.py`：指数退避 + 死信队列 | 可靠性 |
| **10.6 Prometheus 指标** | `backend/metrics/kl_metrics.py`：6 个指标 + 仪表盘 JSON | 可观测 |
| **10.7 tests** | `test_t1_trigger / test_t2_trigger / test_state_machine` | 15+ 用例 |

**T1 验证标准**: 100 条样本中 95%+ 成功从 raw 推进到 refine；T2 验证标准：80% 找到至少 1 个关联 concept。

### B.10.4 Phase 11：抓取层现代化

| 任务 | 详情 | 验收 |
|---|---|---|
| **11.1 BackendSession** | `backend/collectors/session.py`：httpx + proxy + retry + rate-limit | 6 个 collector 注入 |
| **11.2 可读 ID 规范化** | `backend/collectors/id_factory.py`：`{source}:{subtype}:{native_id}` 工厂 | 100% 旧 hash ID 可映射 |
| **11.3 trafilatura 集成** | `backend/parsers/trafilatura_parser.py`：作为 optional extractor | fallback 工作 |
| **11.4 6 个新 collector** | hn / reddit / openbb / telegram / gdelt / ossinsight | 各自 5 用例通过 |
| **11.5 JSON pipeline_config** | `config/pipeline.json`：4 源示例 + 阈值 + 输出 | schema 校验通过 |
| **11.6 tests** | 6 collector × 5 用例 + BackendSession 注入测试 | 30+ 用例 |

### B.10.5 Phase 12：T3/T4/T5 触发器 + 告警系统

| 任务 | 详情 | 触发器/告警 |
|---|---|---|
| **12.1 T3 实施** | `backend/services/triggers/t3_link_to_structure.py`：600s 调度 + 关联数检查 + 摘要生成 | **T3** |
| **12.2 T4 实施** | `backend/services/triggers/t4_structure_to_publish.py`：1800s 调度 + 阈值 + 24h 稳定 + .md 写入 | **T4** |
| **12.3 T5 实施** | `backend/services/triggers/t5_publish_to_refine.py`：用户主动 + 备份 + stale 标记 | **T5** |
| **12.4 调度器扩展** | 注册 kl_trigger_t3 / t4（T5 走用户主动调用，无 scheduler）| 调度 |
| **12.5 告警规则引擎** | `backend/services/alert_engine.py`：3 类基础规则 | **告警 M6** |
| **12.6 告警规则 1**：tech_stack 影响 | 新 CVE 命中 cg_projects.tech_stack → 告警 | 告警 |
| **12.7 告警规则 2**：关键 CVE | NVD CVSS ≥ 9.0 → 告警 | 告警 |
| **12.8 告警规则 3**：标讯命中 | 标讯关键词命中 tech_stack → 告警 | 告警 |
| **12.9 告警 UI** | `frontend/src/components/AlertCenter.tsx`：Inbox + 红色横幅 | UI |
| **12.10 tests** | `test_t3/t4/t5 + test_alert_engine` | 20+ 用例 |

**T3 验证**: 关联数 ≥ 3 的 items 100% 推进到 structure；T4 验证：score ≥ 8 的 items 100% 自动发布；T5 验证：用户回滚 100% 不丢用户编辑。

### B.10.6 Phase 13：复利可视化 + 4/6 模式 + 规划引导

| 任务 | 详情 | 模式 |
|---|---|---|
| **13.1 KnowledgeCompoundingDashboard** | `frontend/src/components/KnowledgeCompoundingDashboard.tsx`：日/周/月趋势 + top concepts + 断点告警 | 简报 |
| **13.2 简报模式 UI** | `BriefingMode.tsx`：每日首次打开 + 一句话摘要 + 3 篇关键文章 + 数据源状态 | 简报 |
| **13.3 快速扫描 UI** | `ScanMode.tsx`（即当前首页）：分类 + 标签 + 时间筛选列表 | 扫描 |
| **13.4 深度阅读 UI** | `DeepReadMode.tsx`：文章全屏 + 右侧栏（推荐/笔记/影响/触发器状态）| 深度 |
| **13.5 告警模式 UI** | `AlertMode.tsx`：红色横幅 + 告警中心 Inbox | 告警 |
| **13.6 触发器状态可视化** | 在 knowledge_items 详情页显示 5 阶段进度条 | 跨模式 |
| **13.7 KnowledgePlanningPanel** | `frontend/src/components/knowledge/KnowledgePlanningPanel.tsx`：基于 reading_states + lifecycle + KL 状态生成个性化规划动作（见 B.7.5 完整设计）| 规划引导 |
| **13.8 planning_action_check job** | `backend/scheduler/jobs.py` 注册 `planning_action_check` 每 10min 跑一次（见 B.9.7）| 调度 |
| **13.9 tests** | 4 模式组件 + dashboard + planning panel 渲染测试 | 25+ 用例 |

> **注 1**: 6 种认知模式中的「整理模式（Outbox）」和「复习模式（SM-2）」由 Phase 17 实施，因为依赖 chunks + attention_score + sm2_reviews 等 Phase 16-17 基础设施。
>
> **注 2**: **规划引导（KnowledgePlanningPanel）独立于 6 模式实施**——它可作为 6 模式外的常驻侧边栏，或在 dashboard 顶部嵌入。即使 6 模式未完成，基于 reading_states + lifecycle 状态仍能给出动作建议。

### B.10.7 Phase 14：子系统联动

| 任务 | 详情 | 联动 |
|---|---|---|
| **14.1 tech_stack_drift 任务** | `backend/services/codegarden_drift.py`：knowledge 新 tech → codegarden 评估 | Knowledge ↔ Codegarden |
| **14.2 CVE 双向同步** | `backend/services/cve_knowledge_sync.py`：双向去重 + sync retry + 死信 | Knowledge ↔ Security |
| **14.3 跨域 entity 命名空间** | `entity_type` 统一：concept / tool / vendor / person / cve / technique / standard / event | 跨域 |
| **14.4 Security Graph 引用 Knowledge concepts** | security.cve_nodes.cve_id → knowledge.item_entities[entity_name] | Security → Knowledge |
| **14.5 tests** | 联动场景测试 | 15+ 用例 |

### B.10.8 Phase 15：清理 + 文档 + 迁移

| 任务 | 详情 |
|---|---|
| **15.1 删 kv_cache** | `migration 045_v1.7_drop_kv_cache.sql` |
| **15.2 删 /api/agent/* 路由** | 移除 deprecated 路由 |
| **15.3 删 4 个 MCP tool** | trigger_extract_tags / mark_digest_read / create_alert_rule 推迟 / trigger_cubox_sync 改本地 |
| **15.4 写 v1.7 迁移指南** | `docs/v1_to_v2_migration.md`：含 5 阶段映射 + 触发器启用步骤 |
| **15.5 写 v1.7 用户文档** | `docs/hotspot_v2_user_guide.md`：5 触发器说明 + 4 模式使用 |
| **15.6 更新 CHANGELOG** | `docs/CHANGELOG.md`：v1.7 新增功能 + 破坏性变更 |
| **15.7 更新 README** | 同步到 v1.7 状态（5 子系统、13 MCP tool、5 阶段）|

### B.10.10 Phase 16：Hybrid AI（Crawl4ai + 本地 LLM + 外部 Agent 并存）

> **v1.7 重大设计变更**：v1.7 Option A 完全依赖外部 Agent，v1.7 引入 Hybrid AI 让 hotspot 具备可选的本地 AI 能力。详见 B.13 完整设计。

| 任务 | 详情 | 验收 |
|---|---|---|
| **16.1 LLM 配置文件 schema** | `config/llm.yaml` + 校验 + 文档 | 4 个场景配置可加载 |
| **16.2 LLMService 实现** | `backend/services/llm_service.py`：多 provider + 降级 + 缓存 | Ollama + OpenAI + Qwen 三 provider 单元测试通过 |
| **16.3 评分任务迁移 T1** | T1 评分从 MCP `score_item` 改 `llm_service.score()` | 100 条样本评分延迟降低 60%+ |
| **16.4 摘要任务迁移 T3** | T3 摘要从 MCP `enrich_concept` 改 `llm_service.summarize()` | 本地 LLM 摘要延迟 < 3s |
| **16.5 (合并到 T3)** | ~~Chunk 摘要生成~~ | **删除**：已并入 T3 触发器副作用（见 B.6.2 T3 副作用项 2）|
| **16.6 Crawl4ai 集成** | `backend/parsers/crawl4ai_parser.py` + 4 源迁移 | 4 源 (hn_thread/reddit_thread/news_article/bid_announcement) 抓取成功率 ≥ 80% |
| **16.7 配置降级矩阵** | 5 种缺失配置场景的降级行为 | 全部通过集成测试 |
| **16.8 成本监控** | `cost_alert` 触发 + 日/月 USD 限额 | 单日 LLM 成本 dashboard 可视化 |
| **16.9 tests** | `test_llm_service / test_crawl4ai / test_hybrid_ai` | 25+ 用例 |

**关键 API**:

```python
# LLMService 暴露给触发器
from backend.services.llm_service import llm_service

# T1 评分
score = await llm_service.score(content=item.text, hotspot_id=item.id)

# T3 摘要
summary = await llm_service.summarize(chunks=item.chunks)

# T3 chunk 摘要（批量）
chunk_summaries = await llm_service.summarize_chunks(
    chunks=item.chunks,
    batch_size=10
)

# MCP tool 兜底
background = await llm_service.enrich_concept(concept_name="RAG")
```

### B.10.11 Phase 17：Chunks + Attention Heatmap + 6 模式完整

> **v1.7 收尾 Phase**：完成 v1.7 优秀设计的全部实施。详见 B.4.5 / B.4.6 / B.9.5。

| 任务 | 详情 | 验证 |
|---|---|---|
| **17.1 chunks 字段迁移** | `migration 046_v1.7_chunks.sql` + `knowledge_chunks` 表 | schema 校验通过 |
| **17.2 (合并到 Phase 11.3)** | ~~chunk 生成器~~ | **删除**：trafilatura 段落切分已由 Phase 11.3 实施，T3 触发时复用 `get_item_chunks()` |
| **17.3 (合并到 T3)** | ~~chunk 摘要~~ | **删除**：chunks_meta 生成已并入 T3 触发器副作用（见 B.6.2 T3）|
| **17.4 chunk 级 FTS5** | `search_knowledge` 支持 chunk_index 返回 | 搜索结果含 chunk 引用 |
| **17.5 chunk 级 UI** | 深度阅读模式高亮 chunk，点击跳转原文 | 前端组件 5 用例通过 |
| **17.6 attention_score 计算** | `backend/services/attention_scorer.py`：5 维度加权 | 单元测试 5 用例 |
| **17.7 attention 事件采集** | 前端埋点：view/dwell/scroll/favorite/annotation | 6 种事件 100% 采集 |
| **17.8 attention 聚合 job** | `attention_aggregate` 每 30 分钟跑一次 | job 启动 + 写回 frontmatter |
| **17.9 AttentionHeatmap 组件** | `AttentionHeatmap.tsx`：30 天 × 时间段热图 | 组件测试 5 用例 |
| **17.10 整理模式（Outbox）UI** | `OutboxMode.tsx`：清单视图 + attention_score 排序 | 组件测试 8 用例 |
| **17.11 复习模式（SM-2）** | `ReviewMode.tsx` + SM-2 算法 + sm2_reviews 表 | 卡片翻转 + 自评 + 评分入库 |
| **17.12 简报/扫描/深度 完善** | 4 模式 UI 完善（chunk 高亮、attention 显示）| 4 组件测试全过 |
| **17.13 tests** | `test_chunks / test_attention / test_6_modes` | 30+ 用例 |

**验收**: 6 种认知模式全部在 UI 可用；知识库每条 items 含 chunks + attention_score；用户可在简报模式看到 30 天热图。

### B.10.12 Phase 总览（v1.7 = 10 个 Phase，~46 天）

| Phase | 名称 | 周期 | 关键交付 | 状态 |
|---|---|---|---|---|
| **8** | 复利基础设施 + 资讯收藏聚合 | ~6 天 | simhash + 4 表 + 4 MCP tool + **KnowledgeFavoritesView（B.6.7）**| 🆕 v1.7 |
| **9** | 资讯抓取流程标准化 | ~4 天 | 断点续传 + 4 类验证 + 结构化日志 | ✅ v1.9 已完成 |
| **10** | T1/T2 触发器 | ~4 天 | 状态机 + 60s/120s 调度 | 🆕 v1.7 |
| **11** | 抓取层现代化 | ~5 天 | BackendSession + 6 个新 collector | 🆕 v1.7 |
| **12** | T3/T4/T5 + 告警 | ~6 天 | 状态机完成 + 3 类告警规则 | 🆕 v1.7 |
| **13** | 复利可视化 + 4/6 模式 + 规划引导 | ~4 天 | 仪表盘 + 简报/扫描/深度/告警 + PlanningPanel | 🆕 v1.7 |
| **14** | 子系统联动 | ~3 天 | tech_stack_drift + cve 同步 | 🆕 v1.7 |
| **15** | 清理 + 文档 + 迁移 | ~5 天 | 删 4 项 + 迁移指南 | 🆕 v1.7 |
| **16** | **Hybrid AI** | **~6 天** | **LLMService + Crawl4ai + 4 源迁移** | 🆕 v1.7 |
| **17** | **Chunks + Attention + 6 模式完整** | **~7 天** | **chunks 表 + 热图 + 整理/复习模式** | 🆕 v1.7 |
| **总预估** | | **~46 天** | 6+4+5+6+4+3+5+6+7（v1.7 Phase 8 + 10–17，不含 v1.9 Phase 9）| |

**总变化**: v1.7 28 天 → v1.7 46 天，**+64%**（5 阶段 + 5 触发器 + 告警 + 4 模式 + Hybrid AI + chunks/attention + 6 模式完整 + 规划引导）

> **实施灵活度（重要）**: hotspot 是**常驻服务**而非一次性项目。上表 10 个 Phase 是**设计目标**，不是固定计划。用户可在任意 Phase 启动 v1.7 部分能力，剩余能力渐进式补齐：
> - **必须先启动**: Phase 8（数据模型）+ Phase 10（T1/T2 触发器）+ Phase 15 部分（清理）
> - **可后补**: Phase 11/12/13/16/17 顺序可调整
> - **规划引导可独立于 6 模式实施**: 即使 6 模式未完成，KnowledgePlanningPanel 仍能基于 reading_states 数据给出动作建议

---

## B.11 验收标准

### B.11.1 北极星指标

| 指标 | 目标 | 验收 |
|---|---|---|
| 知识库日增量 | ≥ 10 items/天 | 30 天平均值达标 |
| 新信息复用率 | ≥ 30% | 新信息中 item_entities 关联到已有 concept 的比例 |
| MCP tool 调用 P95 | < 500ms | Phase 8 测试 |
| 跨源去重准确率 | ≥ 95% | simhash + URL canonicalize 联合测试 |
| 评分后自动入库延迟 | < 5 min | 评分完成后到 knowledge_items 创建的时间 |
| 资讯收藏聚合视图响应 | < 300ms (P95) | `/api/knowledge/imported` 5 数据源合并 + 去重 + 分页 |

### B.11.2 Phase 验收

| Phase | 门禁 |
|---|---|
| 8 | simhash 跨源去重率 ≥ 95%；13 MCP tool 通过外部 Agent 调通；4 新表 CRUD 全过；**资讯收藏聚合视图 5 类型 + 名称 + 时间 + 分页 e2e 8 用例通过**|
| **9** | T1/T2 状态机引擎工作；T1 推进 95%+ 成功率；T2 关联发现率 ≥ 80%；调度器 24 job 全部启动 |
| 10 | BackendSession 注入 6 个新 collector；可读 ID 规范化；trafilatura fallback 工作；6 个新 collector 各自 5 用例通过 |
| 11 | T3/T4/T5 触发器工作；3 类告警规则（tech_stack/CVE/标讯）触发；4 模式 UI 渲染 |
| 12 | KnowledgeCompoundingDashboard 渲染；24 job 中触发器类 job 跑通；daily_digest 自动生成 |
| 13 | tech_stack_drift 触发并评估；Security.cve_nodes 双向同步；跨域 entity 命名空间生效 |
| 14 | kv_cache DROP 完成；/api/agent 路由全删；4 MCP tool 移除；迁移指南完整 |
| **15** | **LLMService 多 provider 工作；Crawl4ai 4 源抓取成功率 ≥ 80%；T1/T3 延迟降低 60%+；5 种降级场景全过；4 场景 LLM 配置可加载** |
| **16** | **chunks 表 + chunks_meta 写入；attention_score 5 维度加权准确；AttentionHeatmap 渲染；6 模式 UI 全可用；sm2_reviews 卡片翻转** |

### B.11.3 Hybrid AI 专项验收

| 维度 | 验收 |
|---|---|
| **配置灵活性** | 4 个场景（Ollama only / Qwen / OpenAI+本地 / v1.7 Option A）均能启动 hotspot |
| **降级正确性** | LLMService 5 种缺失配置场景全通过集成测试 |
| **T1 性能** | Ollama 评分 < 500ms / 条；OpenAI 评分 < 300ms / 条 |
| **T3 性能** | Ollama 摘要 < 3s / 条；OpenAI 摘要 < 2s / 条 |
| **Crawl4ai 抓取** | hn_thread/reddit_thread/news_article/bid_announcement 4 源成功率 ≥ 80% |
| **API key 安全** | llm.yaml 中 api_key_env 引用环境变量，不存明文；日志自动 mask |
| **成本控制** | daily_usd_limit 超额触发 warn / block / fallback_local |
| **MCP 兼容** | 13 tool 仍可调，外部 Agent 工作流不变 |
| **性能对比** | 启用 Hybrid AI 后 T1 评分延迟降低 ≥ 60%；T3 摘要延迟降低 ≥ 40% |

### B.11.4 Chunks + Attention + 6 模式 专项验收

| 维度 | 验收 |
|---|---|
| **chunks 生成** | 100 篇样本 chunks 数 1-15 合理；chunks_meta 写回 .md frontmatter |
| **chunk 摘要** | 100% chunks 有 summary；长度 30-100 字 |
| **chunk 搜索** | `search_knowledge` 返回 chunk_index + 引用；UI 可点击跳转 |
| **attention 计算** | 5 维度加权公式准确；30 分钟聚合 job 写回 frontmatter |
| **热图渲染** | 30 天 × 3 时段（早/中/晚）热图；点击格子弹该时段 items |
| **简报模式** | 一句话摘要 + 3 篇关键文章 + 数据源状态 |
| **快速扫描模式** | 分类 + 标签 + 时间筛选列表 |
| **深度阅读模式** | 文章全屏 + 右侧栏（推荐/笔记/影响/触发器状态/chunk 高亮）|
| **整理模式（Outbox）** | 清单视图（未处理+待复习+待确认+按 attention_score 排序）|
| **复习模式（SM-2）** | 卡片翻转（概念→自评→答案）；评分入库 sm2_reviews；下次复习时间计算正确 |
| **告警模式** | 红色横幅 + 告警中心 Inbox |

---

## B.11.5 测试策略（v1.7 完整保留 + 5 触发器专项测试）

> **保留 v1.7 测试金字塔**：单元 → 集成 → e2e 三层 + 5 触发器专项测试。

### 测试金字塔

```
        ╱╲
       ╱  ╲         E2E（端到端）
      ╱ 5% ╲         - Playwright/Cypress（v1.7 不实施，前端手动）
     ╱──────╲
    ╱        ╲       集成测试（API + DB + 调度器）
   ╱   25%    ╲      - test_*.py e2e 流程
  ╱────────────╲
 ╱              ╲    单元测试（pure functions + 5 触发器）
╱     70%        ╲   - test_simhash / test_t1 / test_t2 / test_state_machine
──────────────────
```

### 测试覆盖目标

| 层级 | 工具 | 目标覆盖率 | 验证 |
|------|------|----------|------|
| 单元测试 | pytest | ≥ 80% | `coverage report --fail-under=80` |
| 集成测试 | pytest + tmp_path + monkeypatch | 关键流程 100% | test_codegarden_phase2b_e2e.py 等 |
| e2e | pytest + requests | 24 job 启动验证 | test_kl_triggers_e2e.py（v1.7 新增）|
| 前端 | Vitest + jsdom | 关键组件 ≥ 80% | npx vitest run |
| 类型 | tsc | 0 错误 | tsc --noEmit |
| Lint | ruff + eslint | 0 错误 | ruff check . && eslint . |

### 5 触发器专项测试

#### T1 测试 (`test_t1_raw_to_refine.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| T1-1: 评分 ≥ 阈值 | hotspot + score=8.0 | lifecycle=kl:refine, 写 ai_scores |
| T1-2: 评分 < 阈值 | hotspot + score=5.0 | archive, 不推进 |
| T1-3: 评分 MCP 超时 | hotspot + 模拟 timeout | 3 次重试后入死信, lifecycle 不变 |
| T1-4: simhash 重复 | hotspot + 已存在 fingerprint | merge_into_existing, 不创建新 |
| T1-5: tag 提取失败 | hotspot + 空 content | 仅更新 lifecycle, warning 日志 |
| T1-6: 批量处理 | 100 hotspots | 95%+ 成功推进 |
| T1-7: 调度器触发 | 启动 job 60s 后 | 至少执行 1 次 |
| **T1-8 (反向): `test_t1_klraw_alert_red_to_green`** | **故意把 1 条 `kl:raw` item 删掉** | **看告警是否变红；恢复后是否回绿** |

#### T2 测试 (`test_t2_refine_to_link.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| T2-1: 找到 ≥1 关联 | hotspot + 已有 items | 调 MCP link_items, lifecycle=kl:link |
| T2-2: 无关联 concept | hotspot + 无匹配 | 创建新 concept, lifecycle=kl:link |
| T2-3: Agent 30min 不响应 | hotspot + 模拟不响应 | 标记 pending_link, 5 次后入死信 |
| T2-4: 关联数 < 3 | hotspot + 1 关联 | 强制推进 (不强制 ≥3) |

#### T3 测试 (`test_t3_link_to_structure.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| T3-1: 关联数 ≥ 3 + 摘要成功 | hotspot + 3 关联 | 写 summaries, lifecycle=kl:structure |
| T3-2: 关联数 < 3 | hotspot + 2 关联 | 不推进, 等关联 |
| T3-3: 摘要 MCP 失败 | hotspot + 模拟失败 | pending_summary, 3 次后入死信 |

#### T4 测试 (`test_t4_structure_to_publish.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| T4-1: score ≥ 阈值 + 24h 稳定 | hotspot | 写 .md, 同步 SQLite, lifecycle=kl:publish |
| T4-2: score < 阈值 | hotspot + score=7 | 不自动发布, 保留 kl:structure |
| T4-3: 24h 内结构变更 | hotspot | 不发布, reason=unstable |
| T4-4: 文件写入失败 | 模拟 IO 错误 | pending_publish, 5 次后入死信 |

#### T5 测试 (`test_t5_publish_to_refine.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| T5-1: 用户主动回滚 | 手动调 MCP | 备份 .md, stale 标记, 触发 T1 |
| T5-2: 文件被外部修改 | 模拟外部变更 | 警告但允许执行 |
| T5-3: 备份失败 | 模拟 IO 错误 | 拒绝执行, 硬错误 |

### 资讯收藏聚合视图专项测试（Phase 8.9-8.11）

#### 聚合服务测试 (`test_imported_aggregator.py`)

| 用例 | 输入 | 期望 |
|------|------|------|
| AGG-1: 5 数据源合并 | 5 favorites + 5 cubox + 3 bookmark + 2 secnews_archive | 15 条按 ingested_at DESC |
| AGG-2: URL 去重 (favorites 优先) | 1 fav + 1 ki 同 URL | 仅返回 favorites |
| AGG-3: 名称关键词搜索 | keyword="AI" | title LIKE '%AI%' 命中 |
| AGG-4: 类型筛选 (5 类型) | type="ai" | category 映射正确 |
| AGG-5: 时间范围筛选 | since=2026-07-20, until=2026-07-26 | BETWEEN 命中 |
| AGG-6: 分页 + has_more | limit=10, offset=10 | total 准确, has_more 正确 |
| AGG-7: origin 分布统计 | 混合数据 | 5 origin 计数正确 |
| AGG-8: 边界 (空数据) | 全部 0 | 返回空数组 + total=0 |

#### 组件测试 (`KnowledgeFavoritesView.test.tsx`)

| 用例 | 验证 |
|------|------|
| CV-1: 5 个 type chip 切换 | active 高亮 + 列表更新 |
| CV-2: 名称搜索 300ms debounce | 输入后等待 300ms 才触发 |
| CV-3: 时间 range picker | date input 改变触发 fetch |
| CV-4: 翻页 上一页/下一页/跳转 | URL 不变（仅本地 state）|
| CV-5: 收藏切换 ☆ → ★ | 调 add_favorite，本地状态更新 |
| CV-6: 空态 / 错误态 | EmptyState 渲染 + 错误条 |
| CV-7: 5th action card 点击 → 跳转 | mock useNavigate 验证 |

### 关键测试场景

- **回归测试**：v1.7 全部 67 个测试文件必须保持通过
- **5 触发器端到端**：100 条样本走完整 T1→T5，验证 5 阶段都触发
- **复利验证**：30 天后知识库日增量 ≥ 10 items，关联率 ≥ 30%
- **告警验证**：3 类告警规则各触发 1 次，验证告警 UI 渲染
- **MCP 集成**：13 tool 通过外部 Agent 调通 100%

### 测试命令（保留 v1.7）

```bash
# 后端
.venv/bin/python3 -m pytest backend/tests/ -v
.venv/bin/python3 -m pytest backend/tests/ -k "trigger_t"  # 5 触发器专项
.venv/bin/python3 -m pytest backend/tests/ -k "merge"      # 同步
.venv/bin/python3 -m pytest backend/tests/ -k "kl_state"   # 状态机
.venv/bin/python3 -m py_compile backend/services/kl_state_machine.py

# 前端
cd frontend
npx vitest run
npx vitest run --watch
npx tsc --noEmit
npm run build

# CI: .github/workflows/ci.yml
# Python compile + pytest + tsc + vitest + vite build
```

---

## B.11.6 迁移策略（v1.7 → v1.7）

> **保留 v1.7 迁移原则**：数据零丢失、平滑过渡、可回滚。

### 5 阶段映射

| v1.7 lifecycle | v1.7 lifecycle | 迁移 |
|----------------|---------------|------|
| `signal` | `kl:raw` | 自动 REPLACE |
| `amplify:tagged` | `kl:refine` | 自动 REPLACE |
| `amplify:linked` | `kl:link` | 自动 REPLACE |
| `amplify:complete` | `kl:structure` | 自动 REPLACE |
| `generate` | `kl:publish` | 自动 REPLACE |
| （空 / NULL）| `kl:raw` | 默认设 kl:raw（v1.7 老 items 已通过 migration 046 迁移）|

### 数据迁移（migration 043-045）

1. **migration 043_v1.7_fingerprints_scores.sql**：
   - 新增 4 表：`content_fingerprints / ai_scores / item_entities / knowledge_links`
   - 加 6 个索引（按查询模式优化）

2. **migration 044_v1.7_kl_rename.sql**（可选，5 阶段已用 `kl:` 前缀）：
   - REPLACE `signal` → `kl:raw`
   - REPLACE `amplify:tagged` → `kl:refine`
   - REPLACE `amplify:linked` → `kl:link`
   - REPLACE `amplify:complete` → `kl:structure`
   - REPLACE `generate` → `kl:publish`
   - SET NULL lifecycle → `kl:raw`（兜底）

3. **migration 045_v1.7_drop_kv_cache.sql**：
   - DROP TABLE `kv_cache`（保留 schema 注释）

### 可读 ID 迁移（双写策略）

| 阶段 | hotspot.id | 兼容 |
|------|------------|------|
| v1.7 启动 | 旧 hash ID 保留 | 直接读 |
| v1.7 写入 | 新 hotspot 双写：旧 hash + 新可读 | 1 个月内切 |
| v1.7.1 | 旧 hash ID 标 deprecated | 警告 |
| v2.1 | 完全切到可读 ID | 旧 hash 失效 |

### MCP tool 迁移

| v1.7.6 tool | v1.7 状态 | 迁移路径 |
|-------------|-----------|---------|
| `trigger_extract_tags` | 删除 | 改为 T1 触发器自动 |
| `trigger_cubox_sync` | 删除 | 保留为本地 cron job |
| `create_alert_rule` | 推迟 v2.1 | v1.7 内置 3 类基础规则 |
| `mark_digest_read` | 删除 | reading_states 自动追踪 |
| 5 读 tool | 保持 | 无变化 |
| 4 保留写 tool | 保持 | 无变化 |
| （新增）4 v1.7 tool | 新增 | 直接可用 |

### 配置迁移

| v1.7 | v1.7 | 迁移 |
|------|------|------|
| `proxy_config.json` | 保持 | 无变化 |
| 无 | `pipeline_config.json` | 新增（4 源示例 + 阈值） |
| 无 | `kl_thresholds.json` | 新增（5 阶段阈值配置） |
| `favorites` 表 + `/api/favorites` | 保持 | 仍为单表入口；新增 `/api/knowledge/imported` 聚合视图（B.6.7）|
| `knowledge_items` 表 | 保持 | repo `list_items()` 扩展 `sources`/`keyword`/`exclude_urls` 参数，向后兼容 |

### 部署步骤

1. **停止 hotspot 服务**
2. **备份数据库**：`cp hotspot.db hotspot.db.v1.7.backup`
3. **执行 migration 043-045**（自动）
4. **替换 backend 二进制**
5. **替换 frontend dist**
6. **启动 hotspot 服务**
7. **运行 5 触发器 1 次**：`python -m backend.scheduler.manual_run --trigger all`
8. **验证仪表盘**：日增量 ≥ 10 items/天
9. **保留 v1.7 数据 30 天**（兜底回滚）

### 5 阶段 lifecycle 数据迁移（migration 046_lifecycle_v2.sql）

**问题**: 生产 `knowledge_items.lifecycle` 字段 100% 有值，但全部是 v1.7 旧 3 阶段（`generate` / `signal` / `amplify:tagged`），与 v1.7 设计 5 阶段（`kl:raw/refine/link/structure/publish`）不一致。

**映射规则**:
- `signal`（未精炼）→ `kl:raw`
- `amplify:tagged`（已打 tag 待关联）→ `kl:refine`
- `generate`（已生成摘要）→ `kl:structure`（v1.7 升级到 kl:structure 等同 generate 的语义，并加 T3 触发 chunks）

**不映射**: 无 lifecycle 值的（如有）→ 保持 `NULL` 留给 Phase 10 T1 触发器处理。

**SQL 草案**:
```sql
-- migration 046_lifecycle_v2.sql
UPDATE knowledge_items
SET lifecycle = CASE lifecycle
    WHEN 'signal'         THEN 'kl:raw'
    WHEN 'amplify:tagged' THEN 'kl:refine'
    WHEN 'generate'       THEN 'kl:structure'
    ELSE lifecycle
END,
updated_at = datetime('now')
WHERE lifecycle IN ('signal', 'amplify:tagged', 'generate');

-- 验证：应输出 0
SELECT COUNT(*) FROM knowledge_items
WHERE lifecycle IN ('signal', 'amplify:tagged', 'generate');
```

**回滚**: 不删原值，迁移 SQL 写在 `046_*_down.sql` 里反向映射。

**验收**: `SELECT lifecycle, COUNT(*) FROM knowledge_items GROUP BY lifecycle` 应只看到 3 个 kl:* 值（外加可能的 NULL 旧值）和 0 个旧 3 阶段值。

### 回滚策略

| 触发条件 | 回滚动作 |
|---------|---------|
| 5 触发器导致数据异常 | 关闭触发器 job，仅保留 catchup |
| 知识库日增量 < 1 item | 检查阈值配置 + 触发器日志 |
| MCP tool 调用失败率 > 10% | 降级为 v1.7.6 模式（保留 9 读 + 4 保留写）|
| 严重 bug | 用 `hotspot.db.v1.7.backup` 还原 |

### 兼容性

- **前端**：v1.7 前端可继续用 v1.7 后端（忽略新字段）
- **后端**：v1.7 后端不能向下兼容 v1.7 前端（部分 UI 缺失）
- **数据库**：v1.7 DB 可被 v1.7 读取（migration 自动）
- **MCP**：v1.7.6 agent 调 v1.7 缺失 tool 会报错，建议升级

---

---

## B.12 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|---|
| 1 | simhash 误判（不同新闻被合并）| 中 | 中 | 阈值 5 起步，先 false positive 监控；用户报告误判后放宽 |
| 2 | AI 评分波动（同一新闻两次评分差大）| 高 | 中 | 存多版本评分；用最新 + 来源标识；v1.7 不自动应用，v2.1 引入置信度 |
| 3 | 自动入库导致知识库噪声 | 中 | 中 | 阈值 ≥ 7 才入；v1.7 不自动应用 knowledge_links；v2.1 引入"已读自动归档" |
| 4 | 6 个新 collector 反爬失败 | 中 | 低 | 借鉴 Horizon 失败模式；v1.7 先实现 3 个（hn/rss/openbb），其余 3 个 v2.1 |
| 5 | trafilatura 引入新依赖 | 低 | 低 | 作为 optional，pip install 时可选 |
| 6 | 可读 ID 迁移复杂 | 中 | 中 | 保留 hash ID 作为 alias；v1.7 双写，v2.1 切读路径 |
| 7 | 外部 AI Agent 不支持 score_item tool | 中 | 高 | 保留 manual `add_favorite` 路径；评分先存后用 |
| 8 | Codegarden 联动破坏项目 | 低 | 高 | tech_stack_drift 只提示，不自动改；用户确认才改 |
| 9 | Security Graph 同步失败 | 中 | 中 | 双向 sync 用 retry + 死信队列；失败时降级为单向 |
| 10 | 删 /api/agent 路由破坏旧 agent | 低 | 中 | v1.7 保留 deprecated 1 个 minor 版本，v2.1 完全删 |
| 11 | 知识库日增量 < 10 items | 中 | 高 | 监控告警；分析原因（评分太严？源失效？）；调阈值或源 |
| 12 | 复利可视化性能差（4147+ items）| 中 | 中 | dashboard 走预聚合表 + 缓存；不直查 items 表 |
| 13 | chunks 字段生成失败（SPA / 反爬强站）| 中 | 中 | trafilatura 失败降级为单 chunk（整篇视为 1 个）；SPA 站改用 Crawl4ai 重抓 |
| 14 | 5 触发器互相等待死锁 | 低 | 高 | T2/T4 加 hard timeout（30min/24h）+ 自动 fallback；监控 `kl_pending_count` 队列；kl_dead_letter_retry 兜底 |
| 15 | attention_score 数据稀疏（v1.7 99.4% items 无 reading_states）| 高 | 中 | v1.7 启动时 backfill：从 SQLite history 推断初始 score；3 个月内新数据为主，旧 items 缓慢覆盖 |
| 16 | Crawl4ai / Playwright 代理配置与 proxy_config.json 不一致 | 中 | 中 | 统一从 `proxy_config.json` 读代理（见 B.13.5.2 v1.7 改造），删除 crawl_config.yaml 的 proxy_pool 硬编码；Playwright 通过 BackendSession 注入 |
| 17 | 资讯收藏聚合视图性能（>5000 条时 offset 分页慢）| 低 | 中 | offset 分页初期可接受；>5000 改 cursor 分页（与 hotspots 一致）；origin 分布条复用 items 总数缓存 |
| 18 | 资讯收藏聚合数据源语义模糊（favorites vs knowledge_items 重复）| 中 | 高 | 服务层用 `exclude_urls` 过滤 + favorites 优先；origin 字段 UI 区分；README 文档化 |
| 19 | 资讯收藏 5th action card 在移动端挤压 | 低 | 低 | grid `md:grid-cols-2` + 5th card `md:col-span-2` 全宽；移动端单列流式 |

---

## B.13 hotspot Hybrid AI 设计（Crawl4ai + 可选本地 LLM）

> **v1.7 重大设计变更**：v1.7 Option A 完全依赖外部 AI Agent；v1.7 引入 **Hybrid AI**：hotspot 可选配置本地 LLM + Crawl4ai 高阶抓取，与外部 Agent 并存，发挥各自优势。

### B.13.1 为什么需要 Hybrid AI（设计动机）

**v1.7 Option A 的痛点**:
- ❌ 5 触发器 T1/T3 必须等待外部 Agent 响应，延迟高
- ❌ 评分、提取等机械任务交给 LLM 浪费外部 Agent 算力
- ❌ 外部 Agent 离线时，T1/T3 全部阻塞
- ❌ 用户必须配置好外部 Agent 才能用 hotspot
- ❌ Crawl4ai 高阶抓取未落地（v1.7 仅在 PRD 提及）

**v1.7 Hybrid AI 方案**:
- ✅ hotspot 可选配置本地 LLM（Ollama / OpenAI / Anthropic / 国产模型）
- ✅ T1/T3 机械任务优先用本地 LLM（低延迟、零依赖）
- ✅ T2/T4 仍用外部 AI Agent（需要用户判断）
- ✅ 采集层升级到 Crawl4ai（高阶内容提取）
- ✅ 配置缺失时降级为 v1.7 Option A（外部 Agent 模式）

### B.13.2 三层 AI 决策矩阵

| 任务 | v1.7（外部 Agent）| v1.7 Hybrid（默认）| 降级（无 LLM 配置）|
|------|------------------|------------------|------------------|
| **T1 评分** | 外部 Agent 调 `score_item` | 本地 LLM（gpt-4o-mini / qwen-turbo）| 保留 v1.7 外部 Agent |
| **T1 标签提取** | 本地规则 | 本地规则 + 本地 LLM 补全 | 本地规则 |
| **T1 实体提取** | 本地规则 + chunk NER | 本地规则 + 本地 LLM NER | 本地规则 |
| **T2 关联** | 外部 Agent 调 `link_items` | 同 v1.7（需用户判断）| 同 v1.7 |
| **T3 摘要** | 外部 Agent 调 enrich | 本地 LLM（gpt-4o / qwen-plus）| 外部 Agent |
| **T3 chunk 摘要** | 外部 Agent 批量 | 本地 LLM 批量（更高效）| 不生成 |
| **T4 发布决策** | 用户 + auto 阈值 | 同 v1.7 | 同 v1.7 |
| **采集 (RSS/Crawl)** | 传统 HTTP + trafilatura | **Crawl4ai 高阶抓取**（JS 渲染 + 智能提取）| 降级为 trafilatura |
| **告警规则匹配** | 规则引擎 | 同 v1.7 | 同 v1.7 |
| **codegarden drift** | 外部 Agent | 同 v1.7（需用户判断）| 同 v1.7 |

### B.13.3 LLM 配置文件 `config/llm.yaml`

```yaml
# hotspot/config/llm.yaml
# v1.7 新增：local LLM 配置，缺失时降级为 v1.7 Option A

enabled: true  # 总开关；false 时降级为外部 Agent 模式
default_provider: openai  # openai | anthropic | ollama | qwen | moonshot | glm
fallback_order:  # 失败时降级顺序
  - ollama       # 优先本地（零成本）
  - qwen         # 次选国产
  - openai       # 末选 openai

providers:
  # === 本地 Ollama（推荐，零成本）===
  ollama:
    type: ollama
    base_url: "http://127.0.0.1:11434"
    models:
      score: "qwen2.5:7b"           # T1 评分
      tag: "qwen2.5:7b"              # T1 标签补全
      ner: "qwen2.5:7b"              # T1 实体提取
      summary: "qwen2.5:14b"         # T3 摘要
      chunk_summary: "qwen2.5:7b"    # T3 chunk 摘要
    timeout_seconds: 30
    max_concurrent: 4

  # === OpenAI ===
  openai:
    type: openai
    api_key_env: "OPENAI_API_KEY"    # 从环境变量读
    base_url: "https://api.openai.com/v1"
    models:
      score: "gpt-4o-mini"           # $0.15/1M tokens
      tag: "gpt-4o-mini"
      ner: "gpt-4o-mini"
      summary: "gpt-4o"              # $5/1M tokens
      chunk_summary: "gpt-4o-mini"
    timeout_seconds: 20
    max_concurrent: 8

  # === 国产模型（Qwen）===
  qwen:
    type: openai_compatible
    api_key_env: "QWEN_API_KEY"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    models:
      score: "qwen-turbo"
      tag: "qwen-turbo"
      ner: "qwen-turbo"
      summary: "qwen-plus"
      chunk_summary: "qwen-turbo"

  # === Anthropic ===
  anthropic:
    type: anthropic
    api_key_env: "ANTHROPIC_API_KEY"
    models:
      summary: "claude-3-5-sonnet-20241022"
      chunk_summary: "claude-3-5-haiku-20241022"

# === 任务级覆盖（高级用法）===
task_overrides:
  t1_score:
    provider: ollama
    model: qwen2.5:7b
    temperature: 0.0
    max_tokens: 50
  t3_summary:
    provider: openai
    model: gpt-4o
    temperature: 0.3
    max_tokens: 500
  t3_chunk_summary:
    provider: ollama
    model: qwen2.5:7b
    temperature: 0.0
    max_tokens: 100
    batch_size: 10  # 一次批量处理 10 个 chunk

# === 限流与成本控制 ===
rate_limits:
  requests_per_minute: 60
  tokens_per_minute: 100000
cost_alert:
  daily_usd_limit: 5.0
  monthly_usd_limit: 100.0
  on_exceeded: warn  # warn | block | fallback_local

# === 缓存策略 ===
cache:
  enabled: true
  ttl_seconds: 86400  # 24h 缓存
  similarity_threshold: 0.95  # simhash ≥ 0.95 视为重复，直接返回缓存
```

### B.13.4 LLM Service 架构

```python
# backend/services/llm_service.py (v1.7 新增)
from typing import Literal

class LLMService:
    """统一 LLM 入口，支持多 provider + 降级 + 缓存"""

    def __init__(self, config_path: str = "config/llm.yaml"):
        self.config = load_config(config_path)
        self.providers = self._init_providers()
        self.cache = LLMCache(ttl=self.config['cache']['ttl_seconds'])

    async def score(self, content: str, hotspot_id: str) -> float:
        """T1 评分，返回 0~10"""
        cache_key = f"score:{simhash(content)}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 按 fallback_order 尝试
        for provider_name in self.config['fallback_order']:
            try:
                score = await self._call_provider(
                    provider_name, 'score', content
                )
                self.cache.set(cache_key, score)
                return score
            except Exception as e:
                log(f"Provider {provider_name} failed: {e}")
                continue

        # 全部失败 → 降级
        return self._fallback_score(content)

    async def summarize(self, chunks: list[str]) -> str:
        """T3 摘要"""
        # 优先用本地 LLM（Ollama）批量处理
        return await self._call_provider('ollama', 'summary', chunks)

    async def extract_entities(self, content: str) -> list[str]:
        """T1 实体提取"""
        # NER 任务
        prompt = f"提取以下文本中的命名实体（人名/公司/技术/产品）：\n{content}"
        return await self._call_provider('ollama', 'ner', prompt)

    async def enrich_concept(self, concept: str) -> str:
        """MCP tool: enrich_concept（也可由本地 LLM 兜底）"""
        return await self._call_provider('ollama', 'summary', f"解释 {concept}")

# 全局单例
llm_service = LLMService()
```

### B.13.5 Crawl4ai 高阶抓取

> **v1.7 PRD 提及 Crawl4ai 但未落地**，v1.7 正式实施。Crawl4ai 是开源 LLM-friendly web crawler，专为 AI 数据提取设计。

#### B.13.5.1 Crawl4ai vs 传统抓取

| 维度 | 传统 (httpx + BeautifulSoup) | Crawl4ai |
|------|------------------------|----------|
| JS 渲染 | ❌ 不支持 | ✅ 内置 Playwright |
| 反爬绕过 | 中 | 强（自动 UA 轮换 + 指纹）|
| LLM 提取 | ❌ 需手动解析 | ✅ 内置 LLM 提取（CSS selector / LLM extraction strategy）|
| Markdown 输出 | 需 trafilatura | ✅ 内置 markdown 转换 |
| 速度 | 快 | 中（首次 JS 渲染慢）|
| 适用场景 | RSS / API / 简单页面 | SPA / 动态内容 / 反爬强站 |

#### B.13.5.2 Crawl4ai 配置（v1.7 统一 proxy + Playwright 同步）

> **v1.7 改造原则**: Crawl4ai 与 Playwright 都走统一代理配置，删除 `crawl_config.yaml` 中 proxy_pool 硬编码，避免双源配置漂移。

```yaml
# backend/proxy_config.json (主代理配置 - 唯一来源)
{
  "http_proxy": "http://127.0.0.1:7897",
  "https_proxy": "http://127.0.0.1:7897",
  "backup_proxies": [  # v1.7 新增：备用代理池
    "http://127.0.0.1:7898",
    "socks5://127.0.0.1:1080"
  ],
  "no_proxy": ["localhost", "127.0.0.1", "*.local"],
  "rotation_strategy": "failover",  # 失败时切换
  "timeout_seconds": 10,
  "max_retries": 2
}
```

```yaml
# backend/collectors/crawl_config.yaml (v1.7 改造后)
crawl4ai:
  enabled: true
  browser: chromium  # chromium | firefox | webkit
  headless: true
  timeout_seconds: 30
  concurrent_requests: 3
  retry_attempts: 2

  # ❌ 删除 proxy_pool 硬编码（v1.7 统一从 proxy_config.json 注入）
  # anti_bot:
  #   proxy_pool: ["http://127.0.0.1:7897"]

  # ✅ 由 BackendSession / Crawl4aiSession 注入（见下文）
  # 备选代理从 proxy_config.json:backup_proxies 读取
  proxy_source: "proxy_config.json"  # 声明代理来源
  proxy_failover: true  # 失败时自动切换 backup_proxies

  llm_extraction:
    enabled: true
    provider: ollama
    model: qwen2.5:7b
    instruction: "提取文章标题、作者、发布日期、正文、关键实体"

  css_extraction:
    enabled: true
    fields:
      title: "h1.article-title"
      author: ".author-name"
      published_at: "time.published-date"
      content: "article.body"

  anti_bot:
    user_agent_rotation: true
    random_delay_seconds: [1, 3]
    stealth_mode: true
    # 代理仍由 Crawl4aiSession 注入

  cache:
    enabled: true
    backend: sqlite
    ttl_seconds: 604800  # 7 天
```

```python
# backend/parsers/crawl4ai_parser.py v1.7
class Crawl4aiParser:
    """Crawl4ai + Playwright 统一代理包装器"""

    def __init__(
        self,
        proxy_config_path: str = "backend/proxy_config.json",
        crawl_config_path: str = "backend/collectors/crawl_config.yaml"
    ):
        # ✅ 统一从 proxy_config.json 读代理
        self.proxy_cfg = load_proxy_config(proxy_config_path)
        self.primary_proxy = self.proxy_cfg['http_proxy']
        self.backup_proxies = self.proxy_cfg.get('backup_proxies', [])

        # ✅ Playwright 也走统一代理
        self.playwright_proxy = {
            'server': self.primary_proxy,
            'username': self.proxy_cfg.get('proxy_username'),
            'password': self.proxy_cfg.get('proxy_password'),
        }

        # 加载 Crawl4ai 特有配置（不含 proxy_pool）
        self.crawl_cfg = load_yaml(crawl_config_path)

    async def crawl(self, url: str) -> CrawlResult:
        """主调用：Playwright + Crawl4ai 统一代理"""
        for attempt in range(self.crawl_cfg['retry_attempts']):
            try:
                # 优先用主代理
                browser = await launch_chromium(
                    proxy=self.playwright_proxy,
                    headless=self.crawl_cfg['headless']
                )
                result = await self._crawl_with_browser(browser, url)
                await browser.close()
                return result
            except ProxyError as e:
                # 代理失败 → 切换备用代理
                log(f"Primary proxy failed: {e}, trying backup...")
                if self.backup_proxies:
                    self.playwright_proxy['server'] = self.backup_proxies.pop(0)
                    continue
                raise
            except Exception as e:
                log(f"Crawl4ai error: {e}")
                if attempt == self.crawl_cfg['retry_attempts'] - 1:
                    raise

    async def _crawl_with_browser(self, browser, url: str) -> CrawlResult:
        """通过 Playwright 渲染后 Crawl4ai 提取"""
        page = await browser.new_page()
        await page.goto(url, timeout=self.crawl_cfg['timeout_seconds'] * 1000)

        # 等待 JS 渲染
        await page.wait_for_load_state('networkidle')

        # Crawl4ai 提取（markdown / llm_extraction / css_extraction）
        result = await self._extract_with_crawl4ai(page)
        await page.close()
        return result
```

**统一性保证**:
| 组件 | 代理来源 | 配置位置 |
|---|---|---|
| **httpx / BackendSession** | `proxy_config.json:http_proxy` | 单一来源 |
| **Playwright** | `proxy_config.json:http_proxy`（由 Crawl4aiSession 注入）| 单一来源 |
| **Crawl4ai** | `proxy_config.json:http_proxy`（由 Crawl4aiSession 注入）| 单一来源 |
| **轮询代理** | `proxy_config.json:backup_proxies` | 单一来源 |

**故障切换流程**:
```
主代理失败 → 自动切 backup_proxies[0] → 仍失败 → backup_proxies[1] → ...
                                          ↓
                                   全部失败 → 标记 source_dead
                                          ↓
                                   source_revival_check 24h 后重试
```

#### B.13.5.2.1 代理切换策略细节（v1.7 新增）

> **目标**：明确"主代理失败"如何判定，备用代理按何种顺序尝试，以及每次失败如何记录。

**1. 失败判定标准**（满足任一即视为失败）：

| 失败类型 | 检测方法 | 重试条件 |
|---|---|---|
| **连接超时** | `asyncio.TimeoutError` / `httpx.ConnectTimeout` | timeout > 10s |
| **连接拒绝** | `ConnectionRefusedError` / `ProxyError` | TCP RST |
| **协议错误** | `407 Proxy Authentication Required` | 认证失败 |
| **HTTP 5xx** | `httpx.HTTPStatusError` | 502/503/504 |
| **DNS 失败** | `socket.gaierror` | 域名无法解析 |
| **TLS 握手失败** | `ssl.SSLError` | 证书/握手错误 |

**2. 切换顺序（rotation_strategy）**：

```python
# backend/services/proxy_pool.py (v1.7 新增)
class ProxyPool:
    """统一代理池，支持 failover + health score"""

    def __init__(self, config_path: str = "backend/proxy_config.json"):
        cfg = load_proxy_config(config_path)
        self.primary = cfg['http_proxy']               # 主代理
        self.backups = cfg.get('backup_proxies', [])   # 备用池
        self.strategy = cfg.get('rotation_strategy', 'failover')
        self.health_score = {self.primary: 1.0}        # 健康分（滑动窗口）
        for p in self.backups:
            self.health_score[p] = 0.5                  # 备用初始 0.5

    def get_next(self) -> str:
        """按策略选下一个代理"""
        if self.strategy == 'failover':
            # 默认：主 → 备 0 → 备 1 → ... 失败重置
            for proxy in [self.primary] + self.backups:
                if self.health_score[proxy] > 0.3:
                    return proxy
            return self.primary  # 全失败仍试主（标记 dead 兜底）
        elif self.strategy == 'round_robin':
            # 轮询：每次按 health_score 加权选
            return weighted_choice(self.health_score)

    def mark_failed(self, proxy: str):
        """失败：health_score -= 0.3（最低 0）"""
        self.health_score[proxy] = max(0, self.health_score[proxy] - 0.3)
        log_proxy_event(proxy, 'failed', score=self.health_score[proxy])

    def mark_success(self, proxy: str):
        """成功：health_score 恢复 +0.1（最高 1.0）"""
        self.health_score[proxy] = min(1.0, self.health_score[proxy] + 0.1)
        log_proxy_event(proxy, 'success', score=self.health_score[proxy])
```

**3. 故障检测 + 切换流程图**：

```
                    ┌──────────────────────┐
                    │ 抓取请求 (collector) │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ ProxyPool.get_next() │ ← health_score 加权选
                    └──────────┬───────────┘
                               ↓
                  ┌────────────┴────────────┐
                  ↓                         ↓
            primary (1.0)             backup_0 (0.5)
                  │                         │
            ┌─────┴──────┐                  │
            ↓            ↓                  │
        成功          失败 → mark_failed    │
        mark_success   (score 1.0 → 0.7)    │
            │            │                  │
            │      尝试 backup_0 ────────────┘
            │            │                  │
            │      ┌─────┴──────┐           │
            │      ↓            ↓           │
            │   成功         失败           │
            │      │            ↓           │
            │      │      尝试 backup_1 ────┘
            │      │            │
            │      │     ... 递归 ...
            │      │            │
            │      └─→ 全部失败
            │                ↓
            │         标记 source_dead
            │                ↓
            │         source_revival_check
            │         (24h 后重试)
            ↓
       返回 crawl result
```

**4. 代理健康度持久化**：

```sql
-- migration 048_v1.7_proxy_health.sql
CREATE TABLE IF NOT EXISTS proxy_health_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_url       TEXT NOT NULL,
    event           TEXT NOT NULL,        -- 'success' | 'failed' | 'timeout' | 'auth'
    source          TEXT,                 -- 哪个 collector 触发
    health_score    REAL,                 -- 当前分数
    latency_ms      INTEGER,
    error_message   TEXT,
    occurred_at     TEXT NOT NULL
);
CREATE INDEX idx_phl_proxy ON proxy_health_log(proxy_url, occurred_at DESC);
CREATE INDEX idx_phl_event ON proxy_health_log(event, occurred_at DESC);
```

**5. 启动时自检（避免配置错误）**：

```python
# backend/services/proxy_pool.py v1.7
async def startup_health_check(self):
    """服务启动时测试每个代理是否可达"""
    test_url = "https://www.google.com/generate_204"  # 轻量探测
    for proxy in [self.primary] + self.backups:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=5) as client:
                resp = await client.get(test_url)
                self.mark_success(proxy)
                log(f"Proxy OK: {proxy} (score={self.health_score[proxy]})")
        except Exception as e:
            self.mark_failed(proxy)
            log(f"Proxy DEAD: {proxy} ({e})", level='warning')

    # 至少 1 个代理可用
    if all(s < 0.3 for s in self.health_score.values()):
        raise RuntimeError("All proxies dead, check proxy_config.json")
```

**6. 跨组件统一性**：

| 组件 | 走 ProxyPool | 健康度写入 | 启动自检 |
|---|---|---|---|
| **httpx / BackendSession** | ✅ | ✅ | ✅ |
| **Playwright** | ✅ | ✅ | ✅（headless 探活）|
| **Crawl4ai** | ✅ | ✅ | ✅（playwright 探活）|
| **传统 collector (RSS/API)** | ✅ | ✅ | 可选（RSS 不需要代理）|

#### B.13.5.3 哪些 collector 用 Crawl4ai

| Collector | 抓取方式 | 原因 |
|-----------|---------|------|
| `rss` | 传统 | RSS 本身就是结构化 |
| `aihot` | 传统 | API 友好 |
| `github_trending` | 传统 | GitHub API |
| `hn` | 传统 | HN API 简洁 |
| **`hn_thread`** | **Crawl4ai** | 评论页面 JS 渲染 |
| **`reddit_thread`** | **Crawl4ai** | Reddit SPA 强制登录态 |
| **`twitter`** | **Crawl4ai** | SPA + 反爬强（v2.1 实施）|
| **`linkedin_post`** | **Crawl4ai** | 强反爬（v2.1 评估）|
| **`news_article`** | **Crawl4ai** | 主流新闻站 JS 渲染多 |
| **`bid_announcement`** | **Crawl4ai + 代理** | 政府采购网强反爬 |
| **未来扩展源** | 优先 Crawl4ai | 新源默认 Crawl4ai |

#### B.13.5.4 抓取成本估算

| 模式 | 单页成本 | 千页成本 | 适用 |
|------|---------|---------|------|
| 传统 httpx | 0 | 0 | RSS/API |
| Crawl4ai 本地 LLM | $0.001 | $1 | 中等规模 |
| Crawl4ai OpenAI | $0.01 | $10 | 大规模或重要源 |
| 混合（按源）| 平均 $0.003 | $3 | 推荐 |

### B.13.6 Hybrid AI 决策流

```
用户调用 hotspot
     ↓
[采集] 入口
     ├─ RSS/API/简单站 → 传统 httpx (无 LLM 成本)
     └─ SPA/反爬强站 → Crawl4ai
            ↓
         (可选 LLM extraction strategy)
            ↓
         [存储到 SQLite hotspots 表]
            ↓
[T1: 评分] 入口
     ├─ 本地 LLM (Ollama qwen2.5:7b) → score 0-10
     ├─ 失败 → OpenAI gpt-4o-mini
     ├─ 失败 → 外部 Agent (MCP score_item)
     └─ 全部失败 → fallback_score (基于关键词)
            ↓
[T1: 标签/实体提取] 入口
     ├─ 本地规则 (快速) → tags
     ├─ 本地 LLM NER → entities
     └─ 外部 Agent (可选增强)
            ↓
[T2: 关联] 入口
     └─ 外部 Agent 调 link_items (需要用户判断)
            ↓
[T3: 摘要] 入口
     ├─ 本地 LLM (Ollama) → 全文章节摘要
     ├─ 本地 LLM 批量 → chunk 摘要
     ├─ 失败 → OpenAI gpt-4o
     └─ 失败 → 外部 Agent enrich_concept
            ↓
[T4: 发布] 入口
     └─ 用户 + auto 阈值 (无需 LLM)
            ↓
[5 阶段完成] 写入 knowledge/items/{id}.md
```

### B.13.7 配置降级矩阵

| 缺失配置 | 行为 | 用户体验 |
|---------|------|---------|
| 无 `llm.yaml` 文件 | 完全降级为 v1.7 Option A | 必须配置外部 Agent |
| `enabled: false` | 同上 | 显式禁用 |
| 无 Ollama + 无 API key | T1/T3 报错 5xx | 必须配置至少一个 provider |
| 仅 Ollama | T1/T3 走本地，T2/T4 仍外部 | 完整工作 |
| Ollama + OpenAI | T1/T3 走本地（默认），失败降级 OpenAI | 最快 + 最可靠 |
| 全部配齐 | 全部走本地，外部 Agent 备用 | 零外部依赖 |

### B.13.8 安全与隐私

- **API key 加密存储**：复用 `secrets_service` Fernet 加密（与 sync_bundle 同源）
- **API key 不写日志**：loguru 过滤器自动 mask `api_key` 字段
- **本地 Ollama 优先**：默认 Ollama 零成本、零外传
- **数据本地化**：所有 LLM 调用仅传 content，不传 user_id 或设备信息
- **撤回机制**：用户可一键关闭所有 LLM 调用（设 `enabled: false`）

### B.13.9 性能目标

| 任务 | 目标 | 实测参考 |
|------|------|---------|
| T1 评分 (Ollama qwen2.5:7b) | < 500ms / 条 | M2 Mac 实测 380ms |
| T1 评分 (OpenAI gpt-4o-mini) | < 300ms / 条 | 实测 250ms |
| T3 摘要 (Ollama qwen2.5:14b) | < 3s / 条 | 实测 2.1s |
| T3 chunk 摘要 (Ollama qwen2.5:7b) 批量 10 | < 5s / 10 条 | 实测 3.8s |
| Crawl4ai 单页抓取 | < 8s | 实测 5-7s |
| Crawl4ai 100 页并发 3 | < 5min | 实测 4.2min |

### B.13.10 与 v1.7 Option A 的兼容性

| 兼容点 | 说明 |
|--------|------|
| MCP 13 tool | 完全兼容，外部 Agent 仍可调 |
| AI Agent 工作流 | 完全兼容，外部 Agent 优先级不变（T2/T4）|
| 数据格式 | 完全兼容，.md / SQLite 不变 |
| 5 阶段状态机 | 完全兼容，触发器逻辑不变 |
| 降级模式 | 完全兼容，无 LLM 时等同 v1.7 |
| 性能 | **提升**：T1/T3 不再等外部 Agent，延迟降低 60%+ |
| 成本 | **新增成本**：LLM API 调用费用（Ollama 零成本）|

### B.13.11 配置示例（4 个常见场景）

#### 场景 1：完全离线（Ollama only）

```yaml
enabled: true
default_provider: ollama
fallback_order: [ollama]
providers:
  ollama:
    type: ollama
    base_url: "http://127.0.0.1:11434"
    models: { score: "qwen2.5:7b", summary: "qwen2.5:14b", ... }
```

#### 场景 2：国内（Qwen 优先）

```yaml
enabled: true
default_provider: qwen
fallback_order: [qwen, ollama]
providers:
  qwen: { type: openai_compatible, base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", ... }
  ollama: { ... }
```

#### 场景 3：高质量（OpenAI + 本地兜底）

```yaml
enabled: true
default_provider: openai
fallback_order: [ollama, openai]
providers:
  ollama: { ... }
  openai: { type: openai, model: gpt-4o, ... }
```

#### 场景 4：v1.7 Option A 兼容（无 LLM）

```yaml
enabled: false
# 全部走外部 Agent（MCP score_item / enrich_concept）
```

---

## 附录 A · v1.7 → v1.7 决策变更总表

| 维度 | v1.7 | v1.7 | 理由 |
|---|---|---|---|
| 架构 | 5 层金字塔 + 双向环 | 3 层（接入/服务/数据）| 简化 |
| **知识生命周期** | **KL 5 阶段** | **KL 5 阶段 + 5 自动化触发器** | 完整保留 + 加 T1-T5 强制推进 |
| 存储 | OKF + SQLite + KV 缓存 | OKF + SQLite（删 KV）| KV 无人维护 |
| 标签 | 6 类（domain/category/framework/...）| 6 类（保持）| 已合理 |
| **6 种认知模式** | **设计完整，5 个未实施** | **v1.7 全部实施 6 种** | Hybrid AI + chunks + attention_score 支撑整理/复习模式 |
| **告警系统 M6** | **设计完整，未实施** | **实施 3 类基础规则**（tech_stack/CVE/标讯）| 用户明确要求恢复 |
| **离线间隔摘要** | **设计** | **v1.7 实施** | catchup 失败恢复后自动生成 |
| 快速捕捉 | 浏览器插件 | 推迟 v2.2 | 开发成本高 |
| **注意力热图** | **设计** | **v1.7 引入**（基于 reading_states + LLM）| 数据足够 + LLM 摘要支持 |
| **chunks 字段** | **设计未落地** | **v1.7 引入**（Hybrid AI 模式）| Local LLM 兜底 + 段落级精确引用 |
| 决策日志 | 设计 | 不做 | 概念模糊 |
| Email/Webhook 输出 | 设计 | 推迟 v2.1 | 单人 Web 优先 |
| Twitter/X 抓取 | 无 | 推迟 v2.1 | 反爬强 |
| 向量数据库 | 显式不引入 | 显式不引入 | 本地优先 |
| 内部 agent | 已删 | 永久不做 | Option A 落实 |
| knowledge_tasks 队列 | 已删 | 永久不做 | Option A 落实 |
| KV 缓存层 | 评估保留 | 删除 | 无人维护 |
| **AI 能力** | **v1.7 Option A（外部 Agent only）** | **Hybrid AI（本地 LLM + Crawl4ai + 外部 Agent 三层）** | 性能提升 60%+，零外部依赖选项 |
| **LLM 配置文件** | **无** | **v1.7 新增 `config/llm.yaml`** | 多 provider + 降级 + 成本控制 |
| **Crawl4ai 高阶抓取** | **PRD 提及未实施** | **v1.7 正式实施，迁移 4 源** | SPA/反爬强站必备 |
| MCP tool 数量 | 13 (5 读 + 8 写) | 13 (5 读 + 4 保留 + 4 新) | 组成优化（删 4 加 4）|
| 抓取层 | 9 个 domain collector | 9 + 6 个源 collector | 借鉴 Horizon |
| 抓取 ID | hash | 可读 `{source}:{subtype}:{native_id}` | 调试友好 |
| 抓取 session | 每个 collector 自建 | 共享 BackendSession | 借鉴 Horizon |
| 去重 | 仅有 URL dedup | URL + simhash | 借鉴 Horizon |
| AI 评分 | 源信任度 | AI 评分 0-10 (本地 LLM / MCP) | 借鉴 Horizon |
| 背景补全 | 无 | MCP enrich_concept + 本地 LLM 兜底 | 借鉴 Horizon |
| 多语言日报 | 无 | v1.7 不做 | 单人 ZH 优先 |
| **5 触发器** | **无（v1.7 100% items 用 v1.7 旧 3 阶段值，未迁 v1.7 5 阶段）** | **T1-T5 自动化触发器 + migration 046** | v1.7 核心创新 |
| **状态机引擎** | **无** | **KLStateMachine + 不变量检查** | 复利基础设施 |
| **复利机制** | **设计无落地** | **T1-T5 + 复利仪表盘 + 关联率 ≥ 30%** | 核心 |
| **chunks 元数据** | **设计未落地** | **v1.7 引入 chunks + chunks_meta + knowledge_chunks 表** | 段落级精确引用 |
| **attention_score** | **无** | **v1.7 新增 5 维度加权 + AttentionHeatmap** | 注意力热图 |
| 三大子系统协同 | 弱 | 强联动 (tech_stack_drift / cve sync) | 差异化 |
| **资讯收藏聚合视图** | **无（favorites + knowledge_items 分散）** | **v1.7 新增 `/api/knowledge/imported` + `/knowledge/imported` 页面（5 类型 + 名称 + 时间 + 分页）**| B.6.7 |
| 调度器 | 15 jobs | **30 jobs**（+4 触发器 + dead_letter + daily_digest + compounding_metrics + attention_aggregate + planning_action_check + 代码库实测补齐）| 触发器调度 + 规划引导 |
| **认知链路 6+1 环节** | **设计** | **T1-T5 一一对应** | 完整闭环 |
| **测试策略** | **70/25/5 比例** | **5 触发器专项测试 (T1-1~T5-3) + Hybrid AI 25 用例 + Chunks/Attention 30 用例** | 全面覆盖 |
| Phase 总数 | 7 (1-6 + 7) | **9 (8-16)** | +2（Hybrid AI + Chunks/Attention/6 模式完整）|
| 总预估 | 28 天 | **46 天** | +64%（Hybrid AI + Chunks + 6 模式 + 5 触发器 + 告警 + 4 模式 + 规划引导）|
| PRD 行数 | 2193 | **4087**（+86%；v1.7 优秀设计全保留 + 5 阶段/5 触发器/Hybrid AI/Chunks/规划引导/资讯收藏聚合扩展 + 附录 E/F 审计归档）| 实际 4087 行 |

## 附录 B · Horizon scrapers 借鉴表

| Horizon scraper | 借鉴 | 改造点 |
|---|---|---|
| base.py (ABC) | ✅ | 注入 BackendSession；返回 RawItem |
| hackernews.py | ✅ 直接借鉴 | 改 ID 为 `hn:story:{id}` |
| reddit.py | ✅ 借鉴 + 简化 | 砍 OAuth（v1.7 用 public JSON）|
| rss.py | ✅ 直接借鉴 | 加 rate-limit |
| github.py | ✅ 借鉴 | 已有 `gh:release:` 形式 |
| gdelt.py | ✅ 借鉴 | 加时区转换 |
| ossinsight.py | ✅ 借鉴 | 加缓存 |
| twitter.py / twitter_playwright.py | 🟡 v2.1 借鉴 | 反爬强，先推迟 |
| telegram.py | 🟡 v2.1 借鉴 | 需 telethon 库 |
| openbb.py | ✅ 借鉴 | 仅需 API key |
| mcp/server.py | ✅ 参考实现 | 改用 fastapi-mcp |
| mcp/horizon_adapter.py | ✅ 参考 | 适配 hotspot 数据模型 |
| extractors/trafilatura.py | ✅ 借鉴 | 加 fallback 链 |
| url_security.py | ✅ 借鉴 | 已有 FinalUrlGate |
| daily-run.sh | ✅ 借鉴 | 改 APScheduler daily_digest job |
| check_mcp.py | ✅ 借鉴 | 改 health check |

---

## 附录 C · 待确认问题清单（2026-07-27 战略审计）

> **来源**: B.0 战略审计 §10（PRD 评审前需与用户 / 干系人确认的 10 个问题）。
> **性质**: 战略层待拍板项，不阻塞 Phase 8-16 实施，但 M1 完成前（首轮可发布前）需逐一确认或显式推迟。

| # | 待确认问题 | 关联章节 | 默认建议 | 阻塞阶段 |
|---|-----------|---------|---------|---------|
| 1 | **AI 评分默认自动应用还是存待确认？** B.9 建议 v1.7 先存待确认、v2.1 再自动，需确认用户信任阈值与过渡节奏 | B.0.8 #7、B.0.7 P0-5 | **v1.7 评分先存待确认**（与 P0-5 评分工具解耦；M1 不阻塞） | M1 末（首轮发布） |
| 2 | **自动建立 knowledge_links 是否需要用户确认？** v1.7 设计为 Agent 经 link_items 确认；是否引入"高置信度自动 + 低置信度待确认"混合策略待定 | B.0.7 P0-4、B.0.8 #6 | **保持"Agent 确认"模式**，v2.1 引入置信度分层 | M1 末 |
| 3 | **本地 LLM（Ollama / Qwen）是否默认开启？** 影响首次启动体验与硬件门槛；默认关闭走外部 Agent，还是默认开启 Hybrid AI？ | B.0.7 P1-7、B.13 | **默认关闭**，高级用户在 B.13 设置面板开启 | M4 启用前 |
| 4 | **T4 自动发布 auto 模式默认开还是关？** auto 模式发布率 80% vs 手动确认 50%，需平衡"自动复利"与"误发布风险" | B.0.7 P1-1 | **默认手动确认**，M3 后视覆盖率回升再切 auto | M3 切 auto 前 |
| 5 | **单人天花板付费验证节奏？** 竞析建议先用 1–2 个垂直场景（安全研究 / 个人技术雷达）验证单人付费意愿，再决定是否开放轻量协作——验证指标与时间点待定 | B.0.5 行动建议 #5、B.0.8 #1 | **v1.7 不开放协作**；M4 后开 1 个垂直场景试点 | v1.7 之后 |
| 6 | **Hybrid AI 降级优先级？** 5 种缺失配置场景下，本地 LLM 与外部 Agent 的取舍顺序（延迟 / 成本 / 隐私）需明确 | B.0.7 P1-7、B.13 | **隐私优先：本地 LLM > 外部 Agent（隐私模式）> 外部 Agent（默认）** | M4 启用前 |
| 7 | **评分阈值（默认 7.0）与发布阈值（默认 8.0）是否开放用户配置？** 安全从业者 vs 轻量浏览者对噪声容忍度不同，是否需要分群阈值？ | B.0.6 北极星指标、B.0.7 P0-5 | **v1.7 内置默认阈值 + 高级配置可调**（Settings 面板） | M1 末 |
| 8 | **"新信息复用率 ≥30%"的口径？** 以 item_entities 关联到已有 concept 为准，还是以 knowledge_links 建立为准？两者定义不同、目标值需对齐 | B.0.6 北极星指标、B.0.7 P0-6 | **统一以 knowledge_links 建立为准**（更严格、与 T2 触发器绑定） | M1 末指标定义 |
| 9 | **双子系统联动（Codegarden / Security Graph）是否纳入 v1.7 付费验证场景？** 还是先作为免费纵深能力提供、付费验证聚焦知识复利本身？ | B.0.2 目标③、B.0.7 P1-9 | **v1.7 保持免费纵深能力**；付费验证仅聚焦复利本身 | v1.7 之后 |
| 10 | **资讯收藏聚合视图的 5 类数据源是否覆盖全部高频场景？** 是否需要补充 Newsletter / YouTube 等，还是严格限制在现有 46 源内的聚合 | B.0.7 P1-3、B.6.7 | **v1.7 严格限制 5 类（favorites / cubox / bookmark / secnews_archive / secnews）**；Newsletter/YouTube 推迟 v2.1 | M1 末 |

> **处置原则**: M1 末（首轮可发布）前需对 #1 / #2 / #7 / #8 给出明确答案；#3 / #4 / #6 在 M3-M4 切档前定调；#5 / #9 / #10 推迟到 v1.7 之后。每次评审会议同步更新本附录（标记已确认 / 已推迟 / 仍待确认）。

---

## 附录 D · 行动清单（M1-M4 / D1-D46）

> **来源**: B.0 战略审计 §11 + §9.2 路线图表合并。
> **性质**: 战略层执行节奏；技术细节落在 B.10 Phase 8-16。

| # | 行动 | 负责方 | 时间窗 | 关联需求 |
|---|------|--------|-------|---------|
| 1 | **落地 P0-2 四张新表 + P0-1 simhash 去重 + P0-5 评分 MCP（M1 地基）** | 主理人（全栈） | D1–10 | P0-1, P0-2, P0-5 |
| 2 | **落地 T1/T2 触发器，知识库日增量开始 >0（M1 闭环打通）** | 主理人（后端） | D11–18 | P0-3, P0-4, P0-6(起始) |
| 3 | **完成 P0-8 遗留清理 + 迁移指南（发布门禁）** | 主理人（全栈） | M1 末（灰度） | P0-8 |
| 4 | **推进 T3/T4/T5 + 三类告警，交付复利仪表盘与 KnowledgePlanningPanel（M2 可视化）** | 主理人（前端/全栈） | D19–28 | P1-1, P1-2, P0-6(收尾), P1-4, P1-5, P1-6 |
| 5 | **接入 6 新 collector + 双子系统联动（M3 现代化）** | 主理人（抓取层） | D29–34 | P1-8, P1-9 |
| 6 | **Hybrid AI 可选启用 + P2 体验项收口（M4）** | 主理人（全栈） | D35–46 | P1-7, P2-1, P2-2, P2-3 |
| 7 | **评审前确认附录 C 的 10 个待确认问题（尤其评分自动应用/本地 LLM 默认）** | 产品负责人 + 主理人 | 评审会前 | 附录 C 全部 |

> **与 B.10 的关系**: 本附录是战略层"做什么 + 何时做"，B.10 是技术层"怎么拆 Phase + 怎么验收"。两端必须保持一致：Phase 8 包含 P0-1/P0-2/P0-5/P1-3 = 行动 #1 + 部分 #4 子集；Phase 10 包含 P0-3/P0-4 = 行动 #2 主干；Phase 14 包含 P0-8 = 行动 #3；Phase 11/12 包含 P1-1/P1-2/P1-4/P1-5/P1-6 = 行动 #4；Phase 10/13 包含 P1-8/P1-9 = 行动 #5；Phase 15/16 包含 P1-7/P2-1/P2-2/P2-3 = 行动 #6。

---

## 附录 E · v1.7 PRD 实测对账与修复记录（2026-07-27 leader skill 产出）

> **来源**: [`docs/v2_prd_review.md`](v2_prd_review.md)（leader skill 2026-07-27 产出，292 行 / 14KB）
> **方法**: 实测代码库 + 全文对账 + 给出可粘贴 patch
> **性质**: PRD 数字与代码库实测的对账报告 + 6 patch 修复落地记录；本附录是诊断层归档。
> **状态**: 6 patch 中 5 个已应用、1 个（Patch 6）因现状 B.7.1 已有更详细版本而跳过格式重写。

### E.1 PRD vs 实测 偏差表（实测命令验证 2026-07-27）

| 项 | PRD 写 | 实测 | 偏差 | 严重度 | 状态 |
|---|---|---|---|---|---|
| `knowledge/items/*.md` 总数 | 4,127 | **4,147** | +20（轻微过时）| 🟡 P2 | 未修（轻过时）|
| **应用 lifecycle 字段的 items 比例** | 25/4127 = 0.6% | **4,147 / 4,147 = 100%** | PRD 严重失实 | 🔴 P0 | ✅ Patch 1 已修 |
| **实际 lifecycle 取值** | "5 阶段未落地" | 3 阶段（`generate`/`signal`/`amplify:tagged`）| 0% 用 5 阶段 | 🔴 P0 | ✅ Patch 1+3 已修（标注+迁移 SQL）|
| `mcp_tool_registry` 工具数 | 13 | 13 | ✅ | 🟢 | — |
| `services/*.py` 数量 | 41 | **58** | -17 | 🟡 P2 | ✅ Patch 2 已修 |
| `api/*.py` routers 数量 | 23 | **41** | -18 | 🟡 P2 | ✅ Patch 2 已修 |
| `quality/*.py` gates 数量 | 13 | **22** | -9 | 🟡 P2 | ✅ Patch 2 已修 |
| **实际调度器 jobs 数** | 24 | **30** | -6 | 🟡 P1 | ✅ Patch 2 已修（24→30）|
| `migrations/*.sql` 文件数 | 24 | 24 | ✅ | 🟢 | — |
| **SQLite 实际表数** | "37+ 表" | **71** | -34 | 🟡 P1 | ✅ Patch 2 已修（37+→71+）|
| backend test 文件数 | 67 | **117** | -50 | 🟡 P2 | 未修（轻过时）|
| frontend test 文件数 | 未提 | 30 | PRD 缺失 | 🟡 P2 | 未修（轻过时）|

**关键洞察**:

- PRD A.1.1 表第 3 行"应用了 lifecycle 字段的 items 25/4127 = 0.6%"是错的。实际情况是 100% 应用了 lifecycle 字段，但 0% 用过 5 阶段（`kl:raw` 等）。这不是"99.4% 无 lifecycle"问题，是"100% 用错的 3 阶段"问题。
- v1.7 设计了 5 阶段，**生产数据反而用的 3 阶段**——这才是 PRD 反复强调"5 阶段是基础设施"的真实背景。但 PRD 把 0.6% 写成了 99.4% 未达标的论据，**逻辑方向反了**。
- B.3 架构图里 41 services / 23 routers / 13 gates / 23 schedulers 全部是 v1.4 时代的数字。当前代码库膨胀了 ~40%。

### E.2 关键决策点检查（5 阶段/触发器/MCP/Phase/收藏视图/6 模式/数据模型）

#### E.2.1 KL 5 阶段 + 5 触发器

| 检查项 | 状态 | 备注 |
|---|---|---|
| 5 阶段定义 | ✅ 清晰 | B.6.1 状态机、副作用、不变量 |
| 5 触发器职责分工 | ✅ 清晰 | B.6.2 触发时机、执行主体、副作用 |
| T3 副作用含 chunks_meta | ✅ | B.6.2 T3 已合并 |
| **生产数据生命周期命名迁移** | 🔴 缺失 | Patch 3 已补：migration 046_lifecycle_v2.sql |
| 5 触发器间的死锁 | ✅ 无环 | T1→T2→T3→T4→T5 线性；T5 回 T1 形成环但有用户触发 |
| 5 触发器调度频率 | ✅ 合理 | 30s/10min/30min（与各阶段人工响应时长匹配）|

#### E.2.2 MCP 13 tool（读独立 + 写副作用）

| 检查项 | 状态 | 备注 |
|---|---|---|
| 13 tool 数量 | ✅ 已 seed，未变 | — |
| 6 独立 + 7 副作用分类 | ✅ 有判定原则 | B.7.2 |
| 7 个写 tool 失败恢复动作 | ✅ 7/7 都有后手 | B.7.3 |
| **B.7.1 工具列表 [A]/[B] 模式标记** | ✅ **实质完成**（17 行，含关联服务/状态列）| Patch 6 提议的 13 行精简版会丢信息，**跳过格式重写**；详见 E.4 |
| `trigger_codegarden_drift` 与 Phase 13 任务重复 | 🟡 引用而非重述 | B.7.1 已统一 |

#### E.2.3 Phase 依赖图

| Phase | 依赖 | 状态 |
|---|---|---|
| 8 (复利 + 资讯收藏聚合) | 无 | ✅ 可起 |
| 9 (T1/T2 触发器) | 8 | ✅ |
| 10 (抓取层) | 8 | ✅ |
| 11 (T3/T4/T5 + 告警) | 9 | ✅ |
| 12 (复利可视化 + 4 模式) | 8, 11 | ✅ |
| 13 (子系统联动) | 11, 12 | ✅ |
| 14 (清理 + 文档 + 迁移) | 8-13 全部 | ✅ |
| 15 (Hybrid AI) | 8 | ✅ |
| 16 (Chunks + Attention + 6 模式完整) | 15 + 11 | ✅ |

无环 ✅。8→9→11→12 强依赖串行，**总预估 46 天已是关键路径**。

#### E.2.4 6 种认知模式

| 模式 | 实施阶段 | 依赖 | 状态 |
|---|---|---|---|
| 简报 (Brief) | 12 | 已有 dashboard | ✅ |
| 扫描 (Scan) | 12 | 已有 trending | ✅ |
| 深度 (Deep) | 12 | `knowledge_chunks` 表 | ⚠️ chunks 表 16 才能跑 |
| 整理 (Outbox) | 16 | reading_states + LLM 摘要 | ⚠️ 16 才有 |
| 复习 (SM-2) | 16 | `sm2_reviews`（已建表）+ LLM | ⚠️ 16 才有 |
| 告警 | 12 | 3 类基础告警规则 | ✅ 11 已铺 |

**结论**: 6 模式"全部实施"成立，但 4 模式 vs 6 模式的实际可用时间差 ~13 天（12 → 16）。

#### E.2.5 验收标准与反向测试

| 检查项 | 状态 | 备注 |
|---|---|---|
| 北极星指标 3 个 | ✅ | B.11.1 量化 |
| Phase 门禁 | ✅ | B.11.2 |
| 5 触发器专项测试 | ✅ | B.11.5（T1-1 ~ T5-3 共 15 用例）|
| 资讯收藏聚合专项 | ✅ | B.11.5 8+7 用例 |
| **反向验证（破坏测试）** | ✅ | Patch 5 已加 `test_t1_klraw_alert_red_to_green` |
| 风险与对策 | ✅ | B.12 14 条 |

### E.3 报告结论（领导 3 行版）

1. **PRD 大方向正确**（5 阶段 + 5 触发器 + 13 tool + 6 模式 + 资讯收藏聚合视图 全部设计自洽），但 **A.1.1 第 3 行 "25/4127 = 0.6%" 数据严重失实**——真实情况是 100% 有 lifecycle 但 0% 用 5 阶段。**P0 必修复**。
2. **B.11.6 迁移策略完全缺 lifecycle 5 阶段数据迁移方案**——4,147 items 等着 v1.7 上线后跑迁移 SQL。Patch 3 已给出可直接用的 SQL。
3. **B.3 架构图 4 个数字（41/23/13/23）全部过时**（实际 58/41/22/30），B.7.1 13 tool 列表缺 `[A]/[B]` 模式标记——Patch 2 + Patch 6 一并修。

### E.4 6 patch 落地情况

| Patch | 目标位置 | 状态 | 落地形式 | 备注 |
|---|---|---|---|---|
| **Patch 1** | A.1.1 第 3 行 | ✅ 已应用 | 1 行替换为 3 行 | 4,147/4,147=100% + 5 阶段 0% + 实际取值分布 |
| **Patch 2** | B.3 架构图 4 数字 | ✅ 已应用 | 整段替换 6 行 | 41→58 / 23→41 / 23→30 / 13→22 / 37+→71+ |
| **Patch 3** | B.11.6 迁移小节 + 2 SQL 文件 | ✅ 已应用 | 新增 ~30 行 + 2 文件 | `046_lifecycle_v2.sql` + `_down.sql` |
| **Patch 4** | B.9.6 端点分工 | ✅ 已应用 | 新增 4 行 | `/api/knowledge/imported` vs `/api/favorites` |
| **Patch 5** | B.11.5 反向测试 | ✅ 已应用 | 新增 1 行 | `test_t1_klraw_alert_red_to_green` |
| **Patch 6** | B.7.1 模式标记 | ⚠️ **跳过格式重写** | 现状已有 17 行 [A]/[B] 表 | Patch 6 提议的 13 行精简版会丢关联服务/状态列信息，保留现状更详细设计；功能实质完成 |

### E.4a Round 2 patch 落地情况（2026-07-27，body 数据基线修正）

> **触发**: Round 1 patch 后，[v2_prd_review.md](../v2_prd_review.md) 偏差表只覆盖了 A.1.1 第 3 行，但**同一错误数据 "25/4127=0.6%" / "99.4% 卡在 kl:raw" 在 PRD 主体中重复 15+ 次**（L90/L147/L166/L281/L367/L376/L385/L407/L411/L475/L476/L483/L498/L499/L1171/L1187/L1967/L2026/L3755）。Round 2 把这 15+ 处全部统一为"4,147 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段（实际 100% 用 v1.7 旧 3 阶段值）"的新叙事，**同步调整 5 触发器论证逻辑**（从"99.4% 卡 raw"改为"100% 用错阶段 + 命名未统一 + 无触发器"）。

| Patch | 目标位置 | 状态 | 落地形式 |
|---|---|---|---|
| **7.1** | A.1.2 关键洞察（L90）| ✅ | 1 行替换 |
| **7.2** | A.3.1 表格行 KL 五阶段（L147）| ✅ | 1 行替换 |
| **7.3** | A.3.2 表格行 复利机制无落地（L166）| ✅ | 1 行替换 |
| **7.4** | A.6.1 复利的关键（L281）| ✅ | 1 行替换 |
| **7.5** | B.0.1 TL;DR 依据（L367）| ✅ | 1 行替换 |
| **7.6** | B.0.1 核心结论卡片 预期影响（L376）| ✅ | 1 行替换 |
| **7.7** | B.0.2 目标①（L385）| ✅ | 1 行替换 |
| **7.8** | B.0.4 核心痛点（L407）| ✅ | 1 行替换 |
| **7.9** | B.0.4 对 v1.7 关键设计（L411）| ✅ | 1 行替换 + 论证逻辑加 migration 046 |
| **7.10** | 5.1 当前指标基线 表（L473-476 → L473-477）| ✅ | 2 行替换为 3 行 |
| **7.11** | 5.1 关键缺口分析（L483）| ✅ | 1 行替换 |
| **7.12** | 5.4 关键决策点 2 行（L498-499）| ✅ | 2 行替换（"5 触发器" → "5 触发器 + migration 046"）|
| **7.13** | B.6 章节引言（L1171）| ✅ | 1 行替换 |
| **7.14** | B.6.1 为什么 5 阶段（L1187）| ✅ | 1 行替换 |
| **7.15** | B.8.1 复利公式（L2146）| ✅ | 4127 → 4,147 |
| **7.16** | B.11.6 migration 046 表 L2940 | ✅ | 1 行替换（"v1.7 99.4% items" → "v1.7 老 items 已通过 migration 046 迁移"）|
| **7.17** | L1967 Python f-string + L2026 UI mockup | ✅ | 2 处代码/UI 文本去错误数据 |
| **7.18** | L3755 5 触发器 行 | ✅ | 1 行替换（v1.7 状态说明 + 加 migration 046）|

**说明**:
- 16 个核心文本位（7.1-7.16）+ 2 个代码/UI 文本位（7.17）+ 1 个表格行（7.18）= 19 处替换
- L325 "✅ 4127+ items 持续增长" 保留（"+" 号是 inclusive 表述，仍准确）
- L3070 "4127+ items" 风险表 同上保留
- L3073 "v1.7 99.4% items 无 reading_states" 不在 audit 范围（reading_states 是不同指标，未实测），保留待后续 patch
- 附录 E/F 中所有 "25/4127" / "99.4%" 引用**故意保留**（作为审计历史归档）

### E.5 实测命令（领导可复跑）

```bash
# 1. lifecycle 实际分布
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('backend/hotspot.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM knowledge_items')
print('total:', cur.fetchone()[0])
cur.execute('SELECT lifecycle, COUNT(*) FROM knowledge_items GROUP BY lifecycle')
for r in cur.fetchall(): print(' ', r)
"

# 2. services / routers / migrations / tests / quality gates
ls backend/services/*.py | wc -l       # 58
ls backend/api/*.py | wc -l            # 41
ls backend/repository/migrations/*.sql | wc -l   # 24
ls backend/quality/*.py | wc -l        # 22
ls backend/tests/test_*.py | wc -l     # 117
find frontend/src -name "*.test.ts" -o -name "*.test.tsx" | wc -l   # 30

# 3. 实际调度器 jobs
.venv/bin/python3 -c "
import re
with open('backend/scheduler/scheduler.py') as f:
    ids = re.findall(r'id=\"([^\"]+)\"', f.read())
print(f'jobs: {len(ids)}')
for i in ids: print('  -', i)
"

# 4. SQLite 实际表数
.venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect('backend/hotspot.db').cursor()
c.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table'\")
print('tables:', c.fetchone()[0])
"
```

---

## 附录 F · v1.7 PRD 修复任务书归档（2026-07-27，已完成）

> **来源**: [`/Users/duke/.trae/documents/review_goal.md`](../../Users/duke/.trae/documents/review_goal.md)（leader skill 任务书，160 行 / 8KB）
> **方法**: 把 v1.7 PRD 复盘发现的 6 个 P0/P1 偏差一次性修掉，让 PRD 从"草案"升到"可贴墙拍板"
> **性质**: 执行型任务书归档；本附录是执行层归档，与 E.4 patch 落地表一一对应。

### F.1 任务目标

**目标**: 把 v1.7 PRD 复盘发现的 **6 个 P0/P1 偏差**（A.1.1 第 3 行失实 + B.3 架构图 4 数字过时 + 5 阶段 lifecycle 数据迁移方案缺失 + 端点分工不明确 + 反向验证测试缺失 + 13 tool 模式标记缺失）一次性修掉。

**让步顺序**: 数据准确 > 数字齐全 > 不破坏现有内容。

### F.2 任务界限

- **只允许改**: `docs/hotspot_v1.7_PRD.md`（6 patch 全部落到这 1 个文件）
- **可新建**: `backend/repository/migrations/046_lifecycle_v2.sql`（Patch 3）+ `046_lifecycle_v2_down.sql`（回滚）
- **不许碰**: 任何 `backend/services/` / `backend/api/` 代码、任何测试文件、`.git` 任何分支操作
- **白名单点名**: PRD 文件 + 2 个 SQL 文件，其他全部只读

### F.3 6 patch 状态一览（与 E.4 对应）

| # | Patch | 目标 | 状态 | 实际改动 |
|---|---|---|---|---|
| 1 | A.1.1 第 3 行 | 25/4127=0.6% → 4147/4147=100% + 5 阶段 0% + 实际取值分布 | ✅ | 1 行→3 行 |
| 2 | B.3 架构图 4 数字 | 41/23/13/23 → 58/41/22/30，表数 37+→71+ | ✅ | 整段替换 6 行 |
| 3 | B.11.6 迁移小节 | 5 阶段 lifecycle 映射 + SQL 草案 + 验收 | ✅ | 新增 ~30 行 + 2 SQL 文件 |
| 4 | B.9.6 端点分工 | `/api/knowledge/imported` vs `/api/favorites` | ✅ | 新增 4 行 |
| 5 | B.11.5 反向测试 | `test_t1_klraw_alert_red_to_green` | ✅ | 新增 1 行 |
| 6 | B.7.1 模式标记 | [A]/[B] 标记 + 失败后手 | ⚠️ 跳过 | 现状 B.7.1 已有 17 行更详细版本（功能实质完成）|

### F.3a Round 2 状态一览（body 数据基线修正）

**触发**: Round 1 patch 后，body 仍有 15+ 处 "25/4127=0.6%" / "99.4% 卡在 kl:raw" 错误数据 + 5 触发器论证逻辑与新现实不符。

| 阶段 | 内容 | 状态 | 实际改动 |
|---|---|---|---|
| Round 1 | 6 patch（A.1.1 + B.3 + B.11.6 迁移 + B.9.6 + B.11.5 + B.7.1 模式）| ✅ | 5 应用 + 1 跳过格式重写 |
| Round 2 | 19 处 body 错误数据修正（含 5 触发器论证逻辑调整）| ✅ | 全部应用；附录 E 新增 E.4a、附录 F 新增 F.3a 归档 |

**Round 2 关键设计变更**:
- 叙事基线: "25/4127=0.6% 没 lifecycle" → "4,147 items 100% 有 lifecycle 但 0% 用 v1.7 5 阶段（100% 用 v1.7 旧 3 阶段值）"
- 5 触发器论证: "99.4% 卡 raw → 强制推进" → "100% 用错阶段值 + 命名未统一 → 触发器 + migration 046 一并修复"
- migration 046 角色: 从 B.11.6 "数据迁移方案" 升级为 "5 触发器立论的关键拼图"（Round 1 没充分体现此点）

**Round 2 验收 grep**:
```bash
# 应输出 0（body 已清，附录 E/F 中保留为历史归档）
grep -nE "25/4127|25/4,127|4127 条仅 25|99\.4% items 卡|99\.4% 卡在 \`kl:raw\`|卡在 kl:raw" docs/hotspot_v1.7_PRD.md
# 实际: 4 行匹配，全部在 L3845/L3859/L3928/L4008 附录 E/F 内
```

### F.4 完成情况

- **硬指标 1**: `docs/hotspot_v1.7_PRD.md` 总行数变化（应用 5 patch 后 +50 行、新增附录 E/F +160 行）→ 已记录在验收报告
- **硬指标 2**: 5 patch 的 8 条 `grep` 验收 + 1 patch（Patch 6）"功能完成 / 格式跳过"说明 → 已通过
- **副作用**: 无新增依赖、流程、权限
- **未做**: 实际执行 `046_lifecycle_v2.sql` 迁移（按 leader 任务的"不执行，只写文件"原则，留待 Phase 10 T1 触发器上线后跑）

### F.5 归档说明

- 本任务书已完成使命，6 patch 中 5 个应用、1 个跳过格式重写，PRD 数字与代码库实测对齐
- 后续如需重做 patch（特别是 Patch 1 的数据快照可能因 items 增长再次过时），可重跑 E.5 实测命令确认偏差
- 任务书原文保存在 `/Users/duke/.trae/documents/review_goal.md`，便于回溯决策过程
- 相关 SQL 文件保留在 `backend/repository/migrations/046_lifecycle_v2*.sql`，等待 Phase 10 执行

---


> **最后**: hotspot v1.7 的核心是**让知识库每天自动增长**（复利），通过 **5 阶段 + 5 触发器** 强制推进 lifecycle，配合 24 个 APScheduler job + 13 个 MCP tool + 6 种认知模式 + Hybrid AI（Crawl4ai + 可选本地 LLM + 外部 Agent）+ chunks 段落级引用 + attention_score 注意力热图，实现从「信息→知识→复利」的完整闭环。
>
> 一切设计都应回答："**今天新增的 items 是 0 还是 10+？今天的 T1→T5 触发器全部跑通了吗？关联率 ≥ 30% 吗？Hybrid AI 启用了吗？6 模式 UI 都好用吗？**"
