# 热点地图 · v1.7 产品需求文档（完整版）

> **版本**: v1.7.7 (SAG 设计吸收版)
> **日期**: 2026-07-26
> **定位**: hotspot v1.7 — 从"信息平台"升级为"互联网资讯知识化平台 + IT 从业者智能工作看板"
> **基线**: v1.6 (CodeGarden Phase2b 完成) + v1.7.6 (Option A MCP 完成)
> **关联文档**: [ARCHITECTURE.md](../ARCHITECTURE.md) · [SPEC.md](./SPEC.md) · [CodeGarden_PRD_v2.0.md](./CodeGarden_PRD_v2.0.md) · [AGENTS.md](../AGENTS.md) · [SAG Paper](https://arxiv.org/abs/2606.15971)
> **本版核心**: 吸收 Zleap-AI/SAG 的 event-entity 检索架构核心思想，强化 LLM-Wiki 2.0 + OKF 存储范式；统一知识存储；建立 Hotspot ↔ AI Agent 双向生产环；升级采集层支持 crawl4ai 高阶抓取；生命周期命名从 SAG 迁移至 KL (Knowledge Lifecycle) 以避 Zleap 命名冲突
> **v1.7.7 关键变化**: 
> - 吸收 SAG 事件-实体模型: OKF item = event, concepts/ = entities, 新增 `item_entities` SQLite 表用于查询时动态超边 JOIN
> - 生命周期重新命名: SAG → KL (Knowledge Lifecycle) 避名冲突
> - 采集层升级: 传统爬虫 + crawl4ai (高阶 LLM 配置) + 标讯内容
> - Hotspot ↔ AI Agent 双向生产环: hotspot 通过 CLI 调用 Agent Skill → Agent 通过 MCP 读写 hotspot
> - 定时轮询: Agent 和 hotspot 互调，轮询时间遵循 KL 刷新周期，可自定义
> - `knowledge/items/` 统一存储类型：OKF + event-entity + chunk 元数据
> - kv_cache 调整为可选 KV 加速层

---

## 目录

0. [版本概述](#0-版本概述)
1. [用户旅程分析](#1-用户旅程分析)
2. [架构总览](#2-架构总览)
3. [数据模型变更](#3-数据模型变更)
4. [API 设计](#4-api-设计)
5. [MCP 协议与外部 AI Agent 集成](#5-mcp-协议与外部-ai-agent-集成)  ← v1.7.6 Option A 重写
6. [功能规格（按用户旅程）](#6-功能规格按用户旅程)
7. [调度器变更](#7-调度器变更)
8. [前端组件与路由](#8-前端组件与路由)
9. [跨端同步变更](#9-跨端同步变更)
10. [迁移策略](#10-迁移策略)
11. [测试策略](#11-测试策略)
12. [Phase 规划](#12-phase-规划)
13. [验收标准](#13-验收标准)
14. [风险与对策](#14-风险与对策)
15. [术语表](#15-术语表)
16. **[Phase 7: MCP Server（让 hotspot ↔ 外部 AI Agent 通过 MCP 通信）](#16-phase-7-mcp-server让-hotspot--外部-ai-agent-通过-mcp-通信)**  ← v1.7.6 增补

---

## 0. 版本概述

### 0.1 解决的问题

v1.6 完成了从"热点聚合"到"工作站"的跨越（项目、服务、资源、编排），但在**信息→知识→行动**的核心工作流上仍存在断裂。用户每天面对 50-200 篇文章，却缺少筛选决策支持、知识自动提取、内化复习机制和行动触发。v1.7 的目标是补齐这些断裂点，并通过**标准 MCP 协议**与外部 AI Agent 协作，让任意外部 AI Agent (Cursor/Claude Desktop/Trae/Workbuddy/Claude Code) 都能读写本地知识库。

> **一句话定位**: 让系统从"被动信息仓库"变成"主动认知协作者"，并通过 MCP 协议开放给所有外部 AI Agent

### 0.2 核心原则

1. **减少认知摩擦**：每新增一个功能都自问"这能减少用户一次决策吗？"
2. **自动化优先**：能自动做的不让用户手动做（提取、推理、推送）
3. **在场不在野**：知识应该在用户需要的位置出现，而不是在知识库页面里等着
4. **渐进式个性化**：系统通过隐式信号学习用户偏好，不需要用户填写兴趣表单
5. **本地优先，零外部依赖**：所有功能在本地可运行，不依赖外部服务
6. **协议优先而非运行时 (v1.7.6 Option A)**：通过标准 MCP 协议开放数据读写，AI 推理交给外部 agent，本地不维护 agent runtime
7. **外部 AI Agent 即协作者**：hotspot 暴露数据 + 工具，AI Agent 在用户已配好的环境中承担智能；hotspot 不替代用户的判断

### 0.3 v1.6 -> v1.7 变化矩阵（v1.7.7 补充）

| 维度 | v1.6 (当前) | v1.7 (目标) | v1.7.6 Option A 简化 |
|------|------------|------------|-------------------|
| 信息筛选 | 5-8 个互斥分类 | 多维标签体系 + AND/OR 查询 | 保持 |
| 知识摄入 | 手动收藏 + 手动提取 | 自动提取关键词/概念/实体 | 保持 |
| 知识内化 | 无复习机制 | SM-2 间隔重复 + 自动衰减 | 保持 |
| 知识->行动 | 无主动桥接 | 技术栈匹配 -> 项目影响评估 | 保持 |
| 信息触达 | 仅 PULL (用户主动打开) | PULL + PUSH (规则引擎告警) | 保持 |
| 搜索 | 各层独立搜索 | 一次查询穿透所有 5 层 | 保持 |
| 交互模式 | 单一主页视图 | 简报/扫描/深度/整理/复习/告警 六种模式 | 保持 |
| 个性化 | 无 | 隐式行为学习 + 阅读状态追踪 | 保持 |
| 失效反馈 | 无 | 数据源完整性仪表盘 | 保持 |
| 知识在场 | 在知识库页面 | 上下文感知推荐 | 保持 |
| **Agent 架构** | **无 Agent** | **Hotspot ↔ Agent 双向环 (Phase 5: 内部 hotspot-agent)** | **标准 MCP 协议 + 外部 AI Agent (Phase 7)** |
| **知识存储** | SQLite 双存储 (favorites + knowledge) | **OKF + LLM-Wiki 2.0 统一 + event-entity 模型** | v1.7.7 强化 |
| **生命周期** | compiled: bool | **KL 五阶段状态机 (原名 SAG)** | v1.7.7 重命名 |
| **缓存层** | 无 | **SQLite KV 缓存层 (可选)** | **评估后保留为可选加速层 (不主动维护, AI Agent 调 MCP 直读)** |
| **任务队列** | 无 | **tasks/pending/ 异步协议** | **移除 (Phase 7 删 knowledge_tasks)** |
| **CLI 工具层** | 独立脚本 | **与 Agent 整合** | **保留 cubox-cli / bookmark 等本地脚本** |

### 0.4 第一性原理：认知链路完整性分析

v1.6 完成了从"热点聚合"到"工作站"的跨越，但在**信息->知识->行动**的核心链路上存在 4 个断裂点。

```
  世界信号 -> 我注意到 -> 我理解 -> 我关联 -> 我决策 -> 我行动
      |          |          |         |         |         |
   采集        筛选       提取      连接      评估      执行
   (v1.0)    (v1.6)     (缺失)    (缺失)    (缺失)   (v1.6)

   OK 已有    WARN 基础  MISS 缺失  MISS 缺失  MISS 缺失  WARN 基础
```

| 环节 | v1.6 状态 | v1.7 目标 | 优先级 |
|------|-----------|-----------|--------|
| 筛选(Signal Filtering) | 仅互斥分类+搜索 | 多维标签+个性化排序 | P0 |
| 提取(Understanding) | 完全手动阅读 | 自动实体/概念/标签提取 (本地规则) + LLM 提取 (外部 Agent 调 MCP) | P0 |
| 关联(Contextualization) | 绝对孤岛 | 跨层搜索+上下文推荐+项目桥接 | P1 |
| 评估(Decision) | 无主动告警 | 规则引擎+PUSH+影响分析 | P1 |
| 行动(Action) | 仅有 Todo | 信息->任务自动桥接 | P1 |
| 内化(Internalization) | 读完就忘 | SM-2 间隔复习+笔记 | P2 |

**v1.7 的核心目标**: 补齐这 6 个环节，使认知链路完整可运行。其中「理解」环节（提取/分析/推理）由外部 AI Agent 通过 MCP 协议完成，hotspot 只做数据存储 + 本地规则提取。

### 0.5 架构升级总览

**v1.6 架构**（线性管道）:
```
Source → Collector → Hotspot DB → User → (手动操作) → Knowledge(.md)
```

**v1.7 架构（v1.7.5 Phase 5 内部 hotspot-agent，已被 Phase 7 Option A 替代）**:
```
Source → Collector → Hotspot DB → Knowledge(.md) → Obsidian
  ↑                        ↕                        ↕
Agent(CLI) ←──────── Hotspot API ←────────── Agent(Task Queue)
  ↑                        ↕
Skills ──────────────── Task Queue
```

**v1.7.6 架构（Phase 7 Option A 简化版 - 当前目标）**:
```
Source → Collector → Hotspot DB → Knowledge(.md) → Obsidian
                              ↑
                          MCP Server  (stdio / SSE)
                              ↑
              ┌───────────────┴───────────────┐
              │   外部 AI Agent (用户机器)      │
              │   Cursor / Claude Desktop      │
              │   Trae / Workbuddy / Claude Code│
              │   (LLM 推理在 agent 侧执行)      │
              │   Agent Skill (通过 CLI 调用)    │
              │   Agent ↔ Hotspot 双向生产环    │
              └───────────────────────────────┘
                   ↑                      ↓
              (读知识/写新知识)    (通过 CLI 调 Agent)
                   ↕
            hotspot HTTP API + CLI
                          ↑
                  Hotspot UI (React)
```

**关键变化（v1.7.6 Option A）**:
- 移除 Phase 5 引入的内部 hotspot-agent 进程
- 移除 knowledge_tasks 异步队列、heartbeat / watchdog 机制
- 改为通过标准 MCP 协议让任意外部 AI Agent 主动连入
- LLM 推理全部在外部 AI Agent 中执行；hotspot 只做数据存储 + 本地规则提取 + MCP 工具暴露
- Phase 5 的 `/api/agent/*` 端点保留为 deprecated 供内部/调试用，不再是 AI Agent 的主入口

详见 §16 完整 Phase 7 设计。

### 0.6 SAG 检索架构核心思想吸收分析

**背景**: Zleap-AI/SAG 是一个基于 SQL-Retrieval Augmented Generation 的原创检索架构，在 HotpotQA/2WikiMultiHopQA/MuSiQue 上取得 8/9 的 SOTA Recall@1/2/5 指标。经评估，SAG 全平台（Docker + JWT + 前后端）过于庞大，不符合 hotspot 本地优先原则。但 SAG 的**事件-实体模型 (Event-Entity Model)** 和**查询时动态超边 (Query-time Dynamic Hyperedges)** 两个核心设计思想可被吸收到 OKF + LLM-Wiki 2.0 中。

**SAG 核心设计思想拆解**:

| SAG 概念 | 对应 OKF + LLM-Wiki 2.0 | 实现方式 |
|----------|------------------------|----------|
| Chunk | `knowledge/items/{id}.md` 中的 `chunks` 字段 | 新增 `chunks` YAML 字段，记录段落级信息 |
| Event (完整语义) | 整个 `.md` 文件 = 一个事件 | 每个 item 的 YAML frontmatter + body = 完整语义单元 |
| Entity (轻量索引) | `concepts/` 目录 + `tags` + `tech_stack` | 新增 `item_entities` SQLite 表 (item_id, entity_name, entity_type) |
| 查询时动态超边 | SQL JOIN over shared entities | 查询时先从 item_entities 找种子实体 → JOIN 找共享实体的 items |
| 原文证据可追溯 | `source_url` + `chunks` 字段 | 每个 item 保留 source_url 和 chunk 级定位 |
| 增量写入 | 每个 .md 独立，无全局重算 | 天然支持，新增 entity 提取器支持增量断点续传 |

**吸收方案 (OKF 强化版)**:

```
SAG 原始模型:
  Document → Chunks → Events (完整语义) + Entities (索引)
                             ↓
                      查询时动态超边 (SQL JOIN)
                             ↓
                      返回原文证据

OKF 强化版 (hotspot):
  Internet Article → .md Item (Event) + Concepts/Entities (索引)
                             ↓
                      查询时多表 JOIN (entities + tags + concepts)
                             ↓
                      返回 source_url + chunk 引用
```

**关键差异**:
- SAG 使用 vector embedding 做语义检索 → hotspot 用 FTS5 + 实体 JOIN 做语义 + 结构检索（本地优先，无需外部模型）
- SAG 有独立的 chunk → event 管道 → hotspot 的文章本身就是事件（不需要额外抽取）
- SAG 的 entity 由 LLM 提取 → hotspot 的 entity 由本地规则 + AI Agent (通过 MCP) 联合提取
- SAG 的增量写入需要 ProcessCheckpoint → hotspot 的增量写入天然支持（每个 .md 独立）

### 0.7 生命周期命名变更: SAG → KL (Knowledge Lifecycle)

**原因**: 原 hotspot 的 SAG (Signal-Amplify-Generate) 生命周期与 Zleap-AI/SAG (SQL-Retrieval Augmented Generation) 命名冲突。为避免混淆，v1.7.7 起生命周期更名为 **KL (Knowledge Lifecycle)**。

**命名映射**:

| 旧名 (SAG) | 新名 (KL) | 含义 | 触发条件 |
|------------|-----------|------|----------|
| signal | kl:raw | 原始信号：刚采集，未处理 | 采集完成自动设置 |
| amplify:tagged | kl:refine | 已精炼：标签/实体提取完成 | 自动标签提取完成，或 AI Agent 通过 MCP 写入 |
| amplify:linked | kl:link | 已关联：概念图节点已创建 | 概念关联完成 |
| amplify:complete | kl:structure | 已结构化：信息完备，上下文完整 | AI Agent 或用户确认信息完整 |
| generate | kl:publish | 已发布：知识条目已生成到 knowledge/items/ | 知识条目达到可发布质量 |

**迁移策略**: 现有 `knowledge_items.lifecycle` 字段值通过 migration 040 批量替换：
```sql
UPDATE knowledge_items SET lifecycle = REPLACE(lifecycle, 'signal', 'kl:raw');
UPDATE knowledge_items SET lifecycle = REPLACE(lifecycle, 'amplify:tagged', 'kl:refine');
UPDATE knowledge_items SET lifecycle = REPLACE(lifecycle, 'amplify:linked', 'kl:link');
UPDATE knowledge_items SET lifecycle = REPLACE(lifecycle, 'amplify:complete', 'kl:structure');
UPDATE knowledge_items SET lifecycle = REPLACE(lifecycle, 'generate', 'kl:publish');
```

**代码变更**: `kl_service.py` → `kl_service.py`，`backend/services/kl_service.py` 重命名为 `kl_service.py`，内部函数签名不变。

### 0.8 第一性原理: 认知链路完整性 (v1.7.7 补充)

v1.7.6 版本已覆盖"信息→知识→行动"链路 6 个环节。v1.7.7 基于 SAG 事件-实体模型和知识复利要求，补充 **2 个新环节**:

```
  世界信号 → 我注意到 → 我理解 → 我关联 → 我内化 → 我决策 → 我行动 → 复利增长
      |          |         |        |        |        |       |        |
   采集      筛选      提取     连接     复习     评估    执行    知识复利
   (v1.0)   (v1.6)    (v1.7)  (v1.7)   (v1.7)   (v1.7)  (v1.6)  (v1.7.7)
```

| 环节 | v1.7.6 状态 | v1.7.7 补充 | 优先级 |
|------|------------|-------------|--------|
| 提取(Understanding) | 自动实体/概念/标签提取 | 吸收 SAG entity 模型，支持实体级检索 + 动态超边 | P0 |
| 关联(Contextualization) | 跨层搜索+上下文推荐+项目桥接 | 查询时多表 JOIN (entities+tags+concepts) 实现动态超边 | P1 |
| 知识复利(Compounding) | 无 | KL 生命周期驱动：kl:raw → kl:publish 过程自动积累知识资产；AI Agent 通过 MCP 读旧知识 → 写新知识 → 形成复利环 | P1 |

---

## 1. 用户旅程分析

### 1.1 典型一天工作流（IT 安全从业者）

```
08:00 - 开电脑，打开 dashboard
  |  (1) 态势感知
  |  * 数据源完整性指示器（绿/黄/红）          -> M11 数据源健康
  |  * 夜间告警汇总                            -> M6 告警系统
  |  * 每日简报（自动生成）                    -> M1 简报模式
  |  * 离线间隔摘要（若昨日未使用过）          -> M1 离线补丁
  |
08:15 - 紧急响应（若有 CVE / 0-day / 攻击事件）
  |  (2) 快速决策
  |  * PUSH 告警 -> 红色标记                    -> M6 告警引擎
  |  * 技术栈影响分析                           -> M5 技术栈桥接
  |  * 一键创建待办                             -> M5 -> Todo
  |
09:00 - 深度阅读（3-5 篇重点文章）
  |  (3) 知识摄入
  |  * 自动提取标签/概念/技术栈                -> M3 自动提取
  |  * 上下文推荐（相关知识库条目）             -> M8 知识推荐
  |  * 笔记区（Markdown，关联文章）              -> M9 笔记空间
  |  * 阅读状态追踪                            -> M10 隐式学习
  |
12:00 - 碎片浏览（GitHub / Twitter）
  |  (4) 快速捕捉
  |  * 一键保存 URL 到系统                     -> 标签系统
  |  * 自动打标签                              -> M3 自动提取
  |
13:00 - 交叉验证与关联分析
  |  (5) 知识验证
  |  * 统一搜索跨 5 层穿透                      -> M7 统一搜索
  |  * 概念图谱可视化                          -> 已有知识图谱
  |  * 同话题多源聚合                          -> M2 标签 AND 查询
  |
15:00 - 行动落地
  |  (6) 知识->行动
  |  * 项目影响评估 -> Todo 创建                 -> M5 技术栈桥接
  |  * 发布/导出分析报告                       -> 已有导出功能
  |
17:00 - 复盘与学习
  |  (7) 知识内化
  |  * 今日看了 N 篇文章，提取了 M 个概念       -> M10 隐式学习
  |  * 复习队列（最长未复习条目优先）           -> M4 间隔复习
  |  * 今日精选（系统推荐最有价值条目）         -> M8 知识推荐
  |
17:30 - 规划明日
  |  (8) 准备
  |  * 设置告警规则                            -> M6 告警规则
  |  * 优先收件箱                              -> 整理模式
  |  * 明日简报预生成                          -> M1 简报模式
  +------------------------------------------
```

### 1.2 六种认知模式

| 模式 | 触发条件 | 界面 | 核心操作 |
|------|---------|------|---------|
| **简报模式** | 每日首次打开 / 离线归来 | 一句话摘要+3 篇关键文章+数据源状态 | 扫一眼，点开感兴趣的 |
| **快速扫描模式** | 默认首页 | 分类+标签+时间筛选列表 | 快速浏览标题 |
| **深度阅读模式** | 点击一篇文章 | 文章全屏+右侧栏(推荐/笔记/影响) | 阅读、提取、笔记 |
| **整理模式** | 手动切换 / 浏览 1h 后自动建议 | 清单视图(未处理+待复习+待确认) | 批量处理 |
| **复习模式** | 复习队列非空时 | 卡片翻转(概念->自评->答案) | 回顾+评分 |
| **告警模式** | 新告警产生 | 红色横幅+告警中心 Inbox | 查看、标记、行动 |

### 1.3 与现有功能集成

| 现有模块 | v1.7 集成方式 |
|----------|--------------|
| **favorites** | 收藏即自动触发提取 + 加入复习队列 + 写入 knowledge/items/ |
| **todos** | 告警命中时自动创建 Todo，标记 source_article_id |
| **knowledge** | 提取的概念自动关联 knowledge_items，KL 生命周期驱动 |
| **codegarden** | tech_stack 桥接 cg_projects，告警影响分析 |
| **security_graph** | 关联的 CVE 实体注入知识推荐 |
| **sync_bundle** | reading_states + annotations 跨端同步 |
| **weekly_report** | digest 作为周报输入素材 |
| **obsidian** | 直接读取 knowledge/items/ 目录，LLM-Wiki 2.0 格式 |
| **外部 AI Agent (v1.7.6)** | 通过 MCP 协议调 hotspot 13 个 tool (5 读 + 8 写)，LLM 推理在 agent 侧；hotspot 不内置 agent runtime |

---

## 2. 架构总览

### 2.1 v1.7 架构核心：Hotspot ↔ Agent 双向环（MCP 化扩展见 §16）

```
 +----------------------------------------------------------+
 |                     Hotspot 平台                           |
 |  +------------------+  +-------------------------------+  |
 |  |   采集层          |  |   知识引擎层                   |  |
 |  |  RSS / Crawler / crawl4ai / 标讯 |  |  自动提取 / 标签 / 推荐        |  |
 |  |  Cubox / Bookmark |  |  SM-2 复习 / 告警             |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             |                   |
 |  +--------v---------+  +--------------v----------------+  |
 |  |   SQLite 主存储    |  |   LLM-Wiki 2.0 / OKF 目录    |  |
 |  |   (37 表, WAL)    |  |  knowledge/ 为源数据         |  |
 |  |   + KV 缓存层     |  |  可读写，结构兼容           |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             |                   |
 |  +--------v---------+  +--------------v----------------+  |
 |  |  HTTP API 层      |  |   MCP Server 层 (Phase 7)     |  |
 |  |  REST / SSE       |  |   /mcp (stdio + sse)         |  |
 |  |  /api/*  (Phase 1-5) | |  读 5 + 写 8, 全部同步直返 |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             ↑                   |
 +-----------|-----------------------------|-------------------+
             |                             |
             |  HTTP API                  |  MCP (stdio / sse)
             |  (供 hotspot 自身 UI / 调试) |  (供外部 AI Agent)
             |                             |
 +-----------v-----------------------------|-------------------+
 |   Hotspot 前端 (React)        外部 AI Agent 进程 (用户机器)   |
 |   - Dashboard / 简报/扫描     Cursor / Claude Desktop        |
 |   - 深度阅读 / 整理 / 复习    Workbuddy / Trae / Claude Code |
 |   - 知识管理 / 标签 / 搜      (用户在 AI Agent 中配 MCP endpoint)
 +----------------------------------------------------------+
              ↓                                     ↓
         hotspot 自身 UI                       LLM 推理在 agent
                                              (Claude/GPT/Gemini/本地)
```

> **v1.7.7 简化升级 (Option A + SAG 吸收)**: hotspot **不**内置 AI Agent runtime，也**不**维护 hotspot-agent 进程。LLM 推理全部在用户已配置的外部 AI Agent 中执行；hotspot 只提供 MCP 工具（5 读 + 8 写，全部同步直返）和数据存储。Phase 5 的 knowledge_tasks 队列 / heartbeat / watchdog / `/agent` 路由**全部移除**。详见 §16。

### 2.2 数据流（无内部 agent，双向同步直返）

```
外部 AI Agent → Hotspot 方向 (AI Agent 写):
  Cursor/Claude Desktop/Trae 调 add_favorite({hotspot_id: "abc", note: "important"})
    → 通过 MCP (stdio/sse) 把请求发到 hotspot
    → hotspot 直接写 SQLite (favorites 表) + 写 knowledge/items/{id}.md
    → 同步返回 {success, item_id} 给 AI Agent
    ↑ 整链路 < 100ms (P95)

外部 AI Agent ← Hotspot 方向 (AI Agent 读):
  AI Agent 调 search_hotspots({q: "ai security"})
    → hotspot SELECT FROM hotspots WHERE ...
    → 同步返回 {items: [...]} 给 AI Agent
    ↑ 整链路 P50 < 100ms, P95 < 500ms

Hotspot UI → Hotspot 自身 (前端调 HTTP API):
  React 前端 → fetch /api/hotspots, /api/knowledge, /api/favorites
    → 同步直返
```

### 2.3 KL (Knowledge Lifecycle) 生命周期状态机

替换 `compiled: bool`，引入五阶段生命周期：

```
                     ┌────────────┐
                     │  kl:raw    │ (原始信号: 刚采集到)
                     └──────┬─────┘
                            │
                     ┌──────v─────┐
                     │ kl:refine  │ (已精炼: 标签/实体提取完成)
                     └──────┬─────┘
                            │
                     ┌──────v─────┐
                     │  kl:link   │ (已关联: 概念图节点已创建)
                     └──────┬─────┘
                            │
                     ┌──────v─────┐
                     │kl:structure│ (已结构化: 信息完备)
                     └──────┬─────┘
                            │
                     ┌──────v─────┐
                     │kl:publish  │ (已发布: 知识条目已生成)
                     └────────────┘
```

**KL 生命周期转移规则**:
- `kl:raw` → `kl:refine`: 自动标签/实体提取完成，或用户/AI Agent 手动标记
- `kl:refine` → `kl:link`: 概念关联完成，知识图谱节点已创建
- `kl:link` → `kl:structure`: 关联信息已完备，上下文已建立
- `kl:structure` → `kl:publish`: 知识条目已生成到 knowledge/items/，可通过 MCP 对外发布
- 所有阶段均支持手动回退：`kl:publish` → `kl:structure`（如用户修改后重新处理）
- AI Agent 可通过 MCP 的 `update_knowledge_item` 直接推进 KL 阶段，hotspot 校验单调性

### 2.4 OKF + LLM-Wiki 2.0 统一存储 (事件-实体模型强化)

**核心原则**: LLM-Wiki 2.0 的 `.md` 文件是知识资产的源数据（single source of truth），SQLite 是 KV 缓存层 + 查询加速层，用于加速查询。

**目录结构（v1.7.6 Option A 调整）**:
```
knowledge/
├── _MAP.md              ← 知识地图（自动生成索引）
├── _SCHEMA.md           ← 数据模型合约
├── SOUL.md              ← 角色画像（由外部 AI Agent 通过 MCP 生成/更新）
├── items/               ← L1: 知识条目 (*.md with YAML frontmatter)
│                           lifecycle: signal | amplify:tagged | ... | generate
│                           tags, tech_stack, concepts 在 frontmatter
├── concepts/            ← L2: 提取的概念
├── learning/            ← L3: 学习计划 + 进度
│   └── tasks/           ← (Phase 7 后保留为兼容, 但 Option A 不再写入新任务)
│       ├── pending/     ← 已清空 (Option A 无任务队列)
│       ├── processing/  ← 已清空
│       ├── done/        ← 历史保留
│       └── failed/      ← 历史保留
├── content/             ← L4: 内容创作
│   ├── drafts/
│   └── calendar.json
└── summaries/           ← 每周摘要
```

> **v1.7.6 Option A 变化**: `tasks/pending/` 不再是 Agent 任务队列的活跃写入位置。AI Agent 改为通过 MCP 协议直接读写 hotspot 同步直返。历史任务文件保留作为 audit log。

**v1.7 新增字段** (在 YAML frontmatter 中):
```yaml
---
id: "a1b2c3"
title: "Article Title"
source: "hotspot"
source_url: "https://..."
ingested_at: "2026-07-22T10:00:00Z"
lifecycle: "kl:refine"           # kl:raw | kl:refine | kl:link | kl:structure | kl:publish
news_type: "cve"                   # cve | vulnerability | technique | tool | paper | news | opinion
domain: "security"
topic: "ai-security"
difficulty: "intermediate"
tags:
  - ai-security
  - langchain
tech_stack:
  - langchain
  - fastapi
concepts:
  - prompt-injection
related_items:
  - "d4e5f6"
---
```

**LLM-Wiki 2.0 作为源数据**: 这意味着 Obsidian 可以直接读取 `knowledge/items/` 目录，用户可以在 Obsidian 中编辑 `.md` 文件的 frontmatter，Hotspot 通过 FSWatch 感知变化并更新 SQLite 缓存。

### 2.5 SQLite KV 缓存层

> **v1.7.6 Option A 变化**: KV 缓存层**评估后保留**。`kv_cache` 表保留作为可选加速层（不删除），但 `kv_cache_cleanup` job 和主动写路径移除。理由：外部 AI Agent 通过 MCP 调 search_hotspots / search_knowledge 同步直读，LLM 调用延迟（秒级）远大于 SQLite 查询（毫秒级），主动缓存收益不显著；但保留表 schema 供未来按需启用。详见 §16.5.1。

**保留的表结构（Phase 1-6 已建，Phase 7 评估后保留为可选）**:
```sql
CREATE TABLE kv_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,        -- JSON 序列化
    etag       TEXT,                 -- 文件内容的 MD5
    expires_at TEXT,                 -- 过期时间 (ISO-8601)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**缓存策略（可选启用，Phase 7 默认不写）**:
- 缓存键: `item:{id}`, `items:list`, `items:by_tag:{tag}`, `fts:index`
- 过期时间: list 30s, single item 60s, fts 5min
- 缓存缺失时自动回退到 `knowledge_items` 或文件系统

**与现有表的关系**:
- `knowledge_items` 表 → 保留作为 SQLite 层的查询入口
- `kv_cache` → 保留为可选加速层（Phase 7 默认不主动维护）
- 写入路径: 用户/Agent 写入 `.md` → FSWatch 感知 → 更新 `knowledge_items`（kv_cache 按需更新）
- 读取路径: 查询 → 优先读 `knowledge_items` / 文件系统（kv_cache 命中作为 bonus）

### 2.6 外部 AI Agent 集成（v1.7.6 简化：Option A）

**v1.7.5 的设计**: hotspot 自带 hotspot-agent 进程 (`agent/cli.py`)，通过轮询 knowledge_tasks 队列、执行 Skill、写回结果。

**v1.7.6 简化 (Option A)**: hotspot **不**内置 agent runtime。LLM 推理全部由用户已配置的外部 AI Agent 完成（Cursor / Claude Desktop / Workbuddy / Trae / Claude Code 等）。hotspot 只暴露标准 MCP 协议供外部 agent 读写。

**新架构**:
```
外部 AI Agent (用户机器, 已在 AI Agent 中配 hotspot MCP endpoint)
  │
  │  MCP (stdio / sse)
  │
  ▼
hotspot 进程
  │
  ├─→ FastAPI HTTP API (/api/*, 供 hotspot 自身 React UI + 调试)
  │
  └─→ MCP Server (Phase 7)
       ├─ 5 读 tool: search_hotspots / get_hotspot / list_favorites /
       │              search_knowledge / get_personal_profile
       └─ 8 写 tool: add_favorite / remove_favorite / add_annotation /
                    update_knowledge_item / trigger_extract_tags (本地规则) /
                    trigger_cubox_sync (本地 CLI) / create_alert_rule /
                    mark_digest_read
       所有 tool 同步直返, 无队列, 无中间层
```

**核心原则**:
- hotspot 不关心哪个 agent 接入、有几个、什么时候接入（零状态耦合）
- AI Agent 通过 MCP 调一次 tool 的延迟 = 单次 LLM 调用延迟（秒级），额外的「写异步队列再让内部 agent 处理」是累赘
- LLM 提取 / 分析 / 推理 在 AI Agent 侧完成，hotspot 只做数据存储 + 简单本地规则
- Phase 5 引入的 hotspot-agent / knowledge_tasks / heartbeat / `/agent` 路由 全部移除

**为什么不集成 NanoClaw/通用 Agent runtime**:
- 依赖少（1 个 fastapi-mcp 库 vs 1 个 Claude Agent SDK + 消息网关 + 协议转换）
- 生态：Cursor / Claude Desktop / Trae / Workbuddy 即插即用
- 模型选择：用户在 AI Agent 中自选（Claude / GPT / Gemini / 本地）
- 状态复杂度：无进程，hotspot 状态纯净
- 调试：mcp-cli 直接调工具
- 风险面：MCP 协议成熟稳定 vs 协议私有、版本漂移、双语言栈

详见 §16 完整设计。

### 2.7 架构设计决策

| # | 决策 | 替代方案 | 选择理由 |
|---|------|----------|---------|
| 1 | **FTS5 统一视图**而非 ES/Meilisearch | ES, Meilisearch | 100k 级数据 FTS5 足够，零外部依赖 |
| 2 | **进程内 asyncio.Queue**而非消息队列 | RabbitMQ, Redis | 单人场景，无需持久化消息 |
| 3 | **规则引擎(条件匹配)**而非 ML/NLP 告警 | ML 模型 | 用户自定义规则更可解释、可调试 |
| 4 | **标签提取: 正则+关键词+规则**而非 LLM | LLM API 调用 | 本地执行、无外部依赖、毫秒级返回 |
| 5 | **SM-2 间隔重复**而非 Anki 集成 | AnkiConnect | 完全在系统内闭环，无需外部工具 |
| 6 | **tags JSON 冗余字段**而非纯多对多 JOIN | 纯 M:N 表 | 减少渲染时的 JOIN 开销 |
| 7 | **阅读状态不实时同步** (允许 <=5min 延迟) | WAL 实时同步 | 简化 sync_bundle 实现 |
| 8 | **告警仅 SSE 推送**而非多渠道(邮件/企微) | SMTP, Webhook | 第一步只做 SSE，后续可扩展 action |
| 9 | **LLM-Wiki 2.0 为源数据** | 纯 SQLite 存储 | 支持 Obsidian 直接读取，AI Agent 可直接写入 .md |
| 10 | **Phase 5 任务队列 → Phase 7 移除** | 知识任务队列 | Option A 不再需要内部 agent，写操作 MCP 同步直返 |
| 11 | **MCP 协议** (Phase 7) | 内部 hotspot-agent + HTTP 轮询 | MCP 是 Anthropic/OpenAI/MS/Google 共识标准, 外部 AI Agent 即插即用 |
| 12 | **AI Agent 外部化 (Option A)** | hotspot 集成 NanoClaw/通用 agent runtime | 依赖少、生态稳定、模型选择自由、状态纯净、调试简单 |
| 13 | **MCP 读写同步直返** | 读直返 + 写走异步队列 | 写也是单次 LLM 调用延迟 (秒级), 异步队列是累赘 |
| 14 | **KL 生命周期** | compiled: bool | 提供更细粒度的生命周期管理，支持知识复利 |
| 15 | **KV 缓存层** (评估后决定) | 直接读文件系统 | 加速查询，避免频繁 I/O |

### 2.8 显式不引入

| 技术 | 原因 |
|------|------|
| 外部搜索引擎 (ES/Meilisearch) | FTS5 + UNION ALL 跨表视图足够 100k 级检索 |
| 外部消息队列 (RabbitMQ/Redis) | 进程内 asyncio.Queue + 文件系统 Task Queue 足够单人场景 |
| 向量数据库 | 本地优先原则，FTS5 + 标签过滤 + 概念图谱覆盖所有搜索需求 |
| ML 模型服务 | 关键词提取用规则+本地，无需 GPU 或外部 API |
| 用户认证/多租户 | 单人本地使用 |
| WebSocket | SSE 单向推送足够；MCP 通信走 stdio / SSE，不需要双向实时通信 |
| **内部 hotspot-agent 进程** (Phase 7 移除) | LLM 推理在外部 AI Agent 中, hotspot 不维护 agent runtime |
| **knowledge_tasks 异步队列** (Phase 7 移除) | MCP 写同步直返, 不需要内部 agent 拉任务 |
| **NanoClaw / 通用 AI Agent runtime** | 协议私有、版本漂移、双语言栈、状态复杂 |
| **MCP Client SDK for hotspot** (不通过 MCP 反向调 agent) | 保持协议栈单一, AI Agent 主动连入 |
| 外部云服务 | 所有数据本地存储，不依赖任何外部服务 |

---

## 3. 数据模型变更

### 3.1 KL 生命周期迁移 (原名 SAG)

**现有 `knowledge_items` 表** (migration 018_knowledge.sql) 变更:
```sql
-- 替换 compiled: bool 为 lifecycle: text
ALTER TABLE knowledge_items ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'kl:raw';
ALTER TABLE knowledge_items ADD COLUMN news_type TEXT DEFAULT '';
ALTER TABLE knowledge_items ADD COLUMN tech_stack TEXT DEFAULT '[]';
-- 迁移现有数据: compiled=true → kl:publish, compiled=false → kl:structure
UPDATE knowledge_items SET lifecycle = 'kl:publish' WHERE compiled = 1;
UPDATE knowledge_items SET lifecycle = 'kl:structure' WHERE compiled = 0;
```

### 3.2 新增表（共 10 张）

#### 3.2.1 tags - 分层标签体系

```sql
CREATE TABLE tags (
    id        TEXT PRIMARY KEY,       -- "ai-security", "langchain", ...
    label     TEXT NOT NULL,          -- 显示名 "AI 安全"
    type      TEXT NOT NULL,          -- domain/category/framework/technique/source/cve
    parent_id TEXT REFERENCES tags(id), -- 层级关系: ai-security -> security
    weight    REAL DEFAULT 1.0,       -- 权重 0-2
    created_at TEXT NOT NULL
);
CREATE INDEX idx_tags_type ON tags(type);
CREATE INDEX idx_tags_parent ON tags(parent_id);

-- 多对多: hotspot -> tags
CREATE TABLE hotspot_tags (
    hotspot_id TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    tag_id     TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (hotspot_id, tag_id)
);
CREATE INDEX idx_hotspot_tags_tag ON hotspot_tags(tag_id);
```

#### 3.2.2 reading_states - 阅读状态与行为日志

```sql
CREATE TABLE reading_states (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT DEFAULT 'local',
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    state          TEXT NOT NULL DEFAULT 'unread',
    opened_count   INTEGER DEFAULT 0,
    total_dwell_ms INTEGER DEFAULT 0,
    last_opened_at TEXT,
    first_read_at  TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE(entity_type, entity_id)
);
CREATE INDEX idx_reading_state ON reading_states(state, last_opened_at);
```

#### 3.2.3 sm2_reviews - 间隔重复复习

```sql
CREATE TABLE sm2_reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type      TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    easiness       REAL DEFAULT 2.5,
    interval_days  INTEGER DEFAULT 0,
    repetitions    INTEGER DEFAULT 0,
    next_review_at TEXT,
    last_grade     INTEGER,
    last_reviewed_at TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE(item_type, item_id)
);
```

#### 3.2.4 annotations - 笔记空间

```sql
CREATE TABLE annotations (
    id            TEXT PRIMARY KEY,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    content       TEXT NOT NULL,
    visibility    TEXT DEFAULT 'private',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

#### 3.2.5 alert_rules - 告警规则

```sql
CREATE TABLE alert_rules (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    enabled       INTEGER DEFAULT 1,
    condition     TEXT NOT NULL,          -- JSON
    action        TEXT NOT NULL,          -- JSON
    cooldown_min  INTEGER DEFAULT 30,
    last_fired_at TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

#### 3.2.6 tech_stack - 个人技术栈

```sql
CREATE TABLE tech_stack (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT,
    version       TEXT,
    project_ids   TEXT DEFAULT '[]',
    aliases       TEXT DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

#### 3.2.7 personal_profile - 个性化画像

```sql
CREATE TABLE personal_profile (
    key           TEXT PRIMARY KEY,
    weight        REAL DEFAULT 1.0,
    updated_at    TEXT NOT NULL
);
```

#### 3.2.8 digests - 简报/摘要

```sql
CREATE TABLE digests (
    id            TEXT PRIMARY KEY,
    digest_type   TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT NOT NULL,
    start_at      TEXT NOT NULL,
    end_at        TEXT NOT NULL,
    item_ids      TEXT NOT NULL,
    read          INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);
```

#### 3.2.9 kv_cache - KV 缓存层

```sql
CREATE TABLE kv_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,        -- JSON 序列化
    etag       TEXT,                 -- 文件内容的 MD5
    expires_at TEXT,                 -- 过期时间 (ISO-8601)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_kv_cache_expires ON kv_cache(expires_at);
```

#### 3.2.10 unified_fts - FTS5 统一搜索虚拟表

```

#### 3.2.11 item_entities - 实体索引表 (SAG 吸收, v1.7.7)

```sql
CREATE TABLE item_entities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       TEXT NOT NULL,                    -- knowledge_items.id
    entity_name   TEXT NOT NULL,                    -- 实体名 (如 "zero-trust-architecture")
    entity_type   TEXT NOT NULL DEFAULT 'concept',  -- concept | tool | vendor | person | cve | technique
    entity_id     TEXT,                             -- 规范 ID (可选, 如 concepts/ 目录中的 slug)
    frequency     INTEGER DEFAULT 1,               -- 在该 item 中出现的次数
    source        TEXT DEFAULT 'auto',              -- auto | mcp | manual
    confidence    REAL DEFAULT 1.0,                 -- 提取置信度 0-1
    created_at    TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES knowledge_items(id) ON DELETE CASCADE
);
CREATE INDEX idx_item_entities_item ON item_entities(item_id);
CREATE INDEX idx_item_entities_name ON item_entities(entity_name);
CREATE INDEX idx_item_entities_type ON item_entities(entity_type);
```

**用途**: 实现 SAG 式查询时动态超边。查询流程：
```
用户搜索 "langchain vulnerability"
  → 从 item_entities 找 name='langchain' OR name LIKE '%vuln%' 的种子 items
  → JOIN 找共享 `langchain` entity 的其他 items (动态超边)
  → UNION 以上结果 + FTS5 语义匹配 → 排序返回
```

**与现有 tags / concepts 的关系**:
- `tags`: 分类用 (domain/category/framework)，层级结构，用于筛选
- `concepts/`: 知识图谱节点，每个 .md 独立，面向人类 + AI Agent 阅读
- `item_entities`: 查询时索引，扁平化 entity_name 用于动态超边 JOIN；由标签提取器 + AI Agent 联合维护

#### 3.2.12 collector_sources - 采集源配置 (v1.7.7)

```sql
CREATE TABLE collector_sources (
    id            TEXT PRIMARY KEY,                 -- source name
    display_name  TEXT NOT NULL,
    source_type   TEXT NOT NULL DEFAULT 'rss',      -- rss | crawl | crawl4ai | tenders | bookmark | cubox
    url           TEXT,                             -- RSS URL 或入口 URL
    enabled       INTEGER DEFAULT 1,
    interval_min  INTEGER DEFAULT 15,               -- 采集间隔
    priority      INTEGER DEFAULT 0,                -- 高优先源先采集
    llm_config    TEXT,                              -- JSON: crawl4ai 的 LLM 配置 (高阶抓取)
    parser_config TEXT,                              -- JSON: 解析配置
    last_fetched  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

> **collector_sources.llm_config**: 可选 JSON 字段，如 `{"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY", "prompt": "提取文章核心论点和关键词"}`。有此项则采集该源时走 crawl4ai 高阶抓取，否则用传统爬虫。

#### 3.2.13 agent_poll_config - Agent 轮询配置 (v1.7.7)

```sql
CREATE TABLE agent_poll_config (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT NOT NULL,                    -- 外部 AI Agent 标识
    poll_interval TEXT NOT NULL DEFAULT '30m',      -- 轮询间隔 (30m | 1h | 6h | 24h, 可自定义)
    poll_mode     TEXT NOT NULL DEFAULT 'kl:raw',   -- 轮询依据 KL 阶段
    last_poll     TEXT,
    mcp_config    TEXT,                              -- 该 Agent 的 MCP endpoint 描述
    enabled       INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_agent_poll_name ON agent_poll_config(agent_name);
```

> **设计原则**: Agent 和 hotspot 的轮询是**松耦合的**。hotspot 只记录 agent 的轮询配置和上次轮询时间，不强制 agent 按配置执行。真实轮询由 AI Agent 自身 (通过 MCP 的 `search_knowledge({lifecycle: "kl:raw"})`) 或 hotspot scheduler (触发 CLI 调用 agent skill) 驱动。

sql
CREATE VIEW unified_search AS
SELECT 'hotspot' AS source_type, id AS entity_id, title, summary AS body,
       source, category, published_at AS ts, score AS rank
FROM hotspots
UNION ALL
SELECT 'knowledge' AS source_type, id AS entity_id, title, '' AS body,
       'knowledge' AS source, domain AS category, ingested_at AS ts, 0 AS rank
FROM knowledge_items
UNION ALL
SELECT 'todo' AS source_type, CAST(id AS TEXT) AS entity_id, title, '' AS body,
       'todo' AS source, '' AS category, created_at AS ts, priority AS rank
FROM todos
UNION ALL
SELECT 'favorite' AS source_type, CAST(id AS TEXT) AS entity_id, title, '' AS body,
       source, category, favorited_at AS ts, 0 AS rank
FROM favorites
UNION ALL
SELECT 'project' AS source_type, CAST(id AS TEXT) AS entity_id, name AS title, description AS body,
       'codegarden' AS source, '' AS category, updated_at AS ts, 0 AS rank
FROM cg_projects;

CREATE VIRTUAL TABLE unified_fts USING fts5(
    source_type, entity_id, title, body, source, category,
    content='unified_search',
    tokenize='unicode61',
    prefix='2,3'
);
```

### 3.3 现有表修改

```sql
-- hotspots: 新增标签和阅读追踪字段
ALTER TABLE hotspots ADD COLUMN tags TEXT DEFAULT '[]';
ALTER TABLE hotspots ADD COLUMN last_read_at TEXT;

-- knowledge_items: 生命周期和扩展字段
ALTER TABLE knowledge_items ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'kl:raw';
ALTER TABLE knowledge_items ADD COLUMN news_type TEXT DEFAULT '';
ALTER TABLE knowledge_items ADD COLUMN tech_stack TEXT DEFAULT '[]';
-- 迁移现有数据
UPDATE knowledge_items SET lifecycle = 'kl:publish' WHERE compiled = 1;
UPDATE knowledge_items SET lifecycle = 'kl:structure' WHERE compiled = 0;

-- cg_projects: 技术栈关联
ALTER TABLE cg_projects ADD COLUMN tech_stack_ids TEXT DEFAULT '[]';
```

### 3.4 数据关系图

```
hotspots --< hotspot_tags >-- tags
    |                           | parent_id (层级)
    |                           | type: domain/category/framework/technique/source
    |
    +-- reading_states (entity_type='hotspot')
    +-- annotations (entity_type='hotspot')
    +-- sm2_reviews (item_type='hotspot')
    |                               |
    +-- favorites (favorited → knowledge/items/ promotion, created_via 区分 MCP/UI)
    +-- extract (本地规则触发 lifecycle, 无 LLM)

knowledge_items --< tags (via YAML frontmatter)
    |               
    +-- lifecycle: KL 生命周期 (kl:raw → ... → kl:publish)
    +-- concepts (提取)
    +-- tech_stack (关联)
    +-- sm2_reviews (item_type='knowledge')
    +-- annotations (entity_type='knowledge')
    +-- kv_cache (可选 KV 加速层)
    +-- item_entities (实体索引, SAG event-entity 吸收)
    +-- chunks YAML 元数据 (段落级引用)
    |               
    +-- Collector: crawl4ai 高阶抓取 (带 llm_config 的源)
    +-- Collector: 传统爬虫 (无 llm_config)
    +-- Collector: 标讯抓取 (source_type='tenders')

kv_cache -- 可选缓存 (Phase 7 默认不主动写)
    |              
    +-- 键: item:{id}, items:list, items:by_tag:{tag}

alert_rules --> cg_events (已存在)
personal_profile (独立, key-value)
tech_stack --> cg_projects (tech_stack_ids)
digests (独立, 快照)
mcp_tool_registry (Phase 7 新增, 启动 seeding)

[v1.7.6 移除]  tasks/pending/ (文件系统, 已清空)
[v1.7.6 移除]  knowledge_tasks (SQLite 表, migration 038 DROP)
[v1.7.6 移除]  agent_heartbeats / agent_task_skills / skill_config
[v1.7.6 移除]  mcp_tool_invocations (Option A 不维护调用记录表, 走 server log)
```

> **v1.7.6 变化**: 内部 agent 相关表（knowledge_tasks / agent_heartbeats / agent_task_skills / skill_config / mcp_tool_invocations）全部 DROP，共 5 张。kv_cache 评估后保留为可选加速层（不主动维护）。详见 §16.5.1。

---

## 4. API 设计

### 4.1 API 设计原则

1. **一致性**: 所有新增端点遵循已有命名规范 `/api/{resource}`
2. **分页**: 列表端点支持 cursor 分页（与现有 `/api/hotspots` 一致）
3. **错误格式**: 统一 `{ "code": "...", "message": "...", "trace_id": "..." }`
4. **时间格式**: ISO-8601 UTC + Z 后缀
5. **标签查询**: 新增 `tag_mode=and|or` 支持交叉查询

### 4.2 API 端点总览（36 新增）

#### Phase 1: 标签与提取（9 个）

| Method | Path | 请求参数 | 状态码 |
|--------|------|----------|--------|
| GET | /api/tags | ?type=domain&parent_id= | 200 |
| GET | /api/tags/suggest | ?q=keyword&limit=10 | 200 |
| POST | /api/tags | { label, type, parent_id?, weight? } | 201 |
| PUT | /api/hotspots/{id}/tags | { tag_ids: [...], mode } | 200 |
| POST | /api/extract/{entity_type}/{entity_id} | - | 202 |
| GET | /api/extract/pending | ?limit=50&cursor= | 200 |
| PUT | /api/extract/confirm/{extract_id} | { action, tags? } | 200 |
| DELETE | /api/extract/pending/{extract_id} | - | 200 |
| GET | /api/hotspots?tags=ai,security&tag_mode=and | +category/time_range/cursor | 200 |

#### Phase 2: 内化与桥接（8 个）

| Method | Path | 请求参数 | 说明 |
|--------|------|----------|------|
| GET | /api/reviews/due | ?limit=20&cursor= | 待复习队列 |
| POST | /api/reviews/{id}/grade | { grade: 0-5 } | 提交评分 |
| GET | /api/reviews/stats | - | 复习统计 |
| GET | /api/reviews/dashboard | ?days=30 | 复习日历 |
| GET | /api/tech-stack | ?category=framework | 技术栈列表 |
| POST | /api/tech-stack | { name, category, version? } | 新增 |
| GET | /api/tech-stack/impact | ?article_id=xxx | 影响分析 |
| PUT | /api/tech-stack/{id} | { name?, version?, project_ids? } | 更新 |

#### Phase 3: 告警与搜索（9 个）

| Method | Path | 请求参数 | 说明 |
|--------|------|----------|------|
| GET | /api/alerts | ?status=unread&cursor= | 告警列表 |
| POST | /api/alerts/rules | { name, condition, action } | 创建规则 |
| GET | /api/alerts/rules | - | 规则列表 |
| PUT | /api/alerts/rules/{id} | { enabled?, condition? } | 更新规则 |
| DELETE | /api/alerts/rules/{id} | - | 删除规则 |
| PUT | /api/alerts/{id}/read | { read: true } | 标记已读 |
| GET | /api/search | ?q=keyword&sources=...&limit= | 统一搜索 |
| GET | /api/mode/current | - | 当前推荐模式 |
| PUT | /api/mode/switch | ?mode=deep | 切换模式 |

#### Phase 4: 智能与体验（7 个）

| Method | Path | 请求参数 | 说明 |
|--------|------|----------|------|
| GET | /api/recommend | ?entity_type=hotspot&entity_id=xxx | 上下文推荐 |
| GET | /api/annotations | ?entity_type=hotspot&entity_id=xxx | 笔记列表 |
| POST | /api/annotations | { entity_type, entity_id, content } | 创建笔记 |
| PUT | /api/annotations/{id} | { content?, visibility? } | 更新笔记 |
| DELETE | /api/annotations/{id} | - | 删除笔记 |
| GET | /api/sources/health | - | 数据源健康状态 |
| GET | /api/sources/{name}/history | ?days=7 | 单源历史 |

#### Phase 7: MCP 通信（已替代 Phase 5 Agent 通信，详见 §16）

> v1.7.5 的 Phase 5 引入了内部 hotspot-agent 通信端点。v1.7.6 (Option A) 改用标准 MCP 协议, hotspot 不再内置 agent 进程, AI Agent 通过 MCP 直接同步读写。Phase 5 通信端点保留为 deprecated 供内部/调试用, 不再是 AI Agent 的主入口。

**MCP 通信 vs Phase 5 HTTP Agent 通信**:

| 维度 | Phase 5 HTTP Agent 通信 | Phase 7 MCP 通信 (Option A) |
|------|-----------------------|----------------------------|
| 协议 | hotspot 自定义 HTTP 端点 | 标准 MCP (Anthropic/OpenAI/MS/Google 共识) |
| 调用方 | hotspot 自带 hotspot-agent 进程 | 任意外部 AI Agent (Cursor/Claude Desktop/Trae/Workbuddy) |
| 写操作 | 走 knowledge_tasks 队列, hotspot-agent 异步拉取 | 同步直返, AI Agent 直接落库 |
| LLM 推理 | hotspot-agent 内调用 (Python + Anthropic SDK) | 外部 AI Agent 调用 (用户自选模型) |
| 状态耦合 | hotspot 维护 session / heartbeat / watchdog | hotspot 零状态, AI Agent 主动连入 |
| 配置 | hotspot 网页 `/agent` 路由 | AI Agent 自身的 settings.json |

> Phase 5 端点 (POST /api/agent/tasks, POST /api/agent/knowledge 等) 保留为 deprecated, 仅供内部调试和向后兼容。前端不再调用, AI Agent 改用 MCP。详见 §16.4.2。

---

## 5. MCP 协议与外部 AI Agent 集成

> **v1.7.6 简化 (Option A)**: hotspot 不再内置 hotspot-agent 进程, 不再使用 knowledge_tasks 异步队列。AI Agent 通过标准 MCP 协议直接读写 hotspot, 同步直返。本章节取代 v1.7.5 的"Agent 协议与任务队列"。

### 5.1 MCP 协议基础

**MCP (Model Context Protocol)**: Anthropic 主导 + OpenAI / Microsoft / Google 共识的 LLM-to-data 协议标准, 定义 AI Agent 如何发现、调用工具, 以及工具如何返回数据。

**核心组件**:
- **MCP Client (AI Agent 侧)**: Cursor / Claude Desktop / Trae / Workbuddy 等内置的 MCP client
- **MCP Server (hotspot 侧)**: 通过 fastapi-mcp 库, 把 FastAPI 端点自动暴露为 MCP tool
- **Transport**: 通信方式
  - **stdio**: 子进程 stdin/stdout 通信 (本地, 默认)
  - **SSE / StreamableHTTP**: HTTP 长连接 (跨网络, 本机调试用)

**协议流程** (Cursor 调 hotspot):
```
Cursor (MCP Client)                          hotspot (MCP Server)
  │                                                │
  │── initialize {client: "cursor", version} ────>│  1. 客户端握手
  │<── {server: "hotspot", tools_count: 13} ──────│
  │                                                │
  │── tools/list ────────────────────────────────>│  2. 列出所有 tool
  │<── {tools: [{name: "search_hotspots", ...},  │
  │            {name: "add_favorite", ...}, ...]}│
  │                                                │
  │── tools/call {name: "search_hotspots",        │  3. 调用 tool
  │              arguments: {q: "ai security"}}  ─>│
  │                                                │     → 路由到 /api/hotspots
  │                                                │     → SQLite 查询
  │<── {content: [{type: "text",                   │
  │              text: "{items: [...]}"}]} ───────│
  │                                                │
  │── tools/call {name: "add_favorite",           │  4. 写 tool (同步直返)
  │              arguments: {hotspot_id: "abc"}}  ─>│
  │                                                │     → 写 favorites 表
  │                                                │     → 写 knowledge/items/{id}.md
  │<── {content: [{type: "text",                  │
  │              text: "{success: true}"}]} ──────│
```

**关键特性**:
- **声明式工具描述**: tool 的 name / description / input_schema 在 tools/list 阶段返回, AI Agent 据此决定调哪个 tool
- **参数自动校验**: hotspot 端用 Pydantic / JSON Schema 校验参数, 错误直接返回不执行
- **同步语义**: tool 调用是同步的, AI Agent 拿到结果后继续 LLM 推理
- **零状态**: MCP server 不维护 session 状态, 每个 tool call 独立 (无认证, 走本地 socket/HTTP 限制)

### 5.2 hotspot 暴露的 13 个 MCP Tool

> 完整 schema 见 §16.3, 此处只列概要。

**读 (5 个)**:
| Tool | 输入 | 输出 | 路由 |
|------|------|------|------|
| `search_hotspots` | `{q, tags?, tag_mode?, time_range?, limit?}` | `{items: [...]}` | `GET /api/hotspots` |
| `get_hotspot` | `{hotspot_id}` | `{hotspot: {...}}` | `GET /api/hotspots/{id}` |
| `list_favorites` | `{limit?, cursor?}` | `{favorites: [...]}` | `GET /api/favorites` |
| `search_knowledge` | `{q, lifecycle?, limit?}` | `{items: [...]}` | `GET /api/knowledge/items` |
| `get_personal_profile` | `{}` | `{profile: {...}}` | `GET /api/profile` |

**写 (8 个, 同步直返)**:
| Tool | 输入 | 输出 | 路由 |
|------|------|------|------|
| `add_favorite` | `{hotspot_id, note?}` | `{success, item_id}` | `POST /api/favorites` |
| `remove_favorite` | `{hotspot_id}` | `{success}` | `DELETE /api/favorites/{id}` |
| `add_annotation` | `{entity_type, entity_id, content}` | `{success, annotation_id}` | `POST /api/annotations` |
| `update_knowledge_item` | `{item_id, fields: {...}}` | `{success}` | `PATCH /api/knowledge/items/{id}` |
| `trigger_extract_tags` | `{hotspot_id}` | `{success, tags: [...]}` | `POST /api/extract/auto` (本地规则, 无 LLM) |
| `trigger_cubox_sync` | `{target_path?, format?}` | `{success, count}` | `POST /api/cubox/sync` (本地 CLI) |
| `create_alert_rule` | `{rule: {...}}` | `{success, rule_id}` | `POST /api/alerts/rules` |
| `mark_digest_read` | `{digest_id}` | `{success}` | `POST /api/digests/{id}/read` |

### 5.3 LLM 推理的责任划分

**关键决策 (Option A 核心)**: LLM 推理在外部 AI Agent 侧, hotspot 不调任何 LLM。

```
AI Agent 调 trigger_extract_tags (本地规则, 无 LLM):
  触发 → hotspot 用本地规则 + 关键词提取 (Phase 1 实现, 置信度 0.5-1.0)
       → 返回 {tags: ["ai-security", "langchain"], confidence: 0.7}
  适用场景: 快速、低成本、不需要深度理解

AI Agent 自己用 LLM 提取 (高级):
  AI Agent 先调 get_hotspot({hotspot_id}) 拿全文
  → AI Agent 在 LLM 上下文中分析
  → AI Agent 调 update_knowledge_item({item_id, fields: {tags: [...]}})
  适用场景: 需要深度语义理解, 用户接受 LLM 调用成本
```

**hotspot 不做的事**:
- ❌ 调 LLM (Anthropic / OpenAI / Gemini)
- ❌ 维护 agent runtime
- ❌ 维护 session 状态
- ❌ heartbeat / watchdog

**hotspot 做的事 (v1.7.7 补充: +crawl4ai +Agent CLI +定时轮询)**:
- ✅ 暴露 MCP tool (13 个)
- ✅ SQLite 读写
- ✅ .md 文件读写
- ✅ 本地规则提取 (无 LLM)
- ✅ cubox-cli 调用 (无 LLM)
- ✅ FTS5 搜索

### 5.4 在 AI Agent 中配置 hotspot MCP

**Claude Desktop / Trae / Cursor** (stdio):
```json
// ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
// 或 Trae / Cursor 的 MCP settings 面板
{
  "mcpServers": {
    "hotspot": {
      "command": "python",
      "args": ["-m", "backend.mcp_stdio_main"],
      "cwd": "/Users/duke/Documents/hotspot"
    }
  }
}
```

**Workbuddy / 任何支持 SSE 的 agent** (HTTP):
```json
{
  "mcpServers": {
    "hotspot": {
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

**前提**:
- hotspot 已启动 (`python run.py`)
- 默认绑定 `127.0.0.1:8000`, 避免远程攻击
- feature.mcp_server = on (默认 on, Option A)

### 5.5 与 Phase 5 的对比

| 维度 | v1.7.5 (Phase 5: 内部 hotspot-agent) | v1.7.6 (Phase 7 Option A: MCP) |
|------|-------------------------------------|-------------------------------|
| Agent 进程 | hotspot 自带 `agent/cli.py` | 外部 Cursor/Claude Desktop 等 |
| 通信协议 | 自定义 HTTP + JSON | 标准 MCP (JSON-RPC) |
| 任务队列 | knowledge_tasks 队列 + 文件系统 | 无 (同步直返) |
| 心跳 / 看门狗 | heartbeat + watchdog | 无 |
| 配置入口 | hotspot 网页 `/agent` 路由 | AI Agent 自身的 settings.json |
| 启停控制 | `/api/agent/start` `/stop` | 无 (由 AI Agent 进程管理) |
| LLM 模型 | Python + Anthropic SDK 锁死 Claude | 用户在 AI Agent 中自选 |
| 写延迟 | 入队 < 50ms, 执行在 agent 轮询周期后 | 同步直返, 取决于 SQLite < 100ms |
| 读延迟 | 走 FastAPI 同步 < 500ms | 走 MCP 同步 < 500ms |
| 状态复杂度 | agent 进程 + 队列 + heartbeat | 零状态 |
| 删除的代码 | - | `agent/` 目录 / `agent_task_service.py` / `agent_protocol.py` / `kv_cache_service.py` / knowledge_tasks 表 / agent_heartbeats 表 / skill_config 表 / `/agent` 路由 + 5 tab 组件 |

> **结论**: Option A 显著简化了 hotspot 的内部状态和职责, AI 智能全部由用户已选好的 AI Agent 承担, hotspot 只做数据存储 + MCP 暴露。详见 §16 完整设计。

---

### 5.6 Hotspot ↔ AI Agent 双向生产环 (v1.7.7)

**概念**: v1.7.6 (Option A) 只实现了"AI Agent → Hotspot"的单向 MCP 通信。v1.7.7 增加"Hotspot → AI Agent"方向，形成双向生产环：

```
                     ┌───────────────────┐
                     │   Hotspot 平台     │
                     │                    │
                     │  ┌─────────────┐   │
                     │  │ MCP Server  │───┼───→ AI Agent (通过 MCP 读/写)
                     │  └─────────────┘   │     ↑
                     │  ┌─────────────┐   │     │
                     │  │ Scheduler    │───┼───→ CLI 调用 Agent Skill
                     │  │ (定时轮询)   │   │     │
                     │  └─────────────┘   │     │
                     │  ┌─────────────┐   │     │
                     │  │ Agent CLI   │<──┼──────┘ Agent 执行完回写
                     │  │ (hotspot-   │   │
                     │  │  agent-cli) │   │
                     │  └─────────────┘   │
                     └───────────────────┘
```

**方向 1: AI Agent → Hotspot (通过 MCP)**
- v1.7.6 已有: 外部 AI Agent 通过 MCP 调 hotspot 13 个 tool
- Agent 读: search_hotspots, get_hotspot, search_knowledge, list_favorites
- Agent 写: add_favorite, update_knowledge_item, add_annotation, create_alert_rule

**方向 2: Hotspot → AI Agent (通过 CLI)**
- v1.7.7 新增: hotspot 通过 scheduler 定时调用 Agent CLI 执行 Skill
- Agent CLI 入口: `hotspot-agent-cli run <skill_name> --params <params>`
- 触发场景: 
  - 新文章进入 `kl:raw` → 调用 Agent 执行 `extract_tags` skill
  - 新 CVE 发布 → 调用 Agent 执行 `analyze_cve` skill
  - 每日摘要 → 调用 Agent 执行 `generate_digest` skill
  - 用户自定义规则触发特定 skill 执行

**通信协议 (方向 2)**:
```
Hotspot Scheduler → subprocess.run(["hotspot-agent-cli", "run", "extract_tags", "--params", json_params])
  → Agent CLI 启动 → 解析 params → 执行对应 Skill
  → Skill 内部调 LLM 分析 → 调 MCP write_tool (如 update_knowledge_item) 写回 hotspot
  → Agent CLI 返回 exit code + stdout JSON 给 Hotspot
  → Hotspot 记录执行结果到 agent_poll_config.last_poll
```

**为什么不直接方向 1 就够了?**：方向 2 (Hotspot → Agent) 解决的是"无人值守的自动化"场景：
- 示例: 凌晨 3 点 CVE 发布 → hotspot 自动调用 Agent 分析 → 结果写入知识库 → 用户早上看到告警
- 方向 1 需要有人(用户)在 Cursor 中发指令；方向 2 让 hotspot 自身具备主动性

### 5.7 定时轮询设计 (v1.7.7)

**轮询架构**: Hotspot ↔ Agent 双向定时轮询，轮询间隔可自定义。

```
┌─────────────────────────────────────────────────┐
│                  Hotspot Scheduler               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ hot_take    │  │ agent_poll  │  │ crawl4ai│ │
│  │ _collect    │  │ _consumer   │  │ _fetch  │ │
│  │ (5min)      │  │ (自定义)    │  │ (按配置) │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │
└─────────┼────────────────┼───────────────┼──────┘
          │                │               │
          ▼                ▼               ▼
    采集新文章       调用 Agent CLI    crawl4ai 高阶抓取
                    (hotspot-agent-cli run ...)
```

**轮询规则**:

| 方向 | 轮询驱动 | 间隔 | 触发条件 | 默认 |
|------|---------|------|----------|------|
| Agent → Hotspot | AI Agent 自身定时查询 | 由 Agent 自己的定时机制控制 | Agent 调 `search_knowledge({lifecycle: "kl:raw"})` 发现新文章 | 外部 Agent 自行决定 |
| Hotspot → Agent | Hotspot scheduler 定时 | `agent_poll_config.poll_interval` | 新 item lifecycle 达到 `agent_poll_config.poll_mode` 阶段 | 30min |
| Hotspot → crawl4ai | `crawl4ai_fetch` job | `collector_sources.interval_min` | 源的 `llm_config` 非空 | 按源配置 |

**延迟考虑**:
- `poll_interval=30m` 时，新文章进入 kl:raw 最差延迟 30min 才被 Agent 处理
- 高优先级源 (如 CVE feeds) 可设置 `poll_interval=5m` 或直达告警 `alert_evaluator` 60s 间隔
- AI Agent 的 LLM 推理时间 (秒级) > 轮询间隔抖动，不构成瓶颈

**休眠期自定义**: 用户可在 `agent_poll_config` 中设置 `quiet_hours` 避免夜间不必要的轮询：
```json
{ "quiet_hours": {"start": "23:00", "end": "07:00"} }
```

**与 KL 阶段对齐**: 轮询间隔建议与 KL 刷新周期对齐：

| KL 阶段 | 典型处理时间 | Agent 轮询间隔建议 |
|---------|-------------|------------------|
| kl:raw → kl:refine | 秒级 (本地规则) | 立即 (auto_extract job) |
| kl:refine → kl:link | 分钟级 | 30min |
| kl:link → kl:structure | 小时级 | 6h |
| kl:structure → kl:publish | 小时级或用户手动 | 24h |

## 6. 功能规格（按用户旅程）

### 6.1 M1: 简报与态势感知（对应 08:00-08:15）

**用户故事**: 每天早上打开 dashboard，系统告诉我"昨夜有 3 个新安全告警，AI 领域新增 23 篇文章，你的 3 个项目无影响"。

**实现要点**:
- `digest_generator` job 每日 08:00 执行，基于昨日热点和 reading_states 生成
- `source_health_check` 每 15min 检查各源采集量 vs 7 日基线
- 简报模式在用户首次访问当日时自动触发

### 6.2 M2: 多维标签与交叉筛选（对应 08:15-09:00 优先级排序）

**用户故事**: 我想看到同时命中 `ai` 和 `security` 标签的漏洞文章，按 `CVE` 技术标签进一步筛选。

**标签规则配置示例**: `backend/data/tag_rules.json`
```json
{
  "rules": [
    { "pattern": "CVE-\\d{4}-\\d{4,7}", "tag_id": "cve", "confidence": 1.0 },
    { "keywords": ["langchain", "LangChain"], "tag_id": "langchain", "confidence": 0.8 },
    { "keywords": ["prompt injection"], "tag_id": "prompt-injection", "confidence": 0.7 }
  ]
}
```

### 6.3 M3: 自动知识提取（对应 09:00-12:00 深度阅读）

**用户故事**: 打开一篇 LangChain 漏洞文章，系统自动识别出 `langchain`、`prompt-injection`、`CVE-2026-XXXX` 三个标签。

**提取器分层**:
```python
extractors = [
    RegexExtractor(patterns=[       # 置信度 1.0
        r'CVE-\d{4}-\d{4,7}',
        r'CNVD-\d{4}-\d{4,7}',
    ]),
    KeywordExtractor(keywords=[     # 置信度 0.7
        ('langchain', 'langchain', 'framework'),
        ('fastapi', 'fastapi', 'framework'),
    ]),
    CategoryDomainExtractor(        # 置信度 0.5
        domain_map=CATEGORY_DOMAIN_MAP,
    ),
]
```

### 6.4 M4: SM-2 间隔复习（对应 17:00 复盘）

**用户故事**: 两周前学过的概念，系统提示"该复习了"——自评 grade=4，系统自动将下次复习延至 7 天后。

**SM-2 公式**:
```python
def sm2_schedule(grade, easiness, interval, reps):
    if grade < 3:
        reps = 0; interval = 1
    else:
        if reps == 0: interval = 1
        elif reps == 1: interval = 6
        else: interval = round(interval * easiness)
        reps += 1
    easiness = max(1.3, easiness + 0.1 - (5-grade)*(0.08 + (5-grade)*0.02))
    return easiness, interval, reps
```

### 6.5 M5: 技术栈桥接（对应 13:00-17:00 行动落地）

**用户故事**: 系统检测到一篇 FastAPI 漏洞文章，自动匹配到项目中使用了 FastAPI 的 3 个项目，创建待确认 Todo。

**流程**:
新文章入库 -> extract_service 提取 tech_stack 标签 -> 匹配 tech_stack 表 -> 匹配 cg_projects -> 创建 cg_events + Todo

### 6.6 M6: 规则告警系统（全天候）

**用户故事**: 设规则"当出现影响 FastAPI/LangChain 的 CVE 时通知我"，凌晨 3 点命中，早上看到红色告警。

**条件 DSL 示例**:
```json
{
  "type": "tag_match",
  "operator": "AND",
  "conditions": [
    { "field": "tags", "op": "contains_any", "value": ["CVE", "vulnerability"] },
    { "field": "tags", "op": "contains_any", "value": ["fastapi", "langchain"] }
  ],
  "actions": { "push": ["sse"], "auto_mark": "urgent", "auto_todo": true }
}
```

### 6.7 M7: 统一跨层搜索（全天候）

**用户故事**: 搜 `langchain security` -> 同一页看到 8 篇热点、2 条知识、1 条待办、3 条收藏、1 个项目。

**性能预算**: unified_fts (100k items): P50 < 100ms, P95 < 500ms

### 6.8 M8: 上下文感知知识推荐（全天候）

**用户故事**: 读 LangChain 漏洞文章时，右侧栏自动显示知识库中相关的 `ai-agent-security` 概念。

### 6.9 M9: 笔记空间（全天候）

深度阅读模式右侧栏 -> "笔记" Tab -> 简化 Markdown 编辑器

### 6.10 M10: 隐式个性化（全天候后台）

**信号采集**: 打开文章(+0.1) / 停留>60s(+0.2) / 收藏(+0.5) / 记笔记(+0.3) / 忽略(-0.05)
**权重公式**: weight = max(-2, min(2, weight_old * 0.95 + signal))

### 6.11 M11: 数据源完整性仪表盘（全天候）

基于该源过去 7 天的日均采集量 +/- 30% 窗口判定状态: green/yellow/red

### 6.12 M12: 收藏→知识提升 + 采集升级（全天候）

**用户故事**: 收藏一篇文章后，系统自动将其写入 knowledge/items/ 目录，触发 KL 生命周期，可由外部 AI Agent 通过 MCP 进一步处理（提取标签和概念）。

**流程（v1.7.6 Option A）**:
```
触发源 1: 用户在 hotspot UI 收藏
  用户点击收藏按钮
    → 写入 favorites 表 (created_via='ui')
    → 创建 knowledge/items/{id}.md (YAML frontmatter + 原文链接)
    → 触发 KL lifecycle: kl:raw
    → 用户可直接在 Obsidian 中阅读和编辑

触发源 2: 外部 AI Agent 通过 MCP 收藏 (Option A 新增)
  Cursor 调 add_favorite({hotspot_id: "abc", note: "important"})
    → MCP server 路由到 POST /api/favorites
    → 写入 favorites 表 (created_via='mcp')
    → 创建 knowledge/items/{id}.md
    → 触发 KL lifecycle: kl:raw
    → 同步返回 {success: true, item_id: "abc"} 给 AI Agent

后续处理 (按需, 异步):
  外部 AI Agent (Cursor/Claude Desktop 等) 通过 MCP 周期性:
    → 调 search_knowledge({lifecycle: "kl:raw"}) 找出待处理条目
    → 调 get_personal_profile() 了解用户偏好
    → 调 get_hotspot({hotspot_id}) 拿全文
    → AI Agent 在 LLM 上下文中分析（提取 tags / concepts / tech_stack）
    → 调 update_knowledge_item({item_id, fields: {...}}) 写回
    → lifecycle: signal → amplify:tagged → amplify:linked → ... → generate
```

> **v1.7.5 旧流程（已删除）**: 收藏 → 写入 tasks/pending/ → 内部 hotspot-agent 轮询 → 执行提取 Skill → 写回 lifecycle。本流程在 v1.7.6 中被 Option A 替代，不再有内部 agent。

### 6.13 M13: 采集层升级 — 传统爬虫 + crawl4ai + 标讯 (v1.7.7)

**用户故事**: 我想在 RSS 采集之外，自动抓取完整文章正文，并支持一键关注招标信息。

**设计**:

```
采集源配置 (collector_sources 表):
┌─────────────┬──────────────┬──────────────────────────────┐
│ source_type │ 说明          │ 示例                         │
├─────────────┼──────────────┼──────────────────────────────┤
│ rss         │ RSS/Atom 订阅 │ 安全资讯 RSS                 │
│ crawl       │ 基础爬虫      │ 简单 HTML 页面，无 JS 渲染   │
│ crawl4ai    │ 高阶爬虫      │ 需要 JS 渲染或 LLM 辅助提取  │
│ tenders     │ 招标/标讯     │ 政府采购公告 (中国招标网等)  │
│ bookmark    │ 浏览器书签    │ 导入的 HTML 书签文件         │
│ cubox       │ Cubox 缓存    │ cubox-cli 本地缓存           │
└─────────────┴──────────────┴──────────────────────────────┘
```

**crawl4ai 集成**:

当 `collector_sources.llm_config` 非空时，采集该源走 crawl4ai：
1. crawl4ai 启动 headless browser → 加载目标 URL → 执行 JS → 获取渲染后的 HTML
2. 将 HTML 交给 LLM (按 llm_config 配置) → LLM 提取文章正文、标题、作者、时间
3. 结果写入 hotspots 表（source_type='crawl4ai'）
4. 同时触发自动标签提取 (auto_extract job)

```python
# backend/collectors/crawl4ai_collector.py (示意)
async def fetch_with_crawl4ai(source: CollectorSource) -> list[dict]:
    if not source.llm_config:
        return await traditional_fetch(source)
    
    # 1. crawl4ai 获取渲染后 HTML
    raw_html = await crawl4ai.fetch(source.url, 
        headless=True, js=source.parser_config.get('js_scripts'))
    
    # 2. LLM 提取结构化内容
    result = await llm_extract(raw_html, 
        model=source.llm_config['model'],
        prompt=source.llm_config.get('prompt', EXTRACT_PROMPT))
    
    # 3. 写入 hotspot
    return [{"title": result.title, "summary": result.body, ...}]
```

**标讯采集**:

`source_type = 'tenders'` 采集政府采购、招标信息：
- 定时轮询指定招标网站 (如 中国采购与招标网、政府采购网)
- 自动提取：项目名称、采购方、预算金额、截止日期、联系方式
- 写入 hotspots 表，标签自动标记为 `tender`、`procurement`
- 匹配 tech_stack (如 "需要网络安全服务" → 匹配用户的技术栈)
- 创建告警 (匹配的项目推送通知)

**配置示例**:
```json
{
  "id": "chinabidding",
  "display_name": "中国采购与招标网",
  "source_type": "tenders",
  "url": "https://www.chinabidding.com.cn/",
  "enabled": true,
  "interval_min": 60,
  "priority": 1,
  "llm_config": null,
  "parser_config": {
    "title_selector": ".bid-title",
    "content_selector": ".bid-content",
    "fields": ["project_name", "buyer", "budget", "deadline"]
  }
}
```

---

## 7. 调度器变更

### 7.1 新增 job（v1.7.5 Phase 5 + v1.7.6 Phase 7 调整后）

| Job | 频率 | 职责 | 优先级 | Phase |
|-----|------|------|--------|-------|
| auto_extract | 采集完成后触发 | 为新增文章本地规则提取标签/概念/技术栈 (无 LLM) | 高 | Phase 1 |
| review_scheduler | 每 6h | 查询 sm2_reviews.next_review_at | 中 | Phase 2 |
| alert_evaluator | 每 60s | 评估新文章是否匹配告警规则 | 高 | Phase 3 |
| profile_updater | 每 30min | 更新 personal_profile 权重 | 低 | Phase 4 |
| digest_generator | 每 24h (08:00) | 生成昨日简报 | 中 | Phase 4 |
| source_health_check | 每 15min | 检查数据源采集覆盖率 | 中 | Phase 4 |
| fts_rebuild | 每 5min | 重建 unified_fts 索引 | 低 | Phase 4 |
| profile_decay | 每 24h (03:00) | 所有 weight 衰减 5% | 低 | Phase 4 |
| cubox_auto_sync | 每 24h (03:00) | 调用 cubox-cli 自动同步到本地缓存 | 中 | Phase 7 |

| crawl4ai_fetch | 按源配置 (interval_min) | crawl4ai 高阶抓取，支持 LLM 辅助提取 | 中 | v1.7.7 |
| agent_poll_consumer | 按 agent_poll_config.poll_interval | 定时调用 Agent CLI 执行 Skill | 低 | v1.7.7 |
| tenders_collect | 按源配置 (默认 60min) | 标讯采集，提取项目/预算/截止日期 | 中 | v1.7.7 |

### 7.2 v1.7.6 移除的 job (Option A 不再需要)

| Job (v1.7.5) | 删除原因 |
|--------------|---------|
| `agent_task_consumer` (60s) | 没有内部 agent 拉任务；外部 AI Agent 通过 MCP 同步直返 |
| `agent_heartbeat_check` | 没有内部 agent 心跳 |
| `kv_cache_cleanup` (30min) | kv_cache 保留为可选层，不再主动维护；不再有定期清理需求 |
| `auto_extract_llm` | LLM 在外部 agent 侧，hotspot 不调 LLM |
| `review_scheduler_llm` | 同上 |

> 详细删除决策见 §16.6.1。

### 7.3 现有 job 修改

| 现有 Job | 修改内容 |
|----------|----------|
| collection_service | 采集完成后触发 `auto_extract`（本地规则）而非写入 tasks/pending/ |
| knowledge_watcher | 继续对 knowledge/items/ 目录 FSWatch，更新 knowledge_items 表；kv_cache 不再强制同步 |

---

## 8. 前端组件与路由

### 8.1 新增组件

| 组件 | 用途 | 父组件 | Phase |
|------|------|--------|-------|
| SourceHealthBar | 数据源状态条 | PageLayout (顶部) | Phase 4 |
| AlertBanner | 告警横幅 | PageLayout (顶部) | Phase 3 |
| BriefModeView | 简报模式 | MainView | Phase 4 |
| DeepReadView | 深度阅读模式 | MainView | Phase 4 |
| ArticlePanel | 文章正文区 | DeepReadView | Phase 4 |
| RecommendationSidebar | 推荐侧栏 | DeepReadView | Phase 4 |
| NotePanel | 笔记输入 | DeepReadView | Phase 2 |
| OrganizeView | 整理模式 | MainView | Phase 1 |
| AlertCenter | 告警中心 | 独立页面 /alerts | Phase 3 |
| ReviewPage | 复习页面 | 独立页面 /reviews | Phase 2 |
| TechStackPage | 技术栈管理 | 独立页面 /tech-stack | Phase 2 |
| TagsPage | 标签管理 | 独立页面 /tags | Phase 1 |
| ProfilePage | 个性化画像 | 独立页面 /profile | Phase 4 |
| **MCPSettingsCard** | **MCP endpoint + 复制按钮 + 13 tool 列表** | **SettingsPage (内嵌)** | **Phase 7** |

### 8.2 v1.7.6 移除的组件 (Option A 不再需要)

| 组件 | 删除原因 |
|------|---------|
| `AgentStatusBadge` | 没有内部 agent，无状态可显示 |
| `AgentPage` (含 5 tab) | 同上 |
| `AgentOverviewTab` / `AgentTasksTab` / `AgentSkillsTab` / `AgentKnowledgeTab` / `AgentLogsTab` | 同上 |

> 详细删除决策见 §16.7.2。

### 8.3 路由变更

| 路由 | 页面 | 懒加载 | Phase |
|------|------|--------|-------|
| / | 简报/扫描(自适应) | 否 | — |
| /deep/:type/:id | 深度阅读 | 是 | Phase 4 |
| /organize | 整理模式 | 是 | Phase 1 |
| /alerts | 告警中心 | 是 | Phase 3 |
| /reviews | 复习页面 | 是 | Phase 2 |
| /tech-stack | 技术栈管理 | 是 | Phase 2 |
| /tags | 标签管理 | 是 | Phase 1 |
| /profile | 个性化画像 | 是 | Phase 4 |
| /settings/mcp | **MCP 设置卡片** | **是** | **Phase 7** |

### 8.4 v1.7.6 移除的路由

| 路由 | 原因 |
|------|------|
| `/agent` (含 5 tab) | Option A 无内部 agent；MCP 配置在 AI Agent 侧 |
| `/agent/cubox` | Cubox 手动同步改由 AI Agent 调 `trigger_cubox_sync` tool |

### 8.5 共享组件

| 组件 | 用途 | 复用场景 |
|------|------|---------|
| TagSelector | 多选标签选择器 | 首页筛选，告警规则配置，搜索过滤 |
| TagPill | 标签 pill 展示 | 卡片列表，筛选栏，告警详情 |
| ReviewCard | 卡片翻转 UI | 复习页面，深度阅读中主动复习 |
| NoteEditor | 简化 Markdown 编辑器 | 笔记区，告警备注 |
| AlertBadge | 告警角标 | 导航栏，首页 |
| SourceHealthIndicator | 数据源状态指示灯 | 首页源状态条，设置页 |
| ModeSwitcher | 模式切换按钮组 | 顶部导航栏 |

### 8.6 Hooks 新增

| Hook | 用途 | Phase |
|------|------|-------|
| useTags() | 标签列表 + 筛选状态 | Phase 1 |
| useExtraction() | 自动提取 + 待确认管理 | Phase 1 |
| useReviews() | 复习队列 + 评分提交 | Phase 2 |
| useAlerts() | 告警列表 + SSE 实时推送 | Phase 3 |
| useSearch() | 统一搜索 (debounced，跨层) | Phase 3 |
| useProfile() | 个性化画像读取 + 手动调整 | Phase 4 |
| useMode() | 当前模式 + 模式切换 | Phase 4 |
| useAnnotations(type, id) | 笔记 CRUD | Phase 2 |
| useSourceHealth() | 数据源健康状态 | Phase 4 |

---

## 9. 跨端同步变更

### 9.1 v1.7 同步策略表

| 表 | 冲突策略 | Phase |
|----|---------|-------|
| reading_states | last_writer_wins (updated_at) | Phase 2 |
| annotations | last_writer_wins (updated_at) | Phase 2 |
| tags | cascade (整表 union) | Phase 1 |
| sm2_reviews | merge (next_review_at 更近者胜出) | Phase 2 |
| kv_cache | **不跨端同步（本地缓存，各端独立）** | Phase 1 |
| mcp_tool_registry | **不跨端同步（启动时 seeding）** | Phase 7 |
| favorites (含 created_via) | last_writer_wins (updated_at) | Phase 1/7 |
| hotspot_tags | cascade | Phase 1 |
| cg_services / cg_resources / cg_dependencies / cg_events | **不跨端（设备本地状态）** | Phase 2b |
| sync_configs / sync_state / sync_history | last_writer_wins | Phase 6 |

### 9.2 同步说明

- `knowledge/items/` 目录中的 `.md` 文件通过 Obsidian 同步（如 Obsidian Sync、iCloud、Git）
- `kv_cache` 是本地缓存，不参与跨端同步，各端独立重建
- `mcp_tool_registry` 启动时根据代码 seeding，不跨端同步
- **Agent 任务队列已删除**（v1.7.6 Option A）：`knowledge/learning/tasks/pending/` 不再是活跃写入位置；历史文件保留作为 audit log
- **MCP 状态不跨端**：每个 hotspot 实例独立启动 MCP server，外部 AI Agent 在各设备上分别配置 MCP endpoint

### 9.3 v1.7 新增同步点

- favorites.created_via 字段记录来源（'ui' / 'mcp' / 'agent'），跨端同步时一并合并
- mcp_tool_registry（v1.7.6）启动时根据代码 seeding；新增 tool 需重启 hotspot
- sync_bundle v1.7 扩展（Phase 6 完成）已支持 5 表读写，含 sm2 特殊 merge

### 9.4 移除的同步项（v1.7.6 Option A）

| 旧同步项 | 移除原因 |
|---------|---------|
| knowledge_tasks 队列状态 | Option A 不再使用内部 agent 任务队列 |
| agent_heartbeats | 没有内部 agent 心跳 |
| agent_task_skills / skill_config | 无 Skill 注册机制 |
| mcp_tool_invocations | Option A 零状态，调用日志走 server log |

---

## 10. 迁移策略

### 10.1 数据库迁移

| 序号 | 文件 | 内容 | Phase |
|------|------|------|-------|
| 024 | 024_v1.7_tags.sql | tags + hotspot_tags 表 | Phase 1 |
| 025 | 025_v1.7_reading_states.sql | reading_states 表 | Phase 2 |
| 026 | 026_v1.7_sm2_reviews.sql | sm2_reviews 表 | Phase 2 |
| 027 | 027_v1.7_annotations.sql | annotations 表 | Phase 2 |
| 028 | 028_v1.7_alert_rules.sql | alert_rules 表 | Phase 3 |
| 029 | 029_v1.7_tech_stack.sql | tech_stack 表 | Phase 2 |
| 030 | 030_v1.7_personal_profile.sql | personal_profile 表 | Phase 4 |
| 031 | 031_v1.7_digests.sql | digests 表 | Phase 4 |
| 032 | 032_v1.7_kv_cache.sql | kv_cache 表 (可选加速层) | Phase 1 |
| 033 | 033_v1.7_unified_fts.sql | unified_fts 视图+虚拟表 | Phase 3 |
| 034 | 034_v1.7_alter_existing.sql | 现有表新增字段: lifecycle, tags, tech_stack, last_read_at | Phase 1-4 |
| 035 | 035_v1.7_migrate_compiled.sql | 迁移 compiled -> lifecycle | Phase 1-4 |
| 036 | 036_v1.7_hotspot_lifecycle.sql | hotspots.lifecycle 字段 | Phase 5 |
| 041 | 041_v1.9_item_entities.sql | item_entities 表 (SAG event-entity 吸收) | v1.7.7 |
| 042 | 042_v1.9_collector_sources.sql | collector_sources 表 (采集源配置) | v1.7.7 |
| 043 | 043_v1.9_agent_poll_config.sql | agent_poll_config 表 (轮询配置) | v1.7.7 |
| 044 | 044_v1.9_kl_migration.sql | migration: SAG lifecycle → KL lifecycle | v1.7.7 |
| **037** | **037_v1.7_mcp_tool_registry.sql** | **mcp_tool_registry 表（启动 seeding）** | **Phase 7** |
| **038** | **038_v1.7_drop_phase5_tables.sql** | **DROP knowledge_tasks / agent_heartbeats / agent_task_skills / skill_config / mcp_tool_invocations (5 张表, kv_cache 评估后保留)** | **Phase 7** |
| **039** | **039_v1.7_add_favorite_source.sql** | **ALTER favorites ADD COLUMN created_via** | **Phase 7** |

> **重要**: Phase 7 migration 038 删除的 5 张表已确认不包含 active 数据。knowledge_tasks 队列内容仅是历史 hot_take_collect + 一些遗留 task-XXX.md，已全部可清理；其他表为 Phase 5 引入但未持续维护。**kv_cache 评估后保留为可选加速层（不主动维护）**，不在 038 范围内。

### 10.2 数据迁移脚本（035_v1.7_migrate_compiled.sql）

```sql
-- 迁移现有 knowledge_items 的 compiled 字段到 lifecycle
UPDATE knowledge_items
SET lifecycle = CASE
    WHEN compiled = 1 THEN 'generate'
    WHEN compiled = 0 THEN 'amplify:complete'
    ELSE 'signal'
END;

-- 迁移现有 hotspots 的 tags 字段
UPDATE hotspots
SET tags = '[]'
WHERE tags IS NULL;

-- 初始化 tags 种子数据
INSERT INTO tags (id, label, type, weight) VALUES
    ('cve', 'CVE', 'cve', 1.5),
    ('vulnerability', '漏洞', 'technique', 1.0),
    ('ai-security', 'AI安全', 'domain', 1.0),
    ('network-security', '网络安全', 'domain', 1.0);
```

### 10.3 功能开关

| 阶段 | 开关 | 默认 | Phase |
|------|------|------|-------|
| Phase 1 标签 | feature.tags | on | Phase 1 |
| Phase 1 提取 | feature.auto_extract | on | Phase 1 |
| Phase 2 复习 | feature.reviews | off (手动开通) | Phase 2 |
| Phase 3 告警 | feature.alerts | off (手动开通) | Phase 3 |
| Phase 3 搜索 | feature.unified_search | on | Phase 3 |
| Phase 4 推荐 | feature.recommendations | off (手动开通) | Phase 4 |
| Phase 4 笔记 | feature.annotations | on | Phase 4 |
| Phase 4 个性化 | feature.personalization | off (手动开通) | Phase 4 |
| ~~Phase 5 Agent~~ | ~~feature.agent~~ | **已移除** | Phase 5 → Phase 7 |
| **Phase 7 MCP** | **feature.mcp_server** | **on (Option A 默认开启)** | **Phase 7** |

### 10.4 Phase 7 文件系统清理

| 路径 | 操作 | 备注 |
|------|------|------|
| `knowledge/learning/tasks/pending/` | 清空 (Option A 无任务队列) | 历史文件保留为 audit log 已规划 |
| `knowledge/learning/tasks/processing/` | 清空 | 同上 |
| `knowledge/learning/tasks/done/` | 保留 (历史归档) | — |
| `knowledge/learning/tasks/failed/` | 保留 (历史归档) | — |
| `agent/` 目录 | **整目录删除** (无 hotspot-agent 进程) | 含 `agent/cli.py` / `agent/skills/` / `agent/heartbeat.py` 等 |
| `backend/services/agent_task_service.py` | 删除 | — |
| `backend/services/agent_protocol.py` | 删除 | — |
| `backend/services/kv_cache_service.py` | 删除 (kv_cache 表保留但服务层不主动维护) | — |
| `backend/services/soul_service.py` (LLM 部分) | 保留, 改为不调 LLM (本地规则) | — |
| `backend/api/agent.py` | 删除或 deprecated | 移除 /agent/start, /agent/stop, /agent/heartbeat 等 |
| `frontend/src/components/agent/` | 整目录删除 | AgentPage + 5 tab 组件 |

---

## 11. 测试策略

### 11.1 v1.7 新增测试文件（Phase 1-6）

| 文件 | 类型 | 覆盖 | Phase |
|------|------|------|-------|
| test_tag_service.py | unit | tags CRUD + filter | Phase 1 |
| test_extract_service.py | unit | 三层提取器 + 置信度 | Phase 1 |
| test_review_service.py | unit | SM-2 公式 + 调度 | Phase 2 |
| test_alert_service.py | unit | 条件匹配 + cooldown | Phase 3 |
| test_search_service.py | integration | unified_fts 性能 | Phase 3 |
| test_annotation_service.py | unit | CRUD | Phase 2 |
| test_profile_service.py | unit | weight 计算 + 衰减 | Phase 4 |
| test_source_health_service.py | unit | 状态判定 | Phase 4 |
| test_tech_stack_bridge.py | integration | 跨模块桥接 | Phase 2 |
| test_kv_cache_service.py | unit | 缓存读写 + 过期 | Phase 1 |
| ~~test_agent_protocol.py~~ | ~~integration~~ | **已删除 (Phase 7 Option A)** | ~~Phase 5~~ |
| test_kl_lifecycle.py | unit | KL 生命周期转移 | Phase 5 |
| test_v1.7_e2e.py | e2e | 全流程 | Phase 1-6 |
| test_sync_bundle_v1_7.py | unit | 5 表同步 + sm2 merge | Phase 6 |
| test_feature_flags.py | unit | 13 个 feature flag | Phase 6 |

### 11.2 v1.7.6 Phase 7 新增测试

| 文件 | 类型 | 覆盖 |
|------|------|------|
| `test_mcp_server.py` | unit | fastapi-mcp 启动 / 关闭, tools/list 返回 13 个 tool |
| `test_mcp_read_tools.py` | integration | 5 个读 tool 路由到正确 FastAPI 端点 |
| `test_mcp_write_tools.py` | integration | 8 个写 tool 同步直返, 写库成功 |
| `test_mcp_stdio.py` | integration | subprocess 启动 stdio 入口, 模拟外部 agent 调 tool |
| `test_mcp_sse.py` | integration | HTTP client 连 /mcp/sse, 调 tool, 验证响应 |
| `test_phase5_table_cleanup.py` | unit | DROP 5 张表 (Phase 5) 的迁移可重放, 现有数据无影响 |
| `test_favorite_created_via.py` | unit | add_favorite MCP 写 created_via='mcp' |
| `test_phase7_e2e.py` | e2e | 启动 hotspot + 模拟 Cursor 调 MCP, 验证读写全链路 |

### 11.3 前端测试

| 文件 | 覆盖 | Phase |
|------|------|-------|
| TagSelector.test.tsx | 多选 + AND/OR | Phase 1 |
| ReviewCard.test.tsx | 卡片翻转 + 评分 | Phase 2 |
| DeepReadView.test.tsx | 全屏阅读 + 侧栏 | Phase 4 |
| AlertCenter.test.tsx | 列表 + 标记已读 + SSE mock | Phase 3 |
| UnifiedSearch.test.tsx | 输入防抖 + 跨层结果 | Phase 3 |
| SourceHealthBar.test.tsx | 状态渲染 | Phase 4 |
| v1.7_modes.test.tsx | 模式切换 + 路由 | Phase 4 |
| **MCPSettingsCard.test.tsx** | **复制按钮 / 13 个 tool 列表 / enabled toggle** | **Phase 7** |

### 11.4 v1.7.6 移除的测试

| 文件 | 原因 |
|------|------|
| `test_agent_protocol.py` (Phase 5 引入) | 没有内部 hotspot-agent，不再需要协议测试 |
| `test_agent_task_service.py` | 同上 |
| `test_kv_cache_cleanup.py` | kv_cache 不再有专门的清理 job |
| `AgentStatusBadge.test.tsx` | 没有内部 agent 状态组件 |
| `AgentPage.test.tsx` (5 tab) | 没有 /agent 路由 |

---

## 12. Phase 规划

| Phase | 名称 | 周期 | 模块 | 依赖 | 状态 |
|-------|------|------|------|------|------|
| 1 | 标签与自动提取（核心基础设施） | ~5 天 | tags 表 + 提取器 + 标签 API | 无 | ✅ |
| 2 | 内化与桥接 | ~5 天 | SM-2 复习 + 技术栈 + 笔记 | Phase 1 | ✅ |
| 3 | 告警与统一搜索 | ~4 天 | 告警规则 + 统一搜索 + 模式切换 | Phase 1 | ✅ |
| 4 | 智能与体验 | ~4 天 | 上下文推荐 + 隐式个性化 + 数据源健康 | Phase 1+2+3 | ✅ |
| 5 | Agent 集成 + KL (原名 SAG) 生命周期 + KV 缓存 | ~5 天 | Agent 协议 + 任务队列 + CLI 整合 + KL 生命周期 + KV 缓存 | Phase 1+2+3+4 | ✅ (代码完成, 后续 Phase 7 删表) |
| 6 | Sync Bundle 扩展 + Feature Flags | ~2 天 | reading_states/annotations/tags/sm2_reviews 同步 + 13 个 feature flags | Phase 5 | ✅ |
| 7 | **MCP Server（让 hotspot ↔ 外部 AI Agent 通过 MCP 通信）** | **~3 天** | **详见 §16** | **Phase 1-6** | **📋 规划中 (v1.7.6)** |

**总预估**: ~28 天（含 Phase 7 Option A 简化）

### 12.1 Phase 5 详细任务（v1.7.5 实施，Phase 7 部分删表）

1. 实现 agent_task_consumer job (写入 tasks/pending/)
2. 实现 Agent CLI 入口 (hotspot-agent 命令)
3. 实现 Agent 轮询协议 (phase-locked polling)
4. 实现 Agent Skill 配置和执行引擎
5. 实现 /api/agent/* 端点
6. 实现 KL 生命周期状态机（替换 compiled: bool）
7. 实现 kv_cache 表和服务
8. 实现 CLI 工具整合（cubox, bookmark, knowledge-tasks）
9. 实现收藏→知识提升流程
10. 实现 Obsidian 侧集成（FSWatch + 文件变更通知）

> **Phase 7 后续动作**: Phase 5 引入的 agent/ 目录、agent_task_service.py、agent_protocol.py、kv_cache_service.py、knowledge_tasks 表、agent_heartbeats 表、skill_config 表、/agent 路由 + 5 tab 组件全部移除（详见 §10.4 / §16）。

### 12.2 Phase 6 详细任务

1. Sync Bundle 增加 reading_states / annotations / tags / sm2_reviews 4 表
2. 实现 tags cascade merge、sm2 next_review_at merge
3. Feature Flag 配置 (13 个 feature_* 字段) + is_enabled 服务
4. 测试：21 + 13 = 34 个新增测试

### 12.3 Phase 7 详细任务（v1.7.6 Option A 简化版，详见 §16）

1. **7.1 MCP Server 基础**（fastapi-mcp + stdio/sse transport）
2. **7.2 MCP 读工具**（5 个：search_hotspots / get_hotspot / list_favorites / search_knowledge / get_personal_profile）
3. **7.3 MCP 写工具**（8 个同步直返：add_favorite / remove_favorite / add_annotation / update_knowledge_item / trigger_extract_tags / trigger_cubox_sync / create_alert_rule / mark_digest_read）
4. **7.4 删表 + 删 API + 删 job**（migration 038 / 删 6 个内部 agent 端点 / 删 5 个 agent job）
5. **7.5 MCPSettingsCard 组件**（SettingsPage 内嵌 + 13 tool 列表 + 复制配置）
6. **7.6 测试 + 文档**（8 个新测试 + docs/mcp_integration.md）

> **简化效果**: Phase 7 总耗时从原 ~7 天（含 Web 设置面板 / Cubox 双轨 / 进程管理）压缩到 **~3 天**（仅 MCP server + 清理 + 1 个设置卡片 + 测试）。Cubox 双轨由 §16.8 描述保留（local cache 保留 + manual sync 改由 MCP tool `trigger_cubox_sync`）。

---

## 13. 验收标准

| Phase | 门禁 | 详细 |
|-------|------|------|
| Phase 1 | 任一历史热点打开后显示自动提取的标签，标签选择器 AND 过滤正常 | — |
| Phase 2 | 新学概念创建后 24h 出现在复习队列，评分后间隔按 SM-2 延长 | — |
| Phase 3 | 新建规则后 60s 内匹配的文章触发告警，统一搜索 500ms 内返回跨层结果 | — |
| Phase 4 | 阅读 3 篇 AI 文章后 AI 分类权重提升，知识推荐侧栏显示相关条目 | — |
| Phase 5 (已废弃) | ~~Agent 启动后自动轮询，新文章 5min 内完成提取；收藏文章自动写入 knowledge/items/；KL 生命周期完整流转；kv_cache 命中率 > 80%~~ | v1.7.6 Option A 替代 |
| Phase 6 | Sync Bundle 包含 4 个新表，sm2 merge 取 due_at 早者，feature flag 默认值与 PRD §10.3 一致 | — |
| **Phase 7 (v1.7.6)** | **MCP server 启动后列出 13 个 tool，外部 AI Agent 通过 MCP 读写成功；删表迁移可重放；MCPSettingsCard 显示完整** | **详见 §16.11** |

### 13.1 性能预算

- 统一搜索 (100k items): P50 < 100ms, P95 < 500ms
- 自动提取 (单篇): 平均 < 500ms
- 告警评估 (单次): P95 < 200ms
- 标签过滤 (10k 文章): P50 < 50ms
- SM-2 复习查询: P50 < 20ms
- ~~Agent 任务写入: P50 < 50ms~~ (v1.7.6 移除)
- ~~kv_cache 命中率: > 80%~~ (v1.7.6 移除主动维护)
- **MCP tool 调用（读）**: P50 < 100ms, P95 < 500ms
- **MCP tool 调用（写）**: 同步直返, P95 < 100ms (Option A 简化, 不再走异步队列)
- **MCP stdio 启动**: < 1s
- **MCP SSE 握手**: < 500ms
- **Cubox 同步 (1000 卡片)**: < 60s (含 cubox-cli 调用)

---

## 14. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | FTS5 统一搜索性能不达标 | 中 | 高 | fallback: 各层独立搜索 + 前端合并 |
| 2 | 自动标签提取准确率低 | 中 | 中 | 置信度阈值 + 用户确认 |
| 3 | SM-2 复习队列冷启动 | 高 | 低 | 默认每天推送 3 条 |
| 4 | 隐式学习偏差 | 中 | 低 | weight 衰减上限 5%/day + 手动重置 |
| 5 | 告警规则太泛导致疲劳 | 中 | 中 | 默认空规则 + cooldown |
| 6 | 多表 JOIN 性能下降 | 低 | 高 | tags JSON 冗余字段 |
| 7 | 新增 9 个 scheduler job 影响采集 (v1.7.6 调整: agent_task_consumer 等 5 个移除) | 低 | 中 | ThreadPoolExecutor 隔离 |
| ~~8~~ | ~~Agent 轮询延迟导致任务堆积~~ | — | — | **v1.7.6 移除 (无内部 agent)** |
| ~~9~~ | ~~Agent 与 Hotspot 状态不一致~~ | — | — | **v1.7.6 移除 (无内部 agent)** |
| 10 | kv_cache 与文件系统不一致 | 低 | 低 | kv_cache 改为可选层，etags 不再强制使用；优先读 knowledge_items |
| 11 | **MCP transport 兼容性问题** (stdio vs sse 不同 agent 实现差异) | 中 | 中 | 双 transport 并行；sse 用 FastAPI 路由；stdio 用 mcp.server.stdio 入口；feature flag 控制 |
| 12 | **外部 AI Agent 写并发冲突** (多个 agent 同时改同一条目) | 中 | 高 | SQLite WAL + last_writer_wins；不维护 session 状态；写操作幂等；favorites.created_via 区分来源 |
| 13 | **MCP server 暴露在 0.0.0.0** 导致远程攻击 | 中 | 高 | 默认绑定 127.0.0.1；feature_mcp_server 默认 on 但 host 默认 127.0.0.1；启动日志打印监听地址；改 0.0.0.0 需手动 + warning log |
| 14 | **Cubox-cli 调用阻塞主进程** (subprocess 卡死) | 中 | 中 | 强制 timeout 60s；fallback 到本地缓存；scheduler 隔离执行 |
| ~~15~~ | ~~Agent 进程崩溃导致任务堆积~~ | — | — | **v1.7.6 移除 (无内部 agent, 进程由 AI Agent 自行管理)** |
| 16 | **fastapi-mcp 与现有中间件不兼容** | 低 | 中 | 中间件测试矩阵；fallback 手写 MCP server |
| 17 | **删表迁移丢数据** (knowledge_tasks 等 Phase 5 表) | 低 | 高 | 迁移前 audit 现有数据；knowledge_tasks 已知只含历史 hot_take_collect 残留；MVP 删除后保留 7 天快照 |
| 18 | **MCP tool schema 升级破坏 agent** | 中 | 中 | 工具版本号字段 (input_schema 加 `version` 字段) + 兼容层 |
| 19 | **外部 AI Agent 退出 / 卸载** 导致历史 MCP 配置残留 | 低 | 低 | 各 AI Agent 的 MCP 配置在用户自己的 settings.json，hotspot 不维护状态；卸载时 AI Agent 端清理即可 |
| 20 | **AI Agent 用户对 LLM 行为无感** (调 MCP 失败时 LLM 仍继续) | 中 | 中 | MCP tool 返回标准 error code + 详细 message，LLM 据此判断是否重试或降级 |

> **风险分组说明**: 1-10 为 v1.7 通用风险；11-20 为 v1.7.6 Phase 7 专项风险（Option A）。详细对策见 §16.12。

---

## 15. 术语表

| 术语 | 说明 |
|------|------|
| SM-2 | SuperMemo-2 间隔重复算法 |
| easiness | SM-2 轻松度因子 |
| 标签置信度 | 0-1，自动提取的可信度 |
| 认知模式 | 六种界面模式适配不同认知带宽 |
| 隐式学习 | 通过行为自动推断偏好 |
| FTS 统一视图 | 跨 5 层 SQL 视图 + FTS5 索引 |
| 离线间隔摘要 | 长时间未打开时自动生成 |
| 技术栈桥接 | 文章标签匹配个人项目 |
| 注意力热图 | 阅读时间分布可视化 |
| KL 生命周期 | Signal → Amplify:tagged → Amplify:linked → Amplify:complete → Generate |
| ~~Phase-locked polling~~ | **v1.7.6 移除** — hotspot 不再内置 agent 轮询 |
| KV 缓存层 | SQLite 中的可选缓存表 (`kv_cache`)，加速 LLM-Wiki 查询；v1.7.6 默认不主动维护 |
| ~~Task Queue~~ | **v1.7.6 移除** — 原 `tasks/pending/` 文件系统任务队列已清空；Option A 中 AI Agent 通过 MCP 直接同步读写 |
| ~~Agent Skill~~ | **v1.7.6 移除** — 原 Phase 5 Agent 执行的 LLM/正则/脚本结构化任务定义 |
| OKF | Original Knowledge Files — 以 .md 文件为源数据的知识存储范式 |
| LLM-Wiki 2.0 | 基于文件系统的 LLM 可读写知识库，支持 Obsidian 读取 |
| **MCP** | Model Context Protocol — Anthropic 主导的 LLM-to-data 协议标准 (Anthropic/OpenAI/MS/Google 共识) |
| **MCP Server** | 暴露工具给外部 LLM Agent 的服务，hotspot 通过 fastapi-mcp 实现 |
| **MCP Transport** | MCP 通信方式：stdio（本地，单进程）或 SSE/StreamableHTTP（HTTP，跨网络） |
| **外部 AI Agent** | 通过 MCP 协议调 hotspot 工具的 LLM Agent：Cursor / Claude Desktop / Workbuddy / Trae / Claude Code 等 |
| **MCP tool** | hotspot 暴露给 AI Agent 的可调用函数，v1.7.6 共 13 个（5 读 + 8 写，详见 §16.3） |
| **MCP 同步直返 (Option A)** | 读写 MCP tool 都同步直接返回结果，无内部 agent、无异步队列；与 Phase 5 双轨（读直返 + 写走队列）不同 |
| ~~MCP 双轨 (Phase 5)~~ | **v1.7.6 移除** — 原设计读直返 + 写走 knowledge_tasks 队列；Option A 统一为同步直返 |
| **MCPSettingsCard** | v1.7.6 新增前端组件，SettingsPage 内嵌：显示 MCP endpoint + 13 个 tool 列表 + 复制配置按钮 |
| **mcp_tool_registry** | v1.7.6 新增 SQLite 表，存储 13 个 tool 的元数据 (name / category / description / input_schema)，启动时 seeding |
| ~~内部 hotspot-agent~~ | **v1.7.6 移除** — 原 Phase 5 hotspot 自带的 `agent/cli.py` 进程已删除 |
| ~~Knowledge Tasks 队列~~ | **v1.7.6 移除** — 原 `knowledge/learning/tasks/pending/` + `knowledge_tasks` SQLite 表双存储的异步任务队列；migration 038 DROP |
| ~~MCP Session~~ | **v1.7.6 移除** — Option A 零状态，不维护 session 表（`mcp_tool_invocations` 表已删除；`mcp_sessions` 表在 Phase 5 中实际未建立） |
| **Cubox 双轨** | 轨 1 (保留): `cubox_auto_sync` job 每日 03:00 自动同步到本地缓存 (`backend/data/cubox/articles/`)；轨 2 (Option A 调整): 手动同步由 AI Agent 调 MCP tool `trigger_cubox_sync` 触发 |
| **Feature Flag** | 通过 `feature_{name}: bool` 配置 + `is_enabled(name)` 服务控制功能开关（v1.7 Phase 6 引入） |
| **created_via** | v1.7.6 新增 favorites 列，记录收藏来源（'ui' / 'mcp' / 'agent'），用于统计和调试 |
| **Option A** | hotspot 只暴露 MCP server 端，不内置 AI Agent runtime；LLM 推理全部在外部 AI Agent 中执行 |

---

## 17.1 事件-实体模型映射

### 17.1.1 映射关系

| SAG 概念层 | OKF 对应 (hotspot) | 存储实现 | 说明 |
|-----------|-------------------|----------|------|
| Chunk | item 的段落 | YAML chunks 字段 (新增) | 长文章按自然段落或标题分块 |
| Event (完整语义) | 整个 .md 文件 | items/{id}.md body | 每篇知识条目 = 一个语义完整的事件 |
| Entity (轻量索引) | concepts + tags + tech_stack + item_entities | SQLite item_entities 表 + concepts/ 目录 | 扁平化 entity_name + entity_type |
| 查询时动态超边 | SQL JOIN over item_entities | item_entities -> knowledge_items -> concepts | 查询时通过 shared entities 动态 JOIN |
| 原文证据可追溯 | source_url + chunks 元数据 | knowledge_items.source_url + chunks[].id | 引用时可定位到段落级 |

### 17.1.2 item_entities 表的实体类型

ENTITY_TYPES = {
    "concept": "知识概念 (如 zero-trust-architecture)",
    "tool": "工具/软件 (如 langchain, fastapi)",
    "vendor": "厂商/组织 (如 CrowdStrike, NIST)",
    "person": "人物 (如 Bruce Schneier)",
    "cve": "CVE 编号 (如 CVE-2026-12345)",
    "technique": "技术/方法 (如 prompt-injection)",
    "standard": "标准/规范 (如 NIST SP 800-207)",
    "event": "事件 (如 RSA Conference 2026)",
}

### 17.1.3 YAML chunks 字段定义

```yaml
# 在 knowledge/items/{id}.md 的 frontmatter 中 (可选，长文章使用)
chunks:
  - id: "chk_001"
    heading: "Introduction"
    summary: "背景介绍"
    char_start: 0
    char_end: 2340
  - id: "chk_002"
    heading: "Attack Vector"
    summary: "攻击路径分析"
    char_start: 2341
    char_end: 5678
    entities:
      - name: "prompt-injection"
        type: technique
      - name: "langchain"
        type: tool

entities:
  - name: "prompt-injection"
    type: technique
    confidence: 0.95
  - name: "langchain"
    type: tool
    confidence: 0.8
```

## 17.2 查询时动态超边实现

### 17.2.1 搜索流程

```
用户查询: "langchain vulnerability impact on supply chain"

步骤 1: 语义信号 (FTS5)
  -> FTS5 MATCH 查询
  -> 返回初筛结果集 A

步骤 2: 实体信号 (item_entities JOIN)
  -> SELECT DISTINCT item_entities.item_id
    FROM item_entities
    WHERE entity_name IN ('langchain', 'supply-chain', 'vulnerability')
    GROUP BY item_id
    HAVING COUNT(DISTINCT entity_name) >= 2
  -> 返回实体匹配结果集 B

步骤 3: 动态超边 JOIN (SAG 核心吸收)
  -> 以结果集 B 中 item_id 为种子，找共享相同 entity_name 的其他 items
  -> SELECT i2.* FROM item_entities e1
    JOIN item_entities e2 ON e1.entity_name = e2.entity_name
    JOIN knowledge_items i2 ON e2.item_id = i2.id
    WHERE e1.item_id IN (结果集 B)
    AND i2.lifecycle IN ('kl:publish', 'kl:structure')
    AND i2.id NOT IN (结果集 B)
  -> 返回相关扩展结果集 C (动态超边)

步骤 4: 合并 + 去重 + 排序
  -> UNION A + B + C
  -> 按 relevance_score 排序 (FTS5 rank + entity match count + recency)
  -> 返回 Top-K (默认 20)
```

### 17.2.2 与原有搜索的兼容

```python
# backend/services/search_service.py (v1.7.7 增强)
async def enhanced_search(q: str, options: dict = None) -> dict:
    if not options or not options.get('enable_dynamic_hyperedge', True):
        return await unified_search(q, options)

    fts_results = await _fts_semantic_search(q)
    entity_seeds = await _extract_entities_from_query(q)
    entity_results = await _entity_join_search(entity_seeds)
    hyperedge_results = await _dynamic_hyperedge_search(entity_results, depth=1)
    return _merge_results(fts_results, entity_results, hyperedge_results)
```

## 17.3 增量实体提取

### 17.3.1 提取流程

```
新 items 进入 kl:raw
  -> auto_extract job 触发 (本地规则提取)
    -> 正则提取器: CVE 编号、URL、邮箱
    -> 关键词提取器: 工具名、厂商名
    -> 分类器: domain/topic/type
    -> 写入 knowledge_items + item_entities
    -> KL lifecycle -> kl:refine

AI Agent 通过 MCP 补充提取 (高级)
  -> Agent 调 get_hotspot({hotspot_id}) 拿全文
  -> Agent LLM 分析 -> 提取实体列表
  -> Agent 调 update_knowledge_item({
      item_id,
      fields: {
        entities: [{name: "prompt-injection", type: "technique"}],
        lifecycle: "kl:refine"
      }
    })
  -> hotspot 写入 item_entities + 更新 lifecycle
```

## 17.4 采集层升级

### 17.4.1 三层采集架构

| 层 | 技术 | 适用场景 | LLM 需求 |
|---|------|---------|---------|
| L1 传统爬虫 | requests + BeautifulSoup | RSS 源、简单 HTML | 不需要 |
| L2 crawl4ai | crawl4ai + headless Chrome | 需 JS 渲染的页面、SPA | 不需要 |
| L3 crawl4ai+LLM | crawl4ai + LLM extraction | 复杂页面、需语义提取 | 需要 |
| L4 标讯 | 专用解析器 | 政府采购、招标信息 | 可选 |

### 17.4.2 LLM 配置示例

```json
{
  "id": "security-blogs",
  "source_type": "crawl",
  "llm_config": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key_env": "OPENAI_API_KEY",
    "prompt": "从HTML中提取文章标题、作者、发布时间、正文内容",
    "max_tokens": 4096
  }
}
```

## 17.5 Agent CLI 集成 (Hotspot -> Agent 方向)

### 17.5.1 命令行接口

```bash
$ hotspot-agent-cli run extract_tags     --params '{"item_id": "a1b2c3", "source_url": "https://..."}'

$ hotspot-agent-cli run analyze_cve     --params '{"cve_id": "CVE-2026-12345"}'

$ hotspot-agent-cli list-skills
$ hotspot-agent-cli status
```

### 17.5.2 内置 Skill

| Skill | 功能 | 调用的 MCP 工具 |
|-------|------|---------------|
| extract_tags | 实体/标签提取 | get_hotspot, update_knowledge_item |
| analyze_cve | CVE 影响分析 | search_knowledge, create_alert_rule |
| generate_digest | 自动摘要 | search_hotspots, mark_digest_read |
| tenders_match | 标讯匹配 tech_stack | search_knowledge, add_annotation |

## 17.6 定时轮询实现

### 17.6.1 Scheduler Jobs

```python
# Job 18: agent_poll_consumer
def agent_poll_consumer():
    configs = agent_poll_repo.get_due_configs()
    for cfg in configs:
        if _in_quiet_hours(cfg):
            continue
        result = subprocess.run(
            ["hotspot-agent-cli", "run", cfg.poll_mode,
             "--params", json.dumps({"source": cfg.agent_name})],
            capture_output=True, text=True, timeout=300
        )
        agent_poll_repo.update_last_poll(cfg.id)

# Job 19: crawl4ai_fetch
def crawl4ai_fetch():
    sources = collector_repo.get_enabled_crawl4ai_sources()
    for source in sources:
        results = crawl4ai_collector.fetch(source)
        for r in results:
            hotspot_repo.insert(r)
```

### 17.6.2 延迟分析

| 事件 | 延迟 | 瓶颈 |
|------|------|------|
| 新文章采集 -> kl:raw | ~5min (采集周期) | 采集频率 |
| kl:raw -> Agent 提取 | 30min (默认轮询间隔) | Agent CLI + LLM |
| kl:refine -> 用户可见 | < 1min | 无瓶颈 |
| 告警触发 (CVE) | < 60s | 规则评估 |

---

## 17.7 实施任务清单

| Task | 周期 | 文件 |
|------|------|------|
| **7.7 SAG 吸收: 事件-实体模型** | | |
| 7.7.1 新增 item_entities 表 | 0.5h | migrations/041 |
| 7.7.2 新增 collector_sources 表 | 0.5h | migrations/042 |
| 7.7.3 新增 agent_poll_config 表 | 0.5h | migrations/043 |
| 7.7.4 SAG -> KL lifecycle 迁移 | 0.5h | migrations/044 |
| 7.7.5 sag_service.py -> kl_service.py 重命名 | 0.5h | backend/services/kl_service.py |
| 7.7.6 item_entities 提取器 (本地规则) | 1h | backend/services/entity_extractor.py |
| 7.7.7 动态超边搜索增强 | 2h | backend/services/search_service.py |
| 7.7.8 YAML chunks 字段支持 | 1h | backend/services/knowledge_sync.py |
| **7.8 采集层升级** | | |
| 7.8.1 基础 crawl4ai 集成 | 2h | backend/collectors/crawl4ai_collector.py |
| 7.8.2 LLM 辅助提取集成 | 1h | backend/collectors/llm_extract.py |
| 7.8.3 标讯采集器 | 2h | backend/collectors/tenders_collector.py |
| 7.8.4 collector_sources 管理 API | 1h | backend/api/collector_sources.py |
| **7.9 Agent CLI 集成** | | |
| 7.9.1 Agent CLI 入口 | 1h | backend/agent/cli.py |
| 7.9.2 内置 Skill: extract_tags | 1h | backend/agent/skills/extract_tags.py |
| 7.9.3 内置 Skill: analyze_cve | 1h | backend/agent/skills/analyze_cve.py |
| 7.9.4 agent_poll_consumer job | 1h | backend/scheduler/jobs.py |
| **7.10 测试** | | |
| 7.10.1 test_item_entities.py | 1h | backend/tests/ |
| 7.10.2 test_kl_lifecycle.py | 1h | backend/tests/ |
| 7.10.3 test_crawl4ai_collector.py | 1h | backend/tests/ |
| 7.10.4 test_agent_cli.py | 1h | backend/tests/ |
| 7.10.5 test_dynamic_hyperedge.py | 1h | backend/tests/ |

**总估算**: ~20 小时 (~3 工作日)

---

## 17.8 术语补充

| 术语 | 说明 |
|------|------|
| KL 生命周期 | Knowledge Lifecycle, 原名 SAG。五阶段: kl:raw -> kl:refine -> kl:link -> kl:structure -> kl:publish |
| 事件-实体模型 | 每个 .md item = 事件; item_entities 表 = 实体索引。查询时 SQL JOIN 构建动态超边 |
| 查询时动态超边 | 查询时通过 item_entities shared entity_name SQL JOIN 即时发现关联 items |
| item_entities | 实体索引表, entity_name + entity_type, 由本地规则 + AI Agent 联合维护 |
|crawl4ai | 高阶爬虫, 支持 headless Chrome + LLM 语义提取 |
| Agent CLI | hotspot-agent-cli 命令行工具, hotspot 通过它调用 Agent Skill |
| 双向生产环 | Agent -> Hotspot (MCP) + Hotspot -> Agent (CLI), 形成知识复利 |

