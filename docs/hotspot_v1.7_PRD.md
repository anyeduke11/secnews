# 热点地图 · v1.7 产品需求文档（完整版）

> **版本**: v1.7
> **日期**: 2026-07-22
> **定位**: hotspot v1.7 — 从"信息平台"升级为"主动认知协作者"
> **基线**: v1.6 (CodeGarden Phase2b 完成)
> **关联文档**: [ARCHITECTURE.md](../ARCHITECTURE.md) · [SPEC.md](./SPEC.md) · [CodeGarden_PRD_v2.0.md](./CodeGarden_PRD_v2.0.md) · [AGENTS.md](../AGENTS.md)
> **本版核心**: 基于第一性原理弥补"信息→知识→行动"链路上 4 个断裂环节，引入 Hotspot ↔ Agent 双向环架构，以 OKF + LLM-Wiki 2.0 统一知识存储范式

---

## 目录

0. [版本概述](#0-版本概述)
1. [用户旅程分析](#1-用户旅程分析)
2. [架构总览](#2-架构总览)
3. [数据模型变更](#3-数据模型变更)
4. [API 设计](#4-api-设计)
5. [Agent 协议与任务队列](#5-agent-协议与任务队列)
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

---

## 0. 版本概述

### 0.1 解决的问题

v1.6 完成了从"热点聚合"到"工作站"的跨越（项目、服务、资源、编排），但在**信息→知识→行动**的核心工作流上仍存在断裂。用户每天面对 50-200 篇文章，却缺少筛选决策支持、知识自动提取、内化复习机制和行动触发。v1.7 的目标是补齐这些断裂点，并引入 Agent 作为认知协作者，形成 Hotspot ↔ Agent 双环生产/消费架构。

> **一句话定位**: 让系统从"被动信息仓库"变成"主动认知协作者"

### 0.2 核心原则

1. **减少认知摩擦**：每新增一个功能都自问"这能减少用户一次决策吗？"
2. **自动化优先**：能自动做的不让用户手动做（提取、推理、推送）
3. **在场不在野**：知识应该在用户需要的位置出现，而不是在知识库页面里等着
4. **渐进式个性化**：系统通过隐式信号学习用户偏好，不需要用户填写兴趣表单
5. **本地优先，零外部依赖**：所有功能在本地可运行，不依赖外部服务
6. **Agent 即协作者，非替代品**：Agent 辅助用户，不替代用户的判断

### 0.3 v1.6 -> v1.7 变化矩阵

| 维度 | v1.6 (当前) | v1.7 (目标) |
|------|------------|------------|
| 信息筛选 | 5-8 个互斥分类 | 多维标签体系 + AND/OR 查询 |
| 知识摄入 | 手动收藏 + 手动提取 | 自动提取关键词/概念/实体 |
| 知识内化 | 无复习机制 | SM-2 间隔重复 + 自动衰减 |
| 知识->行动 | 无主动桥接 | 技术栈匹配 -> 项目影响评估 |
| 信息触达 | 仅 PULL (用户主动打开) | PULL + PUSH (规则引擎告警) |
| 搜索 | 各层独立搜索 | 一次查询穿透所有 5 层 |
| 交互模式 | 单一主页视图 | 简报/扫描/深度/整理/复习/告警 六种模式 |
| 个性化 | 无 | 隐式行为学习 + 阅读状态追踪 |
| 失效反馈 | 无 | 数据源完整性仪表盘 |
| 知识在场 | 在知识库页面 | 上下文感知推荐 |
| **Agent 架构** | **无 Agent** | **Hotspot ↔ Agent 双向环** |
| **知识存储** | SQLite 双存储 (favorites + knowledge) | **OKF + LLM-Wiki 2.0 统一** |
| **生命周期** | compiled: bool | **SAG 五阶段状态机** |
| **缓存层** | 无 | **SQLite KV 缓存层** |
| **任务队列** | 无 | **tasks/pending/ 异步协议** |
| **CLI 工具层** | 独立脚本 | **与 Agent 整合** |

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
| 提取(Understanding) | 完全手动阅读 | 自动实体/概念/标签提取 | P0 |
| 关联(Contextualization) | 绝对孤岛 | 跨层搜索+上下文推荐+项目桥接 | P1 |
| 评估(Decision) | 无主动告警 | 规则引擎+PUSH+影响分析 | P1 |
| 行动(Action) | 仅有 Todo | 信息->任务自动桥接 | P1 |
| 内化(Internalization) | 读完就忘 | SM-2 间隔复习+笔记 | P2 |

**v1.7 的核心目标**: 补齐这 6 个环节，使认知链路完整可运行。

### 0.5 架构升级总览

**v1.6 架构**（线性管道）:
```
Source → Collector → Hotspot DB → User → (手动操作) → Knowledge(.md)
```

**v1.7 架构**（双向环）:
```
Source → Collector → Hotspot DB → Knowledge(.md) → Obsidian
  ↑                        ↕                        ↕
Agent(CLI) ←──────── Hotspot API ←────────── Agent(Task Queue)
  ↑                        ↕
Skills ──────────────── Task Queue
```

**关键变化**: 不再是线性管道，而是 Hotspot 和 Agent 互相生产、互相消费的环形架构。Agent 通过 Skill 执行任务并将结果写回 Hotspot，Hotspot 通过 Task Queue 向 Agent 派发任务。

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
| **knowledge** | 提取的概念自动关联 knowledge_items，SAG 生命周期驱动 |
| **codegarden** | tech_stack 桥接 cg_projects，告警影响分析 |
| **security_graph** | 关联的 CVE 实体注入知识推荐 |
| **sync_bundle** | reading_states + annotations 跨端同步 |
| **weekly_report** | digest 作为周报输入素材 |
| **obsidian** | 直接读取 knowledge/items/ 目录，LLM-Wiki 2.0 格式 |
| **agent (CLI)** | 读取 tasks/pending/ 执行任务，写回 Hotspot API |

---

## 2. 架构总览

### 2.1 v1.7 架构核心：Hotspot ↔ Agent 双向环

```
 +----------------------------------------------------------+
 |                     Hotspot 平台                           |
 |  +------------------+  +-------------------------------+  |
 |  |   采集层          |  |   知识引擎层                   |  |
 |  |  RSS / Crawler   |  |  自动提取 / 标签 / 推荐        |  |
 |  |  Cubox / Bookmark |  |  SM-2 复习 / 告警             |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             |                   |
 |  +--------v---------+  +--------------v----------------+  |
 |  |   SQLite 主存储    |  |   LLM-Wiki 2.0 / OKF 目录    |  |
 |  |   (37 表, WAL)    |  |   knowledge/ 为源数据         |  |
 |  |   + KV 缓存层     |  |   可读写，结构兼容           |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             |                   |
 |  +--------v---------+  +--------------v----------------+  |
 |  |   API 层          |  |   Task Queue                  |  |
 |  |   REST / SSE      |  |   tasks/pending/ 目录         |  |
 |  +--------+---------+  +--------------+----------------+  |
 |           |                             ↑                   |
 +-----------|-----------------------------|-------------------+
             |                             |
             |   HTTP API / FSWatch        | 文件系统监视
             |                             |
 +-----------v-----------------------------|-------------------+
 |  Agent (CLI)                     Scheduler (APScheduler)   |
 |  +------------------+            +---------------------+  |
 |  |  Skill 执行引擎    |            | hot_take_collect    |  |
 |  |  (读取 tasks/pending) |         | auto_extract        |  |
 |  |  调用 Hotspot API  |            | review_scheduler    |  |
 |  |  写回 .md 文件     |            | alert_evaluator     |  |
 |  +--------+---------+            | ... (17+ jobs)      |  |
 |           |                       +---------------------+  |
 |  +--------v---------+                                      |
 |  |  CLI 工具层       |                                      |
 |  |  cubox-sync      |                                      |
 |  |  bookmark-import  |                                      |
 |  |  knowledge-tasks  |                                      |
 |  +------------------+                                      |
 +----------------------------------------------------------+
      ↑
      |
 +----+----+
 |  Skills  |
 | (Skill   |
 |  配置、   |
 |  API 密钥)|
 +---------+
```

### 2.2 双向环数据流

```
Hotspot → Agent 方向（Hotspot 生产，Agent 消费）:
  Hotspot 采集到新文章
    → 写入 hotspots/favorites 表
    → 触发 SAG lifecycle: signal
    → 写入 tasks/pending/ 目录
    → Agent 轮询发现新任务
    → 执行 Skill (提取、分析、关联)
    → 结果写回 Hotspot API

Agent → Hotspot 方向（Agent 生产，Hotspot 消费）:
  Agent 执行 Skill 得到新知识
    → 调用 Hotspot API (POST /api/agent/knowledge)
    → 写入 knowledge/items/ 目录 + 更新 lifecycle
    → 触发知识关联、自动提取
    → 用户通过 Obsidian/dashboard 阅读
    → 用户反馈 (收藏/笔记/评分) 回到 Hotspot
    → Hotspot 更新 tasks/pending/ 触发后续 Agent 任务
```

### 2.3 SAG 生命周期状态机

替换 `compiled: bool`，引入五阶段生命周期：

```
                     ┌─────────────┐
                     │   signal    │ (初始状态: 刚采集到)
                     └──────┬──────┘
                            │
                     ┌──────v──────┐
                     │amplify:     │ (已标记/打标签)
                     │ tagged      │
                     └──────┬──────┘
                            │
                     ┌──────v──────┐
                     │amplify:     │ (已关联到知识图谱)
                     │ linked      │
                     └──────┬──────┘
                            │
                     ┌──────v──────┐
                     │amplify:     │ (信息已完备)
                     │ complete    │
                     └──────┬──────┘
                            │
                     ┌──────v──────┐
                     │  generate   │ (已生成知识条目)
                     └─────────────┘
```

**生命周期转移规则**:
- `signal` → `amplify:tagged`: 自动标签提取完成，或用户手动标记
- `amplify:tagged` → `amplify:linked`: 概念关联完成，知识图谱节点已创建
- `amplify:linked` → `amplify:complete`: 关联信息已完备，上下文已建立
- `amplify:complete` → `generate`: 知识条目已生成到 knowledge/items/
- 所有阶段均支持手动回退：`generate` → `amplify:complete`（如用户修改后重新处理）

### 2.4 OKF + LLM-Wiki 2.0 统一存储

**核心原则**: LLM-Wiki 2.0 的 `.md` 文件是知识资产的源数据（single source of truth），SQLite 是 KV 缓存层 + 查询加速层，用于加速查询。

**目录结构（保持不变）**:
```
knowledge/
├── _MAP.md              ← 知识地图（自动生成索引）
├── _SCHEMA.md           ← 数据模型合约
├── SOUL.md              ← 角色画像（Agent 自动生成）
├── items/               ← L1: 知识条目 (*.md with YAML frontmatter)
│                           lifecycle: signal | amplify:tagged | ... | generate
│                           tags, tech_stack, concepts 在 frontmatter
├── concepts/            ← L2: 提取的概念
├── learning/            ← L3: 学习计划 + 进度
│   └── tasks/
│       ├── pending/     ← Agent 任务队列（Hotspot 写入，Agent 读取）
│       ├── processing/  ← Agent 正在处理
│       ├── done/        ← 已完成
│       └── failed/      ← 失败 + error.md
├── content/             ← L4: 内容创作
│   ├── drafts/
│   └── calendar.json
└── summaries/           ← 每周摘要
```

**v1.7 新增字段** (在 YAML frontmatter 中):
```yaml
---
id: "a1b2c3"
title: "Article Title"
source: "hotspot"
source_url: "https://..."
ingested_at: "2026-07-22T10:00:00Z"
lifecycle: "amplify:tagged"        # signal | amplify:tagged | amplify:linked | amplify:complete | generate
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

**用途**: 加速 LLM-Wiki 查询，避免频繁读取文件系统。

**表结构**:
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

**缓存策略**:
- 读取 `knowledge/items/*.md` 时，先将内容解析为 JSON 缓存到 kv_cache
- 缓存键: `item:{id}`, `items:list`, `items:by_tag:{tag}`, `fts:index`
- 文件变化时更新 etag，标记缓存失效
- 过期时间: list 30s, single item 60s, fts 5min
- 缓存缺失时自动回退到文件系统读取

**与现有表的关系**:
- `knowledge_items` 表 → 保留作为 SQLite 层的查询入口
- `kv_cache` → 新增的加速层，缓存 LLM-Wiki 目录解析结果
- 写入路径: 用户/Agent 写入 `.md` → FSWatch 感知 → 更新 `knowledge_items` + `kv_cache`
- 读取路径: 查询 → 查 `kv_cache` → 命中返回 → 未命中读 `knowledge_items` 或文件系统

### 2.6 Agent 架构

**Agent ≠ 通用 AI Agent**。这里的 Agent 是一个**结构化任务执行引擎**，通过读取 `tasks/pending/` 目录中的任务定义，执行对应的 Skill，并将结果写回。

**Agent 架构**:
```
Agent (CLI)
  ├── Task Queue Watcher (轮询 tasks/pending/ + Hotspot API)
  ├── Skill Executor (读取 Skill 配置，执行 LLM 调用)
  ├── Hotspot API Client (写回结果)
  ├── CLI Tool Layer (cubox, bookmark, knowledge-tasks)
  └── Config (skill 配置、API 密钥、轮询间隔)
```

**核心原则**:
- Agent 不直接调度任务，Hotspot 通过 Task Queue 向 Agent 派发任务
- Skill 是 Agent 原生能力，不是 Hotspot 调度的一部分
- Hotspot 只存储 Skill 配置（ID、API 密钥、模型覆盖参数）
- Agent 执行结果写回 Hotspot API，Hotspot 更新生命周期

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
| 9 | **LLM-Wiki 2.0 为源数据** | 纯 SQLite 存储 | 支持 Obsidian 直接读取，Agent 可直接写入 .md |
| 10 | **Task Queue 基于文件系统** | 数据库任务表 | 与 LLM-Wiki 目录结构一致，Agent 无额外依赖 |
| 11 | **Agent 轮询**而非 Hotspot 推送 | WebSocket 推送 | 解耦 Agent 和 Hotspot 的生命周期 |
| 12 | **Phase-locked polling** | 固定间隔轮询 | 跟随采集节奏，避免 Agent 和 Hotspot 不同步 |
| 13 | **CLI 整合到 Agent** | 独立 CLI 工具 | 统一入口，减少用户心智负担 |
| 14 | **SAG 状态机** | compiled: bool | 提供更细粒度的生命周期管理，支持知识复利 |
| 15 | **KV 缓存层** | 直接读文件系统 | 加速查询，避免频繁 I/O |

### 2.8 显式不引入

| 技术 | 原因 |
|------|------|
| 外部搜索引擎 (ES/Meilisearch) | FTS5 + UNION ALL 跨表视图足够 100k 级检索 |
| 外部消息队列 (RabbitMQ/Redis) | 进程内 asyncio.Queue + 文件系统 Task Queue 足够单人场景 |
| 向量数据库 | 本地优先原则，FTS5 + 标签过滤 + 概念图谱覆盖所有搜索需求 |
| ML 模型服务 | 关键词提取用规则+本地，无需 GPU 或外部 API |
| 用户认证/多租户 | 单人本地使用 |
| WebSocket | SSE 单向推送 + 文件系统轮询足够，不需要双向实时通信 |
| 通用 AI Agent | 结构化任务执行引擎，仅执行预定义 Skill，不引入通用推理 |
| 外部云服务 | 所有数据本地存储，不依赖任何外部服务 |


---

## 3. 数据模型变更

### 3.1 SAG 生命周期迁移

**现有 `knowledge_items` 表** (migration 018_knowledge.sql) 变更:
```sql
-- 替换 compiled: bool 为 lifecycle: text
ALTER TABLE knowledge_items ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'signal';
ALTER TABLE knowledge_items ADD COLUMN news_type TEXT DEFAULT '';
ALTER TABLE knowledge_items ADD COLUMN tech_stack TEXT DEFAULT '[]';
-- 迁移现有数据: compiled=true → generate, compiled=false → amplify:complete
UPDATE knowledge_items SET lifecycle = 'generate' WHERE compiled = 1;
UPDATE knowledge_items SET lifecycle = 'amplify:complete' WHERE compiled = 0;
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

```sql
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
ALTER TABLE knowledge_items ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'signal';
ALTER TABLE knowledge_items ADD COLUMN news_type TEXT DEFAULT '';
ALTER TABLE knowledge_items ADD COLUMN tech_stack TEXT DEFAULT '[]';
-- 迁移现有数据
UPDATE knowledge_items SET lifecycle = 'generate' WHERE compiled = 1;
UPDATE knowledge_items SET lifecycle = 'amplify:complete' WHERE compiled = 0;

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
    +-- favorites (favorited → knowledge/items/ promotion)
    +-- extract (自动提取触发 lifecycle)

knowledge_items --< tags (via YAML frontmatter)
    |               
    +-- lifecycle: SAG 状态机
    +-- concepts (提取)
    +-- tech_stack (关联)
    +-- sm2_reviews (item_type='knowledge')
    +-- annotations (entity_type='knowledge')
    +-- kv_cache (缓存 layer)

kv_cache -- 缓存 knowledge_items 和目录解析结果
    |              
    +-- 键: item:{id}, items:list, items:by_tag:{tag}

alert_rules --> cg_events (已存在)
personal_profile (独立, key-value)
tech_stack --> cg_projects (tech_stack_ids)
digests (独立, 快照)

tasks/pending/ (文件系统, 非 SQLite)
  └── 任务格式: Markdown with YAML frontmatter
  └── Agent 读取, 处理, 移动到 done/ 或 failed/
```

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

#### Phase 5: Agent 通信（3 个）

| Method | Path | 请求参数 | 说明 |
|--------|------|----------|------|
| GET | /api/agent/tasks | ?status=pending&limit=10 | Agent 获取任务列表 |
| POST | /api/agent/knowledge | { item_id, content, lifecycle, ... } | Agent 写回知识条目 |
| POST | /api/agent/tasks/{id}/complete | { status, result, error? } | Agent 标记任务完成 |

**Agent 通信端点详细说明**:

**GET /api/agent/tasks**
- 用途: Agent 轮询获取待处理任务
- 返回: `{ "tasks": [ { "id": "...", "type": "extract", "target_id": "...", "params": {}, "created_at": "..." } ], "cursor": "..." }`
- 行为: 返回 tasks/pending/ 目录中的任务列表，按创建时间排序
- 缓存: 不缓存，每次返回最新任务

**POST /api/agent/knowledge**
- 用途: Agent 将处理结果写回知识库
- 请求体: `{ "item_id": "a1b2c3", "content": "...", "lifecycle": "amplify:linked", "tags": ["ai", "security"], "concepts": ["prompt-injection"], "tech_stack": ["langchain"] }`
- 行为: 写入 knowledge/items/ 目录 + 更新 SQLite 中的 knowledge_items 表 + 更新 kv_cache
- 返回: `{ "success": true, "item_id": "a1b2c3", "path": "knowledge/items/a1b2c3.md" }`

**POST /api/agent/tasks/{id}/complete**
- 用途: Agent 标记任务完成
- 请求体: `{ "status": "done" | "failed", "result": { "extracted_tags": [], "concepts": [] }, "error": "..." }`
- 行为: 将任务从 pending/ 移动到 done/ 或 failed/，写回结果文件
- 返回: `{ "success": true }`

---

## 5. Agent 协议与任务队列

### 5.1 任务队列格式

任务存储在 `knowledge/learning/tasks/pending/` 目录中，每个任务是一个 Markdown 文件，使用 YAML frontmatter 描述任务元数据。

```yaml
---
task_id: "task-20260722-001"
type: "extract"               # extract | analyze | link | generate | review
status: "pending"
created_at: "2026-07-22T10:00:00Z"
target_type: "hotspot"        # hotspot | favorite | knowledge
target_id: "a1b2c3"
priority: 1                   # 1-5, 5 最高
source: "hotspot-api"         # hotspot-api | scheduler | user
params:
  model: "gpt-4o-mini"        # 可选，覆盖默认模型
  skill_id: "extract-tags"    # 可选，指定 Skill
---
```

**任务类型说明**:

| type | 触发时机 | Agent 执行动作 | 写回结果 |
|------|----------|---------------|----------|
| extract | 新文章入库 | 调用 Skill 提取标签/概念/技术栈 | POST /api/agent/knowledge |
| analyze | 文章收藏后 | 调用 Skill 深度分析，生成摘要 | POST /api/agent/knowledge |
| link | 概念提取后 | 调用 Skill 关联知识图谱 | POST /api/agent/knowledge |
| generate | 信息完备后 | 调用 Skill 生成知识条目 .md | POST /api/agent/knowledge |
| review | 定时触发 | 调用 Skill 评估知识质量 | POST /api/agent/tasks/{id}/complete |

### 5.2 Agent 轮询协议

**Phase-locked polling**（相位锁定轮询）:

```
Agent 启动:
  1. 读取 Hotspot 配置: GET /api/config (获取 collect_interval_seconds)
  2. 设置轮询间隔 = collect_interval_seconds (默认 300s)
  3. 启动轮询循环

轮询循环:
  while True:
    1. 调用 GET /api/agent/tasks?status=pending&limit=10
    2. 如果 tasks 非空:
       for task in tasks:
         执行对应的 Skill
         调用 POST /api/agent/tasks/{id}/complete
    3. 如果 tasks 为空:
       调用 GET /api/hotspots?lifecycle=signal&limit=10 (检查新热点)
       if 有新热点:
         创建本地任务
         处理完成后调用 POST /api/agent/knowledge
    4. sleep(轮询间隔)
```

**轮询间隔配置**:
- 默认: 跟随 Hotspot 的 `collect_interval_seconds` (300s)
- 可自定义: 通过 `HOTSPOT_AGENT_POLL_INTERVAL` 环境变量或 `agent_config.yaml`
- 时间片优先级: 短任务优先（如 `extract` < 30s），长任务（如 `generate` > 2min）延迟到低峰期

**延迟考量**:
- 最大延迟: 轮询间隔 + 处理时间 + 网络延迟
- 默认 300s 轮询下，最大延迟约 5.5min
- 如果 Agent 和 Hotspot 在同一台机器，延迟可忽略
- 长任务 (generate) 可能延迟 2-5 轮，可通过优先级调整

**弊端与对策**:

| 弊端 | 影响 | 对策 |
|------|------|------|
| 轮询间隔内任务堆积 | 高并发时延迟增加 | 调整轮询间隔更短 (60s)，或增加 Agent 并发处理数 |
| Agent 宕机导致任务积压 | 任务在 pending/ 堆积 | 重启时优先处理 pending/ 中的任务 |
| 长任务阻塞短任务 | 短任务延迟增加 | 引入时间片优先级，长任务 defer 到低峰期 |
| 轮询频率过高浪费资源 | 空轮询消耗 CPU | 动态调整轮询间隔（任务多时缩短，空时延长） |
| 任务状态不一致 | 任务已完成但状态未更新 | 引入幂等性，任务完成时校验状态 |

### 5.3 Agent Skill 配置

Skill 配置存储在 SQLite 中（`skill_config` 表），Agent 启动时读取。

```json
{
  "id": "extract-tags",
  "name": "标签提取器",
  "description": "从文章内容中提取标签、概念、技术栈",
  "type": "llm",
  "config": {
    "model": "gpt-4o-mini",
    "temperature": 0.1,
    "max_tokens": 1000,
    "prompt_template": "从以下文章内容中提取技术标签、概念和技术栈...",
    "output_format": {
      "tags": ["string"],
      "concepts": ["string"],
      "tech_stack": ["string"]
    }
  },
  "target_types": ["hotspot", "favorite"],
  "created_at": "2026-07-22T00:00:00Z"
}
```

**Skill 类型**:
- `llm`: 调用 LLM 进行文本处理（提取、分析、生成）
- `regex`: 本地正则匹配（不需要 LLM）
- `hybrid`: 先正则后 LLM 补充
- `script`: 执行本地脚本（如 cubox-cli）

### 5.4 Hotspot ↔ Agent 互相调用关系

```
+------------------+                    +------------------+
|     Hotspot      |                    |     Agent        |
+------------------+                    +------------------+
|                  |                    |                  |
| 1. 采集新文章     |                    | 1. 启动轮询       |
| 2. 写入 SQLite   |                    | 2. 读取任务队列   |
| 3. 写入 tasks/   | ←── 文件系统 ────  | 3. 执行 Skill     |
|    pending/     |                    | 4. 调用 API 写回  |
| 4. 更新 lifecycle|                    | 5. 标记任务完成   |
| 5. 通知用户      | ──── API ──────→  |                  |
|                  |                    |                  |
| 6. 接收 Agent    | ←── API ────────  | 6. Agent 生产     |
|    写回数据      |                    |    新知识条目     |
| 7. 更新 lifecycle|                    | 7. 生成 tasks/   |
| 8. 触发后续任务   | ──── 文件系统 ──→  |    pending/ 任务  |
| 9. 通知用户      |                    |                  |
+------------------+                    +------------------+
```

**时序示例（新文章采集 → Agent 提取 → 知识入库）**:

```
Hotspot:                   Agent:
  |                         |
  |-- 采集到新文章 ----------|
  |-- 写入 SQLite ----------|
  |-- 写入 tasks/pending/ --|
  |-- lifecycle: signal ----|
  |                         |-- 轮询: GET /api/agent/tasks
  |                         |-- 读取任务: extract, target_id=a1b2c3
  |                         |-- 执行 Skill: 提取标签/概念
  |                         |-- 调用: POST /api/agent/knowledge
  |-- 接收: 更新 lifecycle ---|
  |-- lifecycle: amplify:tagged
  |-- 写入 tasks/pending/ --|  (下一轮: link 任务)
  |                         |-- 轮询: 读取 link 任务
  |                         |-- 执行 Skill: 关联知识图谱
  |                         |-- 调用: POST /api/agent/knowledge
  |-- 接收: 更新 lifecycle ---|
  |-- lifecycle: amplify:linked
  |-- 写入 tasks/pending/ --|  (下一轮: generate 任务)
  |                         |-- 轮询: 读取 generate 任务
  |                         |-- 执行 Skill: 生成知识条目 .md
  |                         |-- 调用: POST /api/agent/knowledge
  |-- 接收: 更新 lifecycle ---|
  |-- lifecycle: generate
  |-- 知识条目写入 knowledge/items/
  |-- 通知用户: 新知识已生成
  |                         |
```

### 5.5 CLI 与 Agent 整合

**CLI 工具层直接整合到 Agent**，以 Agent 的子命令形式存在：

```
hotspot-agent                  # Agent 主入口
  ├── agent start              # 启动 Agent 轮询
  ├── agent stop               # 停止 Agent
  ├── agent status             # 查看 Agent 状态
  ├── agent tasks              # 查看任务队列
  │
  ├── skill list               # 查看可用 Skill
  ├── skill run <id> <target>  # 手动执行 Skill
  │
  ├── cubox sync               # 同步 Cubox 收藏
  ├── bookmark import <file>   # 导入浏览器书签
  ├── knowledge export <id>    # 导出知识条目
  │
  ├── config show              # 查看配置
  ├── config set <key> <value> # 设置配置
  │
  └── -h, --help               # 帮助
```

**CLI 与 Hotspot API 的交互**:
- `cubox sync` → Hotspot API (POST /api/cubox/sync)
- `bookmark import` → Hotspot API (POST /api/bookmark/import)
- `knowledge export` → Hotspot API (GET /api/knowledge/export)

**CLI 整合原则**:
- Agent 是 CLI 的入口，所有工具操作都通过 Agent 的子命令调用
- Agent 内部维护一个 HTTP 客户端，与 Hotspot API 通信
- CLI 工具不需要独立的数据库连接，全通过 API 层
- 用户可以通过 `hotspot-agent cubox sync` 手动触发同步，也可以由 Agent 轮询自动触发

---

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

### 6.12 M12: 收藏→知识提升（全天候）

**用户故事**: 收藏一篇文章后，系统自动将其写入 knowledge/items/ 目录，触发 SAG 生命周期，Agent 自动提取标签和概念。

**流程**:
```
用户收藏文章
  → 写入 favorites 表
  → 创建 knowledge/items/{id}.md (YAML frontmatter + 原文链接)
  → 触发 SAG lifecycle: signal
  → 写入 tasks/pending/ 任务
  → Agent 轮询获取任务
  → 执行提取 Skill
  → 写回结果，更新 lifecycle → amplify:tagged
  → 用户可直接在 Obsidian 中阅读和编辑
```

---

## 7. 调度器变更

### 7.1 新增 job（10 个）

| Job | 频率 | 职责 | 优先级 |
|-----|------|------|--------|
| auto_extract | 采集完成后触发 | 为新增文章自动提取标签/概念/技术栈 | 高 |
| review_scheduler | 每 6h | 查询 sm2_reviews.next_review_at | 中 |
| alert_evaluator | 每 60s | 评估新文章是否匹配告警规则 | 高 |
| profile_updater | 每 30min | 更新 personal_profile 权重 | 低 |
| digest_generator | 每 24h (08:00) | 生成昨日简报 | 中 |
| source_health_check | 每 15min | 检查数据源采集覆盖率 | 中 |
| fts_rebuild | 每 5min | 重建 unified_fts 索引 | 低 |
| profile_decay | 每 24h (03:00) | 所有 weight 衰减 5% | 低 |
| **agent_task_consumer** | **每 60s** | **检查新文章，写入 tasks/pending/** | **高** |
| **kv_cache_cleanup** | **每 30min** | **清理过期 kv_cache** | **低** |

**agent_task_consumer 详细说明**:
- 职责: 检查新采集/收藏的文章，为其创建 Agent 任务并写入 tasks/pending/
- 逻辑:
  ```
  1. 查询 hotspots 或 favorites 中 lifecycle=signal 的记录
  2. 对于每条记录，创建 extract 任务写入 tasks/pending/{task_id}.md
  3. 更新记录状态为 task_created
  4. 避免重复创建（幂等性校验）
  ```

### 7.2 现有 job 修改

| 现有 Job | 修改内容 |
|----------|----------|
| collection_service | 采集完成后触发 agent_task_consumer，而非仅更新数据库 |
| knowledge_watcher | 增加对 knowledge/items/ 目录的 FSWatch，更新 kv_cache |

---

## 8. 前端组件与路由

### 8.1 新增组件

| 组件 | 用途 | 父组件 |
|------|------|--------|
| SourceHealthBar | 数据源状态条 | PageLayout (顶部) |
| AlertBanner | 告警横幅 | PageLayout (顶部) |
| BriefModeView | 简报模式 | MainView |
| DeepReadView | 深度阅读模式 | MainView |
| ArticlePanel | 文章正文区 | DeepReadView |
| RecommendationSidebar | 推荐侧栏 | DeepReadView |
| NotePanel | 笔记输入 | DeepReadView |
| OrganizeView | 整理模式 | MainView |
| AlertCenter | 告警中心 | 独立页面 /alerts |
| ReviewPage | 复习页面 | 独立页面 /reviews |
| TechStackPage | 技术栈管理 | 独立页面 /tech-stack |
| TagsPage | 标签管理 | 独立页面 /tags |
| ProfilePage | 个性化画像 | 独立页面 /profile |
| AgentStatusBadge | Agent 状态指示 | PageLayout (顶部) |

### 8.2 路由变更

| 路由 | 页面 | 懒加载 |
|------|------|--------|
| / | 简报/扫描(自适应) | 否 |
| /deep/:type/:id | 深度阅读 | 是 |
| /organize | 整理模式 | 是 |
| /alerts | 告警中心 | 是 |
| /reviews | 复习页面 | 是 |
| /tech-stack | 技术栈管理 | 是 |
| /tags | 标签管理 | 是 |
| /profile | 个性化画像 | 是 |

### 8.3 共享组件

| 组件 | 用途 | 复用场景 |
|------|------|---------|
| TagSelector | 多选标签选择器 | 首页筛选，告警规则配置，搜索过滤 |
| TagPill | 标签 pill 展示 | 卡片列表，筛选栏，告警详情 |
| ReviewCard | 卡片翻转 UI | 复习页面，深度阅读中主动复习 |
| NoteEditor | 简化 Markdown 编辑器 | 笔记区，告警备注 |
| AlertBadge | 告警角标 | 导航栏，首页 |
| SourceHealthIndicator | 数据源状态指示灯 | 首页源状态条，设置页 |
| ModeSwitcher | 模式切换按钮组 | 顶部导航栏 |

### 8.4 Hooks 新增

| Hook | 用途 |
|------|------|
| useTags() | 标签列表 + 筛选状态 |
| useExtraction() | 自动提取 + 待确认管理 |
| useReviews() | 复习队列 + 评分提交 |
| useAlerts() | 告警列表 + SSE 实时推送 |
| useSearch() | 统一搜索 (debounced，跨层) |
| useProfile() | 个性化画像读取 + 手动调整 |
| useMode() | 当前模式 + 模式切换 |
| useAnnotations(type, id) | 笔记 CRUD |
| useSourceHealth() | 数据源健康状态 |

---

## 9. 跨端同步变更

| 表 | 冲突策略 |
|----|---------|
| reading_states | last_writer_wins (updated_at) |
| annotations | last_writer_wins (updated_at) |
| tags | cascade |
| sm2_reviews | merge (取 next_review_at 更近的) |
| kv_cache | 不跨端同步（本地缓存，各端独立） |

**同步说明**:
- `knowledge/items/` 目录中的 `.md` 文件通过 Obsidian 同步（如 Obsidian Sync、iCloud、Git）
- `kv_cache` 是本地缓存，不参与跨端同步，各端独立重建
- Agent 任务队列 (`tasks/pending/`) 是本地文件，不跨端同步

---

## 10. 迁移策略

### 10.1 数据库迁移

| 序号 | 文件 | 内容 |
|------|------|------|
| 024 | 024_v1.7_tags.sql | tags + hotspot_tags 表 |
| 025 | 025_v1.7_reading_states.sql | reading_states 表 |
| 026 | 026_v1.7_sm2_reviews.sql | sm2_reviews 表 |
| 027 | 027_v1.7_annotations.sql | annotations 表 |
| 028 | 028_v1.7_alert_rules.sql | alert_rules 表 |
| 029 | 029_v1.7_tech_stack.sql | tech_stack 表 |
| 030 | 030_v1.7_personal_profile.sql | personal_profile 表 |
| 031 | 031_v1.7_digests.sql | digests 表 |
| 032 | 032_v1.7_kv_cache.sql | kv_cache 表 |
| 033 | 033_v1.7_unified_fts.sql | unified_fts 视图+虚拟表 |
| 034 | 034_v1.7_alter_existing.sql | 现有表新增字段: lifecycle, tags, tech_stack, last_read_at |
| 035 | 035_v1.7_migrate_compiled.sql | 迁移 compiled -> lifecycle |

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

| 阶段 | 开关 | 默认 |
|------|------|------|
| Phase 1 标签 | feature.tags | on |
| Phase 1 提取 | feature.auto_extract | on |
| Phase 2 复习 | feature.reviews | off (手动开通) |
| Phase 3 告警 | feature.alerts | off (手动开通) |
| Phase 3 搜索 | feature.unified_search | on |
| Phase 4 推荐 | feature.recommendations | off (手动开通) |
| Phase 4 笔记 | feature.annotations | on |
| Phase 4 个性化 | feature.personalization | off (手动开通) |
| Phase 5 Agent | feature.agent | off (手动开通) |

---

## 11. 测试策略

### 11.1 新增测试文件

| 文件 | 类型 | 覆盖 |
|------|------|------|
| test_tag_service.py | unit | tags CRUD + filter |
| test_extract_service.py | unit | 三层提取器 + 置信度 |
| test_review_service.py | unit | SM-2 公式 + 调度 |
| test_alert_service.py | unit | 条件匹配 + cooldown |
| test_search_service.py | integration | unified_fts 性能 |
| test_annotation_service.py | unit | CRUD |
| test_profile_service.py | unit | weight 计算 + 衰减 |
| test_source_health_service.py | unit | 状态判定 |
| test_tech_stack_bridge.py | integration | 跨模块桥接 |
| test_kv_cache_service.py | unit | 缓存读写 + 过期 |
| test_agent_protocol.py | integration | Agent 任务队列 + API 通信 |
| test_sag_lifecycle.py | unit | SAG 状态机转移 |
| test_v1.7_e2e.py | e2e | 全流程 |

### 11.2 前端测试

| 文件 | 覆盖 |
|------|------|
| TagSelector.test.tsx | 多选 + AND/OR |
| ReviewCard.test.tsx | 卡片翻转 + 评分 |
| DeepReadView.test.tsx | 全屏阅读 + 侧栏 |
| AlertCenter.test.tsx | 列表 + 标记已读 + SSE mock |
| UnifiedSearch.test.tsx | 输入防抖 + 跨层结果 |
| SourceHealthBar.test.tsx | 状态渲染 |
| v1.7_modes.test.tsx | 模式切换 + 路由 |

---

## 12. Phase 规划

| Phase | 名称 | 周期 | 模块 | 依赖 |
|-------|------|------|------|------|
| 1 | 标签与自动提取（核心基础设施） | ~5 天 | tags 表 + 提取器 + 标签 API | 无 |
| 2 | 内化与桥接 | ~5 天 | SM-2 复习 + 技术栈 + 笔记 | Phase 1 |
| 3 | 告警与统一搜索 | ~4 天 | 告警规则 + 统一搜索 + 模式切换 | Phase 1 |
| 4 | 智能与体验 | ~4 天 | 上下文推荐 + 隐式个性化 + 数据源健康 | Phase 1+2+3 |
| 5 | **Agent 集成与双向环** | **~5 天** | **Agent 协议 + 任务队列 + CLI 整合 + SAG 生命周期 + KV 缓存** | **Phase 1+2+3+4** |

**总预估**: ~23 天

**Phase 5 详细任务**:
1. 实现 agent_task_consumer job (写入 tasks/pending/)
2. 实现 Agent CLI 入口 (hotspot-agent 命令)
3. 实现 Agent 轮询协议 (phase-locked polling)
4. 实现 Agent Skill 配置和执行引擎
5. 实现 /api/agent/* 端点
6. 实现 SAG 生命周期状态机（替换 compiled: bool）
7. 实现 kv_cache 表和服务
8. 实现 CLI 工具整合（cubox, bookmark, knowledge-tasks）
9. 实现收藏→知识提升流程
10. 实现 Obsidian 侧集成（FSWatch + 文件变更通知）

---

## 13. 验收标准

| Phase | 门禁 |
|-------|------|
| Phase 1 | 任一历史热点打开后显示自动提取的标签，标签选择器 AND 过滤正常 |
| Phase 2 | 新学概念创建后 24h 出现在复习队列，评分后间隔按 SM-2 延长 |
| Phase 3 | 新建规则后 60s 内匹配的文章触发告警，统一搜索 500ms 内返回跨层结果 |
| Phase 4 | 阅读 3 篇 AI 文章后 AI 分类权重提升，知识推荐侧栏显示相关条目 |
| Phase 5 | Agent 启动后自动轮询，新文章 5min 内完成提取；收藏文章自动写入 knowledge/items/；SAG 生命周期完整流转；kv_cache 命中率 > 80% |

**性能预算**:
- 统一搜索 (100k items): P50 < 100ms, P95 < 500ms
- 自动提取 (单篇): 平均 < 500ms
- 告警评估 (单次): P95 < 200ms
- 标签过滤 (10k 文章): P50 < 50ms
- SM-2 复习查询: P50 < 20ms
- Agent 任务写入: P50 < 50ms
- kv_cache 命中率: > 80%

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
| 7 | 新增 10 个 scheduler job 影响采集 | 低 | 中 | ThreadPoolExecutor 隔离 |
| 8 | Agent 轮询延迟导致任务堆积 | 中 | 中 | 动态调整轮询间隔 + 并发处理 |
| 9 | Agent 与 Hotspot 状态不一致 | 中 | 中 | 幂等性校验 + 重试机制 |
| 10 | kv_cache 与文件系统不一致 | 中 | 低 | etag 校验 + 自动失效 |

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
| SAG 生命周期 | Signal → Amplify:tagged → Amplify:linked → Amplify:complete → Generate |
| Phase-locked polling | Agent 跟随 Hotspot 采集节奏的相位锁定轮询 |
| KV 缓存层 | SQLite 中的缓存表，加速 LLM-Wiki 查询 |
| Task Queue | 基于文件系统的 Agent 任务队列 (tasks/pending/) |
| Agent Skill | Agent 执行的结构化任务定义，包含 LLM/正则/脚本三种类型 |
| OKF | Original Knowledge Files — 以 .md 文件为源数据的知识存储范式 |
| LLM-Wiki 2.0 | 基于文件系统的 LLM 可读写知识库，支持 Obsidian 读取 |

---

**附录 A**: 数据迁移脚本 (`backend/repository/migrations/024_v1.7_tags.sql` 至 `035_v1.7_migrate_compiled.sql`)
**附录 B**: 前端组件树与路由变更 (`docs/v1.7_frontend_components.md`)
**附录 C**: 用户旅程流程图 (`docs/diagrams/v1.7_workflow_sequence.md`)
**附录 D**: 标签体系初始种子数据 (`backend/data/seed_tags.json`)
