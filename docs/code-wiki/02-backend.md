# 02 — 后端详解

> 基准: **v0.7.0** (2026-08-28)。数字快照: 63 router / 93 service / 47 job / 14 collector,
> 由 `scripts/generate_meta.py` 反推维护, 见 `docs/ARCHITECTURE.md` (CI `--check` 验收 47/14/63/93)。

## 1. 启动与生命周期

### 1.1 入口 (`run.py`)

```bash
python run.py            # 等价: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

环境变量: `HOTSPOT_HOST` (默认 127.0.0.1, 无认证, 局域网访问需显式 0.0.0.0) /
`HOTSPOT_PORT` (默认 8000) / `WORKERS` (默认 1, SQLite WAL 下多 worker 有锁竞争);
旧变量 `HOST`/`PORT` 兼容但优先级低。

### 1.2 lifespan (`backend/main.py`)

```
startup:
  setup_logging()              # loguru
  init_db()                    # SQLite + WAL + apply_migrations()
  warmup()                     # 缓存预热
  rebuild_export_cache()       # 导出预生成 (失败只告警)
  [MCP] is_mcp_enabled() →     # feature gate (默认关)
        mcp_tool_registry_seed()  (PRIMARY KEY name, 重启幂等)
        build_mcp_server(app) + mount_sse_endpoint(app, mcp)  # /mcp/sse
  svc = CollectionService(); set_service(svc)
  sched = HotspotScheduler(interval=300); attach_service(svc); start()
  app.state.scheduler = sched  # /api/health 跨请求读取
  try_auto_unlock()            # OS keychain 恢复 secrets 解锁态
  start_watcher()              # knowledge watchdog (config.knowledge_watchdog_enabled, 幂等)
  startup auto-catchup         # background task, 追抓本周一 00:00 Shanghai → 现在
  log_event("startup_complete")
shutdown (yield 之后, 逆序):
  scheduler stop → state 清理 → cache invalidate → close_db
```

- **CORS 白名单**: 8000 / 8898 / 8899 (8899 为 `.ui-preview/` demo 静态服务器端口)
- **中间件**: `TraceIDMiddleware` (`backend/api/middleware.py`)
- **异常体系**: `register_exception_handlers` (`backend/exceptions.py`), 统一错误体
  `{"detail": {"message": "...", "missing": "github_token"}}`, 前端按此解析

### 1.3 配置 (`backend/config.py` + `backend/config/` 包)

Pydantic Settings, 环境变量前缀 `HOTSPOT_`。关键字段:

| 字段 | 默认 | 用途 |
|------|------|------|
| `host` / `port` | 127.0.0.1 / 8000 | 服务绑定 |
| `collect_interval_seconds` | 300 | collect_all 间隔 (可运行时 reschedule) |
| `quality_reputation_interval_seconds` | 21600 | 来源信誉重算间隔 |
| `knowledge_watchdog_enabled` | True | 文件↔DB 自动同步开关 |
| `catchup_on_startup` | True | 启动自动追抓 (测试环境必须关) |
| `feature_workbench_ui` | **True** | `/workbench` 5 视图路由守卫 (v0.7 首页) |
| `feature_*` | 见 01 §4 | 细粒度功能 flag (tag/extract/review/annotation/tech_stack/alert/unified_search/recommendation/digest/mcp_server) |

LLM provider 配置: `backend/config/llm_schema.py` (Pydantic 模型) + 仓库根 `config/llm.yaml`
(v0.5.1 起单一来源, AIService 的 sensenova 硬编码已并入)。

## 2. API 路由层 (`backend/api/`)

### 2.1 注册机制 (v0.6.2 拆分后)

```
api/__init__.py   18 行薄壳 — register_routers(app) 委托 _registry.register_all
api/_registry.py  实际注册表 — 分组 + app.include_router 调用 (无 150 行限制)
api/_flags.py     feature_flag 批量检查 — 收敛 register_routers 内的 if config.feature_xxx 块
```

- 全部 **lazy import** (函数体内 import, 避免循环依赖; `annotations` 等模块用
  `import x as y` 显式绕开 `from __future__ import annotations` 的名字遮蔽)
- 每个 router 文件 **≤ 150 行**; 头部必写路由清单注释
- 三类注册路径:

| 类别 | 判定 | 示例 |
|------|------|------|
| **core 白名单** (`core/routers.py`) | 永远注册 | hotspots / trends / categories / health / export / proxy / quality / sources / favorites / history / refresh / todos / skills / secrets / security / settings / knowledge / knowledge_chunks / content / maintenance / cache / events / attention_events / reports / weekly_report / catchup / knowledge_imported / kl_* / wiki_tools / llm_status / bid_alert / mode / alert_api_v2 / deep_read / cve_analytics / compliance … |
| **extension gates** (`is_extension_enabled`) | 条件注册 | sync · codegarden + codegarden_ops + codegarden_phase14 · crm×3 · mcp×3 + phase5_tools (kl_*/dsh_*) · secnews (kl_pipeline_api + secnews_dashboard_api) · dsh_api |
| **config.feature_* flag** | 条件注册 | tags · extract · reviews · annotations · tech_stack · alerts · search · recommend · digests |

- **依赖方向硬约束**: router 可 import `backend.services.*` / `backend.core.*`,
  **严禁** `import backend.collectors.*` / `import backend.repository.*` (DB 必须经 service)

### 2.2 主要 router 一览 (按域)

| 域 | router | 代表端点 |
|----|--------|----------|
| 资讯 | `hotspots.py` `categories.py` `history.py` `refresh.py` `export.py` | `GET /api/hotspots` · `POST /api/refresh` (手动触发采集) |
| 采集运维 | `sources.py` `quality.py` `cache.py` `catchup.py` | 源列表 / 质量日志 / 缓存管理 / 追抓 |
| 知识 | `knowledge.py` `knowledge_chunks_api.py` `knowledge_imported.py` `attention_events_api.py` | 知识条目 / chunks FTS5 / 收藏聚合 / 注意力事件 |
| 深读/分析 (v0.6 S4) | `deep_read.py` (S4-2 四节 LLM 深度分析) · `cve_analytics.py` (S4-3 CVE 热力图 + ATT&CK 映射) · `compliance.py` (S4-4 合规矩阵: 等保 2.0 + GDPR + ISO 27001) | `/api/deep-read/*` · `/api/cve/*` · `/api/compliance/*` |
| KL | `kl_metrics_api.py` `kl_rollback_api.py` `kl_compounding_api.py` `kl_planning_api.py` `kl_pipeline_api.py` | 触发器指标 / 回滚 / 复利仪表盘 / 规划动作 / 管线 |
| 行动层 | `todos.py` `skills.py` `secrets.py` `reviews.py` `tags.py` `annotations.py` `bid_alert.py` `digests.py` `content.py` | 待办 / 技能 / 密钥 / SM-2 复习 / 标签 / 笔记 / 标讯提醒 / 简报 / 内容日历 |
| 判断层 | `trends.py` `search.py` `recommend.py` `mode.py` | 趋势 / 统一搜索 / 上下文推荐 / 模式切换 |
| 报告 | `reports.py` `weekly_report.py` | 日报/月报 / 周报 |
| 实时 | `events.py` | `GET /api/events` (SSE 推送) |
| 安全 | `security.py` | Security Graph + Terminology |
| CodeGarden | `codegarden.py` `codegarden_ops.py` `codegarden_phase14.py` | `/api/codegarden/*` 项目 / M2-M4 运维 / 漂移+CVE |
| 同步 | `sync.py` | push / pull / 状态 |
| MCP | `mcp.py` `mcp_adapters.py` `mcp_agent_tools.py` `mcp_phase5_tools.py` `wiki_tools.py` | 调试 / 适配 / agent tools / kl+dsh tools / wiki 工具族 |
| 系统 | `health.py` `maintenance.py` `settings.py` `proxy.py` `llm_status.py` | 健康 / DB 维护 / 运行时设置 (含 `/api/settings/features`) / 代理 / LLM 状态 |

`/api/settings/features` (settings.py): 把 feature_gates 派生的扩展状态 + config.feature_*
(含 `workbench_ui`) 下发给前端 `useFeatureFlags`, 是前后端可见性同源点。

## 3. 服务层 (`backend/services/`, 93 模块)

### 3.1 分组总表

| 组 | 模块 |
|----|------|
| **采集编排** | `collection_service` (核心) · `batch_service` · `catchup_service` · `collect_validator` · `collection_logger` · `crawler_seed` · `retry_policy` |
| **源健康** | `source_health_service` · `source_health_machine` (状态机) · `source_prober` · `source_revival_service` · `source_alerter` · `source_scheduler_service` (源级调度) · `proxy_pool` |
| **质量** | `quality_gate_map` · `simhash` |
| **知识** | `knowledge_sync` · `knowledge_watcher` · `compiler` · `concept_linker` · `auto_classifier` · `chunk_service` · `learning_service` · `review_service` (SM-2) · `mastery_projection` · `retention_engine` (艾宾浩斯) · `wiki_archiver` · `map_updater` · `obsidian_service` |
| **KL 管线** | `kl_state_machine` · `planning_service` · `triggers/` (t1_raw_to_refine … t5_publish_to_refine) |
| **报告/摘要** | `daily_report_overview_service` · `weekly_report_service` · `weekly_report_overview_service` · `monthly_report_service` · `digest_service` · `summary_service` · `summary_enricher` · `stats_recycle_service` |
| **CodeGarden** | `codegarden_project_service` · `codegarden_service_service` · `codegarden_resource_service` · `codegarden_orchestration_service` · `codegarden_scanner_service` · `codegarden_github_service` · `codegarden_knowledge_bridge` · `codegarden_drift` · `tech_stack_service` |
| **Security** | `security_graph_service` · `terminology_service` · `graph_builder` · `federation_service` · `cve_knowledge_sync` |
| **AI/LLM** | **`ai_hub/` 子包** (见 §3.3) · `llm/model_router` · `cost_monitor` |
| **同步** | `sync_service` · `sync_merge` · `sync_bundle` · `sync_zip` · `sync_fernet_mixin` · `sync_config_service` · `sync_service_constants` · `webdav_client` · `bookmark_sync` |
| **用户数据** | `hotspot_service` · `search_service` · `recommend_service` · `alert_engine` · `alert_service` · `annotation_service` · `extract_service` · `content_service` · `attention_scorer` |
| **画像** | `profile_service` · `soul_service` · `progress_service` |
| **运维** | `maintenance_service` · `backup_service` · `data_cleaning` · `feature_flag_service` · `secrets_service` · `history_import` · `imported_aggregator` · `export_service` · `trend_service` · `url_batch_check_service` |
| **外部桥接** | `cubox_sync` (Cubox 收藏) · `sag_service` · `dsh/` (bridge + session + task_router, 实验性) |

### 3.2 关键服务详解

**`collection_service.py` — 采集总编排**

- `CollectionService.collectors: dict[Category, list[BaseCollector]]` — 每分类多 collector
  (见 §5.2 注册表); `repo = HotspotRepository()`, `trend = TrendRepository()`
- `run_once()`: `asyncio.gather` 并发跑全部分类 → 单源失败隔离 (`_run_one_safe`) →
  批量 upsert → 趋势重建 → `collection_runs` 审计 (SUCCESS/PARTIAL/FAILED)
- 类级共享状态 `_latest_run` (count/at), 跨请求可读
- simhash 存 SQLite 前做 unsigned→signed 64-bit 转换 (`_to_signed_64`/`_from_signed_64`)

**`sync_*.py` — 跨端同步四件套**

| 模块 | 行数级 | 职责 |
|------|--------|------|
| `sync_service.py` | ~900 | push/pull/双向编排; 委托 build_bundle / apply_bundle / 3-way merge |
| `sync_merge.py` | ~440 | `three_way_merge()`: base/local/remote, 记录按 key 对齐, 字段级 last-write-wins, 冲突计数; 覆盖 favorites/todos/skills/custom_sources/secrets/reading_states/annotations 等表 |
| `sync_bundle.py` | ~850 | bundle 生命周期: 读本地配置 / 写回各表 / Fernet 加解密 / apply |
| `sync_zip.py` | — | zip 容器: `build_sync_zip()` / `extract_sync_zip()`; envelope.json (密文) + manifest.json (明文) |

### 3.3 `ai_hub/` 子包 — LLM 单出口 (v0.7-C 拆分后)

v0.5.0 合并 llm_service + ai_service 为单出口; v0.6.2-v0.7 持续拆分,
原 412 行模块现为子包:

| 模块 | 职责 |
|------|------|
| `service.py` (~126 行) | `AIService` 对外门面 — 业务侧唯一调用入口 |
| `gateway.py` (~406 行, **超 400 行软限, 待拆 gateway/ + tasks_adapter.py**) | provider 网关: 多 provider + fallback_order 依次调用 + 失败回退默认分; sensenova 限频在此 |
| `tasks.py` (~130 行) | 任务型调用 (批量评分 / 深读分析等) |
| `write_back.py` | tasks 的写回门面 (ai_scores 写路径唯一) |
| `cache.py` | LLM 响应缓存 (配 `llm_cache` 表) |
| `usage.py` | token / cost 用量统计 (配 cost_monitor) |
| `prompts.py` | prompt 模板集中 (**工作区未提交新文件, v0.7-C 进行中**) |

配置单一来源 `config/llm.yaml`; AIQualityGate 的 LLM 检测 (sensenova / ollama)
走此出口, `quality.llm_enabled` 默认关。

**其它高频服务**

- `attention_scorer.py`: 5 维加权 (view_count / dwell_time / scroll_depth / is_favorited /
  annotation_count) → 0-100 attention_score
- `auto_classifier.py`: tag → domain 自动分类 (`batch_classify`)
- `compiler.py` / `concept_linker.py` / `soul_service.py`: 知识编译 → 概念关联 → 画像生成
- `secrets_service.py`: Fernet 加密存储 + `try_auto_unlock()` (OS keychain)
- `webdav_client.py`: 坚果云 WebDAV 传输层
- `dsh/bridge.py`: `DSHClient` — HTTP 连接 deepseek-harness 运行时
  (`health_check` / `send_task` / `get_session`); gate `dsh` 默认关,
  **不可达时自动降级 llm_service 直连** (P1-2 实验性定位)

## 4. 数据层 (`backend/repository/`)

### 4.1 `db.py` 访问模式

- `threading.local()` **线程本地连接**, 每线程一个连接, 复用不断开
- `isolation_level=None` **autocommit**; 显式事务仅用于迁移
- PRAGMA: WAL / foreign_keys / busy_timeout
- `init_db()`: 建连接 + `apply_migrations()`
- `apply_migrations()`: 扫描 `migrations/*.sql`, 按文件名版本排序, `executescript()`,
  跳过 `*_down.sql`, 写 `schema_version` 记录; 对历史 DB 的 duplicate column 容错
- **无 async DB** — 全部同步调用; 仅 HTTP 采集是 async
- 约定: **每表一个 repo 模块 + 模块级 singleton** (如 `hotspot_repo.py` → `HotspotRepository`)

### 4.2 核心数据表 (按 migration 域归纳)

| 域 | 表 (代表 migration) |
|----|---------------------|
| 资讯主体 | `hotspots` (001) + `ingested_at` (007) + `hotspot_region` (023) + fingerprints/scores (043) |
| 质量 | quality 日志 (002) + 归档 (062) |
| 源 | `custom_sources` (004) · `source_stats` (005) · discovery_source (060) · proxy_health (053) |
| 采集运维 | `bid_status` (008) · `history_batches` (010) · catchup_runs/checkpoints (040/042) · collect_running_status (041) · crawler_v2 (055-057) |
| 行动 | `todos` (011) · `skills` (012) · `secrets` (013) · tags (024) · reading_states (025) · sm2_reviews (026) · annotations (027) · planning_actions (049) |
| 知识 | `knowledge` (018/020) · unified_fts (033) · compiled (035) · lifecycle (036/046, `kl:*` 5 阶段) · chunks (054 + CJK FTS 061) · knowledge_indexes (063) · wiki_events (065) · digest_summary_md (072) · wiki_items_fts (073, 写后即时同步) |
| CodeGarden | (019) 项目/记忆/Prompt/SDD + (021) cg_services/cg_resources/cg_dependencies/cg_events + drift_assessments (050) |
| 安全图谱 | security_graph (022) + tech_stack (029) |
| 告警 | alert_rules (028/048) |
| 同步 | sync 配置/状态 (014/016) |
| KL | kl_queue (070) · kl_dead_letters (044) · trigger created_by (045) |
| 其它 | weekly_report (017) · personal_profile (030) · digests (031) · mcp_tool_registry (037) · llm_cache (052) · crm_cockpit (071) |

> 迁移清单以 `backend/repository/migrations/` 目录为准 (69 个正向迁移, 001–073)。
> 知识表索引约定: `idx_ki_ingested` (列表排序) + `idx_ki_lifecycle` (T1-T4 触发) + `idx_ki_domain` (domain_coverage)。

## 5. 采集层 (`backend/collectors/` + `backend/parsers/`)

### 5.1 `BaseCollector` 接口 (`base.py`)

| 成员 | 说明 |
|------|------|
| `category` | 目标分类 (Category 枚举) |
| `sources` | 数据源配置列表 |
| `timeout` / `max_items` / `min_items_threshold` | 请求与产出控制 |
| `_parse_html()` | HTML 解析入口: 标题/URL 噪声过滤、去重、发布时间解析、fallback 逻辑 |
| `_fallback()` | 旧 6 分类采集器必须实现 (禁止合成假数据); **Phase 13 起新 collector 不再实现**, 反爬时返回空 + warning |

辅助模块: `session.py` (`BackendSession`, httpx 重试) · `id_factory.py` (`make_readable_id`,
格式 `{source}:{subtype}:{native_id}` 如 `hn:item:12345678`) · `parsing.py` / `keywords.py`
(从 base 拆出) · `item_builder.py` (透传 `raw.get("id")`)。

### 5.2 分类 × 采集器注册表 (`CollectionService.__init__`)

| Category | Collectors |
|----------|-----------|
| AI | `AICollector` |
| AI_SECURITY | `AISecurityCollector` (OWASP/对抗 ML/prompt injection 方向) |
| SECURITY | `SecurityCollector` · `GDELTCollector` |
| FINANCE | `FinanceCollector` · `OpenBBCollector` |
| STARTUP | `StartupCollector` |
| BID | `BidCollector` (四线 AND/OR 检索体系) |
| GITHUB | `GitHubCollector` |
| TECH | `TechCollector` · `HNCollector` · `RedditCollector` · `TelegramCollector` · `OSSInsightCollector` |

共 14 个 BaseCollector 子类。优先级: HN/Reddit/OpenBB 走 JSON API/RSS;
Telegram/GDELT/OSSInsight 遇反爬返回空 + 记 warning (延迟接入)。

### 5.3 解析器 (`backend/parsers/`)

- `base_parser.py`: `BaseSourceParser` (ABC), `parse()` + `_validate()`, 统一输出 `RawItem`
- `__init__.py`: parser 注册表 + `get_parser()`
- `bid/`: 标讯四源站点解析 (`ccgp` 政府采购网 / `cebpub` 招标公告 / `ggzy` 公共资源交易 / `zycg` 中央采购)
- `bid_extractor.py`: 标讯字段抽取 (`extract_all`), 供 collection_service 落 `bid_detail`
- 安全资讯 URL 路径仅允许 `/articles/\d+`, 拦截 `/specials/` `?author=` `?tag=` 等非文章链接

## 6. 质量管线 (`backend/quality/`)

### 6.1 执行流程 (`pipeline.py::QualityGatePipeline.run`)

```
输入 items
  → hard gates (一票否决: schema/recency/duplicate 等)
  → soft gates (扣分: category_match/title_summary/source_reputation 等)
  → quality_check_logs 落日志
  → compute_final_score() + merge_flags()
  → strict 模式 (settings 表 quality.strict_mode / quality.min_score=50) 下低分拒绝
```

`GateContext` (`base.py`) 携带 mode / source reputation / duplicate state 等;
每个 gate 实现 `BaseGate.check()`。

### 6.2 门禁清单 (`DEFAULT_GATES`, 12 个同步 gate)

| Gate | 类型 | 职责 |
|------|------|------|
| `SchemaGate` | hard | 字段完整性校验 |
| `RecencyGate` | hard | 周锚定过滤 (historical_published / no_published_at 标记) |
| `DuplicateGate` | hard | simhash + Hamming 距离去重 (quality_hook 消费全量重复 flag 硬拦) |
| `BidRecencyGate` | hard | 标讯时效 |
| `ContentQualityGate` | soft | 正文质量 |
| `NoiseContentGate` | soft | 噪声内容 |
| `AIQualityGate` | soft | 启发式 (标题营销词/空/低努力) + LLM 检测 (sensenova 限频 / ollama 本地); `quality.llm_enabled` 默认关 |
| `CategoryMatchGate` | soft | 分类匹配度 |
| `TitleSummaryGate` | soft | 标题/摘要一致性 |
| `SourceReputationGate` | soft | 来源信誉评分 |
| `AuthorVerificationGate` | soft | 作者可信度 |
| `FinalUrlGate` | soft | 最终 URL 规范化 |

异步补充: `url_full_check` job (300s) 循环翻页拉全量做 URL 覆盖检查
(url_validity / url_content), 不占同步管线。

v4.4 要点: settings 表 DB 覆盖优先于代码默认; `source_reputation.rebuild_all` 只统计
质量型 gate (排除 duplicate/schema/noise/recency 结构性信号), 未知源默认信任 70→55;
quality_check_logs 膨胀由每周日 job + `POST /api/maintenance/cleanup-quality-logs?days=2` 归档。

## 7. KL 管线 (`backend/kl_pipeline/`)

知识生命周期 5 阶段: `kl:raw → kl:refine → kl:link → kl:structure → kl:publish`
(迁移 `046_v1.7_lifecycle.sql` 一次性迁移旧 3 阶段数据)。

| 模块 | 关键成员 | 职责 |
|------|----------|------|
| `engine.py` | `KLPipeline.kickoff()` / `drain_due()` | 主引擎: 入队 / 执行到期阶段任务并推进 stage, 失败标 error |
| `queue.py` | `KLQueue.enqueue_unique()` (基于 `(item_id, stage)` 唯一约束幂等) · `due()` · `mark_run()` · `mark_done()` · `mark_error()` | 队列 DAO + 状态流转 |
| `runtime.py` | 单例装配 | 绑定 `WikiFs` + `AIHubLLMClient` + `KLPipeline` |
| `services/triggers/` | t1…t5 | T1 raw→refine (60s) / T2 refine→link (120s) / T3 link→structure (600s) / T4 structure→publish (1800s) / T5 publish→refine 回流; 每个含触发条件、执行主体、副作用、失败回退 |
| 死信 | `kl_dead_letters` 表 | `kl_dead_letter_retry` job (600s) 监控重试 |

心跳: `kl_pipeline_heartbeat` job (60s) — `drain_due` 常规消化 + 每 10 拍 sweep 兜底,
归属 secnews 扩展域。

## 8. 调度器 (`backend/scheduler/`)

### 8.1 `HotspotScheduler` 生命周期

1. `attach_service(service)` — 注入 CollectionService (start 前必须)
2. `start()` — 创建 `AsyncIOScheduler` (UTC), 注册 47 个 job, `set_scheduler()` 单例,
   启动后 5s `_run_initial()` 首跑 + sync catch-up 检查
3. `reschedule(interval_seconds)` — 运行时动态调整 collect_all 间隔 (设置 UI 驱动)
4. `stop()` — 优雅关闭 (所有异常吞掉, 保证 SIGTERM rc=0)

并发保护: `AsyncIOExecutor` 单线程异步 + `job_defaults.max_instances=1` (同 job 不重叠)
+ `coalesce=True` (错过的合并); 用 `start_date` 替代 `next_run_time=None`
(否则 IntervalTrigger 首跑后永久不再调度)。

**job 门控单一来源** (v0.6.2 P1-1): `backend/extensions/__init__.py` 的
`EXTENSION_JOBS` 声明扩展→job 归属, scheduler.py 反向派生 `JOB_TO_EXTENSION`
(替代旧散落三处的 `_JOB_EXT_MAP`)。扩展关闭时对应 job 不调度。

### 8.2 Job 全表 (47 个; ⛭ = 受 feature gate 条件注册)

| id | 触发 | 职责 |
|----|------|------|
| `collect_all` | interval 300s (可调) | 全量采集 + post-ingest 链 (trend/fts/enrichment/url_check/export/分类) |
| `source_reputation_rebuild` | interval 6h | 来源信誉重算 |
| `sync` ⛭ | cron 周一 10:30 上海 | 跨端配置同步 |
| `daily_snapshot` | cron 00:30 UTC | 日级趋势快照 |
| `weekly_report` | cron 周一 02:00 UTC | 周报生成 |
| `compile_daily` | cron 02:00 上海 | 知识定时编译 |
| `compile_consumer` | cron 02:30 上海 | 编译任务消费 + 超龄积压归档 |
| `weekly_maintenance` | cron 周日 04:00 上海 | soul → migrate → summary 链 |
| `stats_daily` | cron 06:00 上海 | 发布后数据回收 |
| `telemetry_window` | cron 周日 05:00 上海 | 7 天遥测窗口 (qcl 归档/crawler_runs/raw_items) |
| `daily_db_backup` | cron 04:30 上海 | SQLite 在线备份, 保留 7 份 |
| `cg_upstream_sync` ⛭ | cron 09:00 上海 | CodeGarden 上游同步 (M1) |
| `cg_service_scan` ⛭ | interval 300s | 服务网格自动发现 (M2) |
| `cg_event_process` ⛭ | interval 60s | 事件总线处理 (M4) |
| `kl_pipeline_heartbeat` ⛭ | interval 60s | KL 队列心跳消费 |
| `secnews_liveness_sweep` ⛭ | cron 周日 02:00 UTC | 书签存活三态批扫 (alive/dead/unknown) |
| `mitre_sync` ⛭ | cron 周日 04:00 上海 | MITRE ATT&CK STIX 同步 |
| `catchup_watchdog` | interval 60s | 追抓 watchdog |
| `source_revival_check` | cron 03:00 上海 | 死源复活 |
| `collect_validations_cleanup` | cron 04:00 上海 | validation issues 归档 |
| `kl_trigger_t1` | interval 60s | KL T1 raw→refine |
| `kl_trigger_t2` | interval 120s | KL T2 refine→link |
| `kl_trigger_t3` | interval 600s | KL T3 link→structure |
| `kl_trigger_t4` | interval 1800s | KL T4 structure→publish |
| `kl_dead_letter_retry` | interval 600s | KL 死信监控 |
| `planning_action_check` | interval 600s | 规划动作检查 |
| `cg_drift_assess` ⛭ | interval 3600s | 技术栈漂移评估 |
| `cve_sync_to_security` ⛭ | interval 1800s | CVE 同步到安全实体 |
| `wiki_archiver` | cron 03:50 上海 | 30 天归档 llm-wiki-2.0 |
| `retention_decay` | cron 周日 05:30 上海 | 艾宾浩斯遗忘衰减 |
| `attention_aggregate` | interval 1800s | 注意力事件聚合 (30 天窗口) |
| `bid_expiry_check` | interval 1800s | 标讯过期检查 |
| `url_full_check` | interval 300s | URL 全量校验 |
| `knowledge_classify` | interval 1800s | 未分类条目分类 (500/批) |
| `content_draft_generation` | interval 6h | 已发布条目 → 内容草稿 |
| `knowledge_stub_backfill` | interval 6h | 空壳条目 URL 补全 (20/批) |
| `knowledge_chunk_generation` | interval 1800s | chunks 段落切分 |
| `security_entity_concept_sync` | interval 600s | security↔knowledge 实体统一 |
| `source_scheduler_tick` | interval 60s | 源级调度器 tick |
| `source_probe` | cron 03:30 上海 | 死源探活 |
| `source_alert_eval` | interval 300s | 源级告警评估 |
| `auto_extract_alert` | interval 60s | 标签自动提取 + 告警评估 (合并 job) |
| `digest_generator` | cron 08:00 上海 | 每日简报 |
| `source_health_check` | interval 900s | 数据源健康检查 |
| `profile_decay` | cron 03:00 上海 | Profile 权重衰减 |
| `sm2_daily_push` | cron 08:00 上海 | SM-2 每日复习推送 |
| `map_rebuild_daily` | cron 02:00 上海 | 知识地图重建 |

> 历史注: v1.8 R3 把 trend_rebuild / url_content_check / export_rebuild / fts_rebuild /
> security_enrichment 收敛进 `collect_all` 尾部 post-ingest 链 (无新数据时跳过)。

## 9. 安全图谱 (`backend/security/`)

| 模块 | 职责 |
|------|------|
| `mitre_attack.py` | 从 GitHub raw 拉取 MITRE ATT&CK STIX bundle, 解析 attack patterns / tactics / relationships 写入图谱 (周同步 job); S4-3 在前端以 STIX 子集嵌入做技术映射 |
| `graph.py` | `SecurityGraphEngine` — 构建安全知识图谱, 对 hotspot/knowledge items 抽取安全实体 ID 并关联 |
| `enricher.py` | `enrich_item` / `enrich_batch` — CVE/ATT&CK/合规提取便捷导出层 |
| `compliance.py` | 合规本体种子: 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 (S4-4 扩展 GDPR + ISO 27001 矩阵, API 在 `api/compliance.py`) |

数据落 `security_graph` 表族 (migration 022); terminology 归一化在
`services/terminology_service.py`; CVE 侧另有 `services/cve_knowledge_sync.py`
(30 分钟 job 把 CVE 同步为 security 实体并桥接 knowledge)。

## 10. `wiki_fs/` — 知识文件存储契约

| 模块 | 职责 |
|------|------|
| `store.py` | `WikiFs` — `knowledge/` backed store: `list_ids` / `read_item` / `write_item` / `scan_inbox` (有效 md 移入 items/, 空或异常文件移入 quarantine/) |
| `contract.py` | frontmatter 读写契约 (对应 `knowledge/_SCHEMA.md`) |
| `linker.py` | 条目↔概念 / related_items 关联 |
| `liveness.py` | 书签存活三态 (alive/dead/unknown) 检测 |
| `migrate.py` / `root.py` | llm-wiki-2.0 归档迁移 / 根路径解析 |

## 11. MCP 服务

- **stdio 入口**: `python -m backend.mcp_stdio_main` (外部 Agent 以 stdio 协议接入)
- **SSE 通道**: `main.py` lifespan 内 `build_mcp_server(app)` + `mount_sse_endpoint(app, mcp)`
  → `/mcp/sse`; `mcp_tool_registry_seed()` 用 PRIMARY KEY name 幂等播种 9 个标准 tool 元数据
- **调试/适配路由** (`/api/mcp/*`, `/api/settings/mcp/*`): `mcp.py` (状态/工具列表/配置/开关)、
  `mcp_adapters.py` (`/api/profile` `/api/cubox/sync` `/api/extract/auto`)
- **agent tools**: `mcp_agent_tools.py` — 4 个副作用 tool (score_item / enrich_concept /
  link_items / trigger_codegarden_drift)
- **phase5 扩展**: `mcp_phase5_tools.py` — `kl_*` / `dsh_*` 5 个 tool
- **wiki 工具族**: `wiki_tools.py` — llm-wiki-2.0 消费面
- **gate**: `mcp` 扩展默认**关闭** (启用需 feature_gates.toml 置 true)

## 12. 其它顶层模块

| 模块 | 职责 |
|------|------|
| `secnews_dashboard.py` | SecNews 安全看板聚合逻辑 (配 `secnews_dashboard_api.py`) |
| `metrics/kl_metrics.py` | KL 触发器指标 (配 `/api/kl/metrics`) |
| `enrich_v2.py` | enrichment v2 |
| `tools/import_cache.py` | import 缓存工具 |
| `utils/business_days.py` | `current_week_start()` 等周锚定时间函数 (RecencyGate/catchup 共用) |
| `version.py` | `APP_VERSION = "0.7.0"` 单一来源 |
