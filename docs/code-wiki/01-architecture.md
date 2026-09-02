# 01 — 项目整体架构

> 本文描述 2026-09-01 的 **v0.7.4-cleanup (Batch ⑨)** 代码现状。数据流细节见 02/04 各章。

## 1. 仓库布局

```
hotspot/
├── run.py                     # 后端启动入口 (uvicorn, HOTSPOT_* 环境变量)
├── backend/                   # Python 后端 (FastAPI 单进程单 worker)
│   ├── main.py                # FastAPI app + lifespan + CORS + TraceIDMiddleware
│   ├── config.py              # Pydantic Settings (env 前缀 HOTSPOT_; config/ 包为扩展)
│   ├── config/                # feature_gates.toml + llm_schema.py + degradation_matrix.py
│   ├── core/routers.py        # core router 白名单 (永不消失的路由, 防重叠断言)
│   ├── extensions/            # 扩展注册表单一来源 (EXTENSION_ROUTERS + EXTENSION_JOBS + gates 加载)
│   ├── api/                   # 68 个注册 router (模块文件 71+; 含 obs 观测路由 + v0.7.4-image /api/image/*)
│   │   ├── __init__.py        # 薄壳: register_routers → _registry.register_all
│   │   ├── _registry.py       # 实际分组注册 (lazy import)
│   │   └── middleware.py      # TraceIDMiddleware (观测写表 + 双层 swallow)
│   ├── services/              # 105 个业务编排模块 (含 ai_hub/ subpackage)
│   │   ├── ai_hub/            # LLM 唯一出口 (service/gateway/tasks/write_back/cache/usage/prompts/egress)
│   │   ├── dsh/               # DSH 认知大脑受管子进程 (supervisor/bridge/session/task_router)
│   │   ├── llm/               # model_router (router 决策)
│   │   ├── triggers/          # KL T1-T5 触发器
│   │   ├── observability_sampling.py / observability_thresholds.py  # 观测采样 + 阈值引擎
│   │   ├── alert_channels.py / alert_dispatcher.py                  # 告警 5 通道
│   │   └── oauth_provider.py / secrets_service.py                   # 密钥 + OAuth 解锁
│   ├── repository/            # SQLite DAO: db.py + repo 模块 + migrations/ (85 正向迁移 001–088)
│   ├── collectors/            # 14 个 BaseCollector 子类 + session/id_factory/parsing/keywords
│   ├── parsers/               # 独立解析器 (BaseSourceParser + bid 四源 + trafilatura/crawl4ai)
│   ├── quality/               # 质量门禁 pipeline (12 同步 gate + scorer + simhash)
│   ├── scheduler/             # APScheduler 封装 + jobs/ 包 (51 jobs, 按域拆 7 组)
│   ├── kl_pipeline/           # KL 知识生命周期管线 (engine/queue/runtime/llm_adapter)
│   ├── wiki_fs/               # llm-wiki-2.0 文件存储契约 (store/contract/linker/liveness/paths)
│   ├── security/              # Security Graph (mitre_attack/graph/enricher/compliance)
│   ├── observability.py       # log_event + TraceID ContextVar (启动耗时埋点)
│   ├── observability_records.py # record_* 落表入口 (job/agent/process/audit/api_call) — 全 def 同步
│   ├── mcp_stdio_main.py      # MCP stdio 传输入口
│   └── secnews_dashboard.py   # SecNews 看板聚合
├── frontend/                  # React SPA (Vite + TS + Tailwind)
│   ├── src/routes/            # 路由表 index.tsx (全量, 见 03) + lazy-imports.ts + ROUTE_REGISTRY.md
│   ├── src/components/        # 组件: sentinel/ (哨兵首页) · secnews/ (7 tab 工作台)
│   │                          #       settings/ · secrets/ · codegarden/ · crm/ · security/ …
│   ├── src/hooks/             # ~26 自定义 Hook (数据层)
│   ├── src/lib/               # api.ts (统一 API 客户端) + crm.ts
│   ├── src/contexts/          # ThemeContext (dark/light) + I18nContext (zh-CN/en-US)
│   └── src/config/            # extensions.ts (前端扩展路由表)
├── llm-wiki-2.0/              # 知识库文件唯一真相源 (items/concepts/learning/content/summaries)
├── codegarden/                # CodeGarden 项目工件 (exports/memory/playbooks/prompts/sdds/specs)
├── scripts/                   # 审计/校验/迁移/性能脚本 (generate_meta.py 是 CI 门禁)
├── config/                    # 运行时配置 (agents.yaml / llm.yaml / pipeline.json)
├── docs/                      # 设计文档语料库 + code-wiki/ (本目录) + progress-archive/
└── core.include / core.exclude # "核心代码"路径声明 (review 分流)
```

## 2. 系统总览

```
┌──────────────────────────────────────────────────────────────────────┐
│               Browser (React 18 SPA, :8898)                         │
│   哨兵终端全屏首页 (v0.7.1): / /judge /action /garden …             │
│   SecNews 统一工作台: /secnews (7 tab) · /knowledge /codegarden     │
│   routes/index.tsx 全量声明 + React.lazy 分包 · hooks 数据层         │
│   ThemeContext 令牌 · I18nContext · useSSE 订阅 /api/events          │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP / JSON / SSE (vite 代理 /api → :8000)
┌──────────────────────────────▼───────────────────────────────────────┐
│                  FastAPI 单进程 (uvicorn, :8000)                     │
│  ┌────────────────┐   ┌──────────────────┐   ┌────────────────────┐ │
│  │ api/ 68 router  │ → │ services/ 105    │ → │ repository/ DAO 层  │ │
│  │ (_registry.py  │   │ (ai_hub/ 单出口   │   │ (SQLite, 每表一 repo)│ │
│  │  lazy 注册)     │   │  + obs 服务族)    │   └────────────────────┘ │
│  └───────┬────────┘   └───────┬──────────┘                          │
│  ┌───────▼────────┐   ┌───────▼────────┐   ┌────────────────────┐   │
│  │ collectors/    │   │ kl_pipeline/   │   │ wiki_fs/           │   │
│  │ 14 采集器       │   │ KL 队列引擎     │   │ llm-wiki-2.0 契约  │   │
│  └───────┬────────┘   └────────────────┘   └────────────────────┘   │
│  ┌───────▼────────┐   ┌────────────────┐   ┌────────────────────┐   │
│  │ quality/       │   │ scheduler/     │   │ observability/     │   │
│  │ 12 gate 管线    │   │ 51 jobs (7 组) │   │ record_* + 阈值+告警 │   │
│  └────────────────┘   └────────────────┘   └────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
  ┌───────────┐         ┌────────────────┐     ┌──────────────────┐
  │ SQLite    │         │ llm-wiki-2.0/  │     │ WebDAV (坚果云)   │
  │ WAL 运营层 │         │ md 文件真相源   │     │ zip + Fernet 同步 │
  │ + FTS5    │         │ + SQLite 投影  │     │ (每周一 10:30)    │
  │ + 7 观测表 │         │ + Watchdog     │     │ + DSH 子进程      │
  └───────────┘         └────────────────┘     └──────────────────┘
```

### 前端信息架构 (v0.7.4)

**首页 = 哨兵终端全屏页** (v0.7.1 起生效, 替代 v0.7.0 的 workbench 报纸版):

| 哨兵页面 | 路由 | 说明 |
|----------|------|------|
| 哨兵首页 | `/` | 唯一根路径, 同时是 `*` fallback 落点 |
| 判断层 | `/judge` (+ `/judge/graph`) | 研判 / 图谱 |
| 行动层 | `/action` | 行动待办 |
| 花园 | `/garden` | CodeGarden 入口 (哨兵壳内) |
| 设置 | `/settings` (+ `?cat=...`) | v0.7.x SettingsHub: 统一设置入口 (原 3 处孤页已合并) |

以上页面**独立全屏, 不走 PageLayout**, 壳由 `SentinelShell` 提供。报纸版 `/editorial`
2026-08-29 已退役, 仅保留 `→ /` 重定向防老书签 404。

**业务工作台** (走 PageLayout 嵌套路由):

- `/secnews` — SecNews 统一工作台 7 tab: `feed` / `pipeline` / `knowledge` / `analyze` /
  `analytics` / `observability` (v0.7.3 新增) / `settings`
- `/knowledge` — 4 大领域 (import/process/compile/compound) + 双主路径 (deep-read / review) + heatmap
- `/codegarden` (M1) + `/codegarden/phase2b` (M2-M4, gate 已开) · `/crm`
- 保留旧路由: `/todos` `/history` `/skills` `/secrets` `/sync` `/settings` `/report`
  `/reviews` `/deep/:type/:id` `/quality/rejection` `/bid-alert` `/tags` `/extract` `/search` `/oauth-callback`

## 3. 后端分层与依赖方向

```
api (router, ≤150 行/文件; _registry.py 集中注册)
  │  只做参数校验 + 响应组装; 业务下沉 services
  │  硬约束: 严禁 import backend.collectors / backend.repository (DB 必须经 service)
  ▼
services (业务编排; 严禁 import backend.api)
  │
  ├──▶ repository (SQLite DAO, thread-local 连接)
  ├──▶ domain (Pydantic 模型契约)
  ├──▶ collectors / parsers (采集与解析; 由 collection_service 编排)
  ├──▶ quality (门禁管线)
  ├──▶ kl_pipeline / wiki_fs (知识管线与文件契约)
  ├──▶ security (图谱引擎)
  └──▶ observability_records (观测落表, 仅被 .py 模块 import, 永不 import 业务层)
```

硬性约定 (CI / review 强制):

- **路由文件 ≤ 150 行**, 注册表 `_registry.py` 本身不受此限
- **服务层禁止 `import backend.api`**; router 禁止直接 import collectors/repository
- **`api/__init__.py` 薄壳化** — 实际注册在 `_registry.py`, import 全部 lazy (避免循环依赖)
- **repo 单例** — 每个 repository 模块导出模块级 singleton 实例
- **注册代码改动必须同步架构数字**: `python scripts/generate_meta.py` 重写
  `docs/ARCHITECTURE.md` (CI `--check`; 当前代码事实 **51 jobs / 14 collectors / 68 routers / 105 services** — v0.7.4-image 加 /api/image/*)
- **core 白名单防重叠** — 任何新 router 不允许与 `backend/core/routers.py` 已声明路径前缀重叠
- **观测落表 = 纯 def 同步**: `observability_records.py` 全 `def`, 任何 async 端点禁止
  `await record_*` (线程池派发); record_* 内部失败一律 swallow, 永不阻塞业务响应

## 4. Core / Extension 软分层与 Feature Gates

单一开关源: `backend/config/feature_gates.toml` 的 `[extensions]` 表。

```
feature_gates.toml ──▶ backend/extensions/__init__.py (单一来源)
                        EXTENSION_ROUTERS ──▶ api/_registry.py 条件 include
                        EXTENSION_JOBS ────▶ scheduler.py 反向派生 JOB_TO_EXTENSION
                        is_extension_enabled() ──▶ 前端 /api/settings/features → useFeatureFlags
```

- **优先级**: 默认值 (全部 True) < TOML < 环境变量 `HOTSPOT_FEATURE_GATES` (JSON, CI core-only 冒烟用)
- **保守降级**: TOML 读取失败回退"全部开启", 不阻塞启动
- **当前开关状态** (feature_gates.toml, v0.7.4):

| 扩展 | 状态 | 说明 |
|------|------|------|
| `codegarden` | **true** | M1 项目生命周期 |
| `codegarden_phase2b` | **true** (Batch ⑧ D5 开闸) | M2 服务网格 / M3 资源中枢 / M4 联动引擎 |
| `mcp` | false | MCP Server (SSE + stdio + 9 tools) |
| `sync` | **true** | 跨端同步 |
| `tech_stack` | **true** (Batch ⑧ D5 开闸) | 技术栈管理 + 漂移评估 |
| `security_graph` | **true** (Batch ⑧ D5 开闸) | 控 mitre_sync / cve_sync job |
| `secnews` | **true** | KL 管线 + 安全看板 |
| `crm` | **true** | 业绩座舱 |
| `dsh` | **true** | dsh 认知大脑受管子进程 (前端一键启停; 未配置时如实 not_configured, 业务自动降级 LLM 直连) |

- **核心永不消失**: `backend/core/routers.py` core 白名单与扩展域防重叠断言;
  扩展关闭时对应路由 404, 但 core 域永远可用
- **前端哨兵路由不做 gate** (固定渲染); 扩展路由 (sync/codegarden/codegardenPhase2b/crm)
  由 `useFeatureFlags` 条件渲染

另有 `config.feature_*` 细粒度 flag (`feature_tag` / `feature_review` / `feature_alert` /
`feature_mcp_server` 等), 与 extension gates 并存 (其中老 workbench_ui flag 随 v0.6.3
workbench 并入 SecNews 已无意义, 路由已不消费)。

### core.include / core.exclude (review 分流)

仓库根 `core.include` / `core.exclude` (gitignore-style glob) 声明"核心代码"路径:

- **core 内变更** → 必跑完整架构门: `generate_meta.py --check` + 全量 pytest + ruff +
  pip-audit + 启动冒烟 + feature gates 全开/全闭矩阵
- **non-core 变更** → 可缩减到 `pytest -k <scope>` + touched files ruff
- CI 仅 PR 触发, `git diff --name-only` 经 `generate_meta.py --classify --batch` 输出 `has_core` / `tier`

## 5. 核心数据流

### 5.1 采集管线 (每 5 分钟 `collect_all` job)

```
collect_all_job (instrument_job 包裹 → job_runs 落表)
  → CollectionService.run_once()
      → asyncio.gather 并发跑 8 分类的 14 个 collector (单源失败隔离)
      → 每分类: QualityGatePipeline.run() (12 同步 gate, hard→soft→打分)
      → HotspotRepository.upsert_many() 批量落库 (accepted)
      → collection_runs 审计 (SUCCESS/PARTIAL/FAILED)
  → post-ingest 链 (无新数据时跳过):
      trend 重建 → FTS 重建 → security enrichment → url_content 抽查
      → export 缓存重建 → 自动分类
```

- 启动后 5s 首跑; 另有 startup auto-catchup: 自动追抓「本周一 00:00 (Asia/Shanghai) → 现在」,
  per-source checkpoint + 结构化日志, 中断后可断点续抓
- RecencyGate 语义: `published_at < 本周一 00:00 Shanghai` 标记 `historical_published`,
  `None` 标记 `no_published_at`; TimeRange (D7/H24/D3) 起点与周锚定一致

### 5.2 知识数据流 (文件 ↔ DB 双向, llm-wiki-2.0/ 唯一根)

```
资讯/收藏/Cubox ──▶ llm-wiki-2.0/inbox (scan_inbox 隔离无效文件 → quarantine)
     │
     ▼
KL 管线 (kl:raw → refine → link → structure → publish, T1-T5 触发器 + 60s 心跳)
     │
     ▼
llm-wiki-2.0/items/*.md (真相源, frontmatter 见 _SCHEMA.md; wiki_fs/paths.py 单一路径源)
     │  knowledge_watcher (Watchdog, debounce) ──▶ SQLite 读缓存
     │  wiki_items_fts 写后即时同步
     ▼
编译 (compile_daily) → concepts/graph.json → soul.md 画像 → _MAP.md 索引
     │
     ▼
30 天后 wiki_archiver 归档 → llm-wiki-2.0/ 冷层 + retention.json 驱动遗忘衰减
```

### 5.3 跨端同步 (每周一 10:30 Asia/Shanghai + 启动 catch-up)

```
push: 读本地配置表 → build_bundle → Fernet 加密 envelope.json
      → zip 容器 config-YYYY-MM-DD.zip (ASCII 名) → WebDAV 上传
      → 写 sync_states 作为下次 3-way merge 的 base; 复制 llm_secrets 走 sync_write 审计
pull: 下载 zip → manifest 校验 → 解密 → three_way_merge (base/local/remote)
      → apply 回写各表
```

### 5.4 观测数据流 (v0.7 新增)

```
HTTP 请求 → TraceIDMiddleware (contextvar set_trace_id)
         → record_api_call → api_events (7d TTL; 采样: success 10% / error 100% / slow 100%)
job 运行 → instrument_job 装饰器 → job_runs (30d)
agent 运行 → agent_bridge → agent_runs (30d)
进程事件 → process_supervisor → process_events (14d)
LLM 调用 → ai_hub/usage.record_llm_call → llm_usage_log (+key_source/config_source)
审计动作 → record_audit → audit_log (90d)
        ▼
observability_aggregator (60min) → api_metrics_hourly (30d, hour+path_template 主键)
        ▼
observability_threshold_check (60min, +10min 错峰) → 评估 breach → cooldown 15min
        ▼
observability_alerts (30d) → 告警分发 (alert_dispatcher, 5 通道: status_bar/webhook/email/slack/飞书/钉钉)
        ▼
前端 /secnews/observability + StatusBar 角标 (SSE 推送 / 轮询兜底)
```

## 6. 存储模型

| 存储 | 角色 | 关键约定 |
|------|------|----------|
| SQLite (`hotspot.db`) | 运营层 + 读缓存 + 观测落库 | WAL; thread-local 连接; autocommit; FTS5 (含 CJK); 7 张观测表带 TTL |
| `migrations/*.sql` | schema 演进 | **85 个正向迁移 (001–088, 若干编号留空)**; `apply_migrations()` 按文件名排序执行; `*_down.sql` 跳过 |
| `llm-wiki-2.0/*.md` | 知识真相源 | 唯一根 (v0.6.3 P4 已删旧 `knowledge/`); frontmatter 驱动; Watchdog 回灌 SQLite |
| WebDAV (坚果云) | 跨端同步远端 | zip 容器; envelope.json Fernet 密文 + manifest.json 明文 |
| OS keychain / settings.kv | secrets 持久化 | 主密钥后缀隔离 (admin=0 / user=N); llm_secrets 业务 key |
| `backend/proxy_config.json` | 代理配置 (gitignore) | security/github 采集器必需; 首次安装需自配 |

迁移尾号速记: 074 llm_secrets · 079 llm_usage_log 观测列 · 080 job_runs/agent_runs/process_events/
audit_log · 081 api_events/api_metrics_hourly · 082 observability_alerts · 083 feedback_events ·
084 user_memory · 085 secrets TTL (last_rotated_at) · 086 encryption_keys.role · 087 alert_deliveries ·
088 secrets owner_role。

## 7. 横切关注点

| 模块 | 职责 |
|------|------|
| `backend/cache.py` | 进程内 TTLCache (LRU + TTL); `warmup()` 预热; `invalidate()` 失效 |
| `backend/crypto.py` | PBKDF2 派生 master key → Fernet; secrets 加密 + sync bundle 加密共用 |
| `backend/logging_config.py` | loguru 结构化日志 (`serialize=True` JSON); 组件标签; trace_id 注入 |
| `backend/observability.py` | `log_event()`; `get/set/reset_trace_id` (ContextVar, Token 必须捕获); 启动耗时埋点 |
| `backend/observability_records.py` | `record_api_call` / `record_audit` / `start/finish_job_run` / `start/finish_agent_run` / `record_process_event` — 全 def + 失败 swallow |
| `backend/exceptions.py` | `HotspotException` 基类体系; API 错误统一格式 `{"detail": {"message": "...", "missing": "..."}}` (含 trace_id/version envelope) |
| `backend/api/middleware.py` | `TraceIDMiddleware` 请求追踪 + 观测落表 (双层 swallow; exclude `/api/health`) |
| `backend/proxy_config.py` / `proxy_session.py` / `services/proxy_pool.py` | 代理配置 / 会话 / 池化健康度; 标讯先直连后 `127.0.0.1:7897` |
| `backend/services/simhash.py` | 64-bit simhash + Hamming 距离标题去重 |
| `backend/version.py` | `APP_VERSION = "0.7.0"` 单一来源 (main.py / health / 错误体共用; 批次线走 git tag) |

## 8. 版本演进线

| 版本 | 日期 | 主题 |
|------|------|------|
| v0.5.0 | 2026-08-23 | llm-wiki-2.0 数据底座 + ai_hub LLM 单出口; 4149 items / 96 concepts 迁移 |
| v0.6.0–0.6.3 | 2026-08-25~30 | CRM 发版; workbench 并入 SecNews 统一工作台; `_registry.py` 拆分; dsh 内置化 + pi 执行层; 双根合并锁定 llm-wiki-2.0 唯一根; P0-P3 性能根治 (采集阻塞 337ms → 0.5-8ms) |
| v0.7.0 | 2026-08-28 | workbench 报纸版 100% 接管 (物理删除三层 UI); `APP_VERSION="0.7.0"` |
| v0.7.1 | 2026-08-29 | **哨兵终端首页** (V2 设计稿还原, 独立全屏 + `*` fallback); 报纸版退役; scheduler 重构 (start 拆分 7 组注册) |
| v0.7.2 | 2026-08-31 | Batch 1-6: Observability 地基 (trace_id/job_runs/audit_log) + LLM provider 四级链 + API 观测 + 阈值告警 + llm_secrets 密钥链接入 |
| v0.7.3 | 2026-09-01 | Batch ⑦: 遗留阻塞项 5 项全清 (secrets TTL / 多用户分级 / OAuth / 全审计 / webdav 关单) |
| **v0.7.4-cleanup** | 2026-09-01 | Batch ⑧⑨: 观测深化 (5 通道告警/SSE/采样) + 扩展开闸 (phase2b/tech_stack/security_graph) + i18n 全量 + secrets ACL + 历史债清偿 (check_docstrings 237 模块) |

> 版本契约: `backend/version.py` 保持 "0.7.0" 为法规版本真源; 迭代批次以 git tag
> (v0.7.1 … v0.7.4-cleanup) 与 `docs/CHANGELOG.md` 记录。本 wiki 按 v0.7.4 代码现状编写。