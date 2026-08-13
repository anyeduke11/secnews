# PROJECT.md — 项目心智模型

## 项目概述

- **一句话描述**：面向 AI + 安全从业者的单人本地工作站，聚合 30+ 资讯源，提供知识管理闭环和项目全生命周期管理。
- **核心目标**：
  1. 从"信息聚合工具"升级为"第二大脑"（资料层 → 判断层 → 行动层）
  2. 知识复利闭环：输入 → 学习 → 掌握 → 输出
  3. CodeGarden：AI 协作全生命周期管理
- **技术栈**：
  - 后端：Python FastAPI + SQLite (WAL) + APScheduler
  - 前端：React 18 + Vite 5 + TypeScript + Tailwind CSS 3
  - 数据：文件系统 (knowledge/) + SQLite 缓存
  - 加密：Fernet (PBKDF2-derived master key)
  - 测试：pytest (后端) / Vitest + jsdom (前端)

## 架构概览

### 三大子系统

```
SecNews 热点聚合  ←→  Knowledge 知识闭环  ←→  CodeGarden 项目管理
(资讯/标讯采集)      (学习/掌握/输出)        (服务/资源/事件)
```

### 目标架构（三层·第二大脑）

```
资料层 → 判定层 → 行动层
我有什么    我怎么看    我下一步做什么
```

见 `docs/superpowers/specs/2026-08-06-second-brain-three-layer-architecture-prd.md`

### 三层架构详细设计 (2026-08-07)

#### 模块划分

```
App.tsx (路由总控)
├── LayerNav (新顶层导航: [资料层] [判断层] [行动层] │ [设置])
│
├── DataLayerPage (/data/*)     ← 资料层
│   ├── HotspotGrid (复用)       — 资讯流
│   ├── StatsPanel (复用)       — 数据源统计
│   ├── RegionFilter (复用)     — 标讯地区筛选
│   ├── KnowledgeImport (移入)  — 从原 /knowledge/import
│   ├── FavoritesPanel (复用)   — 收藏夹
│   └── HistoryPage (复用)      — 历史记录
│
├── JudgeLayerPage (/judge/*)   ← 判断层
│   ├── QualityRejectionPage (复用) — 质量门禁
│   ├── TrendChart (移入)       — 从首页移入
│   ├── BidAnalysis (新增)      — 标讯分析面板
│   ├── AttentionHeatmap (复用) — 注意力热力图
│   ├── KnowledgeGraph (复用)   — 知识图谱
│   ├── KnowledgeCompile (移入) — 从原 /knowledge/compile
│   └── <4 阅读模式> (复用)     — 简报/扫描/深度/告警
│
├── ActionLayerPage (/action/*) ← 行动层
│   ├── ReportPage (复用)       — 报告生成
│   ├── OutboxMode (复用)       — 整理
│   ├── ReviewMode (复用)       — 复习
│   ├── KnowledgeCompound (移入) — 从原 /knowledge/compound
│   ├── CodegardenPage (复用)   — 项目管理
│   ├── TodosPage (复用)        — 待办
│   ├── SkillsPage (复用)       — 技能
│   ├── BidAlert (新增)         — 投标提醒
│   └── CodegardenPhase2bPage (复用) — 服务网格/资源/事件
│
└── 旧路由兼容层 (Navigate 重定向)
    └── /category/:cat → /data?category=:cat
    └── /knowledge/*  → 对应新路由
    └── /codegarden/* → /action/codegarden
```

#### 关键接口

```
# LayerNav — 三层顶层导航
interface LayerNavProps {
  currentLayer: 'data' | 'judge' | 'action';
  contextCategory?: string;
  onLayerChange: (layer: string, category?: string) => void;
}

# BidAnalysis — 标讯分析面板 (新增)
interface BidAnalysisProps {
  region?: string; status?: string; businessLine?: string; timeRange?: string;
}

# BidAlert — 投标提醒 (新增)
interface BidAlertProps {
  region?: string; businessLine?: string;
}

# 新后端 API
GET  /api/bid/analysis       → 地区/状态/业务线分布
GET  /api/bid/alerts         → 投标提醒列表
POST /api/bid/subscriptions  → 创建标讯订阅
```

#### 依赖关系

```
前端: LayerNav → DataLayerPage / JudgeLayerPage / ActionLayerPage
      每层壳组件 → 复用现有组件 (无变更 / 只移入)
      新增: BidAnalysis.tsx, BidAlert.tsx, LayerNav.tsx, LayerBreadcrumb.tsx

后端: 所有现有 API 不变
      新增: backend/api/bid.py (标讯分析 + 投标提醒)
      数据库: 无 schema 变更 (基于现有数据聚合查询)
```

### 数据流

```
30+ 采集器 → 13 道质量门禁 → SQLite 存储 → 前端展示
                                        → 知识图谱构建
                                        → 注意力评分
                                        → 报告生成

三层数据流:
  资料层                   判断层                   行动层
  采集 → 存储 → 检索  →  分类 → 分析 → 评分  →  计划 → 执行 → 复盘
```

### 关键路径

```
backend/main.py → uvicorn 启动
  → backend/api/__init__.py → register_routers() 注册 30+ 路由
  → backend/scheduler/ → APScheduler 30 个定时任务
  → backend/collectors/ → 14 个 BaseCollector 子类
  → backend/quality/ → 13 道 Gate 流水线
  → backend/repository/ → 33 个 SQLite DAO
  → backend/services/ → 74 个业务逻辑文件

frontend/src/App.tsx → Routes
  → /data/* → DataLayerPage (资讯/标讯/收藏/历史/导入)
  → /judge/* → JudgeLayerPage (门禁/趋势/分析/图谱/编译/阅读)
  → /action/* → ActionLayerPage (报告/整理/复习/复利/CodeGarden/待办/技能)
  → /settings → SettingsPage
  → (旧路由 Navigate 重定向到对应新路由)
```

## 模块地图

### 三大子系统

| 模块 | 路径 | 职责 | 依赖 | 状态 |
|------|------|------|------|------|
| SecNews | `backend/` | 资讯/标讯采集 + 聚合 + 质量门禁 | 无 | 已完成 |
| Knowledge | `knowledge/` + `backend/services/knowledge*` | 知识库文件系统 + 同步 + 图谱 | SecNews | 已完成 |
| CodeGarden | `codegarden/` + `backend/api/codegarden*` | 项目管理 + 服务网格 + 资源 | Knowledge | 已完成 |

### 后端模块

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| API 路由 | `backend/api/` | 30+ REST 路由 (lazy import) | 已完成 |
| 采集器 | `backend/collectors/` | 14 个 BaseCollector 子类 | 已完成 |
| 质量门禁 | `backend/quality/` | 13 道 Gate 流水线 | 已完成 |
| 存储层 | `backend/repository/` | 33 个 SQLite DAO | 已完成 |
| 业务逻辑 | `backend/services/` | 74 个服务文件 | 已完成 |
| 调度器 | `backend/scheduler/` | 30 个 APScheduler 任务 | 已完成 |
| 安全知识图 | `backend/security/` | MITRE ATT&CK / CVE / 合规 | 已完成 |
| 配置 | `backend/config.py` | Pydantic Settings, env HOTSPOT_ | 已完成 |

### 前端模块

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| 路由 | `frontend/src/App.tsx` | React Router 路由定义 | 已完成 |
| 资讯主页 | `frontend/src/components/` | HotspotGrid + CategoryNav + SearchBar | 已完成 |
| 知识管理 | `frontend/src/components/knowledge/` | 导入/处理/编译/复利 + 6 阅读模式 | 已完成 |
| CodeGarden | `frontend/src/components/codegarden/` | 项目/服务/资源/依赖/事件 | 已完成 |
| 类型 | `frontend/src/types/index.ts` | 共享类型 + CATEGORIES 表 | 已完成 |
| Hooks | `frontend/src/hooks/` | useHotspotData, useTodos, useSSE | 已完成 |

### 知识库 (文件系统)

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| 条目 | `knowledge/items/` | L1: ~405 个知识条目 (.md) | 进行中 |
| 概念 | `knowledge/concepts/` | L2: ~35 个概念 + graph.json | 进行中 |
| 学习 | `knowledge/learning/` | L3: 学习计划 + 任务 | 进行中 |
| 内容 | `knowledge/content/` | L4: 创作日历 + 草稿 | 进行中 |
| 摘要 | `knowledge/summaries/` | 每周摘要 | 进行中 |

### CodeGarden

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| 项目管理 | `backend/api/codegarden.py` | 项目 CRUD + 状态机 | 已完成 |
| 服务网格 | `backend/api/codegarden_ops.py` | 服务/资源/依赖/事件 | 已完成 |
| 扫描器 | `backend/services/codegarden_scanner.py` | lsof/docker/pm2 自动发现 | 已完成 |
| 导出 | `codegarden/exports/` | 导出产物 | 已完成 |

## 编码约定

### 后端

- **命名**：snake_case (Python), 函数名动词开头, 类名 PascalCase
- **文件组织**：一个模块一个文件, 30+ 行 router 保持简洁, 业务逻辑在 services/
- **错误处理**：HTTPException 统一错误格式 `{"detail": {"message": "...", "missing": "..."}}`
- **数据库**：SQLite thread-local 连接, autocommit 模式, 一个 repository 一个文件
- **测试**：pytest, tmp_path + monkeypatch 隔离, 已 2286+ 测试
- **配置**：Pydantic Settings, 环境变量前缀 `HOTSPOT_`

### 前端

- **命名**：PascalCase 组件, camelCase 变量/函数, snake_case 后端字段
- **文件组织**：一个组件一个文件, 测试 colocated
- **路由**：react-router-dom v6, lazy load with Suspense
- **样式**：Tailwind CSS + CSS 变量 (dark/light theme)
- **图标**：`Icon.tsx` 共享 SVG 组件
- **测试**：Vitest + jsdom, 286+ 测试

### 知识库

- **格式**：YAML frontmatter + Markdown 正文
- **命名**：`knowledge/items/{source}-{id}.md`
- **同步**：文件是 source of truth, SQLite 是读缓存
- **联邦**：`[[wiki:local:path]]` 跨 wiki 引用

## 质量红线

1. **不删除已有信息** — 所有 ingested 数据不可删除
2. **列表排序** — 必须用 `ingested_at DESC`, 不用 `published_at`
3. **标讯搜索** — 四线 AND/OR 体系：业务线内 OR, 与采购语境词 AND
4. **URL 过滤** — 安全资讯仅允许 `/articles/\d+` 路径
5. **时效门禁** — 所有 category 应用 RecencyGate, 过滤 `published_at < 本周一`
6. **同步包** — 必须用 zip 容器, ASCII 文件名
7. **前端端口** — 固定 8898, 禁止漂移
8. **敏感字段** — 复用 Fernet 加密, 未解锁时显示 `******`
9. **禁止提交敏感信息** — 不提交 .env, credentials 等
10. **API 错误格式** — 统一 `{"detail": {"message": "...", "missing": "..."}}`

## 决策日志

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|----------|
| 2026-07-14 | 知识管理 4 大领域分类 | 符合知识生命周期（导入→处理→编译→复利） | 三层分类（未采纳，后期改为三层架构） |
| 2026-07-20 | CodeGarden Phase 2b 服务网格 | 自动发现 + 拓扑图 + 联动引擎 | 手动配置（未采纳，自动化更具价值） |
| 2026-08-06 | 第二大脑三层架构 | 统一抽象资讯/标讯/知识/项目，解决"信息过载→噪音干扰→信息闲置" | 原有领域分类导航（未采纳，三层更符合认知模型） |
| 2026-08-06 | 知识管理 4 领域拆分融入三层 | 避免知识管理独立入口，让三层架构覆盖所有功能 | 保留知识管理独立 Tab（未采纳，导致导航碎片化） |
| 2026-08-06 | CodeGarden 归入行动层 | CodeGarden 本质是"项目执行"，符合行动层"我下一步做什么"定位 | 保留独立入口（未采纳，三层统一性更强） |
| 2026-08-07 | 三层架构模块划分 | 资料层复用 HotspotGrid/StatsPanel，判断层聚合门禁/趋势/图谱/阅读，行动层聚合报告/复利/CodeGarden/待办 | 每层独立全量路由（未采纳，壳组件 + 子路由更简洁） |
| 2026-08-07 | 跨层联动用 URL search params | 无需状态管理库，URL 是最简单可靠的跨层传参方式 | Context（未采纳，URL 更可持久化、可分享） |
| 2026-08-07 | 后端 bid.py 独立 API | 标讯分析/投标提醒独立路由，不污染现有 hotspots.py | 合并到 hotspots.py（未采纳，单一职责原则） |
| 2026-08-07 | 数据库无 schema 变更 | 标讯分析基于现有数据聚合查询，无需新增表 | 新建 bid_analysis 表（未采纳，过度设计） |

## 已知问题

- 当前导航仍是领域分类（CategoryNav），尚未按三层架构重构
- 标讯分析面板（地区/状态/业务线分布）尚未开发
- 投标提醒/竞争分析功能尚未开发
- 跨层导航条和上下文联动尚未实现
- 旧路由 `/knowledge/*` 和 `/category/:cat` 的兼容性处理尚未实施
- 三层架构 PRD 已定稿，架构设计已完成，等待进入开发阶段

## 生命周期

当前阶段：**架构**（三层架构详细设计已输出，架构审查通过，等待进入开发阶段）

### 阶段检查记录

| 阶段 | 检查时间 | 结果 | 发现的问题 | 修复状态 |
|------|----------|------|------------|----------|
| 需求 | 2026-08-06 | 通过 | 三层架构 PRD 定稿 | 已定稿 |
| 初始化 | 2026-08-06 | 通过 | PROJECT.md 覆盖全部 8 段落 | 已完成 |
| 架构 | 2026-08-07 | 通过 | 见下方架构审查 | 待实施 |

### 架构审查 (2026-08-07)

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 模块划分是否合理（单一职责、高内聚低耦合） | ✅ 通过 | 资料层负责采集/存储/检索，判断层负责筛选/分析/评分，行动层负责计划/执行/复盘，三层职责不重叠 |
| 依赖关系是否清晰（无循环依赖） | ✅ 通过 | 前端依赖单向：LayerNav → 壳组件 → 复用组件；后端无新增依赖 |
| 接口定义是否完整（输入输出明确） | ✅ 通过 | LayerNav/BidAnalysis/BidAlert 接口已定义，后端 bid.py API 已定义 |
| 技术选型是否匹配项目规模（不过度工程化） | ✅ 通过 | 复用现有组件 + 路由，无新状态管理库，无新数据库表，无新部署依赖 |
| 质量红线是否覆盖关键安全要求 | ✅ 通过 | 现有 10 条红线仍适用，新增 API 复用现有验证模式 |

**审查结论**: 通过。架构设计最小破坏、渐进整合，复用现有组件而非重写，符合项目约束条件。