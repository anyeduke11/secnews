# CodeGarden（代码花园）v2.0 产品需求文档

> **版本**: v2.0
> **日期**: 2026-07-19
> **定位**: hotspot v1.5+ 子系统 — 个人氛围编程产物 + AI 协作全生命周期管理
> **部署**: 纯本地单机（复用 hotspot 既有栈）
> **基线**: 整合 CodeGarden_PRD_v1.0.md 与 hotspot-codegarden.md，与 hotspot 解耦共存
> **开源协议**: MIT License

---

## 0. 版本变更说明

### v1.0 → v2.0 主要变化

| 变更项 | v1.0 | v2.0 |
|--------|------|------|
| 部署形态 | 独立 Tauri 桌面应用 | hotspot 子系统（本地 Web 服务，端口 8898） |
| 后端栈 | Node.js + Fastify | 复用 hotspot FastAPI + SQLite |
| 前端栈 | 独立 React 应用 | 复用 hotspot React + Vite + Tailwind |
| 容器编排 | 提及 K8s | 仅本机 Docker / PM2 / 进程管理 |
| Skill 管理 | 全新表 | 扩展 hotspot `knowledge_skills` 表 |
| GitHub 集成 | 通用代码仓库集成 | 区分"资讯收集"（既有）vs"项目导入"（新增） |
| 模块边界 | 6 大模块平级 | 12 模块分层 + 明确复用/扩展/新建边界 |
| 里程碑 | 单一 v1.0 范围 | 4 阶段（Phase 2a-2d），独立 spec |

### v2.0 整合原则

1. **目的导向**：保留全部 12 个功能模块，不为简化砍除
2. **解耦共存**：作为 hotspot 子系统，独立目录/路由/表前缀，与 knowledge/ 平级
3. **最大化复用**：hotspot 已有的任务队列、同步包、secrets、skill 系统、知识联邦全部复用
4. **避免重复来源**：Skill/GitHub/任务队列等已存在的功能，扩展而非重建

---

## 1. 产品概述

### 1.1 产品定位

CodeGarden 是 hotspot 的代码项目管理子系统，解决个人氛围编程中"开发快、管理乱、维护难、AI 失忆"的核心痛点。

**一句话定位**：
> 你电脑里所有代码项目的"本地驾驶舱" — 从混乱到秩序，只需一个界面。

### 1.2 核心价值主张

> **"从灵感火花到稳定运行，每一个代码产物都有迹可循、有章可依"**

### 1.3 与 hotspot 的关系

```
┌─────────────────────────────────────────────────────────────┐
│                    hotspot v1.5+ 平台                       │
├──────────────────────┬──────────────────────────────────────┤
│  SecNews 资讯聚合    │  Knowledge LLM-Wiki 知识管理         │
│  (安全/AI/科技资讯)  │  (items/concepts/learning/content)   │
├──────────────────────┼──────────────────────────────────────┤
│                      │  CodeGarden 代码花园 (本 PRD)        │
│   共享基础设施        │  • 项目看板 + GitHub 跟踪            │
│  ─────────────────   │  • 服务网格 + 资源中枢               │
│  • FastAPI 后端      │  • AI 协作 (Skill/Memory/Constraint) │
│  • React 前端        │  • Spec/SDD/Prompt 资产              │
│  • SQLite + 同步包   │  • 生命周期 + 联动引擎               │
│  • 任务队列          │                                      │
│  • Secrets 管理      │                                      │
│  • Skill 系统        │                                      │
│  • 知识联邦          │                                      │
└──────────────────────┴──────────────────────────────────────┘
```

### 1.4 关键决策

| 决策项 | 结论 | 说明 |
|--------|------|------|
| 部署形态 | 复用 hotspot 本地 Web 服务 | 端口 8898，禁止漂移 |
| 远程服务器管理 | ❌ 不支持 | 纯本地单机 |
| 内置 CI/CD | ❌ 不内置 | 专注管理，不替代 GitHub Actions |
| 容器编排 | ❌ 不引入 K8s | 仅本机 Docker / PM2 / 进程 |
| 多用户/团队 | ❌ 不支持 | 单用户无登录 |
| Skill 模型 | ✅ 扩展 `knowledge_skills` | 不新建表，避免双重来源 |
| 任务队列 | ✅ 复用 `knowledge_tasks` | task_type 扩展 |
| Secrets | ✅ 复用 hotspot secrets | 不重建加密体系 |
| 数据目录 | 独立 `codegarden/` | 与 `knowledge/` 平级 |
| 表前缀 | `cg_` | 区分 knowledge_* / hotspot_* |

---

## 2. 问题定义与痛点分析

### 2.1 痛点全景

| 痛点层级 | 具体表现 | 影响 | 对应模块 |
|---------|---------|------|---------|
| **开发层** | 代码仓库爆炸式增长，命名混乱，依赖关系不清 | 找代码比写代码更耗时 | M1 项目看板 |
| **部署层** | 端口冲突、服务冲突、环境变量散落各处 | 每次启动都是一次冒险 | M2 服务网格 / M3 资源中枢 |
| **运维层** | 不知道哪些服务在运行、哪些已废弃 | 资源浪费，安全隐患 | M2 服务网格 / M5 生命周期 |
| **协作层** | 二次开发他人项目时理解成本高 | 复用率低，重复造轮子 | M1 项目看板（GitHub 跟踪） |
| **生命周期层** | 没有版本演进记录，没有淘汰机制 | 技术债累积，系统臃肿 | M5 生命周期管理 |
| **AI 协作层** | AI 频繁失忆，重复解释项目背景 | 人机协作效率低 | M7 Memory 三层记忆 |
| **AI 行为失控** | AI 乱改核心文件，引入过多依赖 | 代码质量不可控 | M8 Constraint 约束 |
| **规范缺失** | AI 理解偏差导致反复修改 | 返工率高 | M9 Spec / M10 SDD |
| **提示词靠运气** | 有效 Prompt 无法复用 | 经验流失 | M11 Prompt 资产库 |
| **AI 成本失控** | Token 消耗不可见 | 资源浪费 | M12 AI 调用配额 |
| **二开跟踪缺失** | 上游 repo 更新无感知 | 项目过时，安全漏洞 | M1 GitHub 导入 + 上游跟踪 |

### 2.2 与 hotspot 现状的衔接

- hotspot 已有 409 个 knowledge items，但**没有代码项目维度**的资产
- hotspot 已有 github_collector.py 收集**外部 GitHub 资讯**（trending/热门），但**不跟踪用户自己的 repo**
- hotspot 已有 knowledge_skills 表，但仅用于知识库 skill 配置（publish/compile 等），**未覆盖开发场景的 Skill**（React 专家、DBA、安全审计等）
- hotspot 已有任务队列，可承载 CodeGarden 的异步任务（GitHub 上游同步、健康检查）

---

## 3. 目标用户

| 用户类型 | 特征 | 核心需求 |
|---------|------|---------|
| **氛围编程者** | 每天产生大量原型/实验项目 | 快速归档、自动分类、一键启动 |
| **独立开发者** | 维护多个微服务/工具 | 服务拓扑可视化、依赖管理 |
| **技术博主/教育者** | 需要展示和复用代码 | 项目卡片化展示、快速部署演示 |
| **全栈创业者** | 个人维护完整产品矩阵 | 全局资源监控、成本优化 |
| **二开爱好者** | fork 上游项目二次开发 | 上游更新跟踪、差异感知 |

---

## 4. 功能架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                  CodeGarden 平台架构 (hotspot 子系统)                │
├─────────────┬─────────────┬─────────────┬─────────────────────────┤
│   M1 项目   │   M2 服务   │   M3 资源   │      M4 联动引擎        │
│   看板      │   网格      │   中枢      │                         │
├─────────────┼─────────────┼─────────────┼─────────────────────────┤
│ • 项目卡片  │ • 服务注册  │ • 端口池    │ • 依赖图谱              │
│ • 生命周期  │ • 健康检查  │ • 域名映射   │ • 事件总线              │
│ • 版本追踪  │ • 日志聚合  │ • 环境变量   │ • 自动化工作流           │
│ • 标签体系  │ • 配置管理  │ • 密钥托管   │ • 触发器               │
│ • GitHub    │ • 扩缩容    │ • 存储卷    │                         │
│   导入      │             │             │                         │
│ • 上游跟踪  │             │             │                         │
└─────────────┴─────────────┴─────────────┴─────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    M5 生命周期管理 + M12 AI 配额                     │
├──────────────────────────────┬──────────────────────────────────────┤
│  • 健康度评分                │  • Token/请求配额                    │
│  • 技术债看板                │  • 用量监控                          │
│  • 归档清理                  │  • 上下文压缩                        │
└──────────────────────────────┴──────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    AI 协作管理层（M6-M11）                           │
├──────────┬──────────┬──────────┬──────────┬───────────┬────────────┤
│  M6      │  M7      │  M8      │  M9      │  M10      │  M11       │
│  Skill   │  Memory  │Constraint│  Spec    │  SDD      │  Prompt    │
│  技能定义 │  记忆    │ 行为约束 │  规格    │  设计文档 │  资产库    │
├──────────┼──────────┼──────────┼──────────┼───────────┼────────────┤
│ 角色能力  │ 长期记忆 │ 文件边界 │ 功能契约 │ 系统架构  │ 场景模板   │
│ 知识领域  │ 项目记忆 │ 代码质量 │ 验收标准 │ 模块划分  │ 变量注入   │
│ 输出格式  │ 会话记忆 │ 依赖管控 │ 接口定义 │ 一致性检查│ 效果追踪   │
│ 协作模式  │ 决策历史 │ 安全红线 │ 数据模型 │ 架构守护  │ 智能推荐   │
└──────────┴──────────┴──────────┴──────────┴───────────┴────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│         统一数据层 (SQLite + 文件系统 + hotspot 共享层)              │
│  cg_* 表 │ knowledge_* 表(复用) │ secrets(复用) │ codegarden/ 目录  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. 核心模块详细设计

### 5.1 M1 项目看板模块（Project Board）

#### 5.1.1 项目卡片系统

每个项目以卡片形式呈现，包含：

```
┌────────────────────────────────────┐
│ 🔴 运行中  [项目名]        [⋮]     │
│ 描述：AI对话助手的Web界面            │
│                                    │
│ 标签: #AI #React #实验性            │
│ 生命周期: 活跃开发 → 第3周           │
│ 来源: 🔀 fork from upstream/repo    │
│ 上游落后: 12 commits ⚠️             │
│                                    │
│ [代码] [文档] [服务] [依赖]         │
│ 最后更新: 2小时前  作者: @me        │
│                                    │
│ 健康度: ████████░░ 80%              │
└────────────────────────────────────┘
```

#### 5.1.2 项目生命周期状态机

```
构思(ideation) → 原型(prototype) → 开发(development) →
测试(testing) → 运行(running) → 维护(maintenance) →
归档(archived) / 废弃(deprecated)
```

**自动状态流转规则**：
- 7天无提交 + 无运行记录 → 自动标记"待评估"
- 30天无活动 → 推送"归档建议"
- 依赖存在高危漏洞 → 标记"需修复"
- 上游落后 >50 commits → 标记"需同步"

#### 5.1.3 项目来源类型（source_type）

| 类型 | 字段 | 说明 |
|------|------|------|
| `vibe` | local_path | 自己氛围编程产出，无 upstream |
| `fork` | upstream_url, local_path | 二开他人项目，需跟踪上游 |
| `imported` | repo_url, local_path | 从 GitHub 直接导入（自己的 repo） |
| `reference` | repo_url | 仅参考，不本地开发 |

#### 5.1.3a 与 hotspot github_collector 的协同（资讯→二开源→项目）

**关键认知**：hotspot 既有 `github_collector.py` 收集的 GitHub 资讯，本质是**用户二开的候选源池**，不是单纯的阅读资讯。

**转化通道**：
```
github_collector 抓取 trending/热门 repo
    ↓
进入 knowledge_items (type=github, domain=...)
    ↓
用户在知识详情页发现值得二开的项目
    ↓
点击「加入 CodeGarden」按钮
    ↓
CodeGarden 创建 cg_projects 记录 (source_type=fork 或 reference)
    ↓
保留反向链接 knowledge_item_id (cg_projects.source_item_id)
    ↓
若用户填 local_path → fork 项目进入开发跟踪
若仅参考 → reference 类型，仅跟踪上游更新
```

**数据流方向**：
- `github_collector.py` → `knowledge_items` 表 → （用户决策）→ `cg_projects` 表
- `cg_projects.source_item_id` 字段记录反向溯源（新增字段，见 6.2.1）

**API 端点**（详见 7.2.2）：
- `POST /api/codegarden/projects/from-knowledge/{item_id}` — 从 knowledge_item 一键创建项目

**前端入口**：
- 知识详情页（KnowledgePage）新增「加入 CodeGarden」按钮（仅对 type=github 的 item 显示）
- CodeGarden 看板新增「从知识库导入」入口，列出 type=github 的 knowledge_items 候选

**与既有 github_collector 的边界**：
- `github_collector.py`：**资讯发现层** — 抓取 trending/热门 repo 作为知识条目
- CodeGarden M1：**项目管理层** — 用户决定二开/参考后，纳入项目跟踪
- 两者数据流向单向（knowledge → codegarden），不反向同步
- GitHub HTTP 客户端模式可复用（不重新造 httpx 调用模式）

#### 5.1.4 智能分类与标签

- **自动标签**：基于 `package.json`、`requirements.txt`、`Dockerfile`、`go.mod` 等自动识别技术栈
- **项目类型**：Web 应用 / API 服务 / CLI 工具 / 爬虫 / 实验脚本 / 库/包
- **重要性评级**：用户手动标记 ⭐ ～ ⭐⭐⭐⭐⭐
- **domain 字段**：复用 hotspot 既有 domain 概念（frontend/backend/security/ai 等）

#### 5.1.5 GitHub 导入与上游跟踪

**导入流程**：
```
用户输入 GitHub URL
    ↓
调用 GitHub REST API 拉 repo 元信息
    ↓
识别 upstream（fork 源）
    ↓
扫描本地路径（可选）
    ↓
用户确认 → 创建 cg_projects 记录
    ↓
首次同步 commits behind/ahead
    ↓
项目卡片出现在看板
```

**上游跟踪**：
- 字段：`commits_behind`, `commits_ahead`, `upstream_default_branch`, `last_synced_at`
- 同步方式：
  - 手动触发（项目详情页"立即同步"按钮）
  - 定时任务（复用 hotspot scheduler，默认每日 09:00）
  - 任务队列：复用 `knowledge_tasks` 表，`task_type=project_sync`
- 数据来源：GitHub REST API `compare` 端点
- 显示信息：
  - 落后 commits 数 + 最近 5 条 commit message
  - 上游最新 release tag
  - 上游最近 7 天活跃度

#### 5.1.6 项目知识库

每个项目关联：
- `README.md` 自动渲染（读取 local_path）
- 架构决策记录（ADR）— 存 cg_project_activities
- 踩坑记录 / 解决方案
- 相关项目链接（双向关联，cg_project_links）
- **跨子系统关联**：knowledge_items frontmatter 可加 `project_id` 字段，反查关联项目

---

### 5.2 M2 服务网格模块（Service Mesh）— 本机版

#### 5.2.1 服务注册与发现

自动扫描并注册本机服务：

| 属性 | 说明 |
|------|------|
| 服务名 | 唯一标识，支持命名空间（如 `ai-assistant.web`） |
| 服务类型 | HTTP / WebSocket / gRPC / 静态站点 / 数据库 |
| 运行方式 | Docker 容器 / PM2 进程 / 系统服务 / 裸进程 |
| 健康检查 | HTTP 探针 / TCP 探针 / 自定义脚本 |
| 资源限制 | CPU / 内存 / 磁盘配额 |

**自动发现机制**：
- 启动时扫描 `lsof -i :PORT_RANGE`（如 3000-9999）
- Docker：`docker ps` 解析
- PM2：`pm2 list` 解析
- 与项目关联：通过端口反查所属项目

#### 5.2.2 服务拓扑图

可视化展示本机服务间调用关系（前端用 React Flow 或 Cytoscape.js）：

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Nginx   │────→│  Web App │────→│  API Svc │
│  (网关)  │     │  (3000)  │     │  (8080)  │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
                      ↓                ↓
                 ┌──────────┐    ┌──────────┐
                 │  Redis   │    │ Postgres │
                 │  (6379)  │    │  (5432)  │
                 └──────────┘    └──────────┘
```

**交互功能**：
- 点击节点查看详情
- 拖拽调整布局
- 异常服务红色高亮
- 实时流量动画（可选）

#### 5.2.3 统一日志与监控

- 自动收集各服务日志（Docker logs / PM2 logs / 文件 tail）
- 关键词搜索（复用 hotspot 既有搜索引擎）
- 服务响应时间、错误率图表
- 资源使用率趋势图（psutil）

---

### 5.3 M3 资源中枢模块（Resource Hub）— 本机版

#### 5.3.1 端口管理

```
端口池视图：
┌──────┬─────────────┬──────────┬────────┐
│ 端口 │ 占用服务     │ 状态     │ 操作   │
├──────┼─────────────┼──────────┼────────┤
│ 3000 │ web-app     │ 🟢 运行中 │ 释放   │
│ 3001 │ ─           │ ⚪ 空闲   │ 预留   │
│ 8080 │ api-service │ 🟢 运行中 │ 释放   │
│ 5432 │ postgres    │ 🟢 运行中 │ 释放   │
└──────┴─────────────┴──────────┴────────┘
```

**智能端口分配**：
- 自动检测端口冲突
- 启动服务时自动分配可用端口
- 支持端口段预留（如 3000-3010 给前端项目）
- **hotspot 自身端口 8898 受保护**，禁止释放

#### 5.3.2 域名与路由管理

- 本地开发域名映射（如 `ai-assistant.local` → `localhost:3000`）
- 反向代理配置（Nginx/Caddy 规则自动生成）
- 通过修改本机 hosts 或本地 DNS 实现

#### 5.3.3 环境变量与密钥

- 项目级环境变量模板（存 cg_resources，type=env_template）
- 敏感信息加密存储：**复用 hotspot secrets 系统**（Fernet 加密）
- 环境变量差异对比（开发/测试/生产）
- **不新建加密体系**，直接调用 hotspot secrets_service

#### 5.3.4 存储卷管理

- Docker Volume 映射关系
- 数据备份策略
- 存储空间使用监控

---

### 5.4 M4 联动引擎模块（Orchestration Engine）

#### 5.4.1 依赖图谱

自动解析项目间依赖：
- **代码依赖**：A 项目引用了 B 项目的模块
- **服务依赖**：A 服务调用 B 服务的 API
- **数据依赖**：A 项目读写 B 项目的数据库

**依赖影响分析**：
> 修改 `utils-lib` 将影响以下 5 个项目：[list]

依赖关系存 `cg_dependencies` 表（source_id, target_id, type, metadata）。

#### 5.4.2 事件总线

统一事件系统，支持：

| 事件类型 | 触发条件 | 可执行动作 |
|---------|---------|-----------|
| 代码推送 | Git push（hook 或定时扫描） | 自动重启关联服务 |
| 服务异常 | 健康检查失败 | 发送通知 / 自动重启 |
| 端口冲突 | 启动失败 | 自动分配新端口 |
| 依赖更新 | 上游项目发布新版本 | 推送更新提醒 |
| 项目归档 | 30 天无活动 | 自动停止服务 + 释放端口 |

**实现方式**：复用 hotspot scheduler + 任务队列，事件存 SQLite（轻量级，不引入 Redis/Kafka）。

#### 5.4.3 自动化工作流（Playbook）

可视化编排本机任务：

```
工作流：部署新前端项目
├── 步骤1: 克隆代码仓库
├── 步骤2: 安装依赖 (npm install)
├── 步骤3: 运行测试 (npm test)
├── 步骤4: 构建产物 (npm run build)
├── 步骤5: 分配端口（检查3000-3010范围）
├── 步骤6: 启动服务 (pm2 start)
├── 步骤7: 配置 Nginx 反向代理
├── 步骤8: 注册到服务网格
└── 步骤9: 发送部署成功通知
```

Playbook 以 YAML 定义，存 `codegarden/playbooks/` 目录。

---

### 5.5 M5 生命周期管理模块（Lifecycle Management）

#### 5.5.1 项目健康度评分

综合评分算法：

```
健康度 = w1×代码活跃度 + w2×文档完整度 + w3×依赖新鲜度
       + w4×测试覆盖率 + w5×安全评分 + w6×资源利用率
```

| 维度 | 权重 | 数据来源 |
|------|------|---------|
| 代码活跃度 | 20% | 最近提交频率（git log） |
| 文档完整度 | 15% | README/文档存在性 |
| 依赖新鲜度 | 20% | 依赖包版本落后程度 |
| 安全评分 | 20% | 漏洞扫描结果（pip-audit / npm audit） |
| 资源效率 | 15% | CPU/内存使用率 |
| 用户反馈 | 10% | 手动标记/使用频率 |

#### 5.5.2 技术债看板

- 过期依赖列表（含升级建议）
- 安全漏洞追踪
- 性能瓶颈标记
- 待重构模块清单

#### 5.5.3 归档与清理策略

- 自动归档规则配置
- 一键清理废弃容器/镜像/卷
- 项目导出（生成可迁移的压缩包）
- **与 hotspot 同步包集成**：归档项目自动加入同步包

---

### 5.6 M6 AI Skill 管理（技能定义）

> **设计哲学**：将 AI 的"角色能力"资产化、版本化管理。每个 Skill 是一个可复用的 AI 角色模板。

#### 5.6.1 与 hotspot 既有 Skill 的关系

**复用策略**：扩展 `knowledge_skills` 表，**不新建表**。

| 字段 | 来源 | 用途 |
|------|------|------|
| id, name, display_name, version | 既有 | 基础信息 |
| domain | 既有 | 知识领域 |
| skill_type | **新增** | 区分 `knowledge`（知识库用）/ `development`（开发用） |
| capabilities | **新增**（JSON） | 能力清单 |
| constraints | **新增**（JSON） | 约束条件 |
| output_format | **新增**（JSON） | 输出格式偏好 |
| system_prompt | **新增**（TEXT） | 系统提示词 |
| few_shot_examples | **新增**（JSON） | 示例 |
| success_metrics | **新增**（JSON） | 成功指标 |
| usage_count, avg_rating | **新增** | 效果追踪 |

**筛选机制**：API 默认按 `skill_type` 过滤，知识库页只看 `knowledge`，CodeGarden 页只看 `development`。

#### 5.6.2 数据结构（扩展后）

```json
{
  "id": "skill-uuid",
  "name": "React-Performance-Expert",
  "display_name": "React 性能优化专家",
  "version": "1.2.0",
  "skill_type": "development",
  "domain": ["frontend", "react", "performance"],
  "capabilities": [
    "识别 React 渲染瓶颈",
    "优化 useMemo/useCallback 使用",
    "分析 Bundle 体积",
    "推荐代码分割策略"
  ],
  "constraints": [
    "不引入新的依赖除非必要",
    "保持现有组件接口不变",
    "优先使用 React 内置 API"
  ],
  "output_format": {
    "code_style": "函数组件 + Hooks",
    "comment_language": "zh-CN",
    "include_benchmark": true
  },
  "system_prompt": "你是一位专注于 React 性能优化的资深前端工程师...",
  "few_shot_examples": [
    { "input": "...", "output": "...", "explanation": "..." }
  ],
  "success_metrics": {
    "bundle_size_reduction": ">10%",
    "render_time_improvement": ">20%"
  },
  "created_at": "2026-07-01",
  "updated_at": "2026-07-19",
  "usage_count": 42,
  "avg_rating": 4.8
}
```

#### 5.6.3 核心功能

| 功能 | 说明 |
|------|------|
| **Skill 市场** | 内置常用开发 Skill 模板（全栈、DBA、安全审计、UI 设计等） |
| **自定义 Skill** | 可视化编辑器：能力清单 + 约束条件 + 系统提示词 + 示例 |
| **Skill 组合** | 一个项目可激活多个 Skill（如「React 专家」+「TypeScript 严格模式」） |
| **Skill 版本** | 迭代优化 Skill 定义，保留历史版本可回滚 |
| **效果追踪** | 记录使用该 Skill 后的代码质量评分变化 |

#### 5.6.4 与项目联动

- 项目创建时**推荐 Skill 组合**（基于技术栈自动匹配）
- 代码审查时**调用对应 Skill** 进行专项审计
- 重构任务前**切换 Skill** 改变 AI 行为模式

---

### 5.7 M7 AI Memory 三层记忆管理

#### 5.7.1 三层记忆架构

```
┌─────────────────────────────────────────┐
│  ③ 长期记忆（Long-term Memory）          │
│     跨项目、跨会话的个人编码 DNA          │
│     • 技术偏好（缩进、命名、架构风格）     │
│     • 常用工具链偏好                      │
│     • 个人知识库（踩过的坑、最佳实践）      │
├─────────────────────────────────────────┤
│  ② 项目记忆（Project Memory）            │
│     当前项目的上下文全景图                 │
│     • 架构决策记录（ADR）                 │
│     • 模块依赖关系                        │
│     • 已实现的业务规则                    │
│     • 待办事项与技术债                     │
├─────────────────────────────────────────┤
│  ① 会话记忆（Session Memory）            │
│     当前对话的短期上下文                   │
│     • 本轮修改的文件清单                   │
│     • 当前讨论的功能点                     │
│     • 用户的临时指令                      │
└─────────────────────────────────────────┘
```

#### 5.7.2 与 hotspot 既有记忆系统的关系

hotspot 已有：
- `user_profile.md`（用户级偏好）
- `project_memory.md`（项目级规则）
- `session_memory_*.jsonl`（会话级）

**复用策略**：
- **长期记忆** → 直接读/写 `~/.trae-cn/memory/user_profile.md`（CodeGarden 提供编辑 UI）
- **项目记忆** → 新建 `codegarden/memory/{project_id}.md`，与 hotspot 项目记忆并列
- **会话记忆** → `cg_memories` 表（type=session），轻量级，自动过期（7 天）

#### 5.7.3 核心功能

| 层级 | 功能 | 自动/手动 | 存储位置 |
|------|------|-----------|---------|
| **会话记忆** | 自动记录当前对话修改了哪些文件、产生了哪些决策 | 自动 | cg_memories 表 |
| **项目记忆** | 项目级知识库：ADR、业务规则、API 约定、数据字典 | 半自动 | codegarden/memory/*.md |
| **长期记忆** | 用户画像：编码风格、技术栈熟练度、常见错误模式 | 自动学习 | user_profile.md |

#### 5.7.4 记忆注入机制

每次与 AI 交互前，系统自动组装 Context：

```markdown
【长期记忆】
- 用户偏好：2空格缩进、函数组件优先、中文注释
- 技术栈：React 18 + TypeScript + Tailwind + Zustand

【项目记忆 - ai-assistant】
- 架构：前端 React(Vite) + 后端 Fastify + PostgreSQL
- 已实现的模块：用户认证、对话管理、消息存储
- 待办：接入 WebSocket 实时推送
- 已知问题：消息列表大数据量渲染卡顿（待优化）

【会话记忆】
- 当前任务：优化消息列表渲染性能
- 已修改文件：MessageList.tsx（添加了虚拟滚动）
- 用户最新指令："用 react-window 替换现有实现"
```

#### 5.7.5 记忆编辑与纠正

- **记忆看板**：可视化查看 AI 记住了什么
- **纠正记忆**：用户可标记"AI 记错了，应该是..."
- **遗忘指令**：支持"忘掉刚才关于 XX 的假设"
- **记忆导出**：将项目记忆导出为 `PROJECT_CONTEXT.md`，供其他 AI 工具使用

---

### 5.8 M8 AI Constraint（行为约束）

#### 5.8.1 约束分类体系

```yaml
constraints:
  # 1. 文件系统约束
  filesystem:
    - scope: "只能修改 src/ 目录下的文件"
    - protected: ["package.json", "tsconfig.json", ".env"]
    - max_files_per_session: 10
    - require_approval_for: ["delete", "rename"]

  # 2. 代码质量约束
  code_quality:
    - test_coverage_min: 80
    - max_function_lines: 50
    - max_cyclomatic_complexity: 10
    - forbidden_patterns: ["eval(", "innerHTML", "console.log"]
    - require_types: true

  # 3. 依赖管理约束
  dependencies:
    - allow_new: "ask_first"
    - preferred: ["lodash-es", "date-fns"]
    - forbidden: ["moment", "jquery"]
    - max_bundle_size_increase: "50kb"

  # 4. 安全约束
  security:
    - no_secrets_in_code: true
    - sql_injection_check: true
    - xss_prevention: true
    - dependency_vulnerability_check: true

  # 5. 资源约束
  resources:
    - max_tokens_per_request: 4000
    - max_api_calls_per_hour: 100
    - cost_limit_per_day: "$5"

  # 6. 流程约束
  workflow:
    - plan_before_code: true
    - test_before_merge: true
    - doc_update_required: ["README.md", "CHANGELOG.md"]
```

#### 5.8.2 约束执行机制

| 机制 | 说明 |
|------|------|
| **预检查** | AI 生成代码前，先检查约束条件是否满足 |
| **实时拦截** | 检测到违规操作时，暂停并提示用户确认 |
| **后审计** | 代码提交后，自动运行约束检查并生成报告 |
| **约束模板** | 按项目类型预设（Web 应用 / API / CLI / 库） |

#### 5.8.3 违规处理策略

- **阻断**：直接拒绝执行（如删除核心配置文件）
- **警告**：执行但标记风险（如引入大型依赖）
- **记录**：仅记录日志（如代码风格偏差）

---

### 5.9 M9 Spec 规格管理

#### 5.9.1 功能定义

Spec 是**人机协作的契约**——在写代码之前，先定义"做什么、不做什么、做到什么程度"。

#### 5.9.2 Spec 模板结构

```markdown
# Spec: 消息列表虚拟滚动优化

## 背景
当前消息列表在 1000+ 条消息时渲染卡顿，FPS 低于 30。

## 目标
- 支持 10,000+ 条消息流畅滚动（FPS > 55）
- 保持现有功能完整（选中、复制、跳转）
- 首屏渲染时间 < 100ms

## 非目标（明确不做）
- 不做消息搜索功能
- 不改动消息数据结构
- 不支持无限滚动加载

## 验收标准（AC）
1. [ ] 使用 react-window 实现虚拟滚动
2. [ ] 动态高度消息项正确计算
3. [ ] 滚动到指定消息功能保留
4. [ ] 单元测试覆盖率 > 80%
5. [ ] 在 Chrome/Firefox/Safari 测试通过

## 技术方案（可选，AI 可补充）
- 库选型：react-window vs react-virtualized
- 实现要点：...

## 关联资源
- 相关 Issue: #123
- 设计稿: [Figma 链接]
- 参考实现: [GitHub 链接]
```

#### 5.9.3 核心功能

| 功能 | 说明 |
|------|------|
| **Spec 创建** | 从模板创建，支持 AI 辅助生成（用户描述需求 → AI 输出 Spec 草案） |
| **Spec 评审** | AI 自检：检查 Spec 是否完整、是否有矛盾、技术方案是否可行 |
| **Spec 锁定** | 确认后锁定，AI 按 Spec 执行，防止 scope creep |
| **Spec 追踪** | 实时显示哪些 AC 已完成，哪些 pending |
| **Spec 版本** | 需求变更时生成新版本，保留变更历史 |

#### 5.9.4 与开发流程集成

```
用户描述需求 ──→ AI 生成 Spec 草案 ──→ 用户确认/修改 ──→ Spec 锁定
                                                          ↓
                                               AI 按 Spec 生成代码
                                                          ↓
                                               自动对照 AC 验收
                                                          ↓
                                               Spec 完成归档
```

---

### 5.10 M10 SDD 软件设计文档管理

#### 5.10.1 功能定义

SDD 是项目的**架构宪法**——定义系统如何组织、模块如何交互、数据如何流动。

#### 5.10.2 SDD 核心章节

```markdown
# SDD: AI-Assistant 项目架构设计

## 1. 系统架构
[架构图：C4 Model Level 3 - 组件图]

## 2. 模块划分
| 模块 | 职责 | 技术栈 | 负责人 |
|------|------|--------|--------|
| Web Frontend | 用户界面 | React 18 + Vite | AI/人 |
| API Gateway | 路由/认证 | Fastify | AI/人 |
| Chat Service | 对话逻辑 | Node.js | AI/人 |
| Message Store | 消息持久化 | PostgreSQL | AI/人 |

## 3. 数据模型
## 4. API 设计
## 5. 状态管理
## 6. 错误处理策略
## 7. 安全设计
## 8. 性能基线
## 9. 变更日志
```

#### 5.10.3 核心功能

| 功能 | 说明 |
|------|------|
| **AI 辅助生成** | 基于项目代码自动反向生成 SDD（代码 → 文档） |
| **一致性检查** | 检测代码实现是否与 SDD 定义冲突 |
| **变更影响分析** | 修改 SDD 时，自动标记受影响的代码模块 |
| **架构守护** | AI 生成代码时，强制参考 SDD 约束 |

#### 5.10.4 Spec vs SDD 关系

| 维度 | Spec | SDD |
|------|------|-----|
| **粒度** | 功能级（一个需求） | 系统级（整个项目） |
| **时效** | 随需求创建和销毁 | 长期维护，随架构演进 |
| **受众** | AI 执行代码时参考 | AI 理解上下文时参考 |
| **产出时机** | 需求阶段 | 设计阶段 / 持续维护 |

---

### 5.11 M11 Prompt 资产库

#### 5.11.1 Prompt 数据结构

```json
{
  "id": "prompt-uuid",
  "name": "生成 CRUD API",
  "category": "backend",
  "tags": ["fastify", "prisma", "rest"],
  "template": "请为 {{entity}} 生成完整的 CRUD API...",
  "variables": [
    { "name": "entity", "type": "string", "required": true },
    { "name": "entity_definition", "type": "text", "required": true }
  ],
  "context_injection": ["project_memory", "sdd_api_design"],
  "example_output": "...",
  "success_criteria": "生成可运行的路由文件 + 测试文件",
  "usage_stats": {
    "used_count": 156,
    "success_rate": 92,
    "avg_tokens": 2400
  },
  "version": "2.1.0",
  "author": "user",
  "is_builtin": false
}
```

#### 5.11.2 核心功能

| 功能 | 说明 |
|------|------|
| **场景模板库** | 内置 50+ 高频场景模板（生成组件、写测试、重构、Debug、Code Review 等） |
| **变量注入** | 自动填充项目上下文（如 `{{project_tech_stack}}` 自动替换为 React+TS） |
| **效果追踪** | 记录每次使用的结果质量（用户评分 + AI 输出是否通过测试） |
| **Prompt 优化** | AI 辅助改进提示词（分析失败案例 → 建议模板调整） |
| **个人 Prompt 市场** | 导出/导入 Prompt，形成个人知识资产 |
| **快捷触发** | 在代码编辑器中 `// @prompt:生成单元测试` 快速调用 |

#### 5.11.3 智能推荐机制

根据当前上下文自动推荐 Prompt：
- 用户在 `*.test.ts` 文件中 → 推荐"生成测试用例"Prompt
- 用户选中一段复杂函数 → 推荐"重构简化"Prompt
- 项目技术栈是 React → 过滤掉 Vue 相关 Prompt

---

### 5.12 M12 AI 调用配额管理

#### 5.12.1 配额维度

| 维度 | 说明 |
|------|------|
| 每日 Token 上限 | 跨项目共享，超限告警 |
| 每小时请求数 | 防止突发流量 |
| 单项目配额 | 防止单个项目吃掉所有预算 |
| 单 Skill 配额 | 防止某个 Skill 滥用 |

#### 5.12.2 用量监控

- 实时 Token 消耗看板（按项目/Skill/时间维度）
- 成本估算（按模型单价折算）
- 异常告警（突增、超限）

#### 5.12.3 上下文压缩策略

- 单会话超过阈值时，自动摘要历史对话
- 长期未访问的会话记忆自动归档
- 与 M7 Memory 协同：高频访问的记忆提升优先级

---

## 6. 数据模型设计

### 6.1 核心实体关系

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  cg_projects│◄─────►│ cg_services │◄─────►│cg_resources │
│   项目      │  1:N  │   服务      │  1:N  │   资源      │
└──────┬──────┘       └──────┬──────┘       └─────────────┘
       │                     │
       │              ┌──────┴──────┐
       │              │ cg_dependencies│
       │              │   依赖关系   │
       └─────────────►└─────────────┘
              1:N

┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│cg_project_  │       │cg_project_  │       │cg_project_  │
│  stages     │       │  links      │       │  activities │
│   阶段      │       │   关联      │       │   活动      │
└─────────────┘       └─────────────┘       └─────────────┘

┌──────────────────────────────────────────────────────────┐
│                    AI 协作层（cg_*）                       │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│cg_       │cg_       │cg_       │cg_       │cg_prompts    │
│memories  │constraints│specs    │sdds      │              │
└──────────┴──────────┴──────────┴──────────┴──────────────┘

┌──────────────────────────────────────────────────────────┐
│           hotspot 共享层（复用，不新建）                   │
├──────────────┬─────────────┬─────────────┬──────────────┤
│knowledge_    │knowledge_   │  secrets    │ scheduled_   │
│  skills(扩展)│  tasks(扩展)│  密钥       │  tasks(扩展) │
└──────────────┴─────────────┴─────────────┴──────────────┘
```

### 6.2 表结构定义

#### 6.2.1 cg_projects（项目主表）

```sql
CREATE TABLE cg_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    type TEXT NOT NULL,              -- web_application / api_service / cli / crawler / library / experiment
    source_type TEXT NOT NULL,       -- vibe / fork / imported / reference
    lifecycle_stage TEXT NOT NULL,   -- ideation / prototype / development / testing / running / maintenance / archived / deprecated
    health_score INTEGER DEFAULT 0,
    
    -- 来源信息
    local_path TEXT,
    repo_url TEXT,
    upstream_url TEXT,               -- fork 源
    upstream_default_branch TEXT,
    commits_behind INTEGER DEFAULT 0,
    commits_ahead INTEGER DEFAULT 0,
    last_synced_at TEXT,

    -- 反向溯源（从 knowledge_item 转化时记录）
    source_item_id TEXT,             -- 关联 knowledge_items.id (github 资讯转化)
    source_type_detail TEXT,         -- 转化详情: trending/github_search/manual 等
    
    -- 元数据
    tags TEXT,                       -- JSON array
    tech_stack TEXT,                 -- JSON array (自动识别)
    domain TEXT,                     -- frontend/backend/security/ai/...
    priority INTEGER DEFAULT 0,      -- 0-5 星
    
    -- 关联
    active_skill_ids TEXT,           -- JSON array of skill ids
    
    -- 时间
    created_at TEXT NOT NULL,
    last_activity_at TEXT,
    archived_at TEXT
);
```

#### 6.2.2 cg_project_stages（阶段/交付物）

```sql
CREATE TABLE cg_project_stages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id),
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    deliverable_type TEXT,           -- code / doc / test / config / release
    deliverable_url TEXT,
    deliverable_path TEXT,
    commit_sha TEXT,
    status TEXT NOT NULL,            -- planned / wip / done / skipped
    notes TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

#### 6.2.3 cg_project_links（关联 repo）

```sql
CREATE TABLE cg_project_links (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id),
    link_type TEXT NOT NULL,         -- upstream / reference / inspiration / dependency
    url TEXT NOT NULL,
    label TEXT,
    commits_behind INTEGER,
    commits_ahead INTEGER,
    last_synced_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
```

#### 6.2.4 cg_project_activities（活动日志）

```sql
CREATE TABLE cg_project_activities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id),
    activity_type TEXT NOT NULL,     -- commit / note / decision / release / status_change / sync
    content TEXT NOT NULL,
    metadata TEXT,                   -- JSON
    created_at TEXT NOT NULL
);
```

#### 6.2.5 cg_services（本机服务）

```sql
CREATE TABLE cg_services (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES cg_projects(id),
    name TEXT NOT NULL,
    namespace TEXT,                  -- 如 ai-assistant.web
    type TEXT NOT NULL,              -- http / websocket / grpc / static / database
    runtime TEXT NOT NULL,           -- docker / pm2 / system / bare
    status TEXT NOT NULL,            -- running / stopped / error / unknown
    endpoint_host TEXT,
    endpoint_port INTEGER,
    endpoint_domain TEXT,
    health_check_type TEXT,          -- http / tcp / script
    health_check_path TEXT,
    health_check_interval INTEGER DEFAULT 30,
    cpu_limit TEXT,
    memory_limit TEXT,
    dependencies TEXT,               -- JSON array of service ids
    env_vars TEXT,                   -- JSON
    created_at TEXT NOT NULL,
    last_checked_at TEXT
);
```

#### 6.2.6 cg_resources（资源）

```sql
CREATE TABLE cg_resources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,              -- port / domain / env_template / volume
    value TEXT NOT NULL,             -- 端口号 / 域名 / 模板名 / 卷名
    status TEXT NOT NULL,            -- allocated / free / reserved
    owner_service_id TEXT REFERENCES cg_services(id),
    owner_project_id TEXT REFERENCES cg_projects(id),
    metadata TEXT,                   -- JSON
    reserved_until TEXT,
    created_at TEXT NOT NULL
);
```

#### 6.2.7 cg_dependencies（依赖关系）

```sql
CREATE TABLE cg_dependencies (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,       -- project / service
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,       -- project / service
    target_id TEXT NOT NULL,
    dep_type TEXT NOT NULL,          -- code / service / data
    metadata TEXT,                   -- JSON
    created_at TEXT NOT NULL
);
```

#### 6.2.8 cg_memories（三层记忆）

```sql
CREATE TABLE cg_memories (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,              -- long_term / project / session
    project_id TEXT REFERENCES cg_projects(id),
    session_id TEXT,
    category TEXT,                   -- preference / decision / context / knowledge
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source TEXT NOT NULL,            -- user_explicit / ai_inferred
    created_at TEXT NOT NULL,
    last_accessed_at TEXT,
    expires_at TEXT                  -- session 类型自动过期
);
```

#### 6.2.9 cg_constraints（约束规则）

```sql
CREATE TABLE cg_constraints (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES cg_projects(id),  -- null 表示全局
    category TEXT NOT NULL,          -- filesystem / code_quality / dependencies / security / resources / workflow
    rule_key TEXT NOT NULL,
    rule_value TEXT NOT NULL,
    severity TEXT NOT NULL,          -- block / warn / log
    is_template BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### 6.2.10 cg_specs（Spec 规格）

```sql
CREATE TABLE cg_specs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL,            -- draft / locked / in_progress / completed / cancelled
    version TEXT NOT NULL,
    background TEXT,
    goals TEXT,                      -- JSON array
    non_goals TEXT,                  -- JSON array
    acceptance_criteria TEXT,        -- JSON array of {id, description, status}
    technical_approach TEXT,
    related_resources TEXT,          -- JSON array
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### 6.2.11 cg_sdds（SDD 设计文档）

```sql
CREATE TABLE cg_sdds (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id),
    version TEXT NOT NULL,
    sections TEXT NOT NULL,          -- JSON: {architecture, modules, data_model, api_design, ...}
    adrs TEXT,                       -- JSON array
    consistency_status TEXT,         -- ok / warning / error
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### 6.2.12 cg_prompts（Prompt 资产库）

```sql
CREATE TABLE cg_prompts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT,                       -- JSON array
    template TEXT NOT NULL,
    variables TEXT,                  -- JSON array
    context_injection TEXT,          -- JSON array
    example_output TEXT,
    success_criteria TEXT,
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_tokens INTEGER DEFAULT 0,
    avg_rating REAL DEFAULT 0,
    version TEXT NOT NULL,
    author TEXT,
    is_builtin BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 6.3 既有表扩展

#### 6.3.1 knowledge_skills 扩展字段

```sql
ALTER TABLE knowledge_skills ADD COLUMN skill_type TEXT DEFAULT 'knowledge';
ALTER TABLE knowledge_skills ADD COLUMN capabilities TEXT;       -- JSON
ALTER TABLE knowledge_skills ADD COLUMN constraints_json TEXT;   -- JSON (避开 SQL 关键字)
ALTER TABLE knowledge_skills ADD COLUMN output_format TEXT;      -- JSON
ALTER TABLE knowledge_skills ADD COLUMN system_prompt TEXT;
ALTER TABLE knowledge_skills ADD COLUMN few_shot_examples TEXT;  -- JSON
ALTER TABLE knowledge_skills ADD COLUMN success_metrics TEXT;    -- JSON
ALTER TABLE knowledge_skills ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_skills ADD COLUMN avg_rating REAL DEFAULT 0;
```

#### 6.3.2 knowledge_tasks 扩展 task_type

新增 `task_type` 取值：
- `project_sync` — GitHub 上游同步
- `service_health_check` — 服务健康检查
- `sdd_consistency_check` — SDD 一致性检查
- `lifecycle_scan` — 生命周期扫描
- `prompt_optimize` — Prompt 优化

#### 6.3.3 scheduled_tasks 扩展

新增 CodeGarden 相关定时任务：
- `cg_upstream_sync` — 每日 09:00 GitHub 上游同步
- `cg_service_scan` — 每 5 分钟本机服务扫描
- `cg_health_score` — 每日 06:00 健康度评分
- `cg_lifecycle_check` — 每周一 06:00 生命周期检查

---

## 7. API 设计

### 7.1 API 路由前缀

所有 CodeGarden API 统一前缀 `/api/codegarden/*`，与 hotspot 既有 API 解耦。

### 7.2 核心 API 端点

#### 7.2.1 项目管理

```
GET    /api/codegarden/projects                    列表（支持过滤/排序/分页）
POST   /api/codegarden/projects                    创建
GET    /api/codegarden/projects/{id}               详情
PATCH  /api/codegarden/projects/{id}               更新
DELETE /api/codegarden/projects/{id}               删除
POST   /api/codegarden/projects/{id}/archive       归档
POST   /api/codegarden/projects/{id}/restore       恢复
PATCH  /api/codegarden/projects/{id}/lifecycle     切换生命周期状态
GET    /api/codegarden/projects/{id}/timeline      阶段时间线
GET    /api/codegarden/projects/{id}/activities    活动日志
```

#### 7.2.2 GitHub 导入与上游跟踪

```
POST   /api/codegarden/github/import                导入 GitHub 项目
  Body: { url, local_path?, auto_sync? }
POST   /api/codegarden/projects/from-knowledge/{item_id}  从 knowledge_item 一键转化
  Body: { source_type?: fork|reference, local_path? }
GET    /api/codegarden/projects/candidates           候选二开源（type=github 的 knowledge_items）
POST   /api/codegarden/projects/{id}/sync           手动触发上游同步
GET    /api/codegarden/projects/{id}/upstream       上游状态详情
GET    /api/codegarden/projects/{id}/upstream/commits  上游最近 commits
```

#### 7.2.3 服务网格

```
GET    /api/codegarden/services                     服务列表
POST   /api/codegarden/services                     注册服务
GET    /api/codegarden/services/{id}                详情
PATCH  /api/codegarden/services/{id}                更新
DELETE /api/codegarden/services/{id}                注销
POST   /api/codegarden/services/{id}/restart        重启
GET    /api/codegarden/services/topology            拓扑图数据
GET    /api/codegarden/services/{id}/logs           日志
GET    /api/codegarden/services/{id}/metrics        指标
```

#### 7.2.4 资源中枢

```
GET    /api/codegarden/resources?type=port          端口池
POST   /api/codegarden/resources/ports/allocate     分配端口
POST   /api/codegarden/resources/ports/{port}/release  释放端口
GET    /api/codegarden/resources/domains            域名映射
GET    /api/codegarden/resources/volumes            存储卷
```

#### 7.2.5 AI 协作

```
# Skill（扩展既有 skill API）
GET    /api/codegarden/skills?skill_type=development  开发 Skill 列表
POST   /api/codegarden/skills                          创建开发 Skill
GET    /api/codegarden/skills/{id}                     详情
PATCH  /api/codegarden/skills/{id}                     更新
POST   /api/codegarden/skills/{id}/rate                评分

# Memory
GET    /api/codegarden/memories?type=long_term        长期记忆
GET    /api/codegarden/projects/{id}/memories         项目记忆
POST   /api/codegarden/projects/{id}/memories         添加项目记忆
PATCH  /api/codegarden/memories/{id}                   编辑
DELETE /api/codegarden/memories/{id}                   删除
POST   /api/codegarden/projects/{id}/memories/export  导出为 PROJECT_CONTEXT.md

# Constraint
GET    /api/codegarden/projects/{id}/constraints      项目约束
POST   /api/codegarden/projects/{id}/constraints      添加约束
GET    /api/codegarden/constraints/templates          约束模板
POST   /api/codegarden/constraints/check              检查违规

# Spec
GET    /api/codegarden/projects/{id}/specs            Spec 列表
POST   /api/codegarden/projects/{id}/specs            创建 Spec
POST   /api/codegarden/specs/{id}/lock                锁定
POST   /api/codegarden/specs/{id}/ai-generate         AI 生成草案
POST   /api/codegarden/specs/{id}/verify              AC 验收

# SDD
GET    /api/codegarden/projects/{id}/sdd              SDD 详情
POST   /api/codegarden/projects/{id}/sdd              创建
POST   /api/codegarden/sdds/{id}/ai-generate          AI 反向生成
POST   /api/codegarden/sdds/{id}/consistency-check    一致性检查

# Prompt
GET    /api/codegarden/prompts                        Prompt 列表
POST   /api/codegarden/prompts                        创建
POST   /api/codegarden/prompts/{id}/use               记录使用
POST   /api/codegarden/prompts/{id}/optimize          AI 优化
GET    /api/codegarden/prompts/recommend?context=...  智能推荐

# AI 配额
GET    /api/codegarden/quotas                         配额状态
GET    /api/codegarden/quotas/usage                   用量明细
PATCH  /api/codegarden/quotas                         调整配额
```

---

## 8. 前端 UI 设计

### 8.1 主界面布局

```
┌──────────────────────────────────────────────────────────────┐
│  hotspot                    [CodeGarden] [Knowledge] [SecNews]│
├──────────┬───────────────────────────────────────────────────┤
│          │                                                   │
│  📊 看板  │    ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐             │
│  🌐 服务  │    │项目1│ │项目2│ │项目3│ │  +  │             │
│  🔗 联动  │    └─────┘ └─────┘ └─────┘ └─────┘             │
│  ⚙️ 资源  │                                                   │
│  📈 分析  │    [筛选: 全部 ▼] [排序: 最近更新 ▼] [🔍]        │
│  📝 知识  │                                                   │
│  🤖 AI    │    列表视图 / 卡片视图 / 拓扑视图                    │
│  ─────── │                                                   │
│  快捷操作  │    ┌─────────────────────────────────────┐        │
│  [+新建]  │    │ 最近动态                            │        │
│  [⚡批量] │    │ • 2分钟前 api-service 重启成功       │        │
│  [🧹清理] │    │ • 1小时前 新项目 "data-pipeline" 创建 │        │
│          │    │ • 3小时前 端口 8080 冲突已自动解决    │        │
│          │    └─────────────────────────────────────┘        │
└──────────┴───────────────────────────────────────────────────┘
```

### 8.2 项目详情页

```
┌──────────────────────────────────────────────────────────────┐
│  ← 返回   ai-assistant  [运行中]  [⋮]                         │
├──────────────────────────────────────────────────────────────┤
│  基本信息                                                     │
│  • 类型: web_application  • 来源: 🔀 fork from upstream/repo   │
│  • 技术栈: React + Fastify  • 健康度: ████████░░ 80%          │
│  • 上游落后: 12 commits ⚠️  [立即同步]                        │
├──────────────────────────────────────────────────────────────┤
│  Tab: [概览] [阶段] [活动] [服务] [AI 协作] [依赖] [设置]      │
├──────────────────────────────────────────────────────────────┤
│  阶段时间线                                                   │
│  ✓ 需求分析 (2026-07-01)                                     │
│  ✓ 原型开发 (2026-07-05)                                     │
│  🔄 接入 WebSocket (2026-07-19, 进行中)                       │
│  ○ 性能优化 (计划中)                                          │
├──────────────────────────────────────────────────────────────┤
│  活动日志                                                     │
│  • 2小时前  commit: "fix: 消息列表渲染优化"                   │
│  • 3小时前  note: "react-window 方案可行"                     │
│  • 1天前    decision: "选择 react-window 而非 react-virtual"  │
│  • 2天前    release: "v0.3.0"                                │
└────────────────────────────────────────────────────────────────┘
```

### 8.3 AI 协作面板

```
┌──────────────────────────────────────────────────────────────┐
│  🤖 AI 协作中心 — ai-assistant                                │
├──────────┬───────────────────────────────────────────────────┤
│          │                                                   │
│  🎭 Skill │    活跃 Skill                                    │
│  🧠 Memory│    • React 性能优化专家 [v1.2] ⭐ 4.8             │
│  ⛔ 约束  │    • TypeScript 严格模式 [v1.0]                  │
│  📋 Spec  │    [+ 切换 Skill]                                │
│  📐 SDD   │                                                   │
│  💬 Prompt│    记忆状态                                       │
│  📊 配额  │    长期: 24 条  项目: 156 条  会话: 8 条         │
│          │    [查看记忆看板]                                 │
│          │                                                   │
│          │    约束状态                                       │
│          │    ✅ 文件系统: 只读 src/                          │
│          │    ✅ 测试覆盖率: 82% (>= 80%)                    │
│          │    ⚠️  依赖: 检测到新依赖 lodash-es              │
│          │                                                   │
│          │    [🚀 开始新任务]  [📋 创建 Spec]  [💬 快速对话]  │
└──────────┴───────────────────────────────────────────────────┘
```

### 8.4 前端组件目录

```
frontend/src/
├── components/
│   ├── codegarden/                    # 新增
│   │   ├── ProjectBoard.tsx           # 项目看板
│   │   ├── ProjectCard.tsx            # 项目卡片
│   │   ├── ProjectDetail.tsx          # 项目详情
│   │   ├── ProjectTimeline.tsx        # 阶段时间线
│   │   ├── ActivityLog.tsx            # 活动日志
│   │   ├── GithubImportDialog.tsx     # GitHub 导入
│   │   ├── UpstreamStatus.tsx         # 上游状态
│   │   ├── ServiceMesh.tsx            # 服务网格
│   │   ├── ServiceTopology.tsx        # 服务拓扑图
│   │   ├── ResourceHub.tsx            # 资源中枢
│   │   ├── PortPool.tsx               # 端口池
│   │   ├── AIPanel.tsx                # AI 协作面板
│   │   ├── SkillEditor.tsx            # Skill 编辑器
│   │   ├── MemoryDashboard.tsx        # 记忆看板
│   │   ├── ConstraintPanel.tsx        # 约束面板
│   │   ├── SpecEditor.tsx             # Spec 编辑器
│   │   ├── SDDEditor.tsx              # SDD 编辑器
│   │   ├── PromptLibrary.tsx          # Prompt 资产库
│   │   └── QuotaDashboard.tsx         # 配额看板
│   └── ... (既有)
├── hooks/
│   ├── useCodegardenProjects.ts       # 新增
│   ├── useCodegardenServices.ts       # 新增
│   ├── useCodegardenAI.ts             # 新增
│   └── ... (既有)
├── types/
│   └── codegarden.ts                  # 新增
└── pages/
    └── CodegardenPage.tsx             # 新增主页面
```

---

## 9. 与 hotspot 既有功能的集成方案

### 9.1 集成矩阵

| hotspot 既有能力 | CodeGarden 使用方式 | 改动 |
|----------------|---------------------|------|
| FastAPI 后端 | 新增 `backend/api/codegarden.py` + `backend/services/codegarden_*.py` | 新增模块，不改既有 |
| SQLite | 新增 `cg_*` 表，扩展 `knowledge_skills` 字段 | 迁移脚本 |
| React 前端 | 新增 `/codegarden` 路由 + 组件目录 | 新增 |
| 任务队列 | 复用 `knowledge_tasks`，扩展 `task_type` | 扩展枚举 |
| Scheduler | 新增 cg_* 定时任务 | 新增 jobs |
| Secrets | 直接调用 `secrets_service` | 无改动 |
| Skill 系统 | 扩展 `knowledge_skills` 表字段 | ALTER TABLE |
| 同步包 | 扩展含 `codegarden/` 子目录 | 扩展 sync_bundle |
| 知识联邦 | knowledge_items frontmatter 加 `project_id` | 可选字段 |
| SOUL.md | 新增"项目状态"节 | soul_service 扩展 |
| WebDAV 同步 | codegarden/ 目录纳入同步范围 | sync_zip 扩展 |

### 9.2 数据目录结构

```
hotspot/
├── knowledge/          # 既有 LLM-Wiki
├── codegarden/         # 新增 CodeGarden 数据目录
│   ├── memory/         # 项目记忆 .md
│   │   └── {project_id}.md
│   ├── playbooks/      # 自动化工作流 YAML
│   ├── specs/          # Spec 归档（同步到 cg_specs 表）
│   ├── sdds/           # SDD 归档
│   ├── prompts/        # Prompt 模板备份
│   └── exports/        # 项目导出压缩包
├── backend/
│   ├── api/codegarden.py
│   ├── services/
│   │   ├── codegarden_project_service.py
│   │   ├── codegarden_github_service.py
│   │   ├── codegarden_service_mesh.py
│   │   ├── codegarden_resource_hub.py
│   │   ├── codegarden_orchestration.py
│   │   ├── codegarden_lifecycle.py
│   │   ├── codegarden_memory_service.py
│   │   ├── codegarden_constraint_service.py
│   │   ├── codegarden_spec_service.py
│   │   ├── codegarden_sdd_service.py
│   │   └── codegarden_prompt_service.py
│   └── repository/
│       └── codegarden_repo.py
└── frontend/
    └── src/components/codegarden/
```

### 9.3 跨子系统协同

#### 9.3.1 knowledge → codegarden（资讯作为二开源池 — 核心协同）

**这是 CodeGarden 与 hotspot 的核心协同点**：hotspot 的 GitHub 资讯收集（github_collector.py）产出的不是单纯阅读材料，而是**用户的二开候选源池**。

**协同流程**：
```
github_collector.py 抓取 trending/热门 GitHub repo
    ↓
写入 knowledge_items (type=github, 含 repo_url, stars, description)
    ↓
用户在知识详情页浏览，发现值得二开的项目
    ↓
点击「加入 CodeGarden」按钮
    ↓
CodeGarden 创建 cg_projects 记录：
    - source_type = fork (用户填 local_path) 或 reference (仅参考)
    - source_item_id = knowledge_items.id (反向溯源)
    - upstream_url = knowledge_item.repo_url
    - 首次同步 commits behind/ahead
    ↓
项目出现在 CodeGarden 看板
    ↓
持续跟踪上游更新 (cg_upstream_sync 定时任务)
```

**实现要点**：
- knowledge_items frontmatter 新增可选字段 `project_id`（指向 cg_projects.id，表示已转化）
- knowledge 详情页对 type=github 的条目显示「加入 CodeGarden」CTA
- CodeGarden 看板「从知识库导入」入口列出 type=github 且未转化的 items
- `cg_projects.source_item_id` 提供反向溯源（哪个资讯变成了项目）

**字段扩展**：
- `knowledge_items.frontmatter.project_id` — 已转化标记（避免重复导入）
- `cg_projects.source_item_id` — 反向溯源 knowledge_items.id
- `cg_projects.source_type_detail` — 转化来源详情（trending/search/manual）

#### 9.3.2 codegarden → knowledge（项目沉淀为知识）

- 项目归档时，自动提取关键 ADR / 踩坑记录为 knowledge_items
- 通过 `knowledge_tasks` 队列触发（task_type=project_to_knowledge）

#### 9.3.3 SOUL.md 整合

SOUL.md 新增"项目状态"节，由 codegarden_lifecycle_service 自动生成：
- 活跃项目数 / 各生命周期阶段分布
- 待同步的上游 repo 列表
- 健康度低于阈值的项目告警
- 本周从资讯转化的二开项目数

---

## 10. 技术架构

### 10.1 系统架构图

```
┌─────────────────────────────────────────────┐
│         前端界面 (React + Tailwind)          │
│   hotspot 既有页 + CodeGarden 新增页          │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│         本地核心服务 (FastAPI)               │
│  hotspot 既有 API + /api/codegarden/*        │
│  项目扫描 │ 服务管理 │ 端口分配 │ 事件联动     │
│  Skill 引擎 │ Memory 管理 │ Constraint 检查  │
│  Spec/SDD 管理 │ Prompt 推荐引擎             │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│         本地数据层 (SQLite + 文件系统)        │
│  hotspot_* 表 │ knowledge_* 表 │ cg_* 表     │
│  knowledge/ │ codegarden/ 目录               │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│              本机系统接口层                   │
│  Docker API │ PM2 │ psutil │ FileSystem │ Git│
│  GitHub REST API                             │
└─────────────────────────────────────────────┘
```

### 10.2 技术选型

| 层级 | 技术选型 | 理由 |
|------|---------|------|
| 后端 | **FastAPI**（复用 hotspot） | 与 hotspot 同栈，零迁移成本 |
| 前端 | **React 18 + Vite + Tailwind**（复用） | 同栈 |
| 数据库 | **SQLite**（复用 hotspot） | 零配置，单文件 |
| 可视化 | React Flow / Cytoscape.js | 服务拓扑、依赖图谱 |
| 进程管理 | Docker SDK / PM2 API / psutil / child_process | 不重复造轮子 |
| GitHub 集成 | `httpx` + GitHub REST API | 复用 hotspot github_collector 的 HTTP 客户端模式 |
| 配置存储 | YAML/JSON + SQLite | 人类可读 + 结构化查询 |
| 加密 | **复用 hotspot Fernet** | 不重建加密体系 |

### 10.3 部署方式

- 复用 hotspot 本地 Web 服务（端口 8898，禁止漂移）
- 启动 hotspot 即启动 CodeGarden，无需独立进程
- 数据目录：`hotspot/codegarden/`
- 同步包：纳入 hotspot WebDAV 同步，含 `codegarden/` 子目录

---

## 11. 里程碑规划

### 11.1 4 阶段路线图

| 阶段 | 版本 | 范围 | 优先级 | spec 路径 | 状态 |
|------|------|------|--------|----------|------|
| **Phase 2a MVP** | v1.5 | M1 项目看板 + GitHub 导入 + 上游跟踪 + M6 Skill 扩展 | 最高 | `.trae/specs/phase2a-codegarden-mvp/` | ✓ 已实现 |
| **Phase 2b** | v1.6 | M2 服务网格 + M3 资源中枢 + M4 联动引擎 | 高 | `.trae/specs/phase2b-service-mesh/` | ✓ 已实现 (2026-07-20) |
| **Phase 2c** | v1.7 | M7 Memory + M8 Constraint + M9 Spec + M10 SDD + M11 Prompt + M12 配额 | 中 | `.trae/specs/phase2c-ai-collaboration/` | 待启动 |
| **Phase 2d** | v1.8 | M5 生命周期管理 + 归档清理 + 健康度评分 | 中 | `.trae/specs/phase2d-lifecycle/` | 待启动 |

### 11.2 Phase 2a MVP 详细范围

**目标**：解决最大痛点（vibecoding 成果状态不清晰 + 二开 github 项目管理缺失）

**交付物**：
1. DB schema：cg_projects（含 source_item_id 反向溯源字段）+ cg_project_stages + cg_project_links + cg_project_activities + knowledge_skills 扩展字段
2. 后端 API：项目 CRUD + 状态切换 + GitHub 导入 + **从 knowledge_item 一键转化** + 候选二开源列表 + 上游同步
3. 后端 service：codegarden_project_service + codegarden_github_service + codegarden_knowledge_bridge（资讯→项目转化）
4. 后端 repo：codegarden_repo
5. 前端：项目看板页 + 项目卡片 + 项目详情 + GitHub 导入对话框 + **从知识库导入对话框** + 上游状态组件 + **知识详情页「加入 CodeGarden」CTA**
6. 定时任务：cg_upstream_sync（每日 09:00）
7. 任务队列：task_type=project_sync
8. 数据目录：codegarden/ 初始化
9. 同步包扩展：含 codegarden/ 子目录
10. knowledge_items frontmatter 扩展：可选 project_id 字段（已转化标记）
11. 测试：API 单测 + 前端组件测试 + 资讯→项目转化 e2e 测试

**明确不做（推迟到后续 Phase）**：
- 服务网格（M2）
- 资源中枢（M3）
- 任何 AI 协作功能（M7-M12）

### 11.3 成功指标

| 指标 | 目标值 | 衡量方式 |
|------|--------|---------|
| 项目接入时间 | < 5 分钟 | 从输入 GitHub URL 到完成注册 |
| 找项目耗时 | < 30 秒 | 通过搜索/筛选定位项目 |
| 上游同步延迟 | < 24 小时 | 定时任务执行间隔 |
| 二开项目跟踪覆盖率 | 100% | 所有 fork 项目均纳入跟踪 |
| 知识→项目反查可用 | 是 | knowledge_items.project_id 字段可查 |
| Skill 模型统一 | 是 | 单表 skill_type 区分 |
| 资讯→项目转化率 | > 5% | type=github 的 knowledge_items 中已转化的占比 |
| 资讯→项目转化路径可用 | 是 | 知识详情页 CTA + CodeGarden 候选列表 双入口 |

---

## 12. 非功能性需求

### 12.1 性能要求

- 看板页面加载 < 2 秒（100 个项目以内）
- 服务状态更新延迟 < 5 秒
- 支持同时管理 50+ 个活跃项目
- GitHub 同步单项目 < 10 秒
- AI 记忆注入延迟 < 500ms

### 12.2 可靠性

- 系统自身高可用（watchdog 机制，复用 hotspot）
- 配置自动备份（复用 hotspot 同步包）
- 误操作回滚（如端口释放可恢复）
- AI 约束违规时自动拦截

### 12.3 安全性

- 敏感信息（密钥、密码）复用 hotspot Fernet 加密
- GitHub token 通过 hotspot secrets 存储
- 环境变量访问权限控制
- 服务间网络隔离（Docker 网络）
- AI 约束防止代码注入和敏感信息泄露

### 12.4 扩展性

- 插件系统：支持自定义扫描器、通知渠道
- API 开放：支持第三方工具集成
- Skill/Prompt 市场：社区共享

---

## 13. 成功指标（KPI）

| 指标 | 目标值 | 衡量方式 |
|------|--------|---------|
| 项目接入时间 | < 5 分钟 | 从发现项目到完成注册 |
| 服务启动成功率 | > 95% | 自动解决冲突后成功启动比例 |
| 找项目耗时 | < 30 秒 | 通过搜索/筛选定位项目 |
| 技术债发现率 | 100% | 过期依赖/漏洞是否全部识别 |
| AI 重复解释率 | < 10% | 同一项目上下文 AI 是否需要重复说明 |
| Spec 一次通过率 | > 70% | 锁定 Spec 后 AI 代码无需返工比例 |
| Prompt 复用率 | > 60% | 使用库中模板 vs 从零编写 |
| 二开项目跟踪覆盖率 | 100% | 所有 fork 项目纳入跟踪 |
| 上游同步及时率 | > 95% | 24 小时内完成同步 |

---

## 14. 附录

### 14.1 术语表

| 术语 | 定义 |
|------|------|
| 氛围编程 | Vibe Coding，借助 AI 辅助快速开发代码的方式 |
| CodeGarden | hotspot 的代码项目管理子系统 |
| 服务网格 | 系统中所有运行服务的注册、发现、通信管理 |
| 联动引擎 | 协调多个项目/服务之间自动化协作的引擎 |
| 生命周期 | 项目从创建到废弃的完整阶段 |
| Skill | AI 角色能力模板，定义专业领域和行为模式 |
| Memory | AI 上下文记忆，分长期/项目/会话三层 |
| Constraint | AI 行为约束，防止违规操作 |
| Spec | 功能规格文档，人机协作契约 |
| SDD | 软件设计文档，项目架构宪法 |
| 上游跟踪 | 跟踪 fork 源 repo 的更新情况 |

### 14.2 与原 PRD 的差异说明

#### 14.2.1 与 CodeGarden_PRD_v1.0.md 的差异

| 维度 | v1.0 | v2.0 |
|------|------|------|
| 部署 | Tauri 桌面应用 | hotspot 本地 Web 服务 |
| 后端 | Node.js + Fastify | FastAPI |
| 容器 | 提及 K8s | 仅本机 Docker/PM2 |
| Skill | 全新表 | 扩展 knowledge_skills |
| 范围 | 6 大模块 | 12 模块（更细化） |
| 里程碑 | 单一 v1.0 | 4 阶段 |

#### 14.2.2 与 hotspot-codegarden.md 的差异

| 维度 | 原文档 | v2.0 |
|------|--------|------|
| 定位 | 独立全流程平台 | hotspot 子系统 |
| 架构选型 | 三选一（单体/微服务/Serverless） | 复用 hotspot 单体 |
| 团队 | 1-2 前端 + 1-2 后端 + DevOps + 测试 | 单人 vibecoding |
| 时间 | 6 个月 | 4 阶段渐进 |
| 范围 | 8 模块 | 12 模块（拆分更细） |

### 14.3 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| AI 生成质量不稳定 | 代码返工 | Spec 锁定 + Constraint 拦截 + 强制审查 |
| 工具集成复杂度 | 开发延期 | 优先 GitHub，Docker/PM2 次之，监控最后 |
| 12 模块范围过大 | 无法收敛 | 4 阶段拆分，每阶段独立 spec |
| 与 hotspot 既有功能耦合 | 改动既有代码风险 | 仅扩展不修改，ALTER TABLE 加字段而非改既有字段语义 |
| 单人维护 | 精力分散 | 自动化优先（事件总线 + Playbook） |
| GitHub API 限流 | 同步失败 | token 缓存 + 速率限制 + 退避重试 |

---

> **结语**：CodeGarden v2.0 作为 hotspot 子系统，最大化复用既有基础设施，避免重复造轮子。通过 4 阶段渐进交付，从最痛的"项目状态不清 + 二开跟踪缺失"切入，逐步扩展到服务网格、AI 协作、生命周期管理，最终实现"让氛围编程从野蛮生长走向有序生态"的目标。
