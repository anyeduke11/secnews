# 热点地图 Hotspot Map

> **当前版本**: v1.5+ (Phase 1j 完成, Phase 2a CodeGarden MVP 规划中)
> **定位**: IT 人员专属工作站 — 资讯聚合 + 知识管理 + 代码项目管理 三位一体

覆盖科技/AI、网络安全、金融/投资、独立开发/创业、招标资讯、GitHub 项目、综合热点七大领域的热点聚合看板，并扩展为包含 **知识管理 LLM-Wiki** 与 **CodeGarden 代码花园** 两大子系统。

## 三大子系统

| 子系统 | 路径 | 职责 | 状态 |
|--------|------|------|------|
| **SecNews 资讯聚合** | `backend/collectors/` | 7 领域 30+ 信源采集 + 10 层质量门禁 + 趋势分析 | ✅ v1.4 稳定 |
| **Knowledge LLM-Wiki** | `knowledge/` | 文件系统知识库 (items/concepts/learning/content) + 联邦搜索 + SOUL 画像 | ✅ v1.4 稳定 (409 items, 96 concepts, 17.1% compiled) |
| **CodeGarden 代码花园** | `codegarden/` (待建) | 个人 vibecoding 项目 + GitHub 二开项目全生命周期管理 | 🚧 Phase 2a 规划中 |

## 功能特性

### 资讯聚合（SecNews）
- **七大领域覆盖**：科技/AI、网络安全、金融/投资、独立开发/创业、招标资讯、GitHub 项目、IT/科技
- **分类筛选 + 时间范围 + 关键词搜索**（FTS5 全文检索）
- **原文下钻** + **24h 趋势热力图**
- **质量门禁**：10 层同步/异步门禁 + 来源信誉动态评分
- **5 分钟自动刷新 + 手动刷新 + SSE 实时推送**

### 知识管理（LLM-Wiki）
- **多源同步**：Cubox / 浏览器书签 / SecNews 收藏
- **分层结构**：items (L1) → concepts (L2) → learning (L3) → content (L4)
- **联邦搜索**：与 `~/knowledge-base/` 本地 LLM-Wiki 跨库检索
- **SOUL 角色画像**：自动生成 + 周期更新
- **学习计划 + 进度跟踪 + 测试评估**
- **内容创作**：草稿 + 发布日历 + 多平台发布 (微信公众号/X/微博)

### 代码项目管理（CodeGarden, Phase 2a 规划中）
- **项目看板**：vibecoding 产物 + GitHub fork 项目统一管理
- **8 阶段生命周期**：ideation → prototype → mvp → beta → running → maintenance → deprecated → archived
- **GitHub 上游同步**：commit 差异跟踪 + 每日 09:00 定时同步
- **资讯→项目转化通道**：`knowledge_items` (type=github) → `cg_projects` (source_type=fork/reference)
- **Skill 扩展**：复用 `skills` 表，扩展 9 个新字段（capabilities / constraints / system_prompt 等）
- **跨端同步**：cg_projects 主表纳入 hotspot sync_bundle

详见 [`docs/CodeGarden_PRD_v2.0.md`](./docs/CodeGarden_PRD_v2.0.md) 和 [`.trae/specs/phase2a-codegarden-mvp/`](./.trae/specs/phase2a-codegarden-mvp/)

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- 后端依赖（详见 `backend/requirements.txt`）：
  - `fastapi>=0.100` · `uvicorn[standard]>=0.23` · `aiohttp>=3.8`
  - `pydantic>=2.0` · `pydantic-settings>=2.0` · `python-dateutil>=2.8`
  - `loguru>=0.7`（结构化 JSON Lines 日志）
  - `cachetools>=5.3`（进程内 LRU 缓存）
  - `APScheduler>=3.10`（后台调度）
  - 开发依赖：`pytest>=7.4` · `pytest-asyncio>=0.21` · `pytest-cov>=4.1`

### 启动后端

```bash
# 根目录启动脚本（推荐）
python run.py

# 或等价命令
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

可通过环境变量自定义：
- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `8000`）
- `WORKERS`（默认 `1`，SQLite WAL 模式下多 worker 会有锁竞争）

后端运行在 http://127.0.0.1:8000

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://127.0.0.1:8898

### 访问

打开浏览器访问 http://localhost:8898

### ⚠️ 代理配置（必读）

`backend/proxy_config.json` 在 `.gitignore` 中,不会随仓库分发。**首次安装后必须自行配置**,否则 `security_collector` (搜狗/sogou.com/web) 和 `github_collector` (GitHub) 会拿不到数据,出现"24h security/github 数据为空"。

**最小配置**(编辑 `backend/proxy_config.json`):

```json
{
  "mode": "manual",
  "http_proxy": "http://127.0.0.1:7897",
  "https_proxy": "http://127.0.0.1:7897",
  "socks_proxy": "http://127.0.0.1:7897",
  "no_proxy": "localhost,127.0.0.1,::1"
}
```

把 `7897` 改成你的代理端口(Clash 默认 7890、V2RayN 默认 10809、Surge 默认 6152)。如果你没装代理客户端,改为 `"mode": "off"`(此时 sogou.com/web 厂商漏洞源会被 anti-bot 限流,但 weixin.sogou.com 微信公众号源仍可用)。

也可通过前端 `/api/proxy/settings` 端点运行时修改,无需重启。

## 数据源

| 领域 | 数据源 |
|------|--------|
| 科技/AI | aihot.virxact.com |
| 网络安全 | 阿里云漏洞库(AVD) / CNNVD / 备用数据 |
| 金融/投资 | 新浪财经 / 腾讯证券 |
| 独立开发/创业 | Hacker News / Product Hunt |

## 技术栈

- **前端**：React 18 + Vite 5 + Tailwind CSS 3 + TypeScript
- **后端**：Python FastAPI + aiohttp
- **设计**：暗色数据看板风格，JetBrains Mono 等宽字体

## 目录结构

```
hotspot/
├── backend/                # FastAPI 后端
│   ├── main.py             # API 入口 (APP_VERSION)
│   ├── api/                # 16 个 router (hotspots/knowledge/skills/secrets/sync/codegarden 待加...)
│   ├── collectors/         # 7 大领域数据采集器
│   ├── quality/            # 10 层质量门禁 pipeline
│   ├── repository/         # SQLite + WAL + 迁移 (018_knowledge.sql 已应用, 019_codegarden.sql 待加)
│   ├── services/           # 业务服务 (compiler/soul_service/sync_bundle/codegarden_* 待加...)
│   └── scheduler/          # APScheduler 14 个 job (cg_upstream_sync_job 待加为 job 15)
├── frontend/               # React 18 + Vite 5 + Tailwind
│   └── src/
│       ├── components/     # 22 个组件 (codegarden/ 子目录待加)
│       ├── hooks/          # 10 个 hook (useCodegardenProjects 待加)
│       └── types/          # TypeScript 类型
├── knowledge/              # LLM-Wiki 知识库 (v1.4 已落地)
│   ├── items/              # L1: 409 知识条目 (*.md + YAML frontmatter)
│   ├── concepts/           # L2: 96 概念 + graph.json
│   ├── learning/           # L3: 学习计划 + tasks 队列
│   ├── content/            # L4: 草稿 + calendar.json
│   ├── summaries/          # 周报摘要
│   ├── _MAP.md             # 知识地图索引
│   ├── _SCHEMA.md          # 数据模型契约
│   └── SOUL.md             # 角色画像
├── codegarden/             # CodeGarden 数据目录 (Phase 2a 待建, .gitkeep)
├── docs/                   # 架构 + 规范 + 改进计划 + PRD
│   ├── ARCHITECTURE.md     # 架构方案 v3.0
│   ├── SPEC.md             # 功能规范 v3.1
│   ├── IMPROVEMENT_PLAN.md # 改进计划 (v1.3.0 + v1.5+ Phase 2a-2d)
│   ├── CODE_WIKI.md        # 代码 Wiki
│   ├── CodeGarden_PRD_v2.0.md  # CodeGarden PRD (1685 行)
│   └── hotspot-codegarden.md   # CodeGarden 设计分析报告
├── .trae/specs/            # Phase spec 三件套
│   └── phase2a-codegarden-mvp/  # spec.md + tasks.md + checklist.md
├── AGENTS.md               # AI Agent 操作手册
└── README.md               # 本文档
```

## API 接口

### 资讯聚合（v1.2+）
- `GET /api/hotspots?category=all&time_range=7d&keyword=&limit=100` — 获取热点数据
- `GET /api/categories` — 获取分类列表
- `GET /api/health` — 健康检查
- `GET /api/trends` — 24h 趋势
- `GET /api/favorites` — 收藏列表
- `GET /api/todos` — 待办列表

### 知识管理（v1.4+）
- `GET /api/knowledge/items` — 知识条目列表
- `GET /api/knowledge/concepts` — 概念列表
- `GET /api/knowledge/federation/search` — 联邦搜索
- `POST /api/knowledge/tasks` — 提交任务 (compile/learn/soul/publish)
- `GET /api/skills` — Skill 列表
- `GET /api/secrets` — 密钥列表
- `POST /api/sync/build` — 构建同步包

### CodeGarden（Phase 2a 规划中, 16 个端点）
- `GET /api/codegarden/projects` — 项目列表 + 多维筛选
- `POST /api/codegarden/projects` — 创建项目
- `GET /api/codegarden/candidates` — 候选列表 (type=github 未转化)
- `POST /api/codegarden/from-knowledge` — 资讯→项目转化 (幂等 201/200)
- `POST /api/codegarden/github/import` — GitHub 导入
- `GET /api/codegarden/github/metadata?url=...` — 元数据预览
- `POST /api/codegarden/projects/{id}/lifecycle` — 状态切换
- `POST /api/codegarden/projects/{id}/sync` — 触发上游同步
- 完整 16 端点清单详见 [Phase 2a spec](./.trae/specs/phase2a-codegarden-mvp/spec.md)

## 相关文档

- [AGENTS.md](./AGENTS.md) — AI Agent 操作手册
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 架构方案
- [docs/SPEC.md](./docs/SPEC.md) — 功能规范
- [docs/IMPROVEMENT_PLAN.md](./docs/IMPROVEMENT_PLAN.md) — 改进计划
- [docs/CODE_WIKI.md](./docs/CODE_WIKI.md) — 代码 Wiki
- [docs/CodeGarden_PRD_v2.0.md](./docs/CodeGarden_PRD_v2.0.md) — CodeGarden PRD v2.0
- [docs/hotspot-codegarden.md](./docs/hotspot-codegarden.md) — CodeGarden 设计分析报告
- [.trae/specs/phase2a-codegarden-mvp/](./.trae/specs/phase2a-codegarden-mvp/) — Phase 2a 实施计划三件套
