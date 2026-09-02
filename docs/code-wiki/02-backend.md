# 02 — 后端详解

> 基准: **v0.7.4-cleanup (Batch ⑨, 2026-09-01) + v0.7.4-image (2026-09-02)**。数字快照: 68 router / 105 service / 51 job / 14 collector,
> 由 `scripts/generate_meta.py` AST 反推维护 (代码真源; 注意 `docs/ARCHITECTURE.md` 此刻 jobs 仍记 50, 属滞后 1 项)。

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
  setup_logging()              # loguru, serialize=True JSON
  set_start_time()             # 启动耗时埋点
  init_db()                    # SQLite + WAL + apply_migrations() (85 正向迁移)
  warmup()                     # 缓存预热
  rebuild_export_cache()       # 导出预生成 (失败只告警)
  [MCP] is_mcp_enabled() →     # feature gate (默认关)
        mcp_tool_registry_seed() + build_mcp_server + mount_sse_endpoint (/mcp/sse)
  svc = CollectionService(); set_service(svc)
  sched = get_scheduler() or HotspotScheduler(interval=300); attach; start()
  app.state.scheduler = sched  # /api/health 跨请求读取
  try_auto_unlock()            # OS keychain 恢复 secrets 解锁态 (admin/user 分级)
  [dsh] is_extension_enabled("dsh") → autostart_if_configured()  # 受管子进程
  [watchdog] config.knowledge_watchdog_enabled → start_watcher() (幂等)
  startup auto-catchup         # background task, 追抓本周一 00:00 Shanghai → 现在
  log_event("startup_complete", startup_duration_ms=...)
shutdown (yield 之后, 逆序):
  scheduler stop → app.state.scheduler=None → cache invalidate("*") → close_db
```

- **CORS 白名单**: 8000 / 8898 / 8899 (8899 为 `.ui-preview/` demo 静态服务器端口)
- **中间件**: `TraceIDMiddleware` (`backend/api/middleware.py`) — 注入 trace_id +
  收尾调 `record_api_call` 落 api_events (双层 swallow, exclude `/api/health`)
- **异常体系**: `register_exception_handlers` (`backend/exceptions.py`), 统一错误体
  `{"detail": {"message": "...", "missing": "..."}}` (Batch ⑧ 起带 trace_id/version envelope)

### 1.3 配置 (`backend/config.py` + `backend/config/` 包)

Pydantic Settings, 环境变量前缀 `HOTSPOT_`。关键字段:

| 字段 | 默认 | 用途 |
|------|------|------|
| `host` / `port` | 127.0.0.1 / 8000 | 服务绑定 |
| `collect_interval_seconds` | 300 | collect_all 间隔 (可运行时 reschedule) |
| `quality_reputation_interval_seconds` | 21600 | 来源信誉重算间隔 |
| `knowledge_watchdog_enabled` | True | 文件↔DB 自动同步开关 |
| `catchup_on_startup` | True | 启动自动追抓 (测试环境必须关) |
| `feature_*` | 见 01 §4 | 细粒度功能 flag (tag/extract/review/annotation/alert/mcp_server 等) |

环境变量速查 (运维常用):

| 变量 | 说明 |
|------|------|
| `AI_PROVIDER` | LLM provider 四级链第一级 (env 覆盖) |
| `SENSENOVA_API_KEY` / `OPENAI_API_KEY` / `QWEN_API_KEY` / `ANTHROPIC_API_KEY` | 各 provider 密钥 (env 链) |
| `HOTSPOT_SECRETS_TTL_SECONDS` | secrets 解锁 TTL (默认 1800s=30m) |
| `HOTSPOT_API_SAMPLING_*` | 观测采样率覆盖 (success/error/slow) |
| `DSH_ENDPOINT` | dsh 桥接默认 `http://localhost:3210` |
| `HOTSPOT_FEATURE_GATES` | JSON 覆盖 feature_gates.toml (CI core-only 冒烟用) |

LLM provider 配置: `backend/config/llm_schema.py` (Pydantic 模型) + 仓库根 `config/llm.yaml`
(v0.5.1 起单一来源)。注册 provider: `sensenova` / `ollama` / `openai` / `qwen` / `anthropic`。

## 2. API 路由层 (`backend/api/`)

### 2.1 注册机制

```
api/__init__.py   薄壳 — register_routers(app) 委托 _registry.register_all
api/_registry.py  实际注册表 — 分组 + app.include_router (无 150 行限制)
api/_flags.py     feature_flag 批量检查
```

- 全部 **lazy import** (函数体内 import, 避免循环依赖)
- 每个 router 文件 **≤ 150 行**; 头部必写路由清单注释
- 三类注册路径:

| 类别 | 判定 | 示例 |
|------|------|------|
| **core 白名单** (`core/routers.py`) | 永远注册 | hotspots / trends / health / export / quality / sources / favorites / history / todos / skills / secrets / security / settings / knowledge / content / maintenance / events / reports / **observability_router** / llm_status / deep_read / cve_analytics / … 约 45 个 |
| **extension gates** (`is_extension_enabled`) | 条件注册 | sync · codegarden×2 + codegarden_phase14 · crm×3 · mcp×3 + phase5_tools · secnews (kl_pipeline_api + secnews_dashboard_api) · dsh_api + dsh_control_api |
| **config.feature_* flag** | 条件注册 | tags · extract · reviews · annotations · alerts · search · recommend · digests |

- **依赖方向硬约束**: router 可 import `backend.services.*` / `backend.core.*`,
  **严禁** `import backend.collectors.*` / `import backend.repository.*`

### 2.2 主要 router 一览 (按域)

| 域 | router | 代表端点 |
|----|--------|----------|
| 资讯 | `hotspots.py` `categories.py` `history.py` `refresh.py` `export.py` | `GET /api/hotspots` · `POST /api/refresh` |
| 采集运维 | `sources.py` `quality.py` `cache.py` `catchup.py` | 源列表 / 质量日志 / 缓存 / 追抓 |
| 知识 | `knowledge.py` `knowledge_chunks_api.py` `knowledge_imported.py` `attention_events_api.py` | 条目 / chunks FTS5 / 收藏聚合 / 注意力事件 |
| 深读/分析 (S4) | `deep_read.py` `cve_analytics.py` `compliance.py` | S4-2 四节 LLM 分析 / CVE 热力图+ATT&CK / 合规矩阵 |
| KL | `kl_metrics_api.py` `kl_rollback_api.py` `kl_compounding_api.py` `kl_planning_api.py` `kl_pipeline_api.py` | 触发器指标 / 回滚 / 复利 / 规划动作 / 管线 |
| 行动层 | `todos.py` `skills.py` `secrets.py` `reviews.py` `tags.py` `annotations.py` `bid_alert.py` `digests.py` `content.py` | 待办 / 技能 / 密钥(TTL/轮换/OAuth) / SM-2 / 标签 / 笔记 / 标讯 / 简报 / 内容日历 |
| 判断层 | `trends.py` `search.py` `recommend.py` `mode.py` | 趋势 / 统一搜索 / 推荐 / 模式 |
| 报告 | `reports.py` `weekly_report.py` | 日报月报 / 周报 |
| 实时 | `events.py` | `GET /api/events` (SSE 推送, 含观测事件) |
| 安全 | `security.py` `tech_stack.py` | Security Graph + 术语 / 技术栈+漂移 |
| CodeGarden | `codegarden.py` `codegarden_ops.py` `codegarden_phase14.py` | M1 项目 / M2-M4 运维 / 漂移+CVE |
| 同步 | `sync.py` | push / pull / 状态 |
| MCP | `mcp.py` `mcp_adapters.py` `mcp_agent_tools.py` `mcp_phase5_tools.py` `wiki_tools.py` | 调试 / 适配 / agent tools / kl+dsh tools / wiki 工具族 |
| 观测 (v0.7.3) | `observability_router.py` | `/api/observability/{summary,recent,timeseries,llm-usage,alerts,thresholds,sampling}` — 无条件基础设施 |
| 系统 | `health.py` `maintenance.py` `settings.py` `proxy.py` `llm_status.py` `feedback_api.py` `agents_api.py` `dsh_control_api.py` | 健康 / DB 维护 / 运行时设置(含 POST /api/settings/llm-provider) / 代理 / LLM 状态 (effective_provider+key_source) / 反馈 / pi agent / dsh 启停 |

`/api/settings/features` (settings.py): 把 feature_gates 派生的扩展状态 + config.feature_*
下发给前端 `useFeatureFlags`, 是前后端可见性同源点。

## 3. 服务层 (`backend/services/`, 105 模块)

### 3.1 分组总表

| 组 | 模块 |
|----|------|
| **采集编排** | `collection_service` (核心) · `batch_service` · `catchup_service` · `collect_validator` · `collection_logger` · `crawler_seed` · `retry_policy` |
| **源健康** | `source_health_service` · `source_health_machine` (状态机) · `source_prober` · `source_alerter` · `source_census_service` · `proxy_pool` |
| **质量** | `quality_gate_map` · `simhash` |
| **知识** | `knowledge_sync` · `knowledge_watcher` · `compiler` · `concept_linker` · `auto_classifier` · `chunk_service` · `learning_service` · `review_service` (SM-2) · `mastery_projection` · `retention_engine` · `wiki_archiver` · `map_updater` · `obsidian_service` |
| **KL 管线** | `kl_state_machine` · `planning_service` · `triggers/` (t1…t5) |
| **报告/摘要** | `report_service` 族 · `weekly_report_service` · `digest_service` · `summary_service` · `summary_enricher` · `stats_recycle_service` |
| **CodeGarden** | `codegarden_project_service` · `codegarden_service_service` · `codegarden_resource_service` · `codegarden_orchestration_service` · `codegarden_scanner_service` · `codegarden_github_service` · `codegarden_knowledge_bridge` · `codegarden_drift` · `tech_stack_service` |
| **Security** | `security_graph_service` · `terminology_service` · `graph_builder` · `federation_service` · `cve_knowledge_sync` · `attack_loader` |
| **AI/LLM** | **`ai_hub/` 子包** (见 §3.3) · `llm/model_router` · `cost_monitor` |
| **观测 (v0.7)** | `observability_thresholds` (阈值引擎) · `observability_sampling` (采样) · `alert_channels` (5 通道 ABC) · `alert_dispatcher` (并发分发) |
| **密钥/鉴权** | `secrets_service` (TTL/轮换/分级/解锁) · `oauth_provider` (CloudBase OAuth -> role) |
| **同步** | `sync_service` · `sync_merge` · `sync_bundle` · `sync_zip` · `sync_fernet_mixin` · `sync_config_service` · `webdav_client` · `bookmark_sync` |
| **用户数据** | `hotspot_service` · `search_service` · `recommend_service` · `alert_engine` · `alert_service` · `annotation_service` · `extract_service` · `content_service` · `attention_scorer` · `feedback_service` · `feedback_analyzer` · `user_memory_service` |
| **画像** | `profile_service` · `soul_service` · `progress_service` |
| **运维** | `maintenance_service` · `backup_service` · `data_cleaning` · `feature_flag_service` · `secrets_service` · `history_import` · `imported_aggregator` · `export_service` · `trend_service` |
| **外部桥接** | `cubox_sync` · `sag_service` · `dsh/` (受管子进程) · `agent_bridge` (pi agent) · `process_supervisor` |

### 3.2 关键服务详解

**`collection_service.py` — 采集总编排**

- `CollectionService.collectors: dict[Category, list[BaseCollector]]`; `repo = HotspotRepository()`
- `run_once()`: `asyncio.gather` 并发 → 单源失败隔离 (`_run_one_safe`) → 批量 upsert →
  趋势重建 → `collection_runs` 审计 (SUCCESS/PARTIAL/FAILED)
- 类级共享状态 `_latest_run`; simhash 存 SQLite 前做 unsigned→signed 64-bit 转换

**`sync_*.py` — 跨端同步四件套**

| 模块 | 行数级 | 职责 |
|------|--------|------|
| `sync_service.py` | ~900 | push/pull/双向编排; 委托 build_bundle / apply_bundle / 3-way merge |
| `sync_merge.py` | ~440 | `three_way_merge()`: base/local/remote, 字段级 last-write-wins, 冲突计数 |
| `sync_bundle.py` | ~850 | bundle 生命周期 + Fernet 加解密; **复制 llm_secrets 走 `llm_secrets.sync_write` 审计** |
| `sync_zip.py` | — | zip 容器: envelope.json (密文) + manifest.json (明文) |

**`secrets_service.py` — 密钥生命周期 (v0.7 强化)**

- `setup_master_key` / `setup_user_key` — 主密钥分级: `encryption_keys.role` (admin|user,
  migration 086), keyring/settings 后缀隔离 (`master_key_{key_id}`, admin=0 / user=N)
- `unlock(role=)` / `lock` / `unlock_with_oauth` (CloudBase OAuth token → openid → role, T5)
- `rotation_status()` — `last_rotated_at` (085) + `should_rotate` (90 天) + `HOTSPOT_SECRETS_TTL_SECONDS`
  (默认 30m 自动过期); `rotate_master_key()` 旧→新 + 重加密 llm_secrets/webdav/settings
- 所有 reveal/unlock/lock/create/update/delete 写 `audit_log` (detail 永不含密钥明文)

### 3.3 `ai_hub/` 子包 — LLM 单出口

| 模块 | 职责 |
|------|------|
| `service.py` | `AIService` 对外门面 — 业务侧唯一调用入口; **provider 四级链** (`_resolve_provider`: env > settings.kv `llm.default_provider` > router > yaml) + **key 四级链** (`_resolve_api_key`: env > llm_secrets(provider=) > fail-soft) + `_config_source`/`_key_source` 打标 |
| `gateway.py` | `LLMService` provider 网关: fallback_order 依次调用 + 失败回退默认分; 同步接 AIService 单点取 key (`_ai_key_source`) |
| `tasks.py` | 任务型调用 (批量评分 / 深读分析等) |
| `write_back.py` | tasks 的写回门面 (ai_scores 写路径唯一) |
| `cache.py` | LLM 响应缓存 (配 `llm_cache` 表) |
| `usage.py` | `record_llm_call` 统一入口 (替代旧 log_llm_usage/_usage shim) → `llm_usage_log` (079 加 ok/latency/trace_id/scene/config_source/key_source 列); `success_stats_24h` 含 p50 |
| `prompts.py` | prompt 模板集中 |
| `egress.py` | egress 域名白名单校验 |

配置单一来源 `config/llm.yaml` (5 provider); AIQualityGate 的 LLM 检测走此出口,
`quality.llm_enabled` 默认关。前端 `/settings?cat=pipeline` 可切换默认 provider (写 settings.kv + audit; v0.7.x SettingsHub 已从 `/secnews/settings` 合并)。

### 3.4 观测服务族 (v0.7)

| 模块 | 职责 |
|------|------|
| `backend/observability_records.py` | `record_*` 5 类落表 (api_call/audit/job_run/agent_run/process_event); 全 `def` 同步; SAVEPOINT 隔离兼容两种连接模式; 失败 swallow |
| `backend/observability.py` | `log_event()` + TraceID ContextVar (`set_trace_id` 必须捕获返回 Token) |
| `services/observability_thresholds.py` | `Breach` dataclass + `load/save/validate/evaluate`; 4 类规则 (api/llm/job/audit) 各 warn/critical/window; 缺值兜底 DEFAULT_THRESHOLDS (api.error_rate 5/15, api.p95 800/2000ms, llm.error 10/30, job.fail 10/25) |
| `services/observability_sampling.py` | 3 档采样: success 10% / error 100% / slow 100%; env 覆盖; 前端 GET/PUT `/api/observability/sampling` |
| `services/alert_channels.py` | `BaseAlertChannel` ABC + 5 通道 (Webhook/Email/Slack/Feishu/Dingtalk); 飞书/钉钉 HMAC-SHA256 签名; 共享 `_validate_url` (拒环回/私有/多播/保留) |
| `services/alert_dispatcher.py` | `asyncio.gather` 并发分发 + `alert_deliveries` 表 (087) 落审计 |

### 3.5 其它高频服务

- `attention_scorer.py`: 5 维加权 → 0-100 attention_score
- `auto_classifier.py`: tag → domain 自动分类 (`batch_classify`)
- `compiler.py` / `concept_linker.py` / `soul_service.py`: 知识编译 → 概念关联 → 画像
- `webdav_client.py`: 坚果云 WebDAV 传输层
- `dsh/supervisor.py`: **受管子进程宿主** — 启动/停止/轮询/自动重启/重启上限;
  启停持久化 settings KV; 未配置启动命令时状态如实 `not_configured`
- `dsh/bridge.py`: `DSHClient` HTTP 连接; 不可达自动降级 LLM 直连
- `agent_bridge.py`: pi 执行 agent (`run_agent_task` — start/finish_agent_run 包裹 + trace_id `agent:<name>:<ts>`)

## 4. 数据层 (`backend/repository/`)

### 4.1 `db.py` 访问模式

- `threading.local()` **线程本地连接**; `isolation_level=None` **autocommit**
- PRAGMA: WAL / foreign_keys / busy_timeout; `init_db()` + `apply_migrations()`
  (按文件名版本排序执行, 跳过 `*_down.sql`, 写 `schema_version`)
- **无 async DB** — 全部同步; 仅 HTTP 采集是 async; **观测落表走纯 def + 调用方 to_thread**
- 约定: **每表一个 repo 模块 + 模块级 singleton**

### 4.2 迁移与核心表 (85 正向迁移, 001–088)

| 域 | 表 (代表 migration) |
|----|---------------------|
| 资讯主体 | `hotspots` (001) + `ingested_at` (007) + `hotspot_region` (023) + fingerprints/scores (043) |
| 质量 | `quality_check_logs` (002) + 归档 (062) |
| 源 | `custom_sources` (004) · `source_stats` (005) · discovery_source (060) · proxy_health (053) |
| 采集运维 | `bid_status` (008) · `history_batches` (010) · catchup_runs/checkpoints (040/042) · collect_running_status (041) · crawler_v2 (055-057) |
| 行动 | `todos` (011) · `skills` (012) · `secrets` (013) · tags (024) · reading_states (025) · sm2_reviews (026) · annotations (027) · planning_actions (049) |
| 知识 | `knowledge` (018/020) · unified_fts (033) · compiled (035) · lifecycle (036/046, `kl:*`) · chunks (054+CJK FTS 061) · knowledge_indexes (063) · wiki_events (065) · digest_summary_md (072) · wiki_items_fts (073) |
| CodeGarden | (019) 项目族 + (021) cg_services/resources/dependencies/events + drift_assessments (050) |
| 安全图谱 | security_graph (022) + tech_stack (029) |
| 告警 | alert_rules (028/048) |
| 同步 | sync 配置/状态 (014/016) |
| KL | kl_queue (070) · kl_dead_letters (044) |
| 密钥 (v0.7) | `llm_secrets` (074) · `encryption_keys` (+085 last_rotated_at / 086 role / 088 owner_role) |
| 观测 (v0.7) | `llm_usage_log` (+079 观测列) · `job_runs`/`agent_runs`/`process_events`/`audit_log` (080) · `api_events`/`api_metrics_hourly` (081) · `observability_alerts` (082) · `alert_deliveries` (087) |
| 反馈/记忆 | `feedback_events` (083) · `user_memory` (084) |
| 其它 | weekly_report (017) · personal_profile (030) · digests (031) · mcp_tool_registry (037) · llm_cache (052) · crm_cockpit (071) |

> 观测表 TTL: api_events 7d · api_metrics_hourly 30d · job_runs 30d · agent_runs 30d ·
> process_events 14d · audit_log 90d · observability_alerts 30d (由 `observability_ttl_job` 清理)。
> 知识表索引约定: `idx_ki_ingested` / `idx_ki_lifecycle` / `idx_ki_domain`。

## 5. 采集层 (`backend/collectors/` + `backend/parsers/`)

### 5.1 `BaseCollector` 接口 (`base.py`)

| 成员 | 说明 |
|------|------|
| `category` | 目标分类 (Category 枚举) |
| `sources` | 数据源配置列表 |
| `timeout` / `max_items` / `min_items_threshold` | 请求与产出控制 |
| `_parse_html()` | HTML 解析入口: 标题/URL 噪声过滤、去重、发布时间解析 |
| `_fetch()` | 取数 (httpx / RSS / JSON API) |
| `_fallback()` | 仅旧 6 分类采集器实现; **Phase 13 起新 collector 不实现**, 反爬返回空 + warning |

辅助: `session.py` (`BackendSession`) · `id_factory.py` (`make_readable_id`,
`{source}:{subtype}:{native_id}` 如 `hn:item:12345678`) · `parsing.py` / `keywords.py` ·
`item_builder.py` (透传 `raw.get("id")`) · `fetchers.py` · `quality_hook.py` (含全量重复 flag 硬拦)。

### 5.2 分类 × 采集器注册表

| Category | Collectors |
|----------|-----------|
| AI | `AICollector` |
| AI_SECURITY | `AISecurityCollector` (OWASP/对抗 ML/prompt injection) |
| SECURITY | `SecurityCollector` · `GDELTCollector` |
| FINANCE | `FinanceCollector` · `OpenBBCollector` |
| STARTUP | `StartupCollector` |
| BID | `BidCollector` (四线 AND/OR 检索体系) |
| GITHUB | `GitHubCollector` |
| TECH | `TechCollector` · `HNCollector` · `RedditCollector` · `TelegramCollector` · `OSSInsightCollector` |

共 14 个 BaseCollector 子类。优先级: HN/Reddit/OpenBB 走 JSON API/RSS;
Telegram/GDELT/OSSInsight 遇反爬返回空 + warning。

### 5.3 解析器

- `base_parser.py`: `BaseSourceParser` (ABC) + `RawItem`
- `bid/`: 标讯四源 (`ccgp` / `cebpub` / `ggzy` / `zycg`) + `bid_extractor.py` (`extract_all`)
- 通用正文抽取: `trafilatura_parser.py` / `crawl4ai_parser.py` / `html_generic.py`
  (配合 `utils/crawl4ai_client.py`, crawl4ai 被多采集器作 fallback 渲染)
- 安全资讯 URL 路径仅允许 `/articles/\d+`, 拦截 `/specials/` `?author=` `?tag=` 等

## 6. 质量管线 (`backend/quality/`)

### 6.1 执行流程 (`QualityGatePipeline.run`)

```
输入 items
  → hard gates (一票否决: schema/recency/duplicate/bid_recency)
  → soft gates (扣分: category_match/title_summary/source_reputation/…)
  → quality_check_logs 落日志
  → compute_final_score() + merge_flags()
  → strict 模式 (settings 表 quality.strict_mode / quality.min_score=50) 下低分拒绝
```

`GateContext` (`base.py`) 携带 mode / source reputation / duplicate state 等。

### 6.2 门禁清单 (DEFAULT_GATES, 12 个同步 gate)

| Gate | 类型 | 职责 |
|------|------|------|
| `SchemaGate` | hard | 字段完整性 |
| `RecencyGate` | hard | 周锚定过滤 (historical/no_published_at 标记) |
| `DuplicateGate` | hard | simhash + Hamming 去重 (quality_hook 消费全量重复硬拦) |
| `BidRecencyGate` | hard | 标讯时效 |
| `ContentQualityGate` | soft | 正文质量 |
| `NoiseContentGate` | soft | 噪声内容 |
| `AIQualityGate` | soft | 启发式 + LLM 检测 (sensenova 限频 / ollama 本地); `quality.llm_enabled` 默认关 |
| `CategoryMatchGate` | soft | 分类匹配度 |
| `TitleSummaryGate` | soft | 标题/摘要一致性 |
| `SourceReputationGate` | soft | 来源信誉 (未知源默认信任 55) |
| `AuthorVerificationGate` | soft | 作者可信度 |
| `FinalUrlGate` | soft | 最终 URL 规范化 |

异步补充: `url_full_check` job (300s) 循环翻页拉全量做 URL 覆盖检查;
`source_reputation.rebuild_all` 只统计质量型 gate; quality_check_logs 膨胀由周日 job + 清理 API 归档。

## 7. KL 管线 (`backend/kl_pipeline/`)

知识生命周期 5 阶段: `kl:raw → kl:refine → kl:link → kl:structure → kl:publish`
(迁移 `046` 从旧 3 阶段迁移)。

| 模块 | 关键成员 | 职责 |
|------|----------|------|
| `engine.py` | `KLPipeline.kickoff()` / `drain_due()` | 主引擎: 入队 / 执行到期阶段任务并推进 stage, 失败标 error |
| `queue.py` | `KLQueue.enqueue_unique()` (基于 `(item_id, stage)` 唯一约束幂等) · `due()` · `mark_done()` | 队列 DAO + 状态流转 |
| `runtime.py` | 单例装配 | 绑定 `WikiFs` + `AIHubLLMClient` + `KLPipeline` |
| `llm_adapter.py` | — | LLM 增强适配 (ai_hub 出口) |
| `stages/` | refine/link/structure/publish 四实现 | 阶段执行体 |
| `obs/` | funnel / ledger | KL 漏斗与账本 |
| `services/triggers/` | t1…t5 | T1 raw→refine (60s) / T2 refine→link (120s) / T3 link→structure (600s) / T4 structure→publish (1800s) / T5 publish→refine 回流 |
| 死信 | `kl_dead_letters` | `kl_dead_letter_retry` job (600s) 监控重试 |

心跳: `kl_pipeline_heartbeat` (60s) — `drain_due` + 每 10 拍 sweep 兜底, 归属 secnews 扩展域。

## 8. 调度器 (`backend/scheduler/`)

### 8.1 `HotspotScheduler` 生命周期

1. `attach_service(service)` — 注入 CollectionService (start 前必须)
2. `start()` — 创建 `AsyncIOScheduler` (UTC), 注册 51 个 job (v0.7.1 起按域拆
   `_register_{ingest,kl,knowledge,codegarden,security,digest,maintenance}_jobs` 7 组),
   `set_scheduler()` 单例, 启动后 5s `_run_initial()` 首跑 + sync catch-up 检查
3. `reschedule(interval_seconds)` — 运行时动态调整 collect_all 间隔
4. `stop()` — 优雅关闭 (所有异常吞掉, SIGTERM rc=0)

并发保护: `AsyncIOExecutor` 单线程异步 + `max_instances=1` + `coalesce=True`。
**job 门控单一来源**: `backend/extensions/__init__.py` `EXTENSION_JOBS` →
scheduler 反向派生 `JOB_TO_EXTENSION`。每个 job 经 `instrument_job` 装饰器包裹 (job_runs 落表)。

### 8.2 Job 全表 (51 个; ⛭ = 受 feature gate 条件注册)

| id | 触发 | 职责 |
|----|------|------|
| `collect_all` | interval 300s (可调) | 全量采集 + post-ingest 链 |
| `source_reputation_rebuild` | interval 6h | 来源信誉重算 |
| `catchup_watchdog` | interval 60s | 追抓看护 |
| `source_revival_check` | cron 03:00 上海 | 死源复活 |
| `collect_validations_cleanup` | cron 04:00 上海 | validation issues 归档 |
| `bid_expiry_check` | interval 1800s | 标讯过期检查 |
| `url_full_check` | interval 300s | URL 全量校验 |
| `source_scheduler_tick` | interval 60s | 源级调度 tick |
| `source_probe` | cron 03:30 上海 | 死源探活 |
| `source_alert_eval` | interval 300s | 源级告警评估 |
| `source_health_check` | interval 900s | 数据源健康检查 |
| `auto_extract_alert` | interval 60s | 标签自动提取 + 告警评估 (合并 job) |
| `kl_pipeline_heartbeat` ⛭ | interval 60s | KL 队列心跳 |
| `secnews_liveness_sweep` ⛭ | cron 周日 02:00 UTC | 书签存活三态批扫 |
| `kl_trigger_t1` | interval 60s | KL T1 raw→refine |
| `kl_trigger_t2` | interval 120s | KL T2 refine→link |
| `kl_dead_letter_retry` | interval 600s | KL 死信监控 |
| `kl_trigger_t3` | interval 600s | KL T3 link→structure |
| `kl_trigger_t4` | interval 1800s | KL T4 structure→publish |
| `planning_action_check` | interval 600s | 规划动作检查 |
| `compile_daily` | cron 02:00 上海 | 知识定时编译 |
| `compile_consumer` | cron 02:30 上海 | 编译任务消费 + 超龄积压归档 |
| `knowledge_classify` | interval 1800s | 未分类条目分类 (500/批) |
| `knowledge_stub_backfill` | interval 6h | 空壳条目 URL 补全 |
| `knowledge_chunk_generation` | interval 1800s | chunks 段落切分 |
| `wiki_archiver` | cron 03:50 上海 | 30 天归档 llm-wiki-2.0 |
| `retention_decay` | cron 周日 05:30 上海 | 艾宾浩斯遗忘衰减 |
| `sm2_daily_push` | cron 08:00 上海 | SM-2 每日复习推送 |
| `map_rebuild_daily` | cron 02:00 上海 | 知识地图重建 |
| `attention_aggregate` | interval 1800s | 注意力事件聚合 (30 天窗口) |
| `cg_upstream_sync` ⛭ | cron 09:00 上海 | CodeGarden 上游同步 |
| `cg_service_scan` ⛭ | interval 300s | 服务网格自动发现 (M2) |
| `cg_event_process` ⛭ | interval 60s | 事件总线处理 (M4) |
| `cg_drift_assess` ⛭ | interval 3600s | 技术栈漂移评估 |
| `mitre_sync` ⛭ | cron 周日 04:00 上海 | MITRE ATT&CK STIX 同步 |
| `cve_sync_to_security` ⛭ | interval 1800s | CVE 同步到安全实体 |
| `security_entity_concept_sync` | interval 600s | security↔knowledge 实体统一 |
| `secrets_rotation_check` | interval 6h | **v0.7.4 新增**: 主密钥过期主动通知 (rotation_status + 告警 + 前端 banner) |
| `daily_snapshot` | cron 00:30 UTC | 日级趋势快照 |
| `weekly_report` | cron 周一 02:00 UTC | 周报生成 |
| `stats_daily` | cron 06:00 上海 | 发布后数据回收 |
| `digest_generator` | cron 08:00 上海 | 每日简报 |
| `content_draft_generation` | interval 6h | 已发布条目 → 内容草稿 |
| `sync` ⛭ | cron 周一 10:30 上海 | 跨端配置同步 |
| `weekly_maintenance` | cron 周日 04:00 上海 | soul → migrate → summary 链 |
| `telemetry_window` | cron 周日 05:00 上海 | 7 天遥测窗口清理 |
| `daily_db_backup` | cron 04:30 上海 | SQLite 在线备份, 保留 7 份 |
| `observability_ttl` | interval 1h | 观测表 TTL 清理 (6 张表) |
| `observability_aggregator` | interval 60min | api_events → api_metrics_hourly 聚合 (Python 两步走) |
| `observability_threshold_check` | interval 60min (+10min 错峰) | 阈值评估 → 告警 + audit_log threshold.breach |
| `profile_decay` | cron 03:00 上海 | Profile 权重衰减 |

> 归组速记: ingest 12 · kl 8 · knowledge 10 · codegarden 4 · security 4 · digest 5 · maintenance 8 = 51。
> `observability_ttl` / `observability_aggregator` / `observability_threshold_check` /
> `secrets_rotation_check` 为 v0.7 新增 4 项。

## 9. 安全图谱 (`backend/security/`)

| 模块 | 职责 |
|------|------|
| `mitre_attack.py` | 从 GitHub raw 拉取 MITRE ATT&CK STIX bundle, 解析 attack patterns / tactics / relationships (周同步 job `mitre_sync`) |
| `graph.py` | `SecurityGraphEngine` — 构建图谱, 对 hotspot/knowledge items 抽取实体并关联 |
| `enricher.py` | `enrich_item / enrich_batch` — CVE/ATT&CK/合规提取 |
| `compliance.py` | 合规本体种子: 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 (S4-4 扩展 GDPR + ISO 27001) |

数据落 `security_graph` 表族 (022); 术语归一化在 `services/terminology_service.py`;
CVE 侧 `services/cve_knowledge_sync.py` (30 分钟 job 同步为 security 实体并桥接 knowledge)。
gate `security_graph` = **true** (Batch ⑧ 开闸)。

## 10. `wiki_fs/` — 知识文件存储契约

| 模块 | 职责 |
|------|------|
| `paths.py` | **单一路径源 (v0.6.3 P4)**: ITEMS_DIR/CONCEPTS_DIR/GRAPH_PATH/SOUL_PATH 等全部基于 `resolve_wiki_root()` 派生, 测试 env `HOTSPOT_WIKI_ROOT` 一键重定向 |
| `store.py` | `WikiFs` — `list_ids` / `read_item` (mtime+size 缓存, 35×) / `write_item` / `scan_inbox` (有效 md 移入 items/, 异常移入 quarantine/) / `scan_drafts` / `scan_concepts` |
| `contract.py` | frontmatter 读写契约 (对应 `llm-wiki-2.0/_SCHEMA.md`) |
| `linker.py` | 条目↔概念 / related_items 关联 |
| `liveness.py` | 书签存活三态 (alive/dead/unknown) |
| `migrate.py` / `root.py` | 归档迁移 / 根路径解析 (`HOTSPOT_WIKI_ROOT` 可覆盖) |

## 11. MCP 服务

- **stdio 入口**: `python -m backend.mcp_stdio_main` (外部 Agent 以 stdio 协议接入)
- **SSE 通道**: lifespan 内 `build_mcp_server(app)` + `mount_sse_endpoint(app, mcp)` → `/mcp/sse`;
  `mcp_tool_registry_seed()` 幂等播种 9 个标准 tool 元数据
- **调试/适配路由**: `mcp.py` · `mcp_adapters.py` (`/api/profile` `/api/cubox/sync` `/api/extract/auto`)
- **agent tools**: `mcp_agent_tools.py` — 4 个副作用 tool (score_item / enrich_concept / link_items / trigger_codegarden_drift)
- **phase5 扩展**: `mcp_phase5_tools.py` — `kl_*` / `dsh_*` 5 个 tool
- **wiki 工具族**: `wiki_tools.py` — llm-wiki-2.0 消费面
- **gate**: `mcp` 扩展默认**关闭**

## 12. 其它顶层模块

| 模块 | 职责 |
|------|------|
| `secnews_dashboard.py` | SecNews 工作台聚合 (配 `secnews_dashboard_api.py`) |
| `observability.py` / `observability_records.py` | 见 §1.2 / §3.4 |
| `metrics/kl_metrics.py` | KL 触发器指标 (配 `/api/kl/metrics`) |
| `tools/import_cache.py` | import 缓存工具 |
| `utils/business_days.py` | `current_week_start()` 等周锚定时间函数 |
| `utils/crawl4ai_client.py` | Crawl4AI 浏览器渲染客户端 (采集 fallback) |
| `version.py` | `APP_VERSION = "0.7.0"` 单一来源 |