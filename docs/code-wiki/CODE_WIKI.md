# SecNews Hotspot — Code Wiki

> 版本: v2.0 | 基准代码: v0.6.2 | 生成日期: 2026-08-28 | 目标读者: 开发者 / AI Agent
>
> 本版在旧版 Wiki (2026-07-23) 基础上**全量重写**，补齐 2026-07 以来的新模块:
> `kl_pipeline/` (KL 知识管线)、`wiki_fs/` (文件存储契约)、Core/Extension 软分层与 feature gates、
> SecNews 安全看板、CRM 业绩座舱、DSH 桥接层、Crawler v2 等。
>
> 架构数字 (router / service / job / collector 数量) 由 `scripts/generate_meta.py` AST 反推维护，
> 权威来源是 [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) (CI 有 `--check` 门禁)。
> 本文引用 2026-08-25 快照值，若与代码不符以 `generate_meta.py` 输出为准。

## 导航

| 文档 | 内容 |
|------|------|
| [01-architecture.md](01-architecture.md) | 项目整体架构、分层与依赖关系、Feature Gates 机制、核心数据流、存储模型 |
| [02-backend.md](02-backend.md) | 后端详解：启动流程、路由层、服务层、数据层、采集器、质量管线、KL 管线、调度器 47 job 全表、安全图谱、MCP |
| [03-frontend.md](03-frontend.md) | 前端详解：技术栈、路由表全量、Hooks 数据层、API 客户端、组件目录树、测试 |
| [04-subsystems.md](04-subsystems.md) | 子系统：SecNews 看板、Knowledge LLM-Wiki、CodeGarden、Security Graph、Sync、MCP、DSH、CRM |
| [05-running.md](05-running.md) | 运行方式：环境要求、安装、启动、测试、CI 门禁、常用运维 API、开发约定 |

## 快速概览

### 产品定位

面向 **AI + 安全从业者** 的单人本地工作站: 一个人 · 一台电脑 · 零外部服务。
安全与 AI 是双核心领域 (安全数据源最广, 知识库中安全 + AI 内容合计约 65%),
金融 / 创业 / 招标 / 科技 / GitHub 为辅助领域。AI 安全交叉内容 (OWASP LLM Top 10、
对抗 ML、prompt injection、AI 红队) 是差异化方向。

### 五大子系统

| # | 子系统 | 说明 | 前端入口 |
|---|--------|------|----------|
| 01 | **SecNews 热点聚合** | 8 分类采集器 · 30+ 数据源 · 12 同步质量门禁 + URL 校验 job · 趋势 / 搜索 / 导出 / 追抓 | `/` `/secnews` |
| 02 | **Knowledge LLM-Wiki** | 文件为真相源的知识库 · KL 5 阶段生命周期 · 6 认知模式 · 注意力评分 · SM-2 复习 · FTS5 | `/knowledge` |
| 03 | **CodeGarden** | 个人代码项目全生命周期 (M1) + 服务网格 (M2) + 资源中枢 (M3) + 联动引擎 (M4) | `/codegarden` `/action/codegarden` |
| 04 | **Security Graph** | MITRE ATT&CK · NVD CVE · 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 合规矩阵 | `/knowledge/process` |
| 05 | **MCP Server** | 9 个标准工具 · stdio / SSE 双通道 · 暴露给外部 AI Agent | `python -m backend.mcp_stdio_main` |

### 技术栈

```
┌────────────────────────────────────────────────────────────────┐
│ Frontend: React 18 + TypeScript + Vite 5 + Tailwind 3.4        │
│           react-router-dom v6 · ECharts · Vitest + jsdom       │
│           Port: 8898 (strictPort, 占用即报错)                   │
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
- **优雅退化** — 单个数据源失败不阻塞整轮采集; 外部网络故障不阻塞缓存读取; feature_gates.toml 损坏时回退"全部开启"
- **同步包 ASCII 命名** — 坚果云 WebDAV 对中文文件名 PUT 有 quirk, 同步包固定 `config-YYYY-MM-DD.zip` (envelope.json 密文 + manifest.json 明文)
- **前端端口固定 8898** — `--strictPort`, 禁止自动漂移

### 快速开始

```bash
# 后端 (Python 3.11+)
pip install -r backend/requirements.txt
python run.py                        # http://127.0.0.1:8000

# 前端 (Node 18+)
cd frontend && npm install && npm run dev   # http://localhost:8898

# 测试
python -m pytest backend/tests/ --tb=short -q
cd frontend && npx tsc --noEmit && npx vitest run
```

完整说明 (代理配置、环境变量、CI 门禁、运维 API) 见 [05-running.md](05-running.md)。
