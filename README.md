# SecNews · AI + 安全 知识工作站

> **v1.7.6** · 单人本地部署 · 三大子系统协同 · **标准 MCP 协议对外开放**
>
> 「热点聚合 → 知识闭环 → 项目管理 → AI 协作」的一体化个人工作站，面向 AI 与安全从业者。

[English](#english) | [中文](#中文)

---

## 中文

### 这是什么

**SecNews**（开发代号 `hotspot`）是一个面向 **AI + 安全从业者** 的单人本地工作站。它把日常工作中分散的三件事合并到同一个本地系统：

| 子系统 | 解决什么问题 | 入口 |
|---|---|---|
| **SecNews 热点聚合** | 7 大领域、30+ 数据源，每天自动拉取、分类、去重、入库 | `/` |
| **Knowledge LLM-Wiki** | 文件系统驱动的知识库（OKF + LLM-Wiki 2.0），自动从收藏/书签/Cubox 提炼 | `/knowledge` |
| **CodeGarden 项目管理** | 个人代码项目的全生命周期（Idea → 归档），含服务网格/资源中枢/联动引擎 | `/codegarden` |
| **Security Knowledge Graph**（v1.5+） | MITRE ATT&CK + CVE + 合规本体，安全资讯自动入图 | `/security` |
| **MCP Server**（v1.7 Phase 7） | 13 个标准工具，让 **Cursor / Claude Desktop / Trae / Workbuddy** 直接读写本机知识库 | `stdio` / `http://127.0.0.1:8000/mcp/sse` |

### 适合谁

- **AI/ML 从业者**：跟踪最新模型发布、论文、开源项目（aihot/OpenAI/Anthropic/HackerNews/ProductHunt）
- **安全研究员 / 红蓝队**：跟踪 CVE、ATT&CK 战术、阿里云漏洞库、CNNVD、奇安信、绿盟、安全客、FreeBuf、THN 等 17+ 安全源
- **独立开发者 / 创业者**：管理 side project 的全生命周期，自动分配端口、扫描服务、编排 Playbook
- **知识工作者**：把每天看到的资讯、书签、收藏，自动沉淀为可搜索、可复习、可关联的本地知识库

> 一个人，一台电脑，零外部服务。LLM 推理交给外部 AI Agent（通过 MCP 协议），hotspot 只做数据存储 + 13 个工具的暴露。

### 核心特性

#### 1. SecNews — 多源热点聚合

- **7 大领域**：`ai` / `security` / `finance` / `startup` / `bid` / `github` / `tech`
- **30+ 数据源**：aihot.virxact.com、新浪财经、腾讯证券、阿里云漏洞库、CNNVD、Hacker News、Product Hunt、GitHub Trending 等
- **13 道质量门禁**（`backend/quality/`）：URL 校验、标题摘要、来源信誉、噪声过滤、Recency 门禁（上海时区本周一 00:00 起点）等
- **5min 自动采集** + **1h 趋势重算** + **24h 数据备份**

#### 2. Knowledge — OKF + LLM-Wiki 2.0 统一存储

- **4 层金字塔**：L1 资料库（`.md` 文件）→ L2 概念库 → L3 学习计划 → L4 内容创作
- **3 大数据源自动同步**：
  - **SecNews 收藏**（一星 → 自动入知识库）
  - **Cubox**（`cubox-cli` 同步，含全文 + 标注）
  - **Chrome 书签**（导入 JSON，自动去重）
- **隐式个性化**：EMA 权重 + 兴趣分布，自动生成 `SOUL.md` 角色画像
- **SM-2 间隔重复**：自动安排复习，知识不遗忘
- **多维标签 + 跨层搜索**：一次查询穿透所有 4 层

#### 3. CodeGarden — 项目全生命周期

- **生命周期状态机**：`ideation` → `prototype` → `development` → `testing` → `running` → `maintenance` → `archived` → `deprecated`
- **M2 服务网格**（v1.6 Phase 2b）：自动发现本机服务（`lsof`/`docker ps`/`pm2 list`），拓扑图 + 日志 + 重启
- **M3 资源中枢**：4 类资源（port / domain / env_template / volume），受保护端口 8898 禁止释放
- **M4 联动引擎**：依赖图 + 事件总线 + Playbook YAML 执行 + 影响分析（BFS 反向追溯）
- **批量导入**：从知识库 / GitHub 一键导入项目

#### 4. Security Knowledge Graph（v1.5+）

- **MITRE ATT&CK** 全量 STIX 解析 → `security_entities` + `security_edges`（CC-BY-4.0 署名）
- **NVD CVE** 按需查询 + 30 天本地缓存
- **术语标准化**（zh-CN）：同义词表 + 合规本体（等保 2.0 / 关基条例 / 数安法）
- **入图自动**：每条安全资讯自动提取 `cve_ids` / `attack_techniques` / `compliance_refs`

#### 5. MCP Server（v1.7 Phase 7 — Option A 简化版）

- **13 个标准工具**（5 读 + 8 写）：

  | 读 (5) | 写 (8) |
  |---|---|
  | `search_hotspots` | `add_favorite` |
  | `get_hotspot` | `remove_favorite` |
  | `list_favorites` | `add_annotation` |
  | `search_knowledge` | `update_knowledge_item` |
  | `get_personal_profile` | `trigger_extract_tags` |
  |  | `trigger_cubox_sync` |
  |  | `create_alert_rule` |
  |  | `mark_digest_read` |

- **双传输**：`stdio`（默认，Cursor / Trae / Claude Desktop）+ `SSE`（`/mcp/sse`）
- **零状态**：hotspot 不维护 session / heartbeat，AI Agent 同步直返
- **本地优先**：默认绑定 `127.0.0.1:8000`

### 快速开始

#### 环境要求

- **Python** 3.10+（推荐 3.11 / 3.12）
- **Node.js** 18+（推荐 20 LTS）
- **macOS / Linux**（Windows 未测试，路径分隔符可能有问题）
- 可选：代理客户端（Clash / V2RayN / Surge，用于 `security_collector` 和 `github_collector`）

#### 1. 克隆 & 装依赖

```bash
git clone https://github.com/anyeduke11/secnews.git
cd secnews

# 后端依赖
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

#### 2. 配置代理（重要）

`backend/proxy_config.json` 在 `.gitignore` 中，**不会随仓库分发**。首次安装后必须自行配置，否则 `security_collector` 和 `github_collector` 会拿不到数据。

编辑 `backend/proxy_config.json`：

```json
{
  "mode": "manual",
  "http_proxy": "http://127.0.0.1:7897",
  "https_proxy": "http://127.0.0.1:7897",
  "socks_proxy": "http://127.0.0.1:7897",
  "no_proxy": "localhost,127.0.0.1,::1"
}
```

把 `7897` 改成你的代理端口（Clash 默认 7890、V2RayN 默认 10809）。不装代理可改为 `"mode": "off"`。也可通过前端 `/api/proxy/settings` 运行时修改，无需重启。

#### 3. 启动后端

```bash
# 根目录启动脚本（推荐）
python run.py

# 等价命令
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

环境变量：
- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `8000`）
- `WORKERS`（默认 `1`，SQLite WAL 模式下多 worker 会有锁竞争）
- `HOTSPOT_FEATURE_MCP_SERVER`（默认 `true`，关掉则禁用 MCP 工具暴露）

后端启动后自动完成：
1. `init_db()` 应用 39 个 migration
2. 调度 13 个 APScheduler job
3. 启动 13 个 MCP tool 元数据 seeding
4. 挂载 SSE 端点 `/mcp/sse`

#### 4. 启动前端

```bash
cd frontend
npm run dev
```

前端运行在 `http://localhost:8898`（**端口固定**，禁止漂移）。

#### 5. 配置 MCP Server（可选，但推荐）

打开前端 → 右上角 **设置** → **MCP Server** 卡片 → 点击 **复制 stdio 配置**。

把这段 JSON 粘到你的 AI Agent 配置文件：

| AI Agent | 配置文件路径 |
|---|---|
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Trae** | `~/.trae/mcp_config.json` |
| **Cursor** | `~/.cursor/mcp.json` |
| **Claude Code** | 项目根目录 `.mcp.json` |

```json
{
  "mcpServers": {
    "hotspot": {
      "command": "python",
      "args": ["-m", "backend.mcp_stdio_main"],
      "cwd": "/绝对路径/secnews"
    }
  }
}
```

启动 AI Agent 后，它会自动发现 13 个工具，可直接说「给我列出最近 24h 的安全热点，按威胁等级排序」。

#### 6. 访问

打开浏览器 → `http://localhost:8898`

---

### 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     浏览器 (React SPA)                                │
│   SecNews / Knowledge / CodeGarden / Security / Settings / MCP Card   │
│   (60+ 组件, React 18 + Vite 5 + TypeScript + Tailwind 3)            │
└───────────────┬─────────────────────────────────────┬───────────────┘
                │ HTTP / JSON                        │ SSE / stdio
                │                                     │
┌───────────────▼────────────────────┐    ┌──────────▼──────────────┐
│    FastAPI 进程 (单进程, port 8000) │    │   MCP Server (13 tools) │
│  ┌──────────────────────────────┐  │    │   5 读 + 8 写             │
│  │  23 routers (~50 lines ea)   │  │    │   stdio / SSE 双传输      │
│  │  /api/hotspots /knowledge    │  │    └──────────┬──────────────┘
│  │  /api/codegarden /security   │  │               │
│  │  /api/mcp /api/profile ...   │  │               │
│  └────────────┬─────────────────┘  │               │
│               │                     │               │
│  ┌────────────▼─────────────────┐  │               │
│  │  41 services (业务逻辑层)     │  │◄──────────────┘
│  │  Hotspot / Sync / Cubox /    │  │   外部 AI Agent 直调
│  │  Knowledge / CodeGarden /     │  │   (Cursor / Claude / Trae)
│  │  Security / AutoClassifier   │  │
│  └────────────┬─────────────────┘  │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  20 repository (DAO 层)       │  │
│  │  SQLite WAL + 39 migrations  │  │
│  └────────────┬─────────────────┘  │
│               │                     │
│  ┌────────────▼─────────────────┐  │
│  │  8 collectors (数据源)        │  │
│  │  13 quality gates (过滤)      │  │
│  │  APScheduler (13 jobs)        │  │
│  └────────────┬─────────────────┘  │
└───────────────┼─────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
   ┌─────────┐    ┌──────────┐
   │ SQLite  │    │ .md files │
   │ hotspot │    │ knowledge/│
   │   .db   │    │ items/    │
   │ + WAL   │    │ concepts/ │
   └─────────┘    └──────────┘
        ▲
        │ 加密 (Fernet)
        │
   ┌────┴────────┐
   │ WebDAV 同步 │ ← 跨端配置 (坚果云 / Nextcloud)
   │ (可选)      │
   └─────────────┘
```

#### 技术选型理由

| 组件 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | async + OpenAPI 生态成熟 |
| 主存储 | **SQLite（WAL 模式）** | 零部署、强 SQL、FTS5 全文检索、单文件易备份 |
| 知识存储 | **`.md` 文件** | 文件系统即知识库，git 友好，AI Agent 可直读 |
| 调度 | APScheduler | 单进程内调度，无外部 MQ |
| 缓存 | `cachetools.TTLCache` | 进程内 LRU，TTL 5min |
| 日志 | `loguru` | 结构化、自动轮转 |
| HTTP 客户端 | `aiohttp` + `ProxySession` | 反爬友好 |
| MCP 集成 | `fastapi-mcp` | OpenAPI → MCP 自动转换 |
| 前端 | React 18 + Vite 5 + TypeScript | 已有 ~60 组件，类型安全 |
| 图表 | echarts + recharts | 看板风格 |
| 加密 | Fernet (PBKDF2 派生) | 同步包 / secrets |
| 跨端同步 | WebDAV (坚果云) | zip 容器，Fernet 加密 |

---

### 目录结构

```
secnews/
├── backend/                       # FastAPI 后端
│   ├── main.py                    # API 入口 + lifespan
│   ├── mcp_stdio_main.py          # MCP stdio transport 入口
│   ├── config.py                  # Pydantic Settings
│   ├── api/                       # 23 routers (~50 行/个)
│   │   ├── hotspots.py            # 热点聚合 API
│   │   ├── knowledge.py           # 知识库 API
│   │   ├── codegarden*.py         # CodeGarden API
│   │   ├── security.py            # 安全知识图谱 API
│   │   ├── mcp.py / mcp_*.py      # MCP Server
│   │   └── ...                    # 18 个其他 router
│   ├── services/                  # 41 业务逻辑文件
│   ├── repository/                # 20 仓库 + 39 migrations
│   ├── collectors/                # 8 数据源采集器
│   ├── quality/                   # 13 质量门禁
│   ├── scheduler/                 # APScheduler jobs
│   ├── security/                  # MITRE/NVD 集成
│   ├── parsers/                   # 独立解析器
│   └── tests/                     # 67 pytest 测试文件
├── frontend/                      # React + Vite
│   └── src/
│       ├── components/            # ~60 组件
│       │   ├── codegarden/        # CodeGarden 子组件
│       │   ├── knowledge/         # Knowledge 4 大领域
│       │   ├── security/          # Security Graph
│       │   └── settings/          # 设置面板 (含 MCP Card)
│       ├── hooks/                 # 自定义 hooks
│       ├── types/                 # TS 类型定义
│       └── App.tsx                # 路由 + 主题
├── knowledge/                     # LLM-Wiki 2.0 知识库
│   ├── _MAP.md                    # 自动生成索引
│   ├── _SCHEMA.md                 # 数据模型契约
│   ├── SOUL.md                    # 角色画像 (自动生成)
│   ├── items/                     # L1 资料库 (.md)
│   ├── concepts/                  # L2 概念库
│   ├── learning/                  # L3 学习计划
│   │   └── tasks/                 # pending / done / failed
│   ├── content/                   # L4 内容创作
│   └── summaries/                 # 周报 / 复盘
├── codegarden/                    # CodeGarden 数据
│   ├── playbooks/                 # Playbook YAML
│   ├── sdds/                      # 软件设计文档
│   ├── specs/                     # 项目规范
│   └── exports/                   # 导出产物
├── docs/                          # 设计文档 (28 个)
│   ├── ARCHITECTURE.md            # 架构总览
│   ├── CodeGarden_PRD_v2.0.md     # CodeGarden 完整 PRD
│   ├── hotspot_v1.7_PRD.md        # v1.7 完整 PRD
│   ├── SECURITY_KNOWLEDGE_GRAPH.md
│   ├── mcp_integration.md         # MCP 集成指南
│   ├── phase7_changelog.md        # v1.7.6 变更日志
│   └── ...
├── run.py                         # 启动脚本
├── AGENTS.md                      # 项目级 agent 规则
├── CLAUDE.md                      # 项目级 agent 规则
└── README.md                      # 本文件
```

---

### 配置说明

#### 后端环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `WORKERS` | `1` | uvicorn worker 数（保持 1，SQLite WAL 锁） |
| `HOTSPOT_FEATURE_MCP_SERVER` | `true` | 是否启用 MCP Server |
| `HOTSPOT_LOG_LEVEL` | `INFO` | 日志级别 |
| `HOTSPOT_PROXY_CONFIG` | `backend/proxy_config.json` | 代理配置路径 |
| `HOTSPOT_MASTER_KEY` | (留空 → 自动生成) | Fernet 主密钥（重启前持久化到 keyring） |

#### 前端配置

无构建期配置。所有运行时配置走 `/api/settings/*` 端点，可在前端 UI 修改。

#### 数据目录

| 类型 | 路径 | 备份 |
|---|---|---|
| SQLite DB | `backend/hotspot.db` | `backend/data/backup_*.db` (24h 滚动) |
| 知识文件 | `knowledge/items/*.md` | git 跟踪（推荐） |
| 加密 secrets | OS keyring | 不可导出 |
| 同步包 | WebDAV (坚果云) | zip 容器，Fernet 加密 |
| 日志 | `backend/logs/*.log` | loguru 自动轮转 |

---

### 测试

#### 后端 (67 测试文件，pytest)

```bash
# 全部测试
.venv/bin/python3 -m pytest backend/tests/ -v

# 按关键字筛选
.venv/bin/python3 -m pytest backend/tests/ -k "merge"

# 单文件
.venv/bin/python3 -m pytest backend/tests/test_sync_merge.py -v

# 编译检查
.venv/bin/python3 -m py_compile backend/services/sync_merge.py
```

测试分层：
- **纯函数测试**（无 DB）：`test_sync_merge.py` / `test_auto_classifier.py` / `test_knowledge_watcher.py`
- **DAO 测试**（tmp DB）：`test_db.py` / `test_favorite_created_via.py`
- **API 测试**：每个 router 一个测试文件
- **E2E 测试**：`test_codegarden_phase2b_e2e.py`（全流程 + 8898 保护 + 拓扑图 + Playbook 404）

#### 前端 (Vitest + jsdom)

```bash
cd frontend
npm run test:run          # 全部测试
npm run test:watch        # watch 模式
npx tsc --noEmit          # 类型检查
npm run build             # 生产构建 (tsc + vite)
```

测试分布：60+ 组件测试，240+ 用例，覆盖 4 大领域子页面 + Settings + Knowledge + CodeGarden。

#### CI

`.github/workflows/ci.yml` 在 push / PR 时运行：Python compile + pytest + tsc + vitest + vite build。

---

### 数据源

| 领域 | 数据源 | 数量 |
|---|---|---|
| 科技/AI | aihot.virxact.com | 1 |
| 网络安全 | 阿里云漏洞库 (AVD) / CNNVD / 安全客 / FreeBuf / THN / 奇安信 / 绿盟 / Sogou 微信 | 17+ |
| 金融/投资 | 新浪财经 / 腾讯证券 | 2 |
| 独立开发/创业 | Hacker News / Product Hunt | 2 |
| GitHub | GitHub Trending + 搜索 | 1 |
| 标讯 | 政府采购网 (代理爬取) | 1 |
| 知识 | Cubox / 浏览器书签 / SecNews 收藏 | 3 |

完整列表见 [`backend/collectors/`](file:///Users/duke/Documents/hotspot/backend/collectors)。

---

### Phase 路线图

| Phase | 状态 | 内容 |
|---|---|---|
| v1.0–v1.4 | ✅ | 热点聚合 5 大分类 + 质量门禁 + 同步 |
| v1.5 | ✅ | Security Knowledge Graph (MITRE + CVE + 合规) |
| v1.6 | ✅ | CodeGarden Phase 2b (服务网格/资源中枢/联动引擎) |
| v1.7.1–v1.7.5 | ✅ | Phase 1–6: 知识生命周期 + SM-2 复习 + 告警 + 个人画像 + KV 缓存 + FTS |
| **v1.7.6 Phase 7** | ✅ | **MCP Server (13 tools, stdio + SSE)** |
| v1.8 (规划) | 🚧 | Phase 8+：更多 MCP tool（Cubox 全文检索 / 多端同步协调） |

---

### 核心设计原则

1. **本地优先**：所有数据落本地，进程崩溃/重启不丢
2. **简单胜过复杂**：单进程、嵌入式存储、不为分布式需求预留接口
3. **协议优先而非运行时**：通过标准 MCP 协议开放，AI 推理交给外部 agent
4. **数据与智能分离**：hotspot 暴露数据 + 工具，LLM 推理由外部 AI Agent 承担
5. **优雅退化**：单个数据源失败不阻塞其他源；外部网络故障不阻塞缓存读取
6. **可观测但不重型**：结构化日志 + 简单 metrics，**不引入** Prometheus / Grafana

完整设计见 [`docs/ARCHITECTURE.md`](file:///Users/duke/Documents/hotspot/docs/ARCHITECTURE.md)。

---

### 常见问题

**Q: 为什么不内置 LLM 推理？**
A: 让用户在自己已配好的 AI Agent 环境（Cursor/Claude Desktop/Trae）中推理，避免重复配置和 API key 管理。hotspot 只负责数据存储 + 13 个工具暴露。

**Q: 能多用户吗？**
A: 当前是单用户本地工作站，无多用户/权限隔离。SQLite WAL 模式下 `WORKERS=1` 是约束条件。

**Q: 数据怎么备份？**
A: 3 选 1：
1. `backend/data/backup_*.db`（24h 滚动，APScheduler 自动）
2. WebDAV 同步包（坚果云，zip + Fernet 加密）
3. git 跟踪 `knowledge/` 目录

**Q: 远程访问安全吗？**
A: 默认绑定 `127.0.0.1`，不暴露公网。如需远程，改 `HOST=0.0.0.0` + 加 nginx 反代 + HTTPS。

**Q: 端口冲突怎么办？**
A: 后端改 `PORT=8001` 启动；前端改 `vite --port 8899`。**注意**：CodeGarden 资源中枢的 8898 是受保护端口，禁止释放。

---

### 贡献

欢迎 PR / Issue！但请先读：
- [`AGENTS.md`](file:///Users/duke/Documents/hotspot/AGENTS.md) — 项目级 agent 规则
- [`CLAUDE.md`](file:///Users/duke/Documents/hotspot/CLAUDE.md) — 完整开发指南
- [`docs/IMPROVEMENT_PLAN.md`](file:///Users/duke/Documents/hotspot/docs/IMPROVEMENT_PLAN.md) — 改进计划

**禁止**：
- 提交 `.env` / 真实 proxy 配置 / 个人数据
- 引入新框架（Redis / PostgreSQL / Celery）—— 违反「简单胜过复杂」原则
- 多 worker —— SQLite WAL 锁限制

**推荐**：
- 新增数据源 → 继承 `BaseCollector`，加测试
- 新增质量门禁 → 继承 `BaseGate`，加进 `pipeline.py`
- 新增 MCP tool → 在 `mcp_types.py` 加 Pydantic，在 `mcp_config.py` 加 operation_id

---

### 许可证

[LICENSE](file:///Users/duke/Documents/hotspot/LICENSE) — 详情见文件。

---

### 致谢

- [fastapi-mcp](https://github.com/ycd/manage-fastapi) — MCP 协议集成
- [Anthropic MCP](https://modelcontextprotocol.io/) — MCP 协议规范
- [MITRE ATT&CK](https://attack.mitre.org/) — 攻击技术本体（CC-BY-4.0）
- [NVD](https://nvd.nist.gov/) — CVE 数据源

---

---

## English

### What is this

**SecNews** (codename `hotspot`) is a **single-user local workstation for AI + security practitioners**. It unifies three daily workflows into one local system:

| Subsystem | Problem it solves | Entry |
|---|---|---|
| **SecNews** (news aggregation) | 7 domains, 30+ sources, auto-collected/deduped/stored | `/` |
| **Knowledge LLM-Wiki** | Filesystem-driven KB (OKF + LLM-Wiki 2.0), auto-promoted from favorites/bookmarks/Cubox | `/knowledge` |
| **CodeGarden** (project mgmt) | Full project lifecycle (Idea → Archived) with service mesh / resource hub / orchestration engine | `/codegarden` |
| **Security Knowledge Graph** (v1.5+) | MITRE ATT&CK + CVE + compliance ontology; security news auto-graphs | `/security` |
| **MCP Server** (v1.7 Phase 7) | 13 standard tools for **Cursor / Claude Desktop / Trae / Workbuddy** to read/write the local KB | `stdio` / `http://127.0.0.1:8000/mcp/sse` |

### Who is it for

- **AI/ML practitioners**: track model releases, papers, OSS (aihot / OpenAI / Anthropic / Hacker News / Product Hunt)
- **Security researchers / red-blue teams**: track CVEs, ATT&CK techniques, AVD, CNNVD, QiAnXin, NSFOCUS, FreeBuf, THN, etc.
- **Indie hackers / founders**: full lifecycle for side projects, auto port allocation, service scanning, Playbook orchestration
- **Knowledge workers**: turn daily articles, bookmarks, favorites into searchable, reviewable, linkable local knowledge

> One person, one machine, zero external services. LLM inference runs in your external AI Agent (via MCP); hotspot just stores data and exposes 13 tools.

### Quick start

```bash
git clone https://github.com/anyeduke11/secnews.git
cd secnews

# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Configure proxy (required for security/github collectors)
# Edit backend/proxy_config.json — see "Configure proxy" in Chinese section

# Start backend
python run.py                          # http://127.0.0.1:8000

# Frontend (in another terminal)
cd frontend && npm install && npm run dev   # http://localhost:8898
```

### Configure MCP Server (recommended)

Open the frontend → top-right **Settings** → **MCP Server** card → click **Copy stdio config**.

Paste into your AI Agent's config:

| AI Agent | Config path |
|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Trae | `~/.trae/mcp_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| Claude Code | project root `.mcp.json` |

```json
{
  "mcpServers": {
    "hotspot": {
      "command": "python",
      "args": ["-m", "backend.mcp_stdio_main"],
      "cwd": "/absolute/path/to/secnews"
    }
  }
}
```

13 tools (5 read + 8 write) will be auto-discovered.

### Tech stack

- **Backend**: Python 3.10+, FastAPI, SQLite (WAL), APScheduler, fastapi-mcp, loguru
- **Frontend**: React 18, Vite 5, TypeScript, Tailwind 3, echarts, recharts
- **Storage**: SQLite + filesystem (`.md` files as source of truth)
- **Crypto**: Fernet (PBKDF2-derived key)
- **Sync**: WebDAV (Nutstore/Nextcloud) with zip + Fernet envelope
- **Tests**: 67 backend pytest + 60+ frontend Vitest (240+ cases)

### License

[LICENSE](file:///Users/duke/Documents/hotspot/LICENSE) — see file for details.
