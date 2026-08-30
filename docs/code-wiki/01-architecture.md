# 01 — 项目整体架构

> 本文描述 2026-08-28 发版的 **v0.7.0** 代码现状。数据流细节见 02/04 各章。

## 1. 仓库布局

```
hotspot/
├── run.py                     # 后端启动入口 (uvicorn, HOTSPOT_* 环境变量)
├── backend/                   # Python 后端 (FastAPI 单进程)
│   ├── main.py                # FastAPI app + lifespan + CORS + TraceIDMiddleware
│   ├── config.py              # Pydantic Settings (env 前缀 HOTSPOT_; config/ 包为扩展)
│   ├── core/routers.py        # core router 白名单 (永不消失的路由, 防重叠断言)
│   ├── extensions/            # 扩展注册表单一来源 (EXTENSION_ROUTERS + EXTENSION_JOBS + gates 加载)
│   ├── api/                   # 63 个 router 模块
│   │   ├── __init__.py        # 薄壳 18 行: register_routers → _registry.register_all
│   │   ├── _registry.py       # 实际分组注册 (v0.6.2 从 188 行 __init__ 拆出)
│   │   └── _flags.py          # feature_flag 批量检查
│   ├── services/              # 93 个业务编排模块
│   │   ├── ai_hub/            # LLM 单出口子包 (service/gateway/tasks/write_back/cache/usage/prompts)
│   │   ├── triggers/          # KL T1-T5 触发器
│   │   ├── dsh/               # DSH 桥接 (实验性, gate 默认关)
│   │   └── llm/               # model_router
│   ├── repository/            # SQLite DAO: db.py + repo 模块 + migrations/ (69 正向迁移)
│   ├── collectors/            # 14 个 BaseCollector 子类 + session/id_factory/parsing/keywords
│   ├── parsers/               # 独立解析器 (BaseSourceParser + bid 四源)
│   ├── quality/               # 质量门禁 pipeline (12 同步 gate + scorer + simhash)
│   ├── scheduler/             # APScheduler 封装 + jobs/ 包 (47 jobs)
│   ├── kl_pipeline/           # KL 知识生命周期管线 (engine/queue/runtime)
│   ├── wiki_fs/               # knowledge/ 文件存储契约 (store/contract/linker/liveness)
│   ├── security/              # Security Graph (mitre_attack/graph/enricher/compliance)
│   ├── metrics/               # KL 指标
│   ├── domain/                # Pydantic 模型 + 枚举
│   ├── config/                # llm_schema.py + feature_gates.toml + Settings 扩展
│   ├── mcp_stdio_main.py      # MCP stdio 传输入口
│   └── secnews_dashboard.py   # SecNews 看板聚合
├── frontend/                  # React SPA (Vite + TS + Tailwind)
│   ├── src/routes/            # 路由表 index.tsx (136 行, v0.7.0) + lazy-imports.ts + ROUTE_REGISTRY.md
│   ├── src/components/        # ~270 组件 (v0.7.0 删除 data/judge/action 三目录 + 4 认知模式)
│   │   └── workbench/         # 报纸版 5 视图 (v0.7 唯一首页)
│   ├── src/hooks/             # 27 个自定义 Hook (数据层)
│   ├── src/lib/               # api.ts (统一 API 客户端) + crm.ts
│   ├── src/contexts/          # ThemeContext (dark/light)
│   └── src/config/            # extensions.ts (前端扩展路由表)
├── knowledge/                 # 知识库文件真相源 (items/ concepts/ learning/ content/ ...)
├── codegarden/                # CodeGarden 项目工件 (exports/memory/playbooks/prompts/sdds/specs)
├── scripts/                   # 审计/校验/迁移/性能脚本 (generate_meta.py 是 CI 门禁)
├── config/                    # 运行时配置 (agents.yaml / llm.yaml / pipeline.json)
├── docs/                      # 设计文档语料库 + progress-archive/ 历史归档
└── core.include / core.exclude # "核心代码"路径声明 (review 分流)
```

## 2. 系统总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Browser (React 18 SPA, :8898)                    │
│   v0.7.0: / → /workbench (报纸版 5 视图唯一首页)                       │
│   routes/index.tsx (136 行) + React.lazy 分包 · hooks 数据层          │
│   ThemeContext 设计令牌 · useSSE 订阅 /api/events 实时刷新            │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP / JSON / SSE (vite 代理 /api → :8000)
┌──────────────────────────────▼───────────────────────────────────────┐
│                   FastAPI 单进程 (uvicorn, :8000)                     │
│  ┌───────────────┐   ┌────────────────┐   ┌────────────────────────┐ │
│  │ api/ 63 router │ → │ services/ 93   │ → │ repository/ DAO 层      │ │
│  │ (_registry.py  │   │ (含 ai_hub/    │   │ (SQLite, 每表一 repo)   │ │
│  │  lazy 注册)    │   │  子包)         │   └────────────────────────┘ │
│  └───────┬───────┘   └───────┬────────┘                              │
│  ┌───────▼───────┐   ┌───────▼────────┐   ┌────────────────────────┐ │
│  │ collectors/   │   │ kl_pipeline/   │   │ wiki_fs/               │ │
│  │ 14 采集器      │   │ KL 队列引擎     │   │ knowledge/ 文件契约     │ │
│  └───────┬───────┘   └────────────────┘   └────────────────────────┘ │
│  ┌───────▼───────┐   ┌────────────────┐   ┌────────────────────────┐ │
│  │ quality/      │   │ security/      │   │ scheduler/ 47 jobs      │ │
│  │ 12 gate 管线  │   │ MITRE/CVE/合规  │   │ collect→post-ingest 链 │ │
│  └───────────────┘   └────────────────┘   └────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
  ┌───────────┐         ┌────────────────┐     ┌──────────────────┐
  │ SQLite    │         │ knowledge/*.md │     │ WebDAV (坚果云)   │
  │ WAL 运营层 │         │ + llm-wiki-2.0 │     │ zip + Fernet 同步 │
  │ + FTS5    │         │ (md 真相源)     │     │ (每周一 10:30)    │
  └───────────┘         └────────────────┘     └──────────────────┘
```

### 前端信息架构 (v0.7.0)

**旧三层架构 (资料层 /data · 判断层 /judge · 行动层 /action) 已于 v0.7.0 物理删除**,
功能由 `/workbench` 报纸版 5 视图承接:

| workbench 视图 | 承接的旧功能 |
|----------------|--------------|
| `/workbench/briefing` (默认) | 旧 /data 资料层浏览 + /knowledge/briefing 简报 |
| `/workbench/pipeline` | 采集管线 / 质量流 (旧 /judge/quality) |
| `/workbench/knowledge` | 知识库处理 (编译/复利) |
| `/workbench/analyze` | 趋势 / CVE 热力图 / ATT&CK 映射 (旧 /judge/trends) |
| `/workbench/settings` | 运行时设置 |

其余独立子系统壳保留: `/knowledge` (4 大领域 + DeepRead/Review/Heatmap 主路径)、
`/secnews` (安全看板 7 子页)、`/codegarden`、`/crm`、`/editorial`。
旧路由 (22 个) 已物理删除返回 404, `*` fallback 与根路径均跳 `/workbench`。

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
  └──▶ security (图谱引擎)
```

硬性约定 (CI / review 强制):

- **路由文件 ≤ 150 行**, 注册表 `_registry.py` 本身不受此限
- **服务层禁止 `import backend.api`**; router 禁止直接 import collectors/repository
- **`api/__init__.py` 薄壳化** — 实际注册在 `_registry.py`, import 全部 lazy (避免循环依赖)
- **repo 单例** — 每个 repository 模块导出模块级 singleton 实例
- **注册代码改动必须同步架构数字**: `python scripts/generate_meta.py` 重写
  `docs/ARCHITECTURE.md` (CI `--check`; 当前 47 jobs / 14 collectors / 63 routers / 93 services)
- **core 白名单防重叠** — 任何新 router 不允许与 `backend/core/routers.py` 已声明路径前缀重叠, 启动时断言

## 4. Core / Extension 软分层与 Feature Gates

单一开关源: `backend/config/feature_gates.toml` 的 `[extensions]` 表。

```
feature_gates.toml ──▶ backend/extensions/__init__.py (单一来源, v0.6.2 P1-1)
                        EXTENSION_ROUTERS ──▶ api/_registry.py 条件 include
                        EXTENSION_JOBS ────▶ scheduler.py 反向派生 JOB_TO_EXTENSION
                        is_extension_enabled() ──▶ 前端 /api/settings/features → useFeatureFlags
```

- **优先级**: 默认值 (全部 True) < TOML < 环境变量 `HOTSPOT_FEATURE_GATES` (JSON, CI core-only 冒烟用)
- **保守降级**: TOML 读取失败回退"全部开启", 不阻塞启动
- **当前开关状态** (feature_gates.toml):

| 扩展 | 状态 | 说明 |
|------|------|------|
| `codegarden` | **true** | M1 项目生命周期 |
| `codegarden_phase2b` | false | M2/M3/M4 (P1.6 收缩关闭) |
| `mcp` | false | MCP Server |
| `sync` | **true** | 跨端同步 |
| `tech_stack` | false | 技术栈 + 漂移 |
| `security_graph` | false | 只控 mitre_sync / cve_sync job |
| `secnews` | **true** | KL 管线 + 安全看板 |
| `crm` | **true** | 业绩座舱 (2026-08-25 拍板) |
| `dsh` | false | P1-2 降级实验性; 不可达自动降级 llm_service |
| ~~`workbench_legacy`~~ | **已退役** | v0.7.0 物理删除老路由后失效 |

- **核心永不消失**: `backend/core/routers.py` core 白名单与扩展域防重叠断言;
  扩展关闭时对应路由 404, 但 core 域永远可用
- **前端 workbench_ui flag**: 来自 `config.feature_workbench_ui` (默认 True),
  经 `/api/settings/features` 下发, 守卫 `/workbench` 路由 — 注意它属 config.feature_* 细粒度
  flag 体系, 不在 feature_gates.toml 的 [extensions] 表内

另有一组 **config.feature_* 细粒度 flag** (`feature_tag` / `feature_auto_extract` /
`feature_review` / `feature_annotation` / `feature_tech_stack` / `feature_alert` /
`feature_unified_search` / `feature_recommendation` / `feature_digest` /
`feature_mcp_server` / `feature_workbench_ui`), 与 extension gates 双重接线。

### core.include / core.exclude (review 分流)

仓库根 `core.include` / `core.exclude` (gitignore-style glob) 声明"核心代码"路径:

- **core 内变更** (backend 主干 + frontend/src + CI + 契约文档) → 必跑完整架构门:
  `generate_meta.py --check` + 全量 pytest + ruff + pip-audit + 启动冒烟 + feature gates 全开/全闭矩阵
- **non-core 变更** → 可缩减到 `pytest -k <scope>` + touched files ruff
- CI 仅 PR 触发, `git diff --name-only` 经 `generate_meta.py --classify --batch` 输出 `has_core` / `tier`

## 5. 核心数据流

### 5.1 采集管线 (每 5 分钟 `collect_all` job)

```
collect_all_job
  → CollectionService.run_once()
      → asyncio.gather 并发跑 8 分类的 14 个 collector (单源失败隔离)
      → 每分类: QualityGatePipeline.run() (12 同步 gate, hard→soft→打分)
      → HotspotRepository.upsert_many() 批量落库 (accepted)
      → collection_runs 审计 (SUCCESS/PARTIAL/FAILED)
  → post-ingest 链 (v1.8 R3 收敛进 job 尾部, 无新数据时跳过):
      trend 重建 → FTS 重建 → security enrichment → url_content 抽查
      → export 缓存重建 → 自动分类
```

- 启动后 5s 首跑; 另有 startup auto-catchup: 自动追抓「本周一 00:00 (Asia/Shanghai) → 现在」,
  per-source checkpoint + 结构化日志 + 数据完整性验证, 服务中断后可断点续抓
- RecencyGate 语义: `published_at < 本周一 00:00 Shanghai` 标记 `historical_published`,
  `None` 标记 `no_published_at`; TimeRange (D7/H24/D3) 起点与周锚定一致

### 5.2 知识数据流 (文件 ↔ DB 双向)

```
资讯/收藏/Cubox ──▶ knowledge/inbox (scan_inbox 隔离无效文件)
     │
     ▼
KL 管线 (kl:raw → refine → link → structure → publish, T1-T5 触发器)
     │
     ▼
knowledge/items/*.md (真相源, frontmatter schema 见 _SCHEMA.md)
     │  knowledge_watcher (Watchdog, debounce) ──▶ SQLite 读缓存
     │  wiki_items_fts 写后即时同步 (v0.6.2 P0-3)
     ▼
编译 (compile_daily) → concepts/graph.json → SOUL.md 画像 → _MAP.md 索引
     │
     ▼
30 天后 wiki_archiver 归档 → llm-wiki-2.0/ + retention.json 驱动遗忘衰减
```

### 5.3 跨端同步 (每周一 10:30 Asia/Shanghai + 启动 catch-up)

```
push: 读本地配置表 → build_bundle → Fernet 加密 envelope.json
      → zip 容器 config-YYYY-MM-DD.zip (ASCII 名) → WebDAV 上传
      → 写 sync_states 作为下次 3-way merge 的 base
pull: 下载 zip → manifest 校验 → 解密 → three_way_merge (base/local/remote)
      → apply 回写各表
```

## 6. 存储模型

| 存储 | 角色 | 关键约定 |
|------|------|----------|
| SQLite (`hotspot.db`) | 运营层 + 读缓存 | WAL; thread-local 连接; autocommit (显式事务仅迁移); `busy_timeout`; FTS5 (含 CJK) |
| `migrations/*.sql` | schema 演进 | 69 个正向迁移 (001–073); `apply_migrations()` 按文件名排序执行并记录 `schema_version`; `*_down.sql` 跳过 |
| `knowledge/*.md` | 知识真相源 | frontmatter 驱动; 人机可读可写; Watchdog 监听回灌 SQLite |
| `llm-wiki-2.0/` | 冷归档层 | 30 天自动归档 (wiki_archiver job) + retention.json 遗忘策略 |
| WebDAV (坚果云) | 跨端同步远端 | zip 容器; envelope.json Fernet 密文 + manifest.json 明文 |
| `backend/proxy_config.json` | 代理配置 (gitignore) | security/github 采集器必需; 首次安装需自配 |

## 7. 横切关注点

| 模块 | 职责 |
|------|------|
| `backend/cache.py` | 进程内 TTLCache (LRU + TTL); `warmup()` 预热; `invalidate()` 失效 |
| `backend/crypto.py` | PBKDF2 派生 master key → Fernet; secrets 加密 + sync bundle 加密共用 |
| `backend/logging_config.py` | loguru 结构化日志; 组件标签 `logger.bind(component=...)` |
| `backend/observability.py` | 结构化事件 `log_event()`; 启动耗时埋点 |
| `backend/exceptions.py` | `HotspotException` 基类体系; API 错误统一格式 `{"detail": {"message": "...", "missing": "..."}}` |
| `backend/api/middleware.py` | `TraceIDMiddleware` 请求追踪 |
| `backend/proxy_config.py` / `proxy_session.py` / `services/proxy_pool.py` | 代理配置 / 会话 / 池化健康度; 标讯先直连后 `127.0.0.1:7897` |
| `backend/services/simhash.py` | 64-bit simhash + Hamming 距离标题去重 (SQLite 存 signed 64-bit) |
| `backend/version.py` | `APP_VERSION = "0.7.0"` 单一来源 (main.py / health / 错误体共用) |

## 8. 版本演进线 (近三版)

| 版本 | 日期 | 主题 |
|------|------|------|
| v0.5.0 | 2026-08-23 | llm-wiki-2.0 数据底座 + ai_hub LLM 单出口; graph.json 运行时填入; 4149 items / 96 concepts 迁移 |
| v0.6.0–0.6.2 | 2026-08-25~27 | CRM 业绩座舱发版; ai_hub 双引擎收敛; scheduler jobs 按域拆包; 扩展元数据单一来源; `_registry.py` 拆分; wiki_items_fts 即时同步; DSH 降级实验性 |
| **v0.7.0** | 2026-08-28 | **workbench 报纸版 100% 接管**: Step 1 灰度 (workbench_legacy=false) + Step 2 物理删除 (23 .tsx + 22 老路由 + 8 redirect + gate 退役); 根路径 `/`→`/workbench`; ai_hub 拆 service.py |
