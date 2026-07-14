# Hotspot — Code Wiki

> 仓库: `/Users/duke/Documents/hotspot`
> 文档版本: 1.2.0(对齐 `backend.main.APP_VERSION`)
> 最后更新: 2026-07-06

---

## 1. 项目概述

Hotspot 是一个**热点资讯聚合与质量管控平台**。它从多个公开数据源(RSS、API、HTML 站点)自动采集热点资讯,经过 9 道质量门禁(Quality Gate)筛选打分后入库 SQLite,并通过 React 前端展示给用户。定位是**单人本地使用**的轻量级数据看板。

### 1.1 核心能力

| 能力 | 说明 |
|------|------|
| 多源采集 | 6 大分类(AI / 安全 / 金融 / 创业 / 招标 / GitHub)+ 用户自定义源 |
| 质量门禁 | 9 道同步门禁 + 1 道异步门禁,对每条资讯打分(0-100) |
| 趋势分析 | 按小时聚合,生成 24h 趋势热力图 |
| 收藏系统 | 单用户场景下收藏 / 取消收藏 / 按分类筛选 |
| 定时调度 | APScheduler 驱动周期性采集 + 质量后台任务 |
| 代理感知 | 支持 off / auto / manual 三种代理模式 |
| 全文检索 | SQLite FTS5 + unicode61 分词 |
| 可观测性 | 结构化 JSON 日志 + trace_id + 事件打点 + /api/health + /api/stats |

### 1.2 关键非功能指标

- **启动时间** < 3s(含冷启动 + 首次采集)
- **API P95** < 200ms(缓存命中 < 50ms)
- **数据量** 优雅支撑 1k → 100k+ 条热点
- **故障恢复** 服务重启数据零丢失;外部源失败不影响整体可用
- **进程模型** 单进程 + 嵌入式 SQLite + 进程内调度,**零外部服务依赖**

---

## 2. 系统架构

### 2.1 总体分层

```
┌──────────────────────────────────────────────────────────────────┐
│                       Browser (React SPA)                         │
│   Header / CategoryNav / SearchBar / StatsPanel / TrendChart      │
│   HotspotGrid / SettingsPanel / FavoritesPanel                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP / JSON
┌────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI 进程 (单进程)                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  API Router    │  │ LRU Cache      │  │  Middleware      │   │
│  │  /api/*        │←→│  (in-process)  │  │  TraceID         │   │
│  └────────┬───────┘  └────────────────┘  └──────────────────┘   │
│  ┌────────▼─────────────────────────────────────────────────┐   │
│  │              Domain Service Layer                          │   │
│  │   HotspotService · TrendService · CollectionService       │   │
│  │   ExportService                                           │   │
│  └────────┬──────────────────────────────────────────────────┘   │
│  ┌────────▼─────────┐         ┌────────────────────────────┐    │
│  │  Repository      │←────────│  Scheduler (APScheduler)   │    │
│  │  (SQLite + WAL)  │         │  - 5min: 全量采集           │    │
│  └────────▲─────────┘         │  - 5min: 趋势重算           │    │
│  ┌────────┴─────────┐         │  - 5min: URL 内容验证       │    │
│  │  Collector Pool  │         │  - 30min: 导出预生成        │    │
│  │  6 × BaseCollector│←───────│  - 6h:   来源信誉重算       │    │
│  │  (并发、隔离、降级)│         └────────────────────────────┘    │
│  └──────────────────┘                                            │
└──────────────────────────────────────────────────────────────────┘
        │                                  │
   ┌────▼────┐                        ┌────▼─────┐
   │ SQLite  │                        │ 日志文件  │
   │ *.db    │                        │ logs/*.log│
   └─────────┘                        └──────────┘
```

### 2.2 请求生命周期

```
用户操作 → React 前端 → HTTP API → FastAPI Router
  → TraceIDMiddleware(注入 trace_id)
  → Service Layer(读 list_cache / detail_cache / static_cache)
  → 未命中 → Repository(SQLite 查询)
  → 返回响应 + X-Trace-Id / X-Duration-Ms 头
```

### 2.3 采集生命周期

```
APScheduler.collect_all_job (每 5min)
  → CollectionService.run_once()
    → asyncio.gather(6 个 Collector.collect())       并发抓取
      → 每个 Collector.fetch_source() 走 crawl4ai 或 aiohttp
      → _parse_html() + _build_items() 解析为 HotspotItem
      → _run_quality_gates() 跑 9 道同步门禁(放到 thread pool)
    → HotspotRepository.upsert_many() 单事务批量入库
    → TrendRepository.rebuild(24) 重算趋势
    → cache_invalidate("hotspots:*") + cache_invalidate("trends:*")
    → 异步触发 url_content_check(抽样 10%)
    → evaluate_source_coverage() 评估源覆盖度,写 source_stats
    → 写 collection_runs 审计日志
```

### 2.4 模块依赖关系(自上而下)

```
main.py
  ├── api/*.py          → services/*.py → repository/*.py → db.py
  ├── scheduler/*.py    → services/collection_service.py → collectors/*
  │                                       → quality/pipeline.py → quality/*_gate.py
  ├── cache.py          (全局 TTLCache 实例)
  ├── observability.py  (事件打点)
  ├── logging_config.py (loguru)
  ├── exceptions.py     (异常 + handler)
  └── proxy_*.py        (代理配置 / session)
```

**禁止反向依赖**: repository 不导入 services;collectors 不导入 api;domain 不导入任何上层。

---

## 3. 目录结构详解

### 3.1 顶层结构

```
hotspot/
├── run.py                # 一键启动脚本(uvicorn 入口)
├── backend/              # Python 后端
├── frontend/             # React + TS 前端
├── scripts/              # 运维 / 调试 / 压测 / 混沌测试脚本
├── docs/                 # 设计文档 / 验收报告 / Runbook
├── ARCHITECTURE.md       # 架构文档(v3.0)
├── DESIGN_GUIDE.md       # 设计指南
├── CODE_WIKI.md          # 本文件
├── README.md             # 用户文档
└── AGENTS.md / CLAUDE.md / GEMINI.md  # AI Agent 工作指南
```

### 3.2 后端目录 ([backend/](file:///Users/duke/Documents/hotspot/backend))

```
backend/
├── main.py                 # FastAPI 应用入口 & lifespan
├── config.py               # Pydantic Settings 配置中心
├── exceptions.py           # 异常体系 + 全局 handler
├── cache.py                # TTLCache + 3 个实例 + warmup
├── observability.py        # log_event / uptime_s
├── logging_config.py       # loguru 结构化日志配置
├── proxy_config.py         # 代理配置管理
├── proxy_session.py        # 代理感知的 aiohttp session
├── requirements.txt        # Python 依赖清单
│
├── api/                    # REST API 路由(9 个 router)
│   ├── __init__.py         # register_routers(app)
│   ├── health.py           # /api/health + /api/stats
│   ├── hotspots.py         # /api/hotspots
│   ├── categories.py       # /api/categories
│   ├── trends.py           # /api/trends
│   ├── export.py           # /api/export
│   ├── proxy.py            # /api/proxy
│   ├── favorites.py        # /api/favorites
│   ├── sources.py          # /api/sources(自定义源)
│   ├── quality.py          # /api/quality
│   └── middleware.py       # TraceIDMiddleware
│
├── collectors/             # 数据采集器
│   ├── base.py             # BaseCollector 抽象基类
│   ├── ai_collector.py     # AI 资讯(HackerNews / 量子位 / 36氪 / 机器之心)
│   ├── security_collector.py
│   ├── finance_collector.py
│   ├── startup_collector.py
│   ├── bid_collector.py
│   ├── github_collector.py # GitHub Trending
│   ├── aggregator.py       # 已废弃的兼容层
│   └── __init__.py
│
├── quality/                # 质量门禁系统
│   ├── base.py             # BaseGate + GateContext
│   ├── pipeline.py         # QualityGatePipeline(9 门禁编排)
│   ├── config.py           # QualityConfig + QualityMode
│   ├── scorer.py           # 评分工具
│   ├── schema_gate.py
│   ├── content_quality_gate.py
│   ├── category_match_gate.py
│   ├── url_validity_gate.py
│   ├── source_reputation_gate.py
│   ├── title_summary_gate.py
│   ├── duplicate_gate.py   # URL + Jaccard 标题相似度
│   ├── author_verification_gate.py  # Phase 9
│   ├── final_url_gate.py   # Phase 9.2
│   ├── final_url_resolver.py
│   ├── publisher_registry.py
│   ├── url_content_gate.py # 异步门禁
│   ├── source_coverage.py  # Phase 9 源覆盖度
│   ├── jobs.py             # 异步质量任务
│   └── __init__.py
│
├── services/               # 业务服务层
│   ├── collection_service.py  # 采集编排器
│   ├── hotspot_service.py     # 热点查询 + cursor 分页
│   ├── trend_service.py       # 趋势服务
│   ├── export_service.py      # Excel 导出
│   └── __init__.py
│
├── repository/             # 数据访问层
│   ├── db.py               # SQLite 连接 + 迁移
│   ├── hotspot_repo.py     # hotspots CRUD + FTS5 检索
│   ├── trend_repo.py       # trend_snapshots
│   ├── settings_repo.py    # settings KV
│   ├── favorite_repo.py    # favorites + favorites_stats
│   ├── quality_repo.py     # quality_check_logs + source_reputation
│   ├── source_stats_repo.py
│   ├── custom_source_repo.py
│   └── migrations/         # 6 个 SQL 迁移文件
│
├── scheduler/              # APScheduler 调度
│   ├── scheduler.py        # HotspotScheduler 封装
│   └── jobs.py             # 5 个 job 函数
│
├── domain/                 # Pydantic 数据模型
│   ├── models.py           # HotspotItem / TrendPoint / CollectionRun
│   ├── enums.py            # Category / TimeRange / CollectorStatus
│   ├── collection.py       # SourceResult / CollectionResult / CollectionReport / GateResult / PipelineResult
│   └── __init__.py
│
├── utils/
│   └── crawl4ai_client.py  # 可选的 Playwright 渲染客户端
│
├── tools/
│   └── import_cache.py     # 历史数据导入工具
│
├── scripts/
│   ├── purge_synthetic_urls.py
│   └── verify_phase13.py
│
└── tests/                  # pytest 单元 / 集成测试(38+ 测试文件)
```

### 3.3 前端目录 ([frontend/](file:///Users/duke/Documents/hotspot/frontend))

```
frontend/
├── src/
│   ├── main.tsx            # React 入口
│   ├── App.tsx             # 根组件 + 状态编排
│   ├── index.css           # Tailwind + CSS 变量主题
│   ├── types/
│   │   └── index.ts        # 与后端 Pydantic 对齐的 TS 类型 + CATEGORIES 常量
│   ├── hooks/
│   │   ├── useHotspotData.ts    # 热点列表 + cursor 分页
│   │   ├── useTrendData.ts      # 趋势数据
│   │   └── useRefreshInterval.ts # 自动刷新间隔(从 /api/health 同步)
│   └── components/
│       ├── Header.tsx
│       ├── CategoryNav.tsx
│       ├── SearchBar.tsx
│       ├── HotspotGrid.tsx
│       ├── HotspotCard.tsx
│       ├── TrendChart.tsx
│       ├── StatsPanel.tsx
│       ├── SettingsPanel.tsx
│       ├── FavoritesPanel.tsx
│       └── LoadingSkeleton.tsx
├── index.html
├── package.json
├── vite.config.ts          # dev 代理 /api → http://127.0.0.1:8000
├── tsconfig.json
├── tailwind.config.js
└── postcss.config.js
```

---

## 4. 数据模型

### 4.1 域模型 ([backend/domain/](file:///Users/duke/Documents/hotspot/backend/domain))

#### [HotspotItem](file:///Users/duke/Documents/hotspot/backend/domain/models.py#L39) — 核心数据模型

```python
class HotspotItem(BaseModel):
    id: str                          # "{source}_{name}_{i}"
    title: str                       # 1-500 字符
    summary: Optional[str]           # ≤500 字符
    source: str                      # 数据源名
    url: HttpUrl                     # Pydantic v2 HttpUrl
    category: Category               # 枚举(ai/security/finance/startup/bid/github)
    published_at: datetime           # tz-aware UTC
    fetched_at: datetime             # tz-aware UTC
    score: Optional[int]             # 0-100,可空
    is_fallback: bool = False        # 备用数据标记
    quality_score: int = 100         # 质量评分(0-100)
    quality_flags: list[str]         # ["title_too_short", ...]
    quality_checked_at: Optional[datetime]
    url_check_status: Optional[Literal["pending","verified","mismatch","skipped"]]
```

**强制约束**:`published_at` / `fetched_at` 必须是 tz-aware UTC,字段验证器 `_validate_tz` 拒绝 naive datetime。

#### [Category](file:///Users/duke/Documents/hotspot/backend/domain/enums.py#L18) — 6 个枚举值

```python
class Category(str, Enum):
    AI = "ai"
    SECURITY = "security"
    FINANCE = "finance"
    STARTUP = "startup"
    BID = "bid"
    GITHUB = "github"

    @classmethod
    def from_str(cls, s: str) -> "Category":
        # 容错解析,未知值抛 InvalidParamException
```

#### [TimeRange](file:///Users/duke/Documents/hotspot/backend/domain/enums.py#L51) — 时间窗口

`H24="24h"` / `D3="3d"` / `D7="7d"` / `D30="30d"`,通过 `to_hours()` 转换为小时数。

#### [CollectorStatus](file:///Users/duke/Documents/hotspot/backend/domain/enums.py#L70)

`SUCCESS` / `PARTIAL` / `FAILED`,写入 `collection_runs.status`。

#### 采集报告模型 ([collection.py](file:///Users/duke/Documents/hotspot/backend/domain/collection.py))

| 模型 | 范围 | 关键字段 |
|------|------|---------|
| `SourceResult` | 单源 | source_name, item_count, fallback_used, error_msg, duration_ms |
| `CollectionResult` | 单分类 | category, items, item_count, fallback_count, source_results, error |
| `CollectionReport` | 全量 | total, success_count, failed_count, duration_ms, failures, results |
| `GateResult` | 单门禁 | gate_name, passed, score_deduction, flags, reason, error_msg |
| `PipelineResult` | 单 item 全门禁 | item_id, gate_results, final_score, final_flags, accepted, mode |

### 4.2 数据库 Schema (SQLite)

共 **11 张表**,迁移文件位于 [backend/repository/migrations/](file:///Users/duke/Documents/hotspot/backend/repository/migrations)。

| 表名 | 迁移文件 | 说明 |
|------|---------|------|
| `hotspots` | [001_init.sql](file:///Users/duke/Documents/hotspot/backend/repository/migrations/001_init.sql) | 热点资讯主表(14 字段) |
| `hotspots_fts` | 001 | FTS5 虚拟表(title + summary),3 个触发器同步 |
| `trend_snapshots` | 001 | 24h 趋势桶(hours_ago, category, count) |
| `collection_runs` | 001 | 采集运行审计日志 |
| `settings` | 001 | KV 配置表(`key` PRIMARY KEY) |
| `schema_version` | db.py 运行时创建 | 迁移版本追踪 |
| `quality_check_logs` | [002_quality.sql](file:///Users/duke/Documents/hotspot/backend/repository/migrations/002_quality.sql) | 门禁审计日志 |
| `source_reputation` | 002 | 来源信誉评分(初始 70) |
| `custom_sources` | [004_custom_sources.sql](file:///Users/duke/Documents/hotspot/backend/repository/migrations/004_custom_sources.sql) | 用户自定义源 |
| `source_stats` | [005_source_stats.sql](file:///Users/duke/Documents/hotspot/backend/repository/migrations/005_source_stats.sql) | 源累计统计(active/stale/dead) |
| `coverage_runs` | 005 | 源覆盖度快照 |
| `favorites` | [006_favorites.sql](file:///Users/duke/Documents/hotspot/backend/repository/migrations/006_favorites.sql) | 用户收藏 |
| `favorites_stats` | 006 | 收藏分类聚合 |

#### hotspots 表关键字段

```sql
id              TEXT PRIMARY KEY          -- "{source}_{name}_{i}"
title           TEXT NOT NULL
summary         TEXT
source          TEXT NOT NULL
url             TEXT NOT NULL
category        TEXT NOT NULL CHECK(category IN ('ai','security','finance','startup','bid','github'))
published_at    TEXT NOT NULL             -- ISO 8601 UTC
score           INTEGER
fetched_at      TEXT NOT NULL
is_fallback     INTEGER NOT NULL DEFAULT 0
quality_score   INTEGER NOT NULL DEFAULT 100
quality_flags   TEXT NOT NULL DEFAULT '[]' -- JSON array
quality_checked_at TEXT
url_check_status TEXT                     -- pending|verified|mismatch|skipped
```

#### 关键索引

| 索引 | 用途 |
|------|------|
| `idx_cat_pub` (category, published_at DESC) | 主查询:按分类取最新 |
| `idx_pub` (published_at DESC) | 全局最新 |
| `idx_fallback` (WHERE is_fallback=0) | 过滤备用数据 |
| `idx_source` (source) | 按源查询 |
| `idx_trend_lookup` (hours_ago, category) | 趋势查询 |
| `idx_qcl_item` / `idx_qcl_gate` / `idx_qcl_time` | 门禁日志多维查询 |

#### PRAGMA 配置([db.py](file:///Users/duke/Documents/hotspot/backend/repository/db.py#L75))

```python
PRAGMA journal_mode=WAL         # 并发读 + 单写
PRAGMA synchronous=NORMAL       # 性能/安全平衡
PRAGMA foreign_keys=ON          # 外键约束
PRAGMA busy_timeout=5000        # 5s 等待避免 SQLITE_BUSY
```

---

## 5. 后端模块详解

### 5.1 应用入口 ([main.py](file:///Users/duke/Documents/hotspot/backend/main.py))

**[lifespan](file:///Users/duke/Documents/hotspot/backend/main.py#L34)** 异步上下文管理器:

启动序列:
1. `set_start_time()` 记录启动时间
2. `setup_logging()` 配置 loguru
3. `init_db()` SQLite 完整性检查 + 迁移
4. `warmup()` 缓存预热(哨兵条目)
5. `rebuild_export_cache()` 导出预生成
6. 创建 `CollectionService` → `set_service(svc)`
7. 创建 `HotspotScheduler` → `attach_service(svc)` → `start()`
8. `app.state.scheduler = sched`(Phase 8: 替代模块 singleton)
9. 打 `startup_complete` 事件

关闭序列:`sched.stop()` → 清理 `app.state.scheduler` → `cache_invalidate("*")` → `close_db()`。

**CORS 白名单**:`localhost:8898` / `127.0.0.1:8898` / `localhost:8000` / `127.0.0.1:8000`。

### 5.2 配置中心 ([config.py](file:///Users/duke/Documents/hotspot/backend/config.py))

`Settings` 继承 `pydantic_settings.BaseSettings`,环境变量前缀 `HOTSPOT_`。全局单例 `config = Settings()`。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `host` / `port` | `0.0.0.0` / `8000` | 服务监听 |
| `db_path` | `backend/hotspot.db` | SQLite 路径 |
| `log_dir` | `backend/logs` | 日志目录 |
| `cache_ttl_seconds` | `300` | 列表缓存 TTL |
| `cache_maxsize` | `64` | 列表缓存容量 |
| `collect_interval_seconds` | `300` | 采集间隔 |
| `collect_timeout_seconds` | `60` | 单次采集超时 |
| `quality_strict_mode` | `False` | 严格模式开关 |
| `quality_min_score` | `50` | 最低接受评分 |
| `quality_url_check_sample_rate` | `0.1` | URL 验证抽样率 |
| `quality_url_check_timeout` | `8` | URL 验证超时 |

### 5.3 异常体系 ([exceptions.py](file:///Users/duke/Documents/hotspot/backend/exceptions.py))

```
HotspotException (基类)
  ├── InvalidParamException      → HTTP 400, code=INVALID_PARAM
  ├── NotFoundException          → HTTP 404, code=NOT_FOUND
  ├── RateLimitedException       → HTTP 429, code=RATE_LIMITED
  ├── InternalException          → HTTP 500, code=INTERNAL
  ├── SourceUnavailableException → HTTP 503, code=SOURCE_UNAVAILABLE
  └── QualityGateFailed          → HTTP 422, code=QUALITY_GATE_FAILED
                                    (严格模式拒绝入库时抛)
```

[register_exception_handlers](file:///Users/duke/Documents/hotspot/backend/exceptions.py#L102) 注册全局 handler,统一响应体:

```json
{"code": "...", "message": "...", "trace_id": "...", "version": "1.2.0"}
```

### 5.4 缓存层 ([cache.py](file:///Users/duke/Documents/hotspot/backend/cache.py))

**手写线程安全 TTLCache**(非 cachetools,实际未引入该依赖),LRU + TTL 双重淘汰。

3 个全局实例:

| 实例 | maxsize | TTL | 用途 |
|------|---------|-----|------|
| [list_cache](file:///Users/duke/Documents/hotspot/backend/cache.py#L191) | 64 | 300s | 列表查询、趋势 |
| [detail_cache](file:///Users/duke/Documents/hotspot/backend/cache.py#L192) | 2000 | 600s | 单 item 详情 |
| [static_cache](file:///Users/duke/Documents/hotspot/backend/cache.py#L193) | 16 | 86400s | categories、quality rules、health |

**缓存键命名**:`hotspots:list:{cat}:{time}:{cursor}:{limit}:{keyword}` / `hotspots:detail:{id}` / `trends:24h` / `categories:all` 等。

**失效策略**:
- 采集完成 → `invalidate("hotspots:*")` + `invalidate("trends:*")`
- 单 item 写 → `invalidate("hotspots:detail:{id}")`
- 质量配置更新 → `invalidate("quality:*")`
- 启动时 `warmup()` 插入哨兵条目 `{"_warmed": True}`,首次访问视为 miss 触发 DB 查询。

### 5.5 可观测性

#### [observability.py](file:///Users/duke/Documents/hotspot/backend/observability.py)

`log_event(event, **fields)` 统一打点入口,所有事件带 `event=<name>` 字段便于 grep。事件清单:

| 事件 | 触发点 |
|------|--------|
| `cache_hit` / `cache_miss` | TTLCache `__getitem__` |
| `cache_invalidate` | `TTLCache.invalidate(pattern)` |
| `collect_start` / `collect_end` | `BaseCollector.collect()` 入口/出口 |
| `api_request` / `api_response` | `TraceIDMiddleware.dispatch` |
| `startup_complete` | `lifespan` 启动完成 |

#### [TraceIDMiddleware](file:///Users/duke/Documents/hotspot/backend/api/middleware.py#L28)

- 优先从 `X-Trace-Id` 请求头读取,否则生成 UUIDv4
- 注入 `request.state.trace_id`
- 响应头回写 `X-Trace-Id` + `X-Duration-Ms`
- `/api/health` 路径跳过 duration 日志(避免噪音)

### 5.6 API 路由层 ([backend/api/](file:///Users/duke/Documents/hotspot/backend/api))

[register_routers](file:///Users/duke/Documents/hotspot/backend/api/__init__.py#L13) 注册 9 个 APIRouter:

| 路由 | 文件 | 主要方法 | 说明 |
|------|------|---------|------|
| `/api/health` | [health.py](file:///Users/duke/Documents/hotspot/backend/api/health.py) | GET | 增强版健康检查(db/scheduler/cache/collectors/proxy) |
| `/api/stats` | health.py | GET | 内部统计(24h 采集率、缓存命中、一致性校验) |
| `/api/hotspots` | [hotspots.py](file:///Users/duke/Documents/hotspot/backend/api/hotspots.py) | GET | 列表查询(cursor 分页) |
| `/api/hotspots/{id}` | hotspots.py | GET | 单条详情 |
| `/api/categories` | categories.py | GET | 分类列表 |
| `/api/trends` | trends.py | GET | 24h 趋势 |
| `/api/export` | export.py | GET | 导出 Excel / 静态 HTML |
| `/api/proxy` | proxy.py | GET/PUT | 代理配置 |
| `/api/favorites` | favorites.py | GET/POST/DELETE | 收藏 CRUD |
| `/api/favorites/{id}` | favorites.py | DELETE | 取消收藏 |
| `/api/sources` | sources.py | GET/POST/DELETE | 自定义源 CRUD |
| `/api/quality/summary` | quality.py | GET | 质量统计 |
| `/api/quality/rules` | quality.py | GET/PUT | 门禁配置 |
| `/api/quality/logs` | quality.py | GET | 单 item 门禁追溯 |

**性能优化**:Phase 9 起,所有同步 DB 操作通过 `asyncio.to_thread(...)` 放到 thread pool,避免阻塞 event loop。

### 5.7 业务服务层 ([backend/services/](file:///Users/duke/Documents/hotspot/backend/services))

#### [CollectionService](file:///Users/duke/Documents/hotspot/backend/services/collection_service.py#L43) — 采集编排器

```python
class CollectionService:
    collectors: dict[Category, BaseCollector]  # 6 个采集器实例
    repo: HotspotRepository
    trend: TrendRepository
```

核心方法:
- **`run_once()`** → `CollectionReport`:全量采集编排
  1. 注入 `custom_sources`(用户自定义源追加到 collector.sources)
  2. `asyncio.gather` 并发跑 6 个 collector
  3. `asyncio.to_thread(repo.upsert_many, all_items)` 批量入库
  4. `asyncio.to_thread(trend.rebuild, 24)` 重建趋势
  5. 写 `collection_runs` 审计日志
  6. `cache_invalidate("hotspots:*")` + `("trends:*")`
  7. 异步触发 `run_url_content_check()`
  8. `evaluate_source_coverage(report)` 评估源覆盖度
- **`run_one(category)`**:单分类采集(手动触发)
- **`_run_one_safe(category, collector)`**:异常隔离的单 collector 执行
- **`_write_collection_run(result)`**:写审计日志,根据 fallback_count 派生 SUCCESS/PARTIAL/FAILED 状态

#### [HotspotService](file:///Users/duke/Documents/hotspot/backend/services/hotspot_service.py#L71) — 热点查询

- **`list_hotspots(category, time_range, cursor, limit, keyword)`**:列表查询,3 级流程:`list_cache` → `_hrepo.query` → `_dedupe_by_url`(同 URL 多条选 winner)
- **`get_hotspot(id_)`**:详情查询,走 `detail_cache`
- **`count_by_category()`**:走 `static_cache`
- **`_dedupe_by_url(items)`**:Phase 9 修复,同 URL 多条按 `(not_fallback, quality_score, title_len, fetched_at, id)` 5 级优先级保留 winner
- **`encode_cursor(item)` / `decode_cursor(cursor)`**:base64 编码 `{"id", "ts"}`,对外不暴露内部 cursor 格式

#### [TrendService](file:///Users/duke/Documents/hotspot/backend/services/trend_service.py#L19)

- `get_trends(hours=24)`:跨类别求和,返回 `[{label:"-0h", hours_ago:0, total:N}, ...]`
- `get_category_trends(hours=24)`:按分类拆分,返回 `{ai: [...], security: [...], ...}`

#### ExportService ([export_service.py](file:///Users/duke/Documents/hotspot/backend/services/export_service.py))

Excel 导出(openpyxl)+ 静态 HTML 预生成。`rebuild_export_cache()` 由 lifespan 启动时 + scheduler job 每 30min 调用。

### 5.8 数据访问层 ([backend/repository/](file:///Users/duke/Documents/hotspot/backend/repository))

所有 Repository 实例无状态,通过 [get_connection()](file:///Users/duke/Documents/hotspot/backend/repository/db.py#L52) 获取 **thread-local** 连接。

| Repository | 对应表 | 主要方法 |
|-----------|--------|---------|
| [HotspotRepository](file:///Users/duke/Documents/hotspot/backend/repository/hotspot_repo.py#L57) | `hotspots` | `query` / `upsert_many` / `get_by_id` / `search` (FTS5) / `count_by_category` / `cleanup_older_than` |
| TrendRepository | `trend_snapshots` | `rebuild(hours)` / `get_current()` |
| SettingsRepository | `settings` | `get` / `set` / `list_all` / `delete` |
| FavoriteRepository | `favorites` / `favorites_stats` | `add` / `remove` / `list` / `is_favorited` / `count_by_category` |
| QualityLogRepository | `quality_check_logs` | `write_log` / `list_for_item` / `summary_24h` |
| SourceReputationRepository | `source_reputation` | `get` / `get_many` / `upsert` / `rebuild_all` |
| SourceStatsRepository | `source_stats` / `coverage_runs` | `upsert_after_run` / `summary_by_category` / `list_by_status` |
| CustomSourceRepository | `custom_sources` | `add` / `delete` / `list_enabled_by_category` |

#### [HotspotRepository](file:///Users/duke/Documents/hotspot/backend/repository/hotspot_repo.py) 关键实现

- **`upsert_many(items)`**:单事务 `INSERT ... ON CONFLICT(id) DO UPDATE SET ...`,latest-wins 语义,失败 ROLLBACK + 抛 `InternalException`。
- **`query(category, time_range, keyword, cursor, limit)`**:
  - 时间过滤:`published_at >= datetime('now', '-N hours')`
  - 关键词:FTS5 子查询 `JOIN hotspots_fts f2 ON f2.rowid = h2.rowid WHERE hotspots_fts MATCH ?`
  - cursor:`(strftime('%s', published_at) < ? OR (= ? AND id < ?))` 复合分页
  - `LIMIT N+1` 检测 has_more
- **`search(keyword)`**:纯 FTS5 检索,关键词用双引号包裹作为字面短语
- **`_row_to_item(row)`**:SQLite Row → Pydantic HotspotItem 的反序列化(category 字符串 → 枚举,is_fallback 0/1 → bool,quality_flags JSON → list)

### 5.9 采集器层 ([backend/collectors/](file:///Users/duke/Documents/hotspot/backend/collectors))

#### [BaseCollector](file:///Users/duke/Documents/hotspot/backend/collectors/base.py#L267) 抽象基类

| ClassVar | 默认 | 说明 |
|----------|------|------|
| `name` | "" | 自动从类名派生 |
| `category` | `Category.AI` | 子类必须覆盖 |
| `sources` | `[]` | `[{"name","url","score"?,"keywords"?}]` |
| `timeout` | 30 | 单请求超时(秒) |
| `max_items` | 50 | 硬上限 |
| `min_items_threshold` | 3 | 不足触发降级 |

核心方法:
- **`fetch_source(source)`** → `(items, SourceResult)`:抓单源
  - Phase 11: crawl4ai 优先(若 `USE_CRAWL4AI=1` 且已安装),失败 fallback 到 aiohttp
  - aiohttp 路径通过 `ProxySession` 注入代理配置
- **`_parse_html(html, source)`**:默认 HTML 解析
  - Stage 1: `<h1/h2 class="entry-title"><a rel="bookmark">` WordPress 标准模式(优先)
  - Stage 2: 常规 `<a href title>` / `<a href>text</a>` 兜底
  - 噪声过滤:`X comments` / `Permalink to` / 导航链接 / `#comments` 锚点
  - Bug 2 修复:从 meta / JSON-LD / URL slug 提取 `published_at`
- **`_build_items(raw_items, source)`**:dict → HotspotItem
- **`collect()`** → `list[HotspotItem]`:默认编排
  1. 无 sources → 返回 `[]`
  2. `asyncio.gather` 并发抓所有 source
  3. 全部失败 / items 不足 → 返回 `[]`(Phase 13: 禁止合成 fallback)
  4. 截断到 `max_items`
  5. 跑 `_run_quality_gates(items)`(放到 thread pool)
- **`_run_quality_gates(items)`**:Phase 9.2 起 async,每个 item 用 `asyncio.to_thread(pipeline.run_all, item, ctx)` 跑门禁

**Phase 13 硬约束**:`_fallback()` 默认返回 `[]`,**禁止**生成合成 / 占位 / 搜索 URL 让用户自己点开去搜。所有源失败时直接返回 `[]`,UI 显示"该分类暂无可用资讯"。

#### 具体采集器

| Collector | 分类 | 数据源 |
|-----------|------|--------|
| [AICollector](file:///Users/duke/Documents/hotspot/backend/collectors/ai_collector.py) | AI | HackerNews / 量子位 / 36氪AI / 机器之心 |
| SecurityCollector | security | TheHackerNews / BleepingComputer / Krebs / PortSwigger / SANS ISC / 安全客等 |
| FinanceCollector | finance | 新浪财经 / 东方财富等 |
| StartupCollector | startup | Hacker News / Product Hunt |
| BidCollector | bid | 中国政府采购网等 |
| GitHubCollector | github | GitHub Trending + 仓库搜索 API |

[HotspotAggregator](file:///Users/duke/Documents/hotspot/backend/collectors/aggregator.py):已废弃兼容层,逻辑已委托给 `CollectionService`。

### 5.10 质量门禁系统 ([backend/quality/](file:///Users/duke/Documents/hotspot/backend/quality))

#### [BaseGate](file:///Users/duke/Documents/hotspot/backend/quality/base.py#L43) + [GateContext](file:///Users/duke/Documents/hotspot/backend/quality/base.py#L23)

```python
class BaseGate(ABC):
    name: str = "base"
    @abstractmethod
    def check(self, item: HotspotItem, context: GateContext) -> GateResult: ...

class GateContext(BaseModel):
    mode: str = "loose"               # "strict" / "loose"
    category_keywords: dict[str, list[str]]
    source_reputation: dict[str, dict]
    existing_urls: set[str]           # 去重用
    existing_titles: list[str]
    known_ids / http_session_factory  # 可选扩展点
```

**约定**:`check()` 必须捕获所有内部异常,失败 = 扣分 + 打 flag,不应向上抛。

#### [QualityGatePipeline](file:///Users/duke/Documents/hotspot/backend/quality/pipeline.py#L86)

9 个同步门禁的顺序编排器:

```python
DEFAULT_GATES = (
    SchemaGate,                    # Pydantic 二次校验
    ContentQualityGate,            # 长度 + spam + 乱码
    CategoryMatchGate,             # 关键词匹配
    TitleSummaryGate,              # 标题-摘要一致性
    URLValidityGate,               # HTTP HEAD 可达性
    SourceReputationGate,          # 黑名单 + 信誉分
    AuthorVerificationGate,        # Phase 9 发布者核实
    FinalUrlGate,                  # Phase 9.2 下钻 tag/landing 页
    DuplicateGate,                 # URL + Jaccard 标题相似度
)
```

[build_context](file:///Users/duke/Documents/hotspot/backend/quality/pipeline.py#L40) 一次性构建上下文,从 DB 预拉取 `existing_urls` / `existing_titles` / `source_reputation` / `url_title_pairs`,所有门禁共享。

**`run_all(item, context)`** → `PipelineResult`:
- 顺序跑全部门禁,失败累加 `deductions`,合并 `flags`
- 每次结果写 `quality_check_logs`
- `compute_final_score(100, deductions)` 计算最终分
- 严格模式 + 评分 < `min_score` → 抛 `QualityGateFailed`(调用方丢弃 item)

#### 评分机制([scorer.py](file:///Users/duke/Documents/hotspot/backend/quality/scorer.py))

- 基准分 **100 分**,各门禁失败扣分累加,最低 0 分
- `is_acceptable(score, min_score)`:score >= min_score
- 各门禁扣分详见 [ARCHITECTURE.md §6.4](file:///Users/duke/Documents/hotspot/ARCHITECTURE.md)

#### [QualityConfig](file:///Users/duke/Documents/hotspot/backend/quality/config.py#L87)

运行时配置聚合,实例化时从 `settings` 表 + 环境变量拉取,提供 `refresh()` 重新拉取。

`QualityMode.LOOSE`(默认)vs `QualityMode.STRICT`:严格模式下评分 < `min_score` 时拒绝入库。

#### 异步门禁

[URLContentGate](file:///Users/duke/Documents/hotspot/backend/quality/url_content_gate.py):由 [run_url_content_check()](file:///Users/duke/Documents/hotspot/backend/quality/jobs.py) 抽样 10% 跑,更新 `url_check_status` 字段。

#### Phase 9 高级门禁

- **[AuthorVerificationGate](file:///Users/duke/Documents/hotspot/backend/quality/author_verification_gate.py)**:发布者域名核实,解决"KrebsOnSecurity 转载 MSRC 文章"类问题。基于 [PublisherRegistry](file:///Users/duke/Documents/hotspot/backend/quality/publisher_registry.py)。
- **[FinalUrlGate](file:///Users/duke/Documents/hotspot/backend/quality/final_url_gate.py)**:RSS tag/landing 页下钻到真实文章 URL,基于 [FinalUrlResolver](file:///Users/duke/Documents/hotspot/backend/quality/final_url_resolver.py)。

### 5.11 调度层 ([backend/scheduler/](file:///Users/duke/Documents/hotspot/backend/scheduler))

#### [HotspotScheduler](file:///Users/duke/Documents/hotspot/backend/scheduler/scheduler.py#L48)

`AsyncIOScheduler` 封装,5 个 job:

| Job ID | 触发器 | 默认间隔 | 函数 |
|--------|--------|---------|------|
| `collect_all` | IntervalTrigger | 300s | [collect_all_job](file:///Users/duke/Documents/hotspot/backend/scheduler/jobs.py#L34) |
| `trend_rebuild` | IntervalTrigger | 300s | [trend_rebuild_job](file:///Users/duke/Documents/hotspot/backend/scheduler/jobs.py#L50) |
| `url_content_check` | IntervalTrigger | 300s | [url_content_check_job](file:///Users/duke/Documents/hotspot/backend/scheduler/jobs.py#L61) |
| `source_reputation_rebuild` | IntervalTrigger | 21600s (6h) | [source_reputation_rebuild_job](file:///Users/duke/Documents/hotspot/backend/scheduler/jobs.py#L74) |
| `export_rebuild` | IntervalTrigger | 1800s (30min) | [export_rebuild_job](file:///Users/duke/Documents/hotspot/backend/scheduler/jobs.py#L86) |

生命周期:
1. `attach_service(service)`:注入 `CollectionService` + 调用 `jobs.set_service(service)`
2. `start()`:启动 APScheduler,注册 5 个 job,延迟 5s 触发首次 `collect_all_job`
3. `stop(wait=True, timeout=60)`:Phase 8 容错版,所有异常内部吞掉确保 SIGTERM rc=0
4. `reschedule(interval_seconds)`:运行时调整 `collect_all` 间隔(由 SettingsPanel 触发)

`jobs.py` 中的 job 函数都是 thin async wrapper,真实工作委托给 `CollectionService` / `TrendRepository` / `quality.jobs`。

### 5.12 代理模块

- [proxy_config.py](file:///Users/duke/Documents/hotspot/backend/proxy_config.py):配置管理,支持 off / auto / manual 三种模式。auto 模式检测系统代理(Windows 注册表 + 环境变量),manual 模式支持 HTTP/HTTPS/SOCKS。
- [proxy_session.py](file:///Users/duke/Documents/hotspot/backend/proxy_session.py):代理感知的 aiohttp session 上下文管理器,被 `BaseCollector.fetch_source` 使用。

### 5.13 工具模块

- [crawl4ai_client.py](file:///Users/duke/Documents/hotspot/backend/utils/crawl4ai_client.py):可选依赖,Playwright + Chromium 浏览器渲染客户端。`is_available()` 检测是否安装,`fetch_html(url, timeout)` 拿 fully-rendered HTML。适合 JS SPA / anti-bot 站点(GitHub Trending / 36kr / 量子位)。
- [import_cache.py](file:///Users/duke/Documents/hotspot/backend/tools/import_cache.py):历史 `cache_data.json` → SQLite 导入工具。

---

## 6. 前端模块详解

### 6.1 技术栈

- **框架**:React 18 + TypeScript 5
- **构建**:Vite 5
- **样式**:Tailwind CSS 3 + CSS 变量主题(支持 dark/light)
- **图表**:recharts(趋势折线图)
- **图标**:lucide-react(通过 Header 等组件使用)
- **无路由库**:单页应用,无 react-router
- **无状态管理库**:纯 useState + useCallback,无 Redux/Zustand

### 6.2 入口与根组件

#### [main.tsx](file:///Users/duke/Documents/hotspot/frontend/src/main.tsx)

React 18 root 渲染入口,挂载 `<App />` 到 `#root`。

#### [App.tsx](file:///Users/duke/Documents/hotspot/frontend/src/App.tsx)

根组件,负责全局状态编排:

| 状态 | 来源 | 用途 |
|------|------|------|
| `category` / `timeRange` / `keyword` | useState | 当前查询条件 |
| `theme` | localStorage `hotspot-theme` | dark/light 切换 |
| `settingsOpen` / `favoritesOpen` | useState | 面板开关 |
| `favoritesCount` / `favoritedIds` | `/api/favorites` | 收藏状态 |
| `consistencyDrift` | `/api/stats` | 数据一致性漂移告警 |
| `refreshInterval` | `/api/health.collect_interval_seconds` | 自动刷新间隔 |

主要副作用:
- 启动时拉取 favorites count + ids
- 启动时从 `/api/health` 同步默认刷新间隔
- 每 5min 拉取 `/api/stats` 检测一致性漂移
- `refreshInterval` 变化时重置自动刷新 timer
- `theme` 变化时写 localStorage + `document.documentElement.dataset.theme`

#### 收藏交互([App.tsx#L128](file:///Users/duke/Documents/hotspot/frontend/src/App.tsx#L128))

`handleToggleFavorite` 采用**乐观更新**策略:先更新 UI,再发请求,失败回滚。

### 6.3 类型定义 ([types/index.ts](file:///Users/duke/Documents/hotspot/frontend/src/types/index.ts))

与后端 Pydantic 模型严格对齐,snake_case 命名:

| 类型 | 对应后端 |
|------|---------|
| `HotspotItem` | `backend.domain.models.HotspotItem` |
| `HotspotResponse` | `HotspotService.list_hotspots` 返回 |
| `TrendPoint` / `TrendResponse` | `TrendService` 返回 |
| `HealthResponse` | `/api/health` |
| `StatsResponse` / `ConsistencyDrift` / `ConsistencyCheck` | `/api/stats` |
| `FavoriteItem` / `FavoritesListResponse` 等 | `/api/favorites` |
| `QualityRule` / `QualitySummary` | `/api/quality/*` |

**关键常量**:
- `CATEGORIES`:7 个分类(含 `all`),色值与后端 `CATEGORY_CONFIG` 严格一致
- `TIME_OPTIONS`:`24h` / `3d` / `7d`
- `getCategoryColor(cat)` / `getCategoryLabel(cat)`:颜色 / 标签查询
- `formatRelativeTime(iso)`:相对时间格式化("刚刚" / "5分钟前" / "3天前")
- `getQualityColor(score)`:质量分三色映射(≥80 绿 / ≥50 黄 / <50 红)

### 6.4 Hooks

#### [useHotspotData](file:///Users/duke/Documents/hotspot/frontend/src/hooks/useHotspotData.ts)

热点列表数据 Hook,支持 cursor 分页:

```typescript
const { items, total, categoryCounts, loading, error, hasMore, loadMore, refresh } =
  useHotspotData(category, timeRange, keyword);
```

- 首页请求用 `AbortController` 取消前一个未完成请求
- `loadMore()` 追加下一页(按 id 去重)
- `refresh()` 重新加载首页
- 自动刷新由 `App.tsx` 根据 `useRefreshInterval` 统一管理,避免双 timer 冲突

#### [useTrendData](file:///Users/duke/Documents/hotspot/frontend/src/hooks/useTrendData.ts)

24h 趋势数据 Hook,调用 `/api/trends`。

#### [useRefreshInterval](file:///Users/duke/Documents/hotspot/frontend/src/hooks/useRefreshInterval.ts)

刷新间隔管理,启动时从 `/api/health.collect_interval_seconds` 同步默认值,暴露 `setInterval` 供 SettingsPanel 调整。

### 6.5 组件清单

| 组件 | 文件 | 职责 |
|------|------|------|
| [Header](file:///Users/duke/Documents/hotspot/frontend/src/components/Header.tsx) | 顶栏 | Logo / 总数 / 最后更新 / 刷新按钮 / 主题切换 / 设置 / 收藏(徽标) |
| [CategoryNav](file:///Users/duke/Documents/hotspot/frontend/src/components/CategoryNav.tsx) | 分类导航 | Tab 切换 6 大分类 + all,显示每分类计数 + 漂移告警 |
| [SearchBar](file:///Users/duke/Documents/hotspot/frontend/src/components/SearchBar.tsx) | 搜索栏 | 关键词输入 + 时间范围选择 |
| [StatsPanel](file:///Users/duke/Documents/hotspot/frontend/src/components/StatsPanel.tsx) | 统计面板 | 分类数据柱状图 + 总数 |
| [TrendChart](file:///Users/duke/Documents/hotspot/frontend/src/components/TrendChart.tsx) | 趋势图 | recharts 折线图,24h 跨分类趋势 |
| [HotspotGrid](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotGrid.tsx) | 卡片网格 | 自适应网格布局,空态/错误态处理 |
| [HotspotCard](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotCard.tsx) | 热点卡片 | 标题 / 摘要 / 来源 / 评分(三色) / 收藏按钮 / 原文链接 |
| [SettingsPanel](file:///Users/duke/Documents/hotspot/frontend/src/components/SettingsPanel.tsx) | 设置面板 | 代理配置 / 刷新间隔 / 自定义源管理 |
| [FavoritesPanel](file:///Users/duke/Documents/hotspot/frontend/src/components/FavoritesPanel.tsx) | 收藏面板 | 收藏列表 + 分类筛选 + 导出 |
| [LoadingSkeleton](file:///Users/duke/Documents/hotspot/frontend/src/components/LoadingSkeleton.tsx) | 骨架屏 | 加载占位动画 |

### 6.6 Vite 配置 ([vite.config.ts](file:///Users/duke/Documents/hotspot/frontend/vite.config.ts))

- dev server 端口 `8898`
- `/api` 代理到 `http://127.0.0.1:8000`(后端)
- 构建:`tsc && vite build`,输出到 `dist/`

---

## 7. 依赖关系

### 7.1 Python 依赖 ([requirements.txt](file:///Users/duke/Documents/hotspot/backend/requirements.txt))

| 依赖 | 版本 | 用途 |
|------|------|------|
| `fastapi` | >=0.100 | Web 框架 |
| `uvicorn[standard]` | >=0.23 | ASGI 服务器 |
| `aiohttp` | >=3.8 | 异步 HTTP 客户端 |
| `pydantic` | >=2.0 | 数据校验 |
| `pydantic-settings` | >=2.0 | 配置中心 |
| `loguru` | >=0.7 | 结构化日志 |
| `cachetools` | >=5.3 | (声明但实际未用,cache.py 手写 TTLCache) |
| `APScheduler` | >=3.10 | 定时任务 |
| `python-dateutil` | >=2.8 | 日期解析 |
| `openpyxl` | >=3.1 | Excel 导出 |
| `pytest` / `pytest-asyncio` / `pytest-cov` | dev | 测试 |
| `crawl4ai` | >=0.8.9 (可选) | Playwright 浏览器渲染 |

### 7.2 Node 依赖 ([package.json](file:///Users/duke/Documents/hotspot/frontend/package.json))

| 依赖 | 版本 | 用途 |
|------|------|------|
| `react` / `react-dom` | ^18.2.0 | UI 框架 |
| `recharts` | ^3.9.2 | 趋势图渲染 |
| `tailwindcss` | ^3.4.0 | CSS 框架(dev) |
| `typescript` | ^5.3.3 | 类型系统(dev) |
| `vite` | ^5.0.8 | 构建工具(dev) |
| `@vitejs/plugin-react` | ^4.2.1 | React 插件(dev) |

**注意**:README 中提到 `@tanstack/react-query` 和 `lucide-react`,但 `package.json` 实际未声明 `react-query` 依赖。前端数据请求直接用原生 `fetch`。

### 7.3 模块间依赖(关键路径)

```
main.py
  ├── backend.api.register_routers → 9 个 router
  ├── backend.api.middleware.TraceIDMiddleware
  ├── backend.cache (warmup / invalidate)
  ├── backend.exceptions.register_exception_handlers
  ├── backend.logging_config.setup
  ├── backend.observability (set_start_time / log_event)
  ├── backend.repository.db (init_db / close_db)
  ├── backend.scheduler.scheduler.HotspotScheduler
  │     └── backend.scheduler.jobs (set_service / collect_all_job / ...)
  └── backend.services.collection_service.CollectionService
        ├── backend.collectors.{ai,security,finance,startup,bid,github}_collector
        │     └── backend.collectors.base.BaseCollector
        │           ├── backend.utils.crawl4ai_client (可选)
        │           ├── backend.proxy_session.ProxySession (可选)
        │           └── backend.quality.pipeline.QualityGatePipeline
        │                 └── 9 个 *_gate.py
        ├── backend.repository.hotspot_repo.HotspotRepository
        ├── backend.repository.trend_repo.TrendRepository
        ├── backend.repository.custom_source_repo.CustomSourceRepository
        └── backend.quality.source_coverage.evaluate_source_coverage
```

---

## 8. 运行方式

### 8.1 环境要求

- **Node.js** 18+
- **Python** 3.10+(crawl4ai 要求 3.10+)
- **操作系统**:macOS / Linux / Windows(代理自动检测在 Windows 上更完整)

### 8.2 后端启动

**一键启动**(推荐,项目根目录):

```bash
python run.py
```

等价于 `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`。

**开发模式**(热重载):

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

**环境变量**:

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOTSPOT_HOST` | `0.0.0.0` | 监听地址(兼容旧 `HOST`) |
| `HOTSPOT_PORT` | `8000` | 监听端口(兼容旧 `PORT`) |
| `WORKERS` | `1` | uvicorn worker 数(SQLite WAL 下建议 1) |
| `HOTSPOT_DB_PATH` | `backend/hotspot.db` | SQLite 路径 |
| `HOTSPOT_LOG_LEVEL` | `INFO` | 日志级别 |
| `HOTSPOT_PROXY_MODE` | `off` | 代理模式(off/auto/manual) |
| `HOTSPOT_QUALITY_STRICT_MODE` | `false` | 严格模式 |
| `HOTSPOT_COLLECT_INTERVAL_SECONDS` | `300` | 采集间隔 |
| `USE_CRAWL4AI` | `0` | 启用浏览器渲染(需 `pip install crawl4ai`) |

后端运行在 http://127.0.0.1:8000,Swagger 文档 http://127.0.0.1:8000/docs。

### 8.3 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://127.0.0.1:8898,`/api` 请求代理到后端 8000。

**生产构建**:

```bash
cd frontend
npm run build    # 输出到 dist/
npm run preview  # 本地预览构建产物
```

### 8.4 数据库初始化

**全自动**,无需手动操作。`main.py` lifespan 启动时调用 `init_db()`:

1. `PRAGMA integrity_check` 完整性检查
2. `apply_migrations(conn)` 按字典序应用 `migrations/*.sql`
3. 写 `schema_version` 表追踪版本
4. 确认 `journal_mode=WAL`

首次启动自动创建 `backend/hotspot.db` + 11 张表 + 索引 + 触发器 + 默认 settings 种子数据。

### 8.5 测试

```bash
cd backend
pytest -v                    # 全量
pytest -v tests/test_pipeline.py  # 单个测试文件
pytest -v -k "quality"       # 按名筛选
pytest --cov=backend         # 覆盖率
```

测试覆盖(38+ 测试文件):采集器、质量门禁、数据仓库、API 端点、缓存、配置、调度、可观测性、E2E 采集等。

### 8.6 生产部署

**单机本地使用**(主要场景):

```bash
python run.py &
cd frontend && npm run build && npx vite preview --port 8898 &
```

**多 worker**(不推荐,SQLite 写锁竞争):

```bash
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Docker**:项目不提供 Dockerfile(单人本地使用,ARCHITECTURE.md 明确不引入 Docker/K8s)。

### 8.7 备份

SQLite 单文件备份:

```bash
cp backend/hotspot.db backups/hotspot-$(date +%Y%m%d).db
```

如需 vacuum:

```bash
sqlite3 backend/hotspot.db "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"
```

---

## 9. 设计理念与演进

### 9.1 阶段式演进

项目从 Phase 1 逐步迭代到 Phase 13+,关键里程碑:

| Phase | 主题 | 关键产出 |
|-------|------|---------|
| 0 | Spec 对齐 | SPEC.md / CHECKLIST.md / TASKS.md |
| 1 | 基础设施 | loguru / cachetools / APScheduler / pydantic v2 / exceptions |
| 2 | 数据层 | SQLite + WAL + migration / Pydantic models / FTS5 |
| 3 | 采集层重构 | BaseCollector / 5 个 collector / scheduler |
| 3.5 | 质量门禁 | 7 道同步门禁 + 1 道异步 / quality_check_logs |
| 4 | API 层 | 9 个 router / cursor 分页 / TraceIDMiddleware |
| 5 | 可观测性 | log_event / /api/health 增强 / /api/stats |
| 6 | 前端适配 | cursor 分页 / 色值统一 / 一致性校验 |
| 7 | 试运行 | 24h 试运行 / 混沌测试 / RUNBOOK |
| 8 | 容错 | SIGTERM rc=0 / app.state.scheduler / integrity_cache TTL |
| 9 | 招标源质量 | AuthorVerificationGate / FinalUrlGate / source_coverage |
| 10 | 收藏 | favorites 表 + FavoritesPanel |
| 11 | crawl4ai | Playwright 渲染客户端 |
| 13 | 硬约束 | 禁止合成 fallback URL |

### 9.2 核心设计原则

1. **本地优先**(Local-First):所有数据落本地 SQLite,进程崩溃/重启不丢
2. **简单胜过复杂**:单进程、嵌入式存储、零外部服务
3. **写入一次,查询多次**:写入路径重(采集 + 门禁),读取路径极致轻(缓存 + 索引)
4. **优雅退化**:单个数据源失败不阻塞其他源;外部网络故障不阻塞缓存读取
5. **可观测但不重型**:结构化日志 + 简单 metrics,**不引入** Prometheus/Grafana
6. **可扩展不预留**:通过抽象类扩展新源,**不为不确定的分布式需求预留接口**
7. **真实优先**(Phase 13):禁止合成 / 占位 / 搜索 URL 兜底,所有源失败时显示"暂无可用资讯"

### 9.3 显式不引入

| 不引入 | 原因 |
|--------|------|
| Redis / Memcached | 单人本地,进程内 LRU 已够 |
| PostgreSQL / MySQL | 单文件 SQLite 部署成本更低 |
| Celery / Arq / Dramatiq | 进程内 APScheduler 足够 |
| Elasticsearch | SQLite FTS5 满足 100k 级全文检索 |
| Docker / K8s | 个人项目,over-engineering |
| Prometheus / Grafana | 单人无需时序监控 |
| react-query / Redux | 原生 fetch + useState 足够 |

### 9.4 演进路径(按需触发)

| 触发条件 | 演进动作 |
|----------|---------|
| 数据量 > 100k 或 P95 > 500ms | 引入 Redis 替换 LRU |
| 多端同时使用 | 引入 PostgreSQL + 进程间锁 |
| 采集源 > 20 个 | 拆出独立采集 worker(独立进程) |
| 需要全文高亮 | 引入 ES 替代 FTS5 |

---

## 10. 关键扩展点

### 10.1 添加新数据源

工作量约 30 分钟:

1. 在对应分类的 collector 文件中往 `SOURCES` 列表追加 `{"name", "url", "score", "keywords"}`
2. 重启服务(或等待下次 `collect_all_job`)
3. 观察日志确认新源是否产出 items

### 10.2 添加新分类

1. [enums.py](file:///Users/duke/Documents/hotspot/backend/domain/enums.py) 的 `Category` 加枚举值
2. 新建 `backend/collectors/newcat_collector.py`,继承 `BaseCollector`,覆盖 `category` / `sources`
3. [collection_service.py](file:///Users/duke/Documents/hotspot/backend/services/collection_service.py) 的 `collectors` dict 注册新 collector
4. [config.py](file:///Users/duke/Documents/hotspot/backend/quality/config.py) 的 `DEFAULT_CATEGORY_KEYWORDS` 加该分类关键词
5. 新建 migration `007_newcat.sql`,更新 `hotspots.category` CHECK 约束
6. 前端 [types/index.ts](file:///Users/duke/Documents/hotspot/frontend/src/types/index.ts) 的 `CATEGORIES` 加分类 + 色值
7. 重启服务

### 10.3 添加新质量门禁

1. 新建 `backend/quality/my_gate.py`,继承 `BaseGate`,实现 `check(item, context) -> GateResult`
2. [pipeline.py](file:///Users/duke/Documents/hotspot/backend/quality/pipeline.py#L89) 的 `DEFAULT_GATES` 元组追加新门禁类
3. 写测试 `tests/test_my_gate.py`
4. 重启服务

### 10.4 添加新 API

1. 在 `backend/api/` 下新建 router 文件
2. [api/__init__.py](file:///Users/duke/Documents/hotspot/backend/api/__init__.py) 的 `register_routers` 中 `app.include_router(...)`
3. 前端 [types/index.ts](file:///Users/duke/Documents/hotspot/frontend/src/types/index.ts) 加响应类型
4. 在对应组件 / Hook 中调用

---

## 11. 参考文档

- [ARCHITECTURE.md](file:///Users/duke/Documents/hotspot/ARCHITECTURE.md) — 架构优化方案 v3.0(完整 ADR + 风险矩阵 + 实施计划)
- [DESIGN_GUIDE.md](file:///Users/duke/Documents/hotspot/DESIGN_GUIDE.md) — 设计指南(色值 / 排版 / 交互规范)
- [README.md](file:///Users/duke/Documents/hotspot/README.md) — 用户文档
- [docs/SPEC.md](file:///Users/duke/Documents/hotspot/docs/SPEC.md) — 规范
- [docs/RUNBOOK.md](file:///Users/duke/Documents/hotspot/docs/RUNBOOK.md) — 运维手册
- [docs/ACCEPTANCE.md](file:///Users/duke/Documents/hotspot/docs/ACCEPTANCE.md) — 验收标准
- [docs/RCA.md](file:///Users/duke/Documents/hotspot/docs/RCA.md) — 根因分析记录
- [docs/CHAOS_REPORT.md](file:///Users/duke/Documents/hotspot/docs/CHAOS_REPORT.md) — 混沌测试报告
- [docs/PERF_REPORT.md](file:///Users/duke/Documents/hotspot/docs/PERF_REPORT.md) — 性能报告

---

## 附录 A:术语表

| 术语 | 含义 |
|------|------|
| **fallback 数据** | 外部源失败时返回的预置数据,`is_fallback=True`,不参与趋势统计(Phase 13 起禁止合成,直接返回空) |
| **cursor 分页** | 基于 `(published_at, id)` 游标的分页,避免 OFFSET 性能问题。服务层用 base64 编码 `{"id","ts"}` |
| **WAL 模式** | Write-Ahead Logging,SQLite 的并发优化模式,支持并发读 + 单写 |
| **写入直通**(write-through) | 写操作同时更新缓存与存储(本项目采用失效模式:写后 invalidate) |
| **warmup 哨兵** | 启动时插入 `{"_warmed": True}` 标记,首次访问视为 miss 触发 DB 查询,避免冷启动全部走 DB |
| **质量门禁**(Quality Gate) | 对每条 item 跑的校验规则,失败扣分 + 打 flag,严格模式下拒绝入库 |
| **trace_id** | 分布式追踪 ID,通过 `X-Trace-Id` 头透传,写入每条日志便于 grep |
| **source coverage** | Phase 9 引入的源覆盖度评估,识别长期无产出的"死源"(active/stale/dead) |
| **FinalUrlGate** | Phase 9.2 引入的 URL 下钻门禁,把 RSS tag/landing 页解析到真实文章 URL |

## 附录 B:外部参考

- [SQLite WAL 模式](https://www.sqlite.org/wal.html)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [Pydantic v2 文档](https://docs.pydantic.dev/latest/)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [crawl4ai](https://github.com/unclecode/crawl4ai)
