# 01 — 项目整体架构

## 1. 目录结构

```
hotspot/
├── run.py                    # 后端启动入口 (uvicorn)
├── backend/                  # Python 后端 (FastAPI)
│   ├── main.py               # FastAPI app 创建 + lifespan + 中间件
│   ├── config.py             # Pydantic Settings (HOTSPOT_* 环境变量)
│   ├── exceptions.py         # 统一异常体系 (HotspotException 基类)
│   ├── cache.py              # TTLCache (LRU + TTL 进程内缓存)
│   ├── logging_config.py     # loguru 日志配置
│   ├── observability.py      # 结构化事件日志 (log_event)
│   ├── crypto.py             # Fernet 加密 (master key 派生)
│   ├── api/                  # 26 个 API Router 模块
│   ├── services/             # 41 个业务逻辑模块
│   ├── repository/           # 20 个 DAO 仓库 + 35 个 SQL 迁移
│   ├── collectors/           # 8 个采集器 (BaseCollector 子类)
│   ├── parsers/              # 独立解析器 (BaseSourceParser 子类)
│   ├── domain/               # Pydantic 数据模型 + 枚举
│   ├── quality/              # 13 个质量门禁 (Pipeline)
│   ├── scheduler/            # APScheduler 封装 (19 个 job)
│   ├── security/             # 安全知识图谱 (ATT&CK / CVE / 合规)
│   └── tests/                # 67 个测试文件
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── App.tsx           # 路由 + 主题 + 全局状态
│   │   ├── components/       # ~60 个 React 组件
│   │   ├── hooks/            # 自定义 Hooks
│   │   ├── types/            # TypeScript 类型定义
│   │   └── test/             # Vitest 测试
│   ├── package.json          # Vite + React + Tailwind
│   └── vite.config.ts
├── knowledge/                # LLM-Wiki 知识库 (文件系统)
│   ├── items/                # ~405 个知识条目 (.md)
│   ├── concepts/             # ~35 个概念 (.md + graph.json)
│   ├── learning/tasks/       # 学习任务队列
│   ├── content/              # 内容创作 (drafts + calendar.json)
│   ├── summaries/            # 周报/回顾
│   ├── _MAP.md               # 知识地图 (自动生成)
│   ├── _SCHEMA.md            # 数据模型契约
│   └── SOUL.md               # 角色画像 (自动生成)
├── codegarden/               # CodeGarden 项目配置
│   ├── playbooks/            # Playbook YAML 定义
│   ├── specs/                # 项目规约
│   ├── prompts/              # Prompt 模板
│   └── exports/              # 导出产物
├── docs/                     # 设计文档
│   ├── ARCHITECTURE.md       # 架构优化方案 v3.0
│   ├── DESIGN_GUIDE.md       # 设计规范
│   ├── CodeGarden_PRD_v2.0.md
│   └── v1.7_development_plan.md
└── scripts/                  # 运维脚本
```

## 2. 系统拓扑

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Browser (React SPA :8898)                       │
│  Header / CategoryNav / SearchBar / StatsPanel / TrendChart / Grid  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP/JSON + SSE
┌──────────────────────────────▼───────────────────────────────────────┐
│                    FastAPI (uvicorn, :8000, 1 worker)                 │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ 26 API Router│  │  TTLCache    │  │  19 APScheduler Jobs     │   │
│  │ /api/*       │  │  (3 实例)    │  │  Interval + Cron         │   │
│  └──────┬───────┘  └──────────────┘  └───────────┬──────────────┘   │
│         │                                         │                   │
│  ┌──────▼─────────────────────────────────────────▼──────────────┐   │
│  │                    Service Layer (41 modules)                   │   │
│  │  CollectionService / SyncService / AutoClassifier /            │   │
│  │  ConceptLinker / SoulService / CodeGarden*Service / ...        │   │
│  └──────┬─────────────────────────────────────────────────────────┘   │
│         │                                                             │
│  ┌──────▼──────────┐  ┌──────────────────┐  ┌────────────────────┐   │
│  │ Repository (20) │  │ Collector Pool   │  │ Quality Pipeline   │   │
│  │ SQLite DAO      │  │ 8 BaseCollector  │  │ 13 Gates (sync)    │   │
│  └──────┬──────────┘  └────────┬─────────┘  └────────────────────┘   │
│         │                      │                                      │
└─────────┼──────────────────────┼──────────────────────────────────────┘
          │                      │
   ┌──────▼──────┐       ┌───────▼────────┐
   │ SQLite .db  │       │ 30+ External   │
   │ (WAL mode)  │       │ RSS/API/HTML   │
   └─────────────┘       └────────────────┘
```

## 3. 设计原则

| # | 原则 | 实现 |
|---|------|------|
| 1 | **本地优先** | 所有数据落 SQLite，进程崩溃不丢 |
| 2 | **简单胜过复杂** | 单进程、嵌入式存储、零外部服务 |
| 3 | **写入一次，查询多次** | 写入路径重（采集+质量+入库），读取路径极致轻（缓存+SQL） |
| 4 | **优雅退化** | 单源失败不阻塞，外部网络故障不阻塞缓存读取 |
| 5 | **可观测但不重型** | loguru 结构化日志 + `log_event`，不引入 Prometheus/Grafana |
| 6 | **文件优先** | Knowledge 以 .md 为 source of truth，SQLite 为读缓存 |

## 4. 数据流

```
外部数据源 (RSS/API/HTML)
    │
    ▼
BaseCollector.collect()          ← 并行采集，隔离异常
    │
    ▼
QualityGatePipeline.run()        ← 13 个门禁顺序执行，累加扣分
    │
    ▼
HotspotRepository.upsert()       ← SQLite 写入，去重
    │
    ▼
cache.invalidate("hotspots:*")   ← 写穿透失效缓存
    │
    ▼
API Router → TTLCache → SQLite   ← 读路径：缓存命中 < 50ms
```

## 5. 技术栈明细

| 层 | 技术 | 版本 |
|----|------|------|
| Web 框架 | FastAPI | latest |
| ASGI 服务器 | Uvicorn | latest |
| 数据库 | SQLite (WAL) | 3.x |
| 调度器 | APScheduler (AsyncIO) | latest |
| 缓存 | 自研 TTLCache (thread-safe) | — |
| 加密 | Fernet (cryptography) | — |
| HTTP 客户端 | aiohttp + ProxySession | — |
| 日志 | loguru | — |
| 前端框架 | React | 18.2 |
| 构建工具 | Vite | 5.x |
| CSS | Tailwind CSS | 3.4 |
| 图表 | ECharts 6 + Recharts 3 | — |
| 路由 | react-router-dom | 6.23 |
| 测试 | Vitest + jsdom | 2.x |
| 类型 | TypeScript | 5.3 |