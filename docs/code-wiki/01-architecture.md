# 01 — 项目整体架构

> 本文描述 2026-08 当前代码 (v0.5.0) 的静态架构与依赖关系。数据流细节见 02/04 各章。

## 1. 仓库布局

```
hotspot/
├── run.py                     # 后端启动入口 (uvicorn, HOTSPOT_* 环境变量)
├── backend/                   # Python 后端 (FastAPI 单进程)
│   ├── main.py                # FastAPI app + lifespan + CORS + TraceIDMiddleware
│   ├── config.py              # Pydantic Settings (env 前缀 HOTSPOT_)
│   ├── core/routers.py        # core router 白名单 (永不消失的路由)
│   ├── extensions/            # 扩展注册表 (feature_gates.toml 单一开关源)
│   ├── api/                   # 57 个 router 模块 (lazy import 注册)
│   ├── services/              # 89 个业务编排模块 (+ triggers/ T1-T5 + dsh/ + llm/)
│   ├── repository/            # SQLite DAO 层: db.py + 37 repo + migrations/ (69 正向迁移)
│   ├── collectors/            # 14 个 BaseCollector 子类 + session/id_factory/parsing/keywords
│   ├── parsers/               # 独立解析器 (BaseSourceParser + bid 四源解析)
│   ├── quality/               # 质量门禁 pipeline (12 同步 gate + scorer + simhash)
│   ├── scheduler/             # APScheduler 封装 + 47 jobs (+ jobs/kl.py)
│   ├── kl_pipeline/           # KL 知识生命周期管线 (engine/queue/runtime)
│   ├── wiki_fs/               # knowledge/ 文件存储契约 (store/contract/linker/liveness)
│   ├── security/              # Security Graph (mitre_attack/graph/enricher/compliance)
│   ├── metrics/               # KL 指标 (kl_metrics)
│   ├── domain/                # Pydantic 模型 + 枚举 (HotspotItem, CollectionReport, ...)
│   ├── config/                # llm_schema.py (LLM 配置模型) + feature_gates.toml
│   ├── mcp_stdio_main.py      # MCP stdio 传输入口
│   └── secnews_dashboard.py   # SecNews 看板聚合
├── frontend/                  # React SPA (Vite + TS + Tailwind)
│   ├── src/routes/            # 路由表 (index.tsx + lazy-imports.ts + ROUTE_REGISTRY.md)
│   ├── src/components/        # ~130 组件, 按域分 19 个子目录
│   ├── src/hooks/             # 27 个自定义 Hook (数据层)
│   ├── src/lib/               # api.ts (统一 API 客户端) + crm.ts
│   ├── src/contexts/          # ThemeContext (dark/light)
│   └── src/config/            # extensions.ts (前端扩展路由表)
├── knowledge/                 # 知识库文件真相源 (items/ concepts/ learning/ content/ ...)
├── codegarden/                # CodeGarden 项目工件 (exports/memory/playbooks/prompts/sdds/specs)
├── scripts/                   # 审计/校验/迁移/性能脚本 (generate_meta.py 是 CI 门禁)
├── config/                    # 运行时配置 (agents.yaml / llm.yaml / pipeline.json)
├── docs/                      # 设计文档语料库 (ARCHITECTURE.md 为数字权威)
└── core.include / core.exclude # "核心代码"路径声明 (review 分流)
```

## 2. 系统总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Browser (React 18 SPA, :8898)                    │
│   routes/ 路由表 + React.lazy 分包 · hooks 数据层 · lib/api.ts        │
│   ThemeContext 设计令牌 · useSSE 订阅 /api/events 实时刷新            │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP / JSON / SSE (vite 代理 /api → :8000)
┌──────────────────────────────▼───────────────────────────────────────┐
│                   FastAPI 单进程 (uvicorn, :8000)                     │
│  ┌───────────────┐   ┌────────────────┐   ┌────────────────────────┐ │
│  │ api/ 57 router │ → │ services/ 89   │ → │ repository/ 37 repo    │ │
│  │ (lazy 注册,    │   │ (业务编排)      │   │ (SQLite DAO, 每表一 repo)│
│  │  gates 条件化) │   └───────┬────────┘   └───────────┬────────────┘ │
│  └───────┬───────┘           │                        │              │
│  ┌───────▼───────┐   ┌───────▼────────┐   ┌───────────▼────────────┐ │
│  │ collectors/   │   │ kl_pipeline/   │   │ wiki_fs/               │ │
│  │ 14 采集器      │   │ KL 队列引擎     │   │ knowledge/ 文件契约     │ │
│  └───────┬───────┘   └────────────────┘   └────────────────────────┘ │
│  ┌───────▼───────┐   ┌────────────────┐   ┌────────────────────────┐ │
│  │ quality/      │   │ security/      │   │ scheduler/ 47 jobs      │ │
│  │ 12 gate 管线  │   │ MITRE/CVE/合规  │   │ APScheduler (进程内)    │ │
│  └───────────────┘   └────────────────┘   │ collect → post-ingest 链│ │
│                                             └────────────────────────┘ │
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

### 前端三层信息架构 (v0.4 起主导航)

| 层 | 路由 | 职责 |
|----|------|------|
| 资料层 | `/data` | 多源资讯的导入 / 收藏 / 历史 (DataLayerPage) |
| 判断层 | `/judge` | 趋势分析 / 标讯分析 / 质量拒绝流 (JudgeLayerPage) |
| 行动层 | `/action` | 报告 / 复利 / 待办 / Outbox / 复习 / 技能 / CodeGarden / 标讯提醒 |

其上叠挂子系统壳: `/knowledge` (知识管理 4 领域 + 6 认知模式)、`/secnews` (安全看板)、
`/codegarden`、`/crm`、`/workbench` (5 视图统一壳)。旧路由以 `Navigate` 重定向兼容保留。

## 3. 后端分层与依赖方向

```
api (router, ≤150 行/文件)
  │  只做参数校验 + 响应组装; 业务下沉 services
  ▼
services (业务编排, 禁止 import backend.api)
  │
  ├──▶ repository (SQLite DAO, thread-local 连接)
  ├──▶ domain (Pydantic 模型契约)
  ├──▶ collectors / parsers (采集与解析)
  ├──▶ quality (门禁管线)
  ├──▶ kl_pipeline / wiki_fs (知识管线与文件契约)
  └──▶ security (图谱引擎)
```

硬性约定 (CI / review 强制):

- **路由文件 ≤ 150 行**, 超出必须拆分
- **服务层禁止 `import backend.api`** (依赖方向单向: api → services)
- **`backend/api/__init__.py` 全部 lazy import** — 不在模块级触发 import, 避免循环依赖
- **repo 单例** — 每个 repository 模块导出模块级 singleton 实例
- **注册代码改动必须同步架构数字**: `python scripts/generate_meta.py` 重写 `docs/ARCHITECTURE.md` (CI `--check`)

## 4. Core / Extension 软分层与 Feature Gates (v0.4.3)

单一开关源: `backend/config/feature_gates.toml` 的 `[extensions]` 表。

```
feature_gates.toml ──▶ backend/extensions/__init__.py
                        is_extension_enabled(name)
                        ├─▶ api/__init__.py:    扩展 router 条件 include
                        ├─▶ scheduler.py:       _JOB_EXT_MAP 条件 add_job
                        └─▶ 前端 useFeatureFlags: 条件渲染 Route
```

- **优先级**: 默认值 (全部 True) < TOML < 环境变量 `HOTSPOT_FEATURE_GATES` (JSON, CI core-only 冒烟用)
- **保守降级**: TOML 读取失败回退"全部开启", 不阻塞启动
- **扩展域** (8 个, 登记于 `_EXTENSION_NAMES`): `codegarden` (M1 项目核心) / `codegarden_phase2b` (M2/M3/M4) /
  `mcp` / `sync` / `tech_stack` / `security_graph` (只占 job) / `secnews` / `crm`;
  另有 `dsh` 在 `api/__init__.py` 以 `is_extension_enabled("dsh")` 条件注册, 但未登记进
  `_EXTENSION_NAMES` (加载器按 `_DEFAULT_GATES` 过滤 TOML 键, 未知名称恒返回 True)
- **core 永不消失**: `backend/core/routers.py` 定义 43 个 core router 白名单, 与扩展域防重叠断言;
  扩展关闭时对应路由 404, 但 core 域 (采集 / 知识库 / 行动层 / KL / 系统) 永远可用
- **测试约定**: conftest autouse fixture 测试环境全开 gates; 组合矩阵见 `backend/tests/test_feature_gates.py`
- **`security_graph` 特殊**: 不占 router (security / kl_* 属 core 安全数据), 只控制 `mitre_sync` / `cve_sync_to_security` 两个 job

另有一组 **config.feature_* 细粒度 flag** (`feature_tag` / `feature_auto_extract` / `feature_review` /
`feature_annotation` / `feature_tech_stack` / `feature_alert` / `feature_unified_search` /
`feature_recommendation` / `feature_digest` / `feature_mcp_server`), 与 extension gates 双重接线。

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
- URL 全量校验独立成 job (`url_full_check` 每 5 分钟), 与同步 gate 分离
- RecencyGate 语义: `published_at < 本周一 00:00 Shanghai` 标记 `historical_published`,
  `None` 标记 `no_published_at`; TimeRange (D7/H24/D3) 起点与周锚定一致

### 5.2 知识数据流 (文件 ↔ DB 双向)

```
资讯/收藏/Cubox ──▶ knowledge/inbox (scan_inbox 隔离无效文件)
     │                    │
     ▼                    ▼
KL 管线 (kl:raw → refine → link → structure → publish, T1-T5 触发器)
     │
     ▼
knowledge/items/*.md (真相源, frontmatter schema 见 _SCHEMA.md)
     │  knowledge_watcher (Watchdog, debounce) ──▶ SQLite 读缓存
     │  knowledge_sync: write_item_to_md (DB → md) / sync_item_to_db (md → DB)
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
| SQLite (`hotspot.db`) | 运营层 + 读缓存 | WAL 模式; thread-local 连接; autocommit (显式事务仅迁移); `busy_timeout`; FTS5 全文索引 (含 CJK) |
| `migrations/*.sql` | schema 演进 | 69 个正向迁移 (001–073, 编号跳过 066–069); `apply_migrations()` 按文件名排序执行并记录 `schema_version`; `*_down.sql` 跳过 |
| `knowledge/*.md` | 知识真相源 | frontmatter 驱动; 人机可读可写; Watchdog 监听变更 debounce 回灌 SQLite |
| `llm-wiki-2.0/` | 冷归档层 | 30 天自动归档 (wiki_archiver job) + retention.json 遗忘策略 |
| WebDAV (坚果云) | 跨端同步远端 | zip 容器; envelope.json Fernet 密文 + manifest.json 明文元数据 |
| `backend/proxy_config.json` | 代理配置 (gitignore) | security/github 采集器必需; 首次安装需自配 |

## 7. 横切关注点

| 模块 | 职责 |
|------|------|
| `backend/cache.py` | 进程内 TTLCache (LRU + TTL); `warmup()` 预热; `invalidate()` 失效 |
| `backend/crypto.py` | PBKDF2 派生 master key → Fernet; secrets 加密 + sync bundle 加密共用 |
| `backend/logging_config.py` | loguru 结构化日志; 组件标签 `logger.bind(component=...)` |
| `backend/observability.py` | 结构化事件 `log_event()` (如 `startup_complete`); 启动耗时埋点 |
| `backend/exceptions.py` | `HotspotException` 基类体系 + `register_exception_handlers`; API 错误统一格式 `{"detail": {"message": "...", "missing": "..."}}` |
| `backend/api/middleware.py` | `TraceIDMiddleware` 请求追踪 |
| `backend/proxy_config.py` / `proxy_session.py` / `services/proxy_pool.py` | 代理配置加载 / 会话 / 池化健康度; 标讯抓取先 HTTP 直连, 失败走 `127.0.0.1:7897` |
| `backend/services/simhash.py` | 64-bit simhash + Hamming 距离标题去重 (SQLite 存 signed 64-bit) |
