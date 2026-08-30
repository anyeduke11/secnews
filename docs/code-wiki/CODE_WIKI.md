# SecNews Hotspot — Code Wiki

> 版本: v3.0 | 基准代码: **v0.7.0** (2026-08-28 正式发版) | 生成日期: 2026-08-29 | 目标读者: 开发者 / AI Agent
>
> 本版对齐 v0.7.0「workbench 报纸版 100% 接管」后的代码现状。
> 相对 v0.5/v0.6 的最大变化: **首页已变** — 根路径 `/` 重定向到 `/workbench`
> (报纸版 5 视图工作台), 旧三层架构 (data/judge/action) 与 4 个认知模式组件已**物理删除**,
> `workbench_legacy` gate 退役 (详见 [05-running.md](05-running.md) §9 与
> `docs/v0.7_migration_checklist.md`)。
>
> 架构数字 (47 jobs / 14 collectors / 63 routers / 93 services) 由
> `scripts/generate_meta.py` AST 反推维护, 权威来源是
> [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (CI 有 `--check` 门禁)。

## 导航

| 文档 | 内容 |
|------|------|
| [01-architecture.md](01-architecture.md) | 项目整体架构、分层与依赖关系、Feature Gates 机制、核心数据流、存储模型 |
| [02-backend.md](02-backend.md) | 后端详解：启动流程、路由注册表、服务层 (ai_hub 子包)、数据层、采集器、质量管线、KL 管线、调度器 47 job 全表、安全图谱、MCP |
| [03-frontend.md](03-frontend.md) | 前端详解：技术栈、**v0.7.0 路由表全量** (workbench 唯一首页)、Hooks 数据层、API 客户端、组件目录树、测试 |
| [04-subsystems.md](04-subsystems.md) | 子系统：SecNews 看板、Knowledge LLM-Wiki、CodeGarden、Security Graph、Sync、MCP、DSH、CRM |
| [05-running.md](05-running.md) | 运行方式：环境要求、安装、启动、测试、CI 门禁、常用运维 API、开发约定、**首页变更与回退说明** |

## 快速概览

### 产品定位

面向 **AI + 安全从业者** 的单人本地工作站: 一个人 · 一台电脑 · 零外部服务。
安全与 AI 是双核心领域 (安全数据源最广, 知识库中安全 + AI 内容合计约 65%),
金融 / 创业 / 招标 / 科技 / GitHub 为辅助领域。AI 安全交叉内容 (OWASP LLM Top 10、
对抗 ML、prompt injection、AI 红队) 是差异化方向。

### 五大子系统

| # | 子系统 | 说明 | 前端入口 (v0.7.0) |
|---|--------|------|----------|
| 01 | **SecNews 热点聚合 + 工作台** | 8 分类采集 · 30+ 数据源 · 12 同步质量门禁 · **报纸风 5 视图工作台 (唯一首页)** | `/` `/workbench` `/secnews` |
| 02 | **Knowledge LLM-Wiki** | 文件为真相源的知识库 · KL 5 阶段生命周期 · 2 主路径认知模式 (DeepRead/Review) · 注意力评分 · SM-2 · FTS5 | `/knowledge` |
| 03 | **CodeGarden** | 个人代码项目全生命周期 (M1) + 服务网格 (M2) + 资源中枢 (M3) + 联动引擎 (M4) | `/codegarden` |
| 04 | **Security Graph** | MITRE ATT&CK · NVD CVE (热力图+ATT&CK 映射) · 等保 2.0 / GDPR / ISO 27001 合规矩阵 | `/workbench/analyze` `/secnews/analytics` |
| 05 | **MCP Server** | 9 个标准工具 · stdio / SSE 双通道 · 暴露给外部 AI Agent (默认关闭) | `python -m backend.mcp_stdio_main` |

### 技术栈

```
┌────────────────────────────────────────────────────────────────┐
│ Frontend: React 18 + TypeScript + Vite 5 + Tailwind 3.4        │
│           react-router-dom v6 · ECharts · Vitest + jsdom       │
│           Port: 8898 (strictPort, 占用即报错)                   │
│           v0.7.0: workbench 报纸版 5 视图为唯一首页             │
├────────────────────────────────────────────────────────────────┤
│ Backend:  FastAPI + Uvicorn (单进程单 worker)                   │
│           SQLite WAL (thread-local 连接, autocommit)            │
│           APScheduler (47 jobs, 进程内) · loguru 结构化日志      │
│           Port: 8000 (CORS 白名单: 8000/8898/8899)              │
├────────────────────────────────────────────────────────────────┤
│ Storage:  SQLite (hotspot.db, ~69 个正向迁移)                   │
│           knowledge/*.md 文件 (真相源) + llm-wiki-2.0 归档层     │
│           WebDAV (坚果云) zip 容器 + Fernet 加密同步             │
└────────────────────────────────────────────────────────────────┘
```

### 关键设计决策

- **单用户、单进程、零外部服务** — 显式不引入 Redis / PostgreSQL / Celery / Elasticsearch / Docker / Prometheus
- **SQLite WAL 模式** — 线程本地连接 + autocommit; `WORKERS=1` 避免多 worker 锁竞争
- **文件优先** — Knowledge 以 `.md` 为 source of truth, SQLite 是读缓存 (Watchdog 双向同步)
- **Core / Extension 软分层** — `backend/config/feature_gates.toml` 单一开关源, 关闭扩展不删代码, 只隐藏路由 / job / 前端 tab; core 白名单路由永不消失
- **v0.7.0 workbench 单入口** — 旧三层 UI 物理删除 (非 gate 开关), 功能由 `/workbench` 5 视图承接; 回退只能 git revert 历史 commit
- **优雅退化** — 单源失败不阻塞整轮采集; feature_gates.toml 损坏回退"全部开启"; DSH 不可达自动降级 llm_service 直连
- **同步包 ASCII 命名** — 坚果云 WebDAV quirk, 同步包固定 `config-YYYY-MM-DD.zip`
- **前端端口固定 8898** — `--strictPort`, 禁止自动漂移

### 快速开始

```bash
# 后端 (Python 3.11+)
pip install -r backend/requirements.txt
python run.py                        # http://127.0.0.1:8000

# 前端 (Node 18+)
cd frontend && npm install && npm run dev   # http://localhost:8898 → 自动跳 /workbench

# 测试
python -m pytest backend/tests/ --tb=short -q          # 2938 passed (2 failed 为 codegarden 端口预存)
cd frontend && npx tsc --noEmit && npx vitest run      # 304 passed
```

完整说明 (代理配置、环境变量、CI 门禁、运维 API、首页变更回退) 见 [05-running.md](05-running.md)。
