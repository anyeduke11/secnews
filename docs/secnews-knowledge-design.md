# secnews-knowledge 知识管理看板设计方案

> 版本：v1.0 | 日期：2026-07-15 | 状态：设计评审中

---

## 目录

1. [项目总览与定位](#1-项目总览与定位)
2. [架构总览](#2-架构总览)
3. [三种知识来源](#3-三种知识来源)
4. [数据模型设计](#4-数据模型设计)
5. [前端页面布局设计](#5-前端页面布局设计)
6. [后端 API 与 AI 引擎设计](#6-后端-api-与-ai-引擎设计)
7. [内容创作系统集成](#7-内容创作系统集成)
8. [实施路线图](#8-实施路线图)

---

## 1. 项目总览与定位

### 1.1 项目名称

**secnews-knowledge** —— 在 secnews 上扩展的知识管理模块。

### 1.2 核心定位

将 Cubox 知识库 + 浏览器书签 + secnews 归档资讯 从"收藏即遗忘"的静态仓库，转变为 **"学习 → 掌握 → 输出"** 的闭环系统。

### 1.3 三阶段闭环

| 阶段 | 做什么 | 产物 |
|------|--------|------|
| 输入 | 同步 Cubox + 书签 + secnews 归档 → AI 自动分类打标 → 知识图谱 | 领域知识地图 |
| 学习 | 学习路径图 + 本周任务 + 推荐工具 + 复习计划 | 可执行的学习任务清单 |
| 输出 | 学完的知识 → 选题建议 → 接入内容创作系统（13 项子技能） | 快讯/长文/事件分析/分发 |

### 1.4 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + Vite 5 + Tailwind CSS 3 + TypeScript（复用 secnews 现有架构） |
| 后端 | Python FastAPI（复用 secnews 现有架构，新增 `/api/knowledge` 路由） |
| AI 引擎 | 内置 LLM 调用（支持 OpenAI 兼容 API，可配置百炼/火山方舟/DeepSeek 等） |
| 数据同步 | cubox-cli（API 拉取）+ 书签文件解析（HTML 解析）+ secnews 内部归档 |
| 数据存储 | 本地 JSON 文件（数据量可控，热更新，无需数据库） |

### 1.5 与 secnews 的关系

在 secnews 现有 5 大领域的基础上，新增一个 **「知识管理」** 顶级 Tab，与现有的 Tech/AI、网络安全、金融投资、独立开发、综合热点 并列。共用同一套前端框架、后端服务和 UI 风格。

---

## 2. 架构总览

### 2.1 系统架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                         secnews-knowledge                        │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                  │
│  │  Cubox   │  │ 浏览器书签 │  │secnews 归档   │  ← 三种知识来源 │
│  │ 知识库   │  │ (4,046)  │  │ (阅读后归档)  │                  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘                  │
│       │             │               │                            │
│       └─────────────┼───────────────┘                            │
│                     ▼                                            │
│  ┌──────────────────────────────────────┐                       │
│  │           AI 知识引擎                  │  ← 核心处理层        │
│  │  · 分类 · 打标签 · 去重 · 融合        │                      │
│  │  · 知识图谱构建 · 能力评估 · 缺口分析  │                      │
│  │  · 学习路径生成 · 选题建议            │                      │
│  │  · 内置 LLM 驱动（OpenAI 兼容 API）    │                      │
│  └──────────────────┬───────────────────┘                       │
│                     │                                            │
│       ┌─────────────┼─────────────┐                              │
│       ▼             ▼             ▼                              │
│  ┌────────┐  ┌──────────┐  ┌──────────────┐                    │
│  │学习看板 │  │知识图谱   │  │内容创作飞轮   │  ← 展示与输出层    │
│  │路径图   │  │领域地图   │  │P1-P5 支柱    │                    │
│  │本周任务 │  │技能树     │  │13 项子技能    │                    │
│  │复习计划 │  │关联关系   │  │采集→分发→复盘 │                    │
│  └────────┘  └──────────┘  └──────────────┘                    │
│                                                                  │
│  ┌──────────────────────────────────────┐                       │
│  │            🔄 知识更新 按钮            │  ← 一键触发全流程     │
│  └──────────────────────────────────────┘                       │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
知识更新触发
  ↓
三源同步（Cubox API / 书签文件解析 / secnews 归档读取）
  ↓
AI 引擎处理（分类、打标、去重、难度评估）
  ↓
知识图谱更新（节点、边、技能树）
  ↓
学习计划生成（本周任务、推荐工具、复习计划）
  ↓
看板刷新 + 选题建议推送
```

---

## 3. 三种知识来源

### 3.1 Cubox 知识库

| 属性 | 说明 |
|------|------|
| 来源方式 | 通过 cubox-cli API 拉取 |
| 数据内容 | 收藏文章、标注、AI 摘要、文件夹/标签结构 |
| 更新频率 | 每次「知识更新」时同步 |
| 特点 | 主动收藏，有全文和标注，质量最高 |

**Cubox CLI 接口：**
- `cubox-cli folder list` — 获取文件夹结构
- `cubox-cli tag list` — 获取标签列表
- `cubox-cli card list --all` — 获取全部卡片
- `cubox-cli card detail --id ID` — 获取卡片详情（含全文、AI 摘要、标注）
- `cubox-cli annotation list --all` — 获取全部标注

### 3.2 浏览器书签

| 属性 | 说明 |
|------|------|
| 来源方式 | 解析 Chrome 书签导出 HTML 文件 |
| 数据内容 | 4,046 条书签，40+ 文件夹分类，3 层深度 |
| 更新频率 | 手动导入书签文件，或定期自动解析 |
| 特点 | 历史沉淀，领域覆盖广，但无全文内容 |

**当前书签分布（按主题）：**

| 主题 | 数量 | 占比 |
|------|------|------|
| 安全 | 1,310 | 32.4% |
| AI/大模型/机器学习 | 847 | 20.9% |
| 编程/开发工具 | 541 | 13.4% |
| 资讯/自媒体 | 203 | 5.0% |
| 知识管理/文档 | 123 | 3.0% |
| 其他 | 1,022 | 25.3% |

### 3.3 secnews 归档资讯

| 属性 | 说明 |
|------|------|
| 来源方式 | secnews 热点列表中，用户点击「归档到知识库」 |
| 数据内容 | 热点文章标题、URL、摘要、领域分类 |
| 更新频率 | 用户手动归档，实时写入 |
| 特点 | 与资讯流打通，形成闭环；从"看过即忘"到"永久沉淀" |

**资讯-知识闭环：**

```
secnews 热点浏览 → 阅读有价值文章 → 一键归档到知识库
    ↓
AI 知识引擎消化 → 分类打标 → 学习任务生成
    ↓
学习完成 → 选题建议 → 内容创作
    ↓
内容发布 → 回流 secnews 资讯流（如公众号文章）
```

---

## 4. 数据模型设计

### 4.1 KnowledgeItem（知识条目）

```typescript
interface KnowledgeItem {
  id: string;                    // 唯一标识
  source: "cubox" | "bookmark" | "secnews_archive";  // 来源
  source_id: string;             // 原始来源中的 ID
  url: string;                   // 原始链接
  title: string;                 // 标题
  description: string;           // 摘要 / Cubox AI 摘要
  content?: string;              // 全文（Cubox 有，书签/归档无）
  annotations?: {                // Cubox 标注
    text: string;
    note: string;
    color: string;
  }[];

  // AI 引擎填充字段
  domain: string;                // 知识领域
  subdomain: string;             // 子领域
  tags: string[];                // AI 自动打标
  difficulty: "beginner" | "intermediate" | "advanced";  // 难度
  learning_status: "unread" | "reading" | "mastered" | "review_needed";
  quality_score: number;         // 0-100，AI 评估质量分

  // 时间
  created_at: string;
  updated_at: string;
  last_reviewed_at?: string;
}
```

### 4.2 KnowledgeDomain（知识领域）

```typescript
interface KnowledgeDomain {
  id: string;
  name: string;                  // 领域名称
  parent_id?: string;            // 父领域
  item_count: number;            // 条目数
  mastered_count: number;        // 已掌握数
  subdomains: KnowledgeDomain[]; // 子领域
  skills: Skill[];               // 关联技能
}
```

### 4.3 Skill（技能）

```typescript
interface Skill {
  id: string;
  name: string;                  // 技能名称
  domain_id: string;             // 所属领域
  level: "none" | "beginner" | "intermediate" | "advanced" | "expert";
  prerequisites: string[];       // 前置技能 ID
  related_items: string[];       // 关联知识条目 ID
  tools: Tool[];                 // 相关工具
}
```

### 4.4 Tool（工具）

```typescript
interface Tool {
  id: string;
  name: string;
  url: string;
  category: string;              // 工具类别
  description: string;
  tags: string[];
}
```

### 4.5 KnowledgeGraph（知识图谱）

```typescript
interface KnowledgeGraph {
  nodes: {
    id: string;
    label: string;
    type: "domain" | "skill" | "tool";
    size: number;                // 基于条目数的权重
    color: string;               // 领域颜色
  }[];
  edges: {
    source: string;
    target: string;
    relation: "contains" | "prerequisite" | "related" | "tool_of";
    weight: number;
  }[];
}
```

### 4.6 LearningPlan（学习计划）

```typescript
interface LearningPlan {
  week_start: string;            // 周起始日期
  generated_at: string;          // 生成时间

  tasks: {
    id: string;
    title: string;
    domain: string;
    items: string[];             // 关联 KnowledgeItem ID
    estimated_hours: number;
    priority: 1 | 2 | 3;         // 1=最高
    tools: { name: string; url: string; purpose: string }[];
    status: "pending" | "in_progress" | "completed";
  }[];

  review_tasks: {
    item_id: string;
    title: string;
    domain: string;
    last_reviewed: string;
    due: string;                 // 下次复习日期
    interval_days: number;       // 间隔天数
  }[];

  recommended_tools: {
    name: string;
    url: string;
    category: string;
    reason: string;
  }[];

  content_suggestions: {         // 选题建议，桥接内容创作系统
    title: string;
    pillar: string;              // P1-P5
    source_items: string[];      // 来源知识条目
    outline: string;             // AI 生成大纲
  }[];
}
```

### 4.7 数据文件结构

```
secnews/
├── backend/
│   └── data/
│       ├── knowledge_items.json     # 知识条目（统一存储）
│       ├── knowledge_graph.json     # 知识图谱
│       ├── learning_plan.json       # 当前学习计划
│       ├── domains.json             # 领域定义
│       └── tools.json               # 工具库
```

---

## 5. 前端页面布局设计

### 5.1 导航结构

在 secnews 现有导航栏中新增一个 Tab：

```
[Tech/AI] [网络安全] [金融投资] [独立开发] [综合热点] [知识管理] ← 新增
```

### 5.2 知识管理页面布局

页面采用三栏布局 + 顶部操作栏：

```
┌─────────────────────────────────────────────────────────────────┐
│  🔄 知识更新    📊 统计: 4,046 条 · 3 源 · 12 领域 · 上次更新: 2h前 │
├────────────────────┬────────────────────┬───────────────────────┤
│                    │                    │                       │
│   📚 知识图谱      │   📋 学习路径      │   ✍️ 内容创作选题      │
│   (左栏 35%)      │   (中栏 35%)      │   (右栏 30%)          │
│                    │                    │                       │
│  ┌──────────────┐ │  ┌──────────────┐ │  ┌─────────────────┐  │
│  │ 领域节点图    │ │  │ 学习路径图    │ │  │ 本周选题建议     │  │
│  │ (ECharts 力导 │ │  │ (树形/流程图) │ │  │ · AI安全 x3     │  │
│  │  向图)       │ │  │              │ │  │ · 攻防实战 x2   │  │
│  │              │ │  │ 安全攻防      │ │  │ · 开发工具 x1   │  │
│  │  安全 ←→ AI  │ │  │  ├─ 渗透测试  │ │  └─────────────────┘  │
│  │   ↕    ↕     │ │  │  ├─ 应用安全  │ │                       │
│  │  开发   运维  │ │  │  └─ 蓝队防守  │ │  ┌─────────────────┐  │
│  └──────────────┘ │  └──────────────┘ │  │ 创作快捷入口     │  │
│                    │                    │  │ [快讯] [长文]    │  │
│                    │                    │  │ [事件分析] [分发] │  │
├────────────────────┴────────────────────┴───────────────────────┤
│                                                                  │
│  📝 本周学习任务                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ [进行中] 提示词注入攻击检测（安全/AI）  ⏱ 3h  🔧 Claw·Burp  ││
│  │ [待开始] RAG 知识库搭建实战（AI/开发）  ⏱ 4h  🔧 LangChain  ││
│  │ [待开始] 云原生安全监控体系（安全/运维）  ⏱ 5h  🔧 Falco    ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  🔧 学习工具推荐           📖 复习任务（间隔重复）               │
│  ┌────────────────────┐  ┌────────────────────────────────────┐  │
│  │ Claw · Burp · Nmap │  │ 深度学习基础 → 2天后复习            │  │
│  │ LangChain · Docker │  │ SQL注入原理 → 明天复习              │  │
│  │ Falco · Wireshark  │  │ 大模型API调用 → 5天后复习           │  │
│  └────────────────────┘  └────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 组件树

```
KnowledgePage
├── KnowledgeHeader
│   ├── SyncButton (知识更新按钮)
│   ├── StatsBar (统计条：条目数、来源分布、领域数、上次更新)
│   └── SourceFilter (来源筛选：Cubox/书签/归档)
│
├── KnowledgeTopRow (三栏)
│   ├── KnowledgeGraphPanel (知识图谱 · ECharts 力导向图)
│   │   ├── DomainNodes (领域节点，可点击下钻)
│   │   └── DomainEdges (关联边)
│   ├── LearningPathPanel (学习路径图)
│   │   ├── DomainTree (领域树形图)
│   │   └── SkillTree (技能树，前置依赖箭头)
│   └── ContentSuggestionsPanel (内容创作选题)
│       ├── SuggestionCards (选题卡片 · P1-P5 标签)
│       └── QuickCreateButtons (快捷入口)
│
├── WeeklyTasksPanel (本周学习任务)
│   ├── TaskList (任务列表，可拖拽排序)
│   └── TaskDetail (展开详情：关联条目、工具、进度)
│
├── ToolsPanel (学习工具推荐)
│   └── ToolCards (工具卡片：名称、链接、用途)
│
└── ReviewPanel (复习任务)
    └── ReviewList (复习列表：条目、上次复习、下次到期)
```

### 5.4 交互设计

| 交互 | 行为 |
|------|------|
| 点击「知识更新」 | 触发后端同步 + AI 处理，Loading 态显示进度，完成后刷新全页 |
| 点击图谱节点 | 筛选该领域的知识条目和学习任务 |
| 点击学习任务 | 展开详情，显示关联条目列表和工具链接 |
| 点击选题卡片 | 跳转到内容创作系统对应子技能 |
| 标记任务完成 | 更新学习状态，AI 重新评估该领域掌握度 |
| 标记复习完成 | 更新复习时间，间隔重复算法自动计算下次复习日期 |

---

## 6. 后端 API 与 AI 引擎设计

### 6.1 API 路由

```
/api/knowledge
├── POST /sync                    # 触发知识同步（三源）
├── GET  /items                   # 获取知识条目列表
│       ?source=cubox|bookmark|secnews
│       &domain=安全
│       &status=unread
│       &page=1&limit=50
├── GET  /items/:id               # 获取单条知识详情
├── PATCH /items/:id              # 更新学习状态
├── GET  /domains                 # 获取领域列表
├── GET  /graph                   # 获取知识图谱数据
├── GET  /plan                    # 获取当前学习计划
├── POST /plan/refresh            # 重新生成学习计划
├── PATCH /plan/tasks/:id         # 更新任务状态
├── GET  /tools                   # 获取工具推荐
├── GET  /suggestions             # 获取内容创作选题建议
└── GET  /stats                   # 获取统计概览
```

### 6.2 AI 引擎设计

AI 引擎是看板的核心，负责所有智能化处理，**不依赖 TRAE 调用**，直接通过 LLM API 驱动。

**引擎配置：**

```python
# config/ai_engine.py
AI_ENGINE_CONFIG = {
    "provider": "openai_compatible",  # 支持 OpenAI 兼容 API
    "api_base": "https://api.deepseek.com/v1",  # 可配置百炼/火山方舟/DeepSeek
    "api_key_env": "AI_ENGINE_API_KEY",
    "model": "deepseek-chat",
    "max_tokens": 4096,
    "temperature": 0.3
}
```

**引擎能力矩阵：**

| 能力 | Prompt 策略 | 触发时机 | 产物 |
|------|------------|----------|------|
| 自动分类 | 给定标题+摘要，输出领域/子领域 | 每次同步后 | `domain`, `subdomain` |
| 自动打标 | 给定标题+摘要，输出 3-5 个标签 | 每次同步后 | `tags[]` |
| 难度评估 | 给定标题+摘要，输出 beginner/intermediate/advanced | 每次同步后 | `difficulty` |
| 质量评分 | 给定标题+摘要+来源，输出 0-100 分 | 每次同步后 | `quality_score` |
| 去重 | 给定两条条目，判断是否重复 | 同步后批量比对 | 合并/标记 |
| 知识图谱 | 给定所有领域，输出关联关系 | 领域变更后 | `edges[]` |
| 学习路径 | 给定技能树+未掌握条目，输出学习顺序 | 每次计划刷新 | 排序后的任务列表 |
| 选题建议 | 给定近期学习内容+内容支柱，输出选题 | 每次计划刷新 | `content_suggestions[]` |
| 工具推荐 | 给定学习任务，推荐相关工具 | 每次计划刷新 | `recommended_tools[]` |

**AI 调用流程：**

```
1. 同步阶段（批量）
   - 遍历新条目，每个条目调用一次分类+打标+难度+质量（可并发）
   - 新条目与已有条目比对去重

2. 图谱构建阶段（领域级）
   - 聚合所有领域，调用 LLM 分析关联关系
   - 生成知识图谱 edges

3. 计划生成阶段（任务级）
   - 基于未掌握条目 + 技能树，调用 LLM 生成学习路径
   - 基于间隔重复算法，生成复习计划
   - 基于学习内容 + 内容支柱，生成选题建议
```

### 6.3 数据同步策略

**Cubox 同步：**

```python
# 伪代码
def sync_cubox():
    cards = cubox_cli("card list --all")
    for card in cards:
        detail = cubox_cli(f"card detail --id {card.id}")
        item = KnowledgeItem(
            source="cubox",
            source_id=card.id,
            title=card.title,
            url=card.url,
            description=detail.insight.get("summary", ""),
            content=detail.content,
            annotations=detail.annotations,
        )
        # AI 引擎处理
        item = ai_engine.enrich(item)
        upsert(item)
```

**书签同步：**

```python
def sync_bookmarks():
    bookmarks = parse_chrome_bookmarks_html("bookmarks.html")
    for bm in bookmarks:
        item = KnowledgeItem(
            source="bookmark",
            source_id=hash(bm.url),
            title=bm.title,
            url=bm.url,
            description="",
            tags=bm.folder_path,  # 用文件夹层级作为初始标签
        )
        item = ai_engine.enrich(item)
        upsert(item)
```

**secnews 归档同步：**

```python
def sync_secnews_archive():
    archived = secnews_db.query("SELECT * FROM hotspots WHERE archived=true")
    for h in archived:
        item = KnowledgeItem(
            source="secnews_archive",
            source_id=h.id,
            title=h.title,
            url=h.url,
            description=h.summary,
            domain=h.category,  # 复用 secnews 已有分类
        )
        item = ai_engine.enrich(item)
        upsert(item)
```

---

## 7. 内容创作系统集成

### 7.1 集成方式

内容创作系统（13 项子技能）作为知识管理看板的**输出模块**，通过以下方式桥接：

1. **选题建议**：AI 引擎分析学习内容后，自动推荐选题，标注对应 P1-P5 支柱
2. **快捷入口**：看板右侧提供内容创作快捷按钮，直接跳转到对应子技能
3. **知识引用**：内容创作时，可引用知识库中的条目作为素材来源

### 7.2 选题建议映射

| 学习领域 | 内容支柱 | 选题示例 |
|----------|----------|----------|
| AI 安全 / 提示注入 | P4 Security for AI | 《金融大模型提示注入攻击的 5 种手法》 |
| 渗透测试 / 红队 | P2 攻防实战 | 《HVV 复盘：一次红队渗透的全流程》 |
| 安全运营 / SOC | P3 AI for Security | 《AI 如何让 SOC 告警降噪 90%》 |
| 数据安全 / 隐私 | P1 监管合规 | 《数据脱敏的三条红线与合规实践》 |
| 威胁情报 / APT | P5 安全事件分析 | 《某 APT 组织攻击链分析》 |

### 7.3 调用链

```
知识看板「选题建议」卡片
  ↓ 点击
内容创作系统编排层
  ↓ 选择支柱
对应子技能执行
  · news-subscription → 资讯采集
  · content-longform → 专业长文
  · incident-analysis-sop → 事件分析
  · content-distribution → 多平台分发
  ↓
内容发布
  ↓
回流 secnews 资讯流
```

---

## 8. 实施路线图

### Phase 1：数据基础（2-3 天）

- [ ] 在 secnews 后端新增 `/api/knowledge` 路由模块
- [ ] 实现三种数据源的同步逻辑（Cubox CLI / 书签 HTML 解析 / secnews 归档）
- [ ] 实现数据模型 CRUD 和 JSON 文件存储
- [ ] 编写 AI 引擎基础调用封装（分类、打标、难度评估）

### Phase 2：AI 引擎（2-3 天）

- [ ] 实现知识条目 AI 自动标注（分类、标签、难度、质量分）
- [ ] 实现去重算法
- [ ] 实现知识图谱构建
- [ ] 实现学习路径生成
- [ ] 实现选题建议生成

### Phase 3：前端看板（3-4 天）

- [ ] 导航栏新增「知识管理」Tab
- [ ] 实现知识图谱可视化（ECharts 力导向图）
- [ ] 实现学习路径图（树形/流程图）
- [ ] 实现本周任务面板
- [ ] 实现工具推荐和复习计划面板
- [ ] 实现内容创作选题面板和快捷入口
- [ ] 实现「知识更新」按钮和进度反馈

### Phase 4：集成与闭环（1-2 天）

- [ ] 内容创作系统选题建议桥接
- [ ] secnews 资讯「归档到知识库」按钮
- [ ] 学习状态与知识图谱联动更新
- [ ] 端到端测试：同步 → 学习 → 输出全流程

---

## 附录

### A. 知识领域定义（预设）

| 领域 ID | 名称 | 初始来源 |
|---------|------|----------|
| security-offensive | 安全攻防（渗透/红队） | 书签：渗透测试与红队(1,116) |
| security-defensive | 安全防御（蓝队/SOC） | 书签：蓝队与防守(38) + SOC(2) |
| security-app | 应用安全 | 书签：应用安全(139) |
| security-malware | 恶意软件与逆向 | 书签：恶意软件与逆向(75) |
| security-gov | 安全治理与合规 | 书签：安全管理与体系(136) + 标准合规(8) |
| ai-llm | AI 与大模型 | 书签：大模型(285) |
| ai-dev | AI 编程与开发 | 书签：AI编程与开发(231) |
| ai-agent | Agent 与 MCP | 书签：Agent与MCP(33) |
| dev-ops | 运维与云原生 | 书签：运维与监控(477) |
| dev-frontend | 前端与 Web | 书签：前端与Web(112) |
| finance | 金融与投资 | 书签：金融监管(21) + AI量化(6) |
| productivity | 工具与效率 | 书签：效率与软件工具(98) + 笔记知识管理(3) |

### B. 依赖清单

```
# 前端（复用 secnews 现有）
- react, react-dom
- vite, tailwindcss, typescript
- echarts (知识图谱可视化)
- @tanstack/react-query (数据请求)

# 后端（新增）
- cubox-cli (Cubox 数据同步)
- openai (LLM API 调用)
- beautifulsoup4 (书签 HTML 解析)
```

### C. 环境变量

```bash
# AI 引擎
AI_ENGINE_API_KEY=sk-xxx
AI_ENGINE_API_BASE=https://api.deepseek.com/v1
AI_ENGINE_MODEL=deepseek-chat

# Cubox
CUBOX_SERVER=cubox.pro
CUBOX_TOKEN=xxx

# 书签文件路径
BOOKMARKS_FILE=/path/to/bookmarks.html
```