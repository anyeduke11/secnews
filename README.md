# SecNews · AI + 安全 知识工作站

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="SecNews v0.7.0 — 单人本地 AI + 安全工作站: Sentinel Terminal 三层工作流 (Data/Judge/Action) 经 MCP 协议暴露 19 个工具">
</p>

> **SecNews**（开发代号 `hotspot`）是面向 **AI + 安全从业者** 的单人本地工作站。
> 从 v0.7.0 起，全站统一收敛为 **Sentinel Terminal** 三层工作流：
> **Data（采集 / 流水线）→ Judge（知识沉淀 / 评估）→ Action（执行 / 协作）**。
> 通过 **MCP 协议** 对外暴露 **19 个工具** (11 读 + 8 写)，
> Cursor / Claude Desktop / Trae / Claude Code 等外部 AI Agent 零改造接入。
>
> 一个人 · 一台电脑 · 零外部服务。

---

## 快速开始

```bash
git clone https://github.com/anyeduke11/secnews.git && cd secnews

# 后端（端口 8000）
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python run.py                        # http://127.0.0.1:8000

# 前端（端口 8898，8898 是 CodeGarden 资源中枢的受保护端口）
cd frontend && npm install && npm run dev   # http://localhost:8898
```

**代理配置（可选）**：`backend/proxy_config.json` 默认 `mode=off`。
需要时把 `127.0.0.1:7897` 改成你的代理端口；
`security_collector` 和 `github_collector` 走代理才能拿到数据，
前端 `/secnews/settings` 可运行时改，无需重启。

> **隐私保护**：`proxy_config.json` / `.env` / `*.db` / `node_modules` 全部已在 `.gitignore` 排除。
> 仓库仅包含 `proxy_config.example.json` / `.env.example` 模板，
> 你需要本地复制并填入自己的代理 / API key，**不会被推送到 GitHub**。

## Sentinel Terminal — 三层工作流

| 层     | 解决什么                                                                 | 入口路由                                                                                       |
| ------ | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| **Data**     | 14 采集器 × 11+ 质量门禁 × Pipeline 流水线 · 趋势 / 搜索 / 导出       | `/secnews` (Feed · Pipeline · Analytics 3 tab)                                                  |
| **Judge**    | 知识库 v2 · md 真源 · kl_pipeline 5 阶段 · FTS5 检索 · 注意力 5 维     | `/knowledge` (Import · Process · Compile · Compound 4 tab) + `/judge` (Sentinel Judge)         |
| **Action**   | CodeGarden 资源中枢 · Service Mesh · 联动引擎 · AI 协作                | `/action` (Sentinel Action) + `/codegarden` + `/garden` (Sentinel Garden) + `/sentinel/settings` |

主入口（v0.7.0 起 `/` 为 **SentinelHomePage** 决策指挥中心）：

| 路由             | 作用                                                                           |
| ---------------- | ------------------------------------------------------------------------------ |
| `/`              | SentinelHomePage — Data/Judge/Action 健康度指挥台 · 今日关键决策             |
| `/judge`         | SentinelJudgePage — 知识管线判官（改走 `/api/kl/compounding` 全量聚合）        |
| `/judge/graph`   | SentinelGraphPage — 知识图谱可视化                                              |
| `/action`        | SentinelActionPage — 执行层 · CodeGarden 联动                                  |
| `/garden`        | SentinelGardenPage — 个人项目花园                                               |
| `/sentinel/settings` | SentinelSettingsPage — dsh 受管子进程 / pi agent / 同步策略               |
| `/secnews`       | 统一工作台 6 tab：Feed · Pipeline · Knowledge · Analyze · Analytics · Settings |
| `/knowledge`     | 知识库 4 tab：Import · Process · Compile · Compound                            |
| `/codegarden`    | CodeGarden 项目管理（项目 · 服务 · 资源 · 事件 · Playbook）                    |
| `/crm`           | CRM 业绩座舱（v0.6 落地）                                                       |

> **重大变更（v0.7.0）**：原 `/workbench` 5 视图已**物理删除**并并入 `/secnews` 统一工作台；
> `dsh` 认知大脑从外部子进程降级为**受管子进程**（gate `dsh=true` 由前端一键启停）。
> v0.5 P1 起 `knowledge/` 根被废弃，**唯一真源为 `llm-wiki-2.0/`** md 文件，SQLite 只做投影索引。

## MCP Server — 19 个工具

> 11 读 + 8 写，外部 AI Agent 零改造接入（`/api/mcp` SSE 通道 + `python -m backend.mcp_stdio_main` stdio 通道双暴露）。

| 读 (11)                                                                                                                                        | 写 (8)                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `search_hotspots` · `get_hotspot` · `list_favorites` · `search_knowledge` · `get_personal_profile` · `wiki_search` · `wiki_read` · `wiki_graph` · `db_trace` · `kl_status` · `dsh_analyze` | `add_favorite` · `remove_favorite` · `add_annotation` · `update_knowledge_item` · `wiki_write` · `kl_enqueue` · `kl_retry` · `dsh_summarize` |

stdio 配置（粘到你的 AI Agent 配置）：

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

| AI Agent         | 配置文件路径                                                            |
| ---------------- | ----------------------------------------------------------------------- |
| Claude Desktop   | `~/Library/Application Support/Claude/claude_desktop_config.json`      |
| Trae             | `~/.trae/mcp_config.json`                                               |
| Cursor           | `~/.cursor/mcp.json`                                                    |
| Claude Code      | 项目根目录 `.mcp.json`                                                  |

启动 AI Agent 后直接说「给我列最近 24h 的安全热点」「把今天这几条喂给 kl_pipeline」即可。

## 架构

<p align="center">
  <img src="./assets/readme/architecture.svg" width="100%" alt="三层架构: 浏览器 / AI Agent 在最上, FastAPI 单进程在中间, SQLite + .md 在底层, 经 MCP 暴露给外部 AI Agent">
</p>

## 数据源

| 领域          | 来源                                                                             |
| ------------- | -------------------------------------------------------------------------------- |
| 科技 / AI     | AIHOT · AGI Hunt · 小互AI                                                        |
| 网络安全      | 阿里云漏洞库 · CNNVD · 安全客 · FreeBuf · THN · 奇安信 · 绿盟 · Sogou 微信        |
| 金融 / 投资   | 新浪财经 · 腾讯证券 · OpenBB                                                     |
| 独立开发      | Hacker News · Reddit · Product Hunt                                              |
| GitHub        | GitHub Trending + 搜索 · OSS Insight                                             |
| 标讯          | 政府采购网（代理爬取）                                                           |
| 知识          | Cubox · 浏览器书签 · SecNews 收藏 · Telegram 频道                                |
| 公开数据      | GDELT（全球事件）                                                                |

完整列表见 [`backend/collectors/`](./backend/collectors)。

## 技术选型

| 组件        | 选型                              | 理由                                                                              |
| ----------- | --------------------------------- | --------------------------------------------------------------------------------- |
| Web 框架    | FastAPI                           | async + OpenAPI 生态成熟                                                           |
| 主存储      | **SQLite WAL** + `llm-wiki-2.0/`  | 零部署 · FTS5 · git 友好 · LLM 可直读 · md 文件是 source of truth                |
| 调度        | APScheduler · **47 jobs**         | 单进程内调度，无外部 MQ；含 cg_service_scan / cg_event_process 等 CodeGarden job   |
| 采集器      | **14 个** BaseCollector           | 7 大领域覆盖，stdin/stdout 标准化                                                  |
| 路由器      | **65 个** FastAPI include_router | core 43 个白名单 + 22 个扩展域（feature_gates 条件注册）                          |
| 业务服务    | **96 个** services 包             | 含 ai_hub / kl_pipeline / dsh / wiki_fs / model_router / agent_bridge 等          |
| MCP         | fastapi-mcp                       | OpenAPI → MCP 自动转换 · 19 个工具                                                 |
| 前端        | React 18 + Vite 5 + TypeScript    | 300+ 组件 · 类型安全 · 热重载                                                      |
| 图表        | echarts + recharts                | 看板风格                                                                          |
| 加密        | Fernet (PBKDF2 派生)              | secrets · 同步包                                                                  |
| 跨端同步    | WebDAV (坚果云) · zip 容器        | 加密包最小化 · 不依赖云服务                                                        |

> 数字由 [`scripts/generate_meta.py`](./scripts/generate_meta.py) AST 反推维护，CI `generate_meta.py --check` 强约束，
> 改完注册代码必须同步 `docs/ARCHITECTURE.md`。

## 路线图

<p align="center">
  <img src="./assets/readme/roadmap.svg" width="100%" alt="SecNews 路线图: 5 个发布版本从 v0.4.3 软分层到 v0.7.0 Sentinel Terminal">
</p>

## 历史版本（GitHub Releases）

每个版本附带源码 zip（`git archive` 产物，不含依赖与个人数据）：

| 版本       | 发布日期       | 关键里程碑                                                  | 源码归档                                                          |
| ---------- | -------------- | ----------------------------------------------------------- | ----------------------------------------------------------------- |
| **v0.7.0** | 2026-08-30     | Sentinel Terminal 三层工作流 (Data/Judge/Action)            | [Source code (zip)](https://github.com/anyeduke11/secnews/releases/tag/v0.7.0) |
| v0.6.0     | 2026-08-27     | 统一工作台 6 tab · dsh 受管子进程 · CRM 业绩座舱            | [Source code (zip)](https://github.com/anyeduke11/secnews/releases/tag/v0.6.0)   |
| v0.5.1     | 2026-08-26     | Chunks / Attention · FTS5 检索 · 5 维注意力评分              | [Source code (zip)](https://github.com/anyeduke11/secnews/releases/tag/v0.5.1)   |
| v0.5.0     | 2026-08-23     | LLM-Wiki 2.0 · kl_pipeline 5 阶段 · md 真源                 | [Source code (zip)](https://github.com/anyeduke11/secnews/releases/tag/v0.5.0)   |
| v0.4.3     | 2026-08-19     | 软分层 / Feature Gates · core/exec 边界                      | [Source code (zip)](https://github.com/anyeduke11/secnews/releases/tag/v0.4.3)   |

## 测试

```bash
# 后端（100+ pytest 文件 · 3000+ 用例）
.venv/bin/python3 -m pytest backend/tests/ -v
.venv/bin/python3 -m pytest backend/tests/ -k "merge"        # 单一域筛选
.venv/bin/python3 -m py_compile backend/services/sync_merge.py

# 前端（Vitest + jsdom · 300+ 用例）
cd frontend
npx vitest run
npx tsc --noEmit
npm run build
```

CI: `.github/workflows/ci.yml` — Python compile + pytest + tsc + vitest + vite build + `generate_meta.py --check` + `harness_analyze.py --check`。

## 常见问题

**Q: 为什么不内置 LLM 推理？**
A: 让用户在自己已配好的 AI Agent 环境（Cursor / Claude Desktop / Trae / Claude Code）中推理，
避免重复配置和 API key 管理。SecNews 只负责数据存储 + 19 工具暴露。

**Q: 能多用户吗？**
A: 当前是单用户本地工作站，无多用户 / 权限隔离。SQLite WAL 模式下 `WORKERS=1` 是约束条件。

**Q: 数据怎么备份？**
A: 3 选 1：
1. `backend/data/backup_*.db`（24h 滚动，APScheduler 自动）
2. WebDAV 同步包（坚果云 · zip + Fernet 加密）
3. git 跟踪 `llm-wiki-2.0/` 目录

**Q: 端口冲突怎么办？**
A: 后端改 `PORT=8001` 启动；前端改 `vite --port 8899`。
**8898 是受保护端口**（CodeGarden 资源中枢），禁止释放。

**Q: 为什么不用 PostgreSQL / Redis / Celery？**
A: 违反「简单胜过复杂」原则 — 单机单用户场景下 SQLite WAL + APScheduler 已足够；
引入分布式组件会破坏「git clone 就能跑」的承诺。

**Q: dsh / pi agent 怎么启停？**
A: 走前端 `/sentinel/settings` 一键启停（gate `dsh=true`），
控制面经 `/api/dsh/control/*`；pi 执行 agent 经 `/api/agents/run` 调用。

## 贡献

新源 → 继承 `BaseCollector` + 测试
新门禁 → 继承 `BaseGate` + 进 `pipeline.py`
新 MCP tool → `mcp_types.py` 加 Pydantic + `mcp_config.py` 加 operation_id（当前 19 个工具: 11 读 + 8 写）

详细：[`AGENTS.md`](./AGENTS.md) · [`CLAUDE.md`](./CLAUDE.md) · [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) · [`docs/CHANGELOG.md`](./docs/CHANGELOG.md)

**禁止**：
- 提交 `.env` / 真实 proxy 配置 / 个人数据 / SQLite 数据库
- 引入 Redis / PostgreSQL / Celery（违反「简单胜过复杂」原则）
- 多 worker（SQLite WAL 锁限制）

## 许可证

[LICENSE](./LICENSE) — GNU GPL-3.0

---

## English

**SecNews** (codename `hotspot`) is a **single-user local workstation for AI + security practitioners**.
As of **v0.7.0**, the whole app is unified into the **Sentinel Terminal** 3-layer workflow:
**Data (collect / pipeline) → Judge (knowledge / evaluate) → Action (execute / collaborate)**.
It exposes **19 MCP tools** (11 read + 8 write) to external AI Agents — Cursor, Claude Desktop, Trae, Claude Code — with zero modifications.

> One person · one machine · zero external services.

### Quick start

```bash
git clone https://github.com/anyeduke11/secnews.git && cd secnews
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python run.py                          # http://127.0.0.1:8000
cd frontend && npm install && npm run dev   # http://localhost:8898
```

Configure `backend/proxy_config.json` (set your proxy port, default `mode=off`).
Copy `proxy_config.example.json` → `proxy_config.json` first; the real file is gitignored.

### MCP stdio config

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

### Releases

| Version | Date       | Milestone                                                                              |
| ------- | ---------- | -------------------------------------------------------------------------------------- |
| v0.7.0  | 2026-08-30 | Sentinel Terminal 3-layer workflow (Data / Judge / Action)                              |
| v0.6.0  | 2026-08-27 | Unified workbench (6 tab) · dsh as managed subprocess · CRM cockpit                    |
| v0.5.1  | 2026-08-26 | Chunks / Attention · FTS5 search · 5-dimensional attention scoring                     |
| v0.5.0  | 2026-08-23 | LLM-Wiki 2.0 · kl_pipeline 5-stage · md as source of truth                             |
| v0.4.3  | 2026-08-19 | Soft core/exec partitioning · Feature Gates (TOML)                                     |

### License

[LICENSE](./LICENSE) — GNU GPL-3.0
