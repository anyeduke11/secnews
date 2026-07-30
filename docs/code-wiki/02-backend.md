# 02 — 后端详解

## 1. 启动流程 (`backend/main.py`)

```
run.py / main.py
  │
  ├─ lifespan: startup
  │   ├─ setup_logging()          # loguru 初始化
  │   ├─ init_db()                # SQLite 连接 + WAL + 迁移
  │   ├─ warmup()                 # 缓存预热
  │   ├─ rebuild_export_cache()   # 导出预生成
  │   ├─ HotspotScheduler.start() # 启动 19 个定时 job
  │   ├─ try_auto_unlock()        # 尝试 OS keychain 恢复 unlock
  │   └─ log_event("startup_complete")
  │
  ├─ 中间件
  │   ├─ CORSMiddleware            # localhost:8898/8000
  │   └─ TraceIDMiddleware         # 请求 trace_id 注入
  │
  ├─ register_exception_handlers() # 统一错误响应格式
  ├─ register_routers()            # 26 个 APIRouter 注册
  │
  └─ lifespan: shutdown
      ├─ scheduler.stop()
      ├─ cache.invalidate("*")
      └─ close_db()
```

### 关键类/函数

| 名称 | 文件 | 职责 |
|------|------|------|
| `app: FastAPI` | `backend/main.py` | FastAPI 应用实例，title="热点地图 API" |
| `lifespan(app)` | `backend/main.py` | async context manager，启停生命周期 |
| `Settings` | `backend/config.py` | Pydantic Settings，环境变量前缀 `HOTSPOT_*` |
| `config` | `backend/config.py` | 全局单例 Settings 实例 |

### 配置项 (`backend/config.py`)

```python
class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Paths
    db_path: Path = BASE_DIR / "hotspot.db"

    # Cache
    cache_ttl_seconds: int = 300       # 列表缓存 TTL
    cache_maxsize: int = 64

    # Collection
    collect_interval_seconds: int = 300  # 采集间隔
    collect_timeout_seconds: int = 60

    # Quality
    quality_strict_mode: bool = False
    quality_min_score: int = 50

    # Knowledge
    local_wiki_enabled: bool = False
    knowledge_watchdog_enabled: bool = True
```

---

## 2. 异常体系 (`backend/exceptions.py`)

统一错误响应格式：`{code, message, trace_id, version}`

```
HotspotException (基类)
├── InvalidParamException     → HTTP 400
├── NotFoundException         → HTTP 404
├── RateLimitedException      → HTTP 429
├── InternalException         → HTTP 500
├── SourceUnavailableException → HTTP 503
└── QualityGateFailed         → HTTP 422 (采集层内部)
```

全局异常处理器：
- `hotspot_exception_handler` — 捕获 `HotspotException` 子类
- `general_exception_handler` — 捕获未处理异常，包装为 INTERNAL

---

## 3. 缓存层 (`backend/cache.py`)

自研 `TTLCache`（线程安全 LRU + TTL），三实例：

| 实例 | 用途 | TTL | maxsize |
|------|------|-----|---------|
| `list_cache` | 列表查询（hotspots/trends/categories） | 5min | 64 |
| `detail_cache` | 单 item 详情 | 10min | 128 |
| `static_cache` | 准静态数据（categories/rules/health） | 24h | 32 |

**Key 命名约定**：
- `hotspots:list:<category>:<time_range>:<cursor>:<limit>`
- `hotspots:detail:<id>`
- `trends:<time_range>`
- `categories:all`

**失效策略**：写操作后调用 `invalidate("hotspots:*")` 模糊匹配删除。

---

## 4. API 路由层 (`backend/api/`)

26 个 Router 模块，通过 `register_routers(app)` 统一注册（lazy import）。

| Router | 文件 | 功能 | 端点示例 |
|--------|------|------|----------|
| **hotspots** | `hotspots.py` | 热点 CRUD + 列表 | `GET /api/hotspots`, `GET /api/hotspots/{id}` |
| **trends** | `trends.py` | 趋势数据 | `GET /api/trends` |
| **categories** | `categories.py` | 分类统计 | `GET /api/categories` |
| **search** | `search.py` | 统一跨层搜索 (v1.7) | `GET /api/search?q=...` |
| **favorites** | `favorites.py` | 收藏管理 | `POST/GET/DELETE /api/favorites` |
| **history** | `history.py` | 浏览历史 | `GET /api/history` |
| **todos** | `todos.py` | 待办事项 | `POST/GET/PUT/DELETE /api/todos` |
| **skills** | `skills.py` | Skill 管理 | `GET/POST /api/skills` |
| **secrets** | `secrets.py` | 密钥管理 (LLM API Keys) | `POST /api/secrets/unlock` |
| **sync** | `sync.py` | 跨端配置同步 (WebDAV) | `POST /api/sync` |
| **export** | `export.py` | 静态 HTML 导出 | `GET /api/export` |
| **health** | `health.py` | 健康检查 | `GET /api/health` |
| **quality** | `quality.py` | 质量配置 | `GET/PUT /api/quality` |
| **proxy** | `proxy.py` | 代理配置 | `GET/PUT /api/proxy` |
| **sources** | `sources.py` | 数据源管理 | `GET /api/sources` |
| **refresh** | `refresh.py` | 手动触发采集 | `POST /api/refresh` |
| **events** | `events.py` | SSE 实时推送 | `GET /api/events/stream` |
| **weekly_report** | `weekly_report.py` | 周报 | `GET /api/weekly-report` |
| **knowledge** | `knowledge.py` | 知识库 | `GET /api/knowledge/items` |
| **content** | `content.py` | 内容创作 | `GET/POST /api/content/calendar` |
| **maintenance** | `maintenance.py` | DB 维护 | `POST /api/maintenance/vacuum` |
| **security** | `security.py` | 安全知识图谱 | `GET /api/security/graph` |
| **codegarden** | `codegarden.py` | CodeGarden Phase 1 | `GET/POST /api/codegarden/projects` |
| **codegarden_phase2b** | `codegarden_phase2b.py` | CodeGarden Phase 2b | 26 端点 (services/resources/events) |
| **tags** | `tags.py` | 标签管理 (v1.7) | `GET/POST/PUT/DELETE /api/tags` |
| **extract** | `extract.py` | 标签自动提取 (v1.7) | `POST /api/extract` |
| **reviews** | `reviews.py` | SM-2 间隔复习 (v1.7) | `GET/POST /api/reviews` |
| **annotations** | `annotations.py` | 笔记空间 (v1.7) | `GET/POST /api/annotations` |
| **tech_stack** | `tech_stack.py` | 技术栈桥接 (v1.7) | `GET /api/tech-stack` |
| **alerts** | `alerts.py` | 告警规则 (v1.7) | `GET/POST /api/alerts` |
| **mode** | `mode.py` | 模式切换 (v1.7) | `GET /api/mode/current` |

---

## 5. 数据层 (`backend/repository/`)

### 5.1 数据库连接 (`db.py`)

```
get_connection()  → 线程本地 sqlite3.Connection
  ├─ PRAGMA journal_mode=WAL       # 并发读 + 单写
  ├─ PRAGMA synchronous=NORMAL     # 性能与安全平衡
  ├─ PRAGMA foreign_keys=ON        # 外键约束
  ├─ PRAGMA busy_timeout=5000      # 5s 等待而非 SQLITE_BUSY
  └─ row_factory = sqlite3.Row     # 字典式行访问

init_db() → integrity_check → apply_migrations() → 返回版本号
apply_migrations() → 扫描 migrations/*.sql → 顺序执行 → schema_version 表记录
```

### 5.2 Repository 模块 (20 个)

| Repository | 文件 | 对应表 |
|------------|------|--------|
| `HotspotRepository` | `hotspot_repo.py` | hotspots |
| `TrendRepository` | `trend_repo.py` | trend_snapshots |
| `FavoriteRepository` | `favorite_repo.py` | favorites |
| `TodoRepository` | `todo_repo.py` | todos |
| `KnowledgeRepository` | `knowledge_repo.py` | knowledge_items, knowledge_concepts |
| `SecurityRepository` | `security_repo.py` | security_entities, security_edges |
| `QualityLogRepository` | `quality_repo.py` | quality_logs |
| `SourceStatsRepository` | `source_stats_repo.py` | source_stats |
| `SyncConfigRepository` | `sync_configs_repo.py` | sync_configs |
| `SyncStateRepository` | `sync_states_repo.py` | sync_states |
| `SyncHistoryRepository` | `sync_history_repo.py` | sync_history |
| `SecretsRepository` | `secrets_repo.py` | secrets |
| `SettingsRepository` | `settings_repo.py` | settings |
| `EncryptionKeysRepository` | `encryption_keys_repo.py` | encryption_keys |
| `SkillsRepository` | `skills_repo.py` | skills |
| `UserRepository` | `user_repo.py` | users |
| `WeeklyReportRepository` | `weekly_report_repo.py` | weekly_reports |
| `CustomSourceRepository` | `custom_source_repo.py` | custom_sources |
| `CodeGardenRepository` | `codegarden_repo.py` | cg_projects |
| `CodeGardenServiceRepository` | `codegarden_service_repo.py` | cg_services |
| `CodeGardenResourceRepository` | `codegarden_resource_repo.py` | cg_resources |
| `CodeGardenOrchestrationRepository` | `codegarden_orchestration_repo.py` | cg_dependencies, cg_events |
| `TagsRepository` | `tags_repo.py` | tags (v1.7) |
| `ReadingStatesRepository` | `reading_states_repo.py` | reading_states (v1.7) |
| `ReviewsRepository` | `reviews_repo.py` | reviews (v1.7) |
| `AnnotationsRepository` | `annotations_repo.py` | annotations (v1.7) |
| `TechStackRepository` | `tech_stack_repo.py` | tech_stack (v1.7) |
| `AlertsRepository` | `alerts_repo.py` | alerts (v1.7) |

### 5.3 数据库迁移 (35 个 SQL 文件)

`backend/repository/migrations/` 下按序号命名：
- `001_init.sql` — 初始 schema
- `002-018` — 增量迁移 (trends, favorites, quality, todos, knowledge, sync, security...)
- `019_codegarden.sql` — CodeGarden Phase 1
- `021_codegarden_phase2b.sql` — CodeGarden Phase 2b
- `024-035` — v1.7 标签系统 (tags, reading_states, reviews, annotations, tech_stack, alerts...)

迁移通过 `schema_version` 表追踪，幂等执行（`IF NOT EXISTS`）。

---

## 6. 采集器 (`backend/collectors/`)

### 6.1 基类 `BaseCollector` (`base.py`)

```python
class BaseCollector(ABC):
    category: ClassVar[Category]       # 子类必须定义
    name: str                          # 自动从类名派生
    sources: list[dict]                # 数据源配置列表
    timeout: int = 30                  # 单个源超时
    max_items: int = 50                # 单源最大条目

    async def collect() -> CollectionResult  # 主入口
    async def fetch_source(source) -> str     # 抓取 HTML / API
    def _parse_html(html, source) -> list     # 解析 HTML → HotspotItem
    def _fallback() -> list[HotspotItem]       # 备用硬编码数据
```

**设计约定**：
- 所有 datetime 字段 tz-aware UTC
- 异常隔离：单源失败写入 `SourceResult.error_msg`，不向上抛
- 代理支持：通过 `ProxySession` (127.0.0.1:7897) 绕过反爬

### 6.2 采集器清单 (8 个)

| 采集器 | 分类 | 数据源 | 特点 |
|--------|------|--------|------|
| `SecurityCollector` | security | 安全客/Krebs/PortSwigger/SANS/FreeBuf/奇安信/AVD/CNNVD/CNVD | 双源聚合 (安全客 wechat + rss) |
| `AICollector` | ai | aihot/Hacker News/机器之心/量子位 | AI 资讯聚合 |
| `AISecurityCollector` | ai_security | AI 安全专项 | OWASP LLM Top 10/对抗 ML/prompt injection |
| `FinanceCollector` | finance | 新浪财经/东方财富/金十数据 | HTTP API + HTML 解析 |
| `StartupCollector` | startup | 36氪/虎嗅/创业邦 | 创业资讯 |
| `BidCollector` | bid | 中国政府采购网 | 四线 AND/OR 搜索体系，ProxySession 反爬 |
| `GithubCollector` | github | GitHub Trending | API 调用 |
| `TechCollector` | tech | Solidot/IT之家/稀土掘金/酷安 | IT/科技资讯 |

### 6.3 支撑模块

| 模块 | 文件 | 职责 |
|------|------|------|
| `parsing.py` | `collectors/parsing.py` | HTML 解析工具 (`_extract_published_at`, `_is_noise_title`, `_resolve_url`) |
| `keywords.py` | `collectors/keywords.py` | 分类关键词匹配 (`_CAT_KEYWORDS`, `_is_title_relevant_to_category`) |
| `aggregator.py` | `collectors/aggregator.py` | 多源聚合去重 |
| `bid_search.py` | `collectors/bid_search.py` | 标讯搜索 (四线 AND/OR) |
| `bid_status.py` | `collectors/bid_status.py` | 标讯状态提取 (招标中/中标/变更/终止) |
| `sogou_search.py` | `collectors/sogou_search.py` | 搜狗微信搜索 |

---

## 7. 解析器 (`backend/parsers/`)

独立于采集器的解析器，用于特定格式源：

| 解析器 | 文件 | 用途 |
|--------|------|------|
| `BaseSourceParser` | `base_parser.py` | 解析器抽象基类 |
| `AihotParser` | `aihot_parser.py` | AI HOT API JSON 解析 |
| `Jin10Parser` | `jin10_parser.py` | 金十数据 API 解析 |
| `ClsdParser` | `clsd_parser.py` | 财联社 API 解析 |

---

## 8. 质量管线 (`backend/quality/`)

### 8.1 架构

```
QualityGatePipeline.run(items, config)
  │
  ├─ SchemaGate           # 字段完整性校验
  ├─ URLValidityGate      # URL 格式合法性
  ├─ DuplicateGate        # URL + 标题去重
  ├─ RecencyGate          # 时效性过滤 (Phase 47)
  ├─ TitleSummaryGate     # 标题/摘要质量
  ├─ ContentQualityGate   # 内容质量评分
  ├─ CategoryMatchGate    # 分类匹配度
  ├─ NoiseContentGate     # 噪声内容过滤
  ├─ AuthorVerificationGate # 作者验证
  ├─ SourceReputationGate # 来源信誉评分
  ├─ BidRecencyGate       # 标讯时效性 (仅 bid)
  └─ FinalUrlGate         # 最终 URL 有效性
  │
  └─ compute_final_score() → PipelineResult
```

### 8.2 模式

- **loose** (默认)：失败打 flag + 扣分，仍入库
- **strict**：`final_score < min_score` 时 `accepted=False`，拒绝入库

### 8.3 关键类

| 类 | 文件 | 职责 |
|----|------|------|
| `BaseGate` | `base.py` | 门禁抽象基类 |
| `GateContext` | `base.py` | 门禁上下文 (URLs, titles, reputation) |
| `QualityGatePipeline` | `pipeline.py` | 顺序执行 13 个门禁，累加扣分 |
| `QualityConfig` | `config.py` | 质量配置 (mode, min_score, 采样率) |

---

## 9. 调度器 (`backend/scheduler/`)

### 9.1 `HotspotScheduler` (`scheduler.py`)

封装 APScheduler `AsyncIOScheduler`，管理 19 个定时 job：

| # | Job ID | 触发 | 功能 |
|---|--------|------|------|
| 1 | `collect_all` | Interval 300s | 全量采集 |
| 2 | `trend_rebuild` | Interval 300s | 趋势重算 |
| 3 | `url_content_check` | Interval 300s | URL 内容异步验证 |
| 4 | `source_reputation_rebuild` | Interval 6h | 来源信誉重算 |
| 5 | `export_rebuild` | Interval 30min | 导出缓存预生成 |
| 6 | `sync` | Cron 周一 10:30 | 跨端配置同步 |
| 7 | `daily_snapshot` | Cron 00:30 UTC | 日级趋势快照 |
| 8 | `weekly_report` | Cron 周一 02:00 UTC | 周报自动生成 |
| 9 | `compile_daily` | Cron 每日 02:00 | 知识编译 |
| 10 | `compile_weekly` | Cron 周日 03:00 | 知识编译 |
| 11 | `soul_weekly` | Cron 周日 04:00 | SOUL 更新 |
| 12 | `stats_daily` | Cron 每日 06:00 | 数据回收 |
| 13 | `migrate_weekly` | Cron 周日 05:00 | 掌握度迁移 |
| 14 | `summary_weekly` | Cron 周日 06:00 | 周回顾 |
| 15 | `cg_upstream_sync` | Cron 每日 09:00 | CodeGarden 上游同步 |
| 16 | `cg_service_scan` | Interval 300s | 服务自动发现 |
| 17 | `cg_event_process` | Interval 60s | 事件总线处理 |
| 18 | `mitre_sync` | Cron 周日 04:00 | MITRE ATT&CK 同步 |
| 19 | `security_enrichment` | Interval 300s | 安全实体增强 |

**时区**：`Asia/Shanghai` 用于所有 Cron 触发（sync/compile/soul/stats/migrate/summary/mitre）。

### 9.2 生命周期

```
attach_service(CollectionService)
  → start()
    → 注册 19 个 job
    → 5s 后异步执行首次 collect_all + sync catch-up
  → stop(wait=True)
    → scheduler.shutdown()
    → reset_service()
```

---

## 10. 服务层 (`backend/services/`)

41 个业务逻辑模块，核心如下：

| 服务 | 文件 | 职责 |
|------|------|------|
| **CollectionService** | `collection_service.py` | 编排全量采集流程 |
| **SyncService** | `sync_service.py` | 跨端同步编排 (push/pull/bidirectional) |
| **SyncMerge** | `sync_merge.py` | 三路合并引擎 (base/local/remote) |
| **SyncBundle** | `sync_bundle.py` | 同步包构建/加密/解密 |
| **AutoClassifier** | `auto_classifier.py` | 标签→分类自动映射 |
| **ConceptLinker** | `concept_linker.py` | 标签→概念自动关联 |
| **SoulService** | `soul_service.py` | SOUL.md 角色画像生成 |
| **ExportService** | `export_service.py` | 静态 HTML 导出 |
| **SecretsService** | `secrets_service.py` | 密钥加密/解密 (Fernet) |
| **MaintenanceService** | `maintenance_service.py` | DB vacuum/cleanup |
| **CodeGardenProjectService** | `codegarden_project_service.py` | 项目 CRUD + 生命周期 |
| **CodeGardenScanner** | `codegarden_scanner.py` | 本地项目扫描 |
| **CodeGardenServiceService** | `codegarden_service_service.py` | 服务网格 |
| **CodeGardenResourceService** | `codegarden_resource_service.py` | 资源中枢 |
| **CodeGardenOrchestrationService** | `codegarden_orchestration_service.py` | 联动引擎 |
| **CodeGardenGitHubService** | `codegarden_github_service.py` | GitHub 导入 |
| **CodeGardenKnowledgeBridge** | `codegarden_knowledge_bridge.py` | Knowledge ↔ CodeGarden 桥接 |
| **ReviewService** | `review_service.py` | SM-2 间隔复习 (v1.7) |
| **AnnotationService** | `annotation_service.py` | 笔记空间 (v1.7) |
| **TechStackService** | `tech_stack_service.py` | 技术栈桥接 (v1.7) |
| **AlertService** | `alert_service.py` | 告警规则引擎 (v1.7) |
| **SearchService** | `search_service.py` | 统一跨层搜索 (v1.7) |
| **DigestService** | `digest_service.py` | 每日摘要 (v1.7) |
| **ExtractService** | `extract_service.py` | 标签自动提取 (v1.7) |
| **SecurityGraphService** | `security_graph_service.py` | 安全图谱编排 |
| **TerminologyService** | `terminology_service.py` | 安全术语标准化 |
| **KnowledgeWatcher** | `knowledge_watcher.py` | .md 文件变更检测 (watchdog) |

---

## 11. 域模型 (`backend/domain/`)

### 11.1 枚举 (`enums.py`)

| 枚举 | 值 | 说明 |
|------|-----|------|
| `Category` | ai, ai_security, security, finance, startup, bid, github, tech | 8 大分类 |
| `TimeRange` | 24h, 3d, 7d, 30d | 时间窗口 (Shanghai TZ) |
| `CollectorStatus` | success, partial, failed | 采集状态 |

### 11.2 核心模型 (`models.py`)

**`HotspotItem`** — 热点条目 (14 字段)：
```
id, title, summary, source, url, category,
published_at, fetched_at, ingested_at,
bid_status, region, score, is_fallback,
quality_score, quality_flags
```

**`CollectionResult`** — 采集结果：
```
category, status, items, errors, duration_ms, sources_attempted, sources_succeeded
```

**`PipelineResult`** — 质量管线结果：
```
accepted, final_score, flags, gate_results
```

---

## 12. 同步系统

三文件拆分（可测试性）：

| 模块 | 文件 | 行数 | 职责 |
|------|------|------|------|
| `sync_service.py` | 编排 | 371 | push/pull/bidirectional 流程 |
| `sync_merge.py` | 合并 | 246 | 三路合并引擎 (base/local/remote) |
| `sync_bundle.py` | 序列化 | 400 | 构建/加密/解密 zip 包 |

**传输**：WebDAV (坚果云)，zip 容器格式：
```
config-YYYY-MM-DD.zip
├── envelope.json    # Fernet 密文
└── manifest.json    # 明文元数据
```

**加密**：Fernet via master_key 派生 key，PBKDF2 密钥派生。