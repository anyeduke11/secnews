# SecNews（hotspot）· 现状架构文档

> 📜 **状态标注 (2026-08-25)**: hotspot 活跃开发中 — 当前代码 v0.5.0，对应 `docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6 (Phase 0 已交付 commit `2592a640`)。
>
> Phase 7 (后端退役至 dsh-SecNews) **破坏性步骤已冻结** (D+2 停 :8000 / D+3 git mv), 见 `PROGRESS.md` §2026-08-24 §连锁裁决; `scripts/export_for_dsh.py` 等工具保留为参考资产。
>
> **退役文档**: [`HOTSPOT_RETIREMENT.md`](HOTSPOT_RETIREMENT.md) (含冻结横幅, 当前为参考档案)
> **整合 spec**: [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) + [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md)

---

> 本文档描述 **2026-08 当前代码 (v0.5.0)** 的真实架构，供新开发者快速理解系统。
> 定位：现状概览，不是设计历史；历史决策与演进见 `docs/IMPROVEMENT_PLAN.md`。
> 所有数字均从代码/文件核对（迁移 60、router 52、测试 2662/292、备份保留 1、同步上限 100k）。
> v0.5.0 (2026-08-23): llm-wiki-2.0 数据底座 + ai_hub LLM 单出口 — graph.json
> 6 边运行时填入 + 一次性迁移 4149 items / 96 concepts; 详见 `docs/v0.5_refactor_plan.md`。
> v0.4.0 (2026-08-16): 审计重构 Phase 0-6 落地 — 知识闭环数据流/采集管道/同步安全/
> 导航操作流统一, 详见 `docs/audit_first_principles_plan.md`。

---

## 一、系统总览

面向 **AI + 安全从业者** 的单人本地工作站：一个人 · 一台电脑 · 零外部服务。
五个子系统共享同一个 FastAPI 进程与 SQLite 数据库：

| # | 子系统 | 说明 | 入口 |
|---|--------|------|------|
| 01 | **SecNews 热点聚合** | 8 分类采集器 · 30+ 数据源 · 13 质量门禁 · 趋势/搜索/导出 | `/` |
| 02 | **Knowledge LLM-Wiki** | 文件为真相源的知识库 · 6 认知模式 · 注意力评分 · FTS5 | `/knowledge` |
| 03 | **CodeGarden** | 项目全生命周期 + 服务网格 + 资源中枢 + 联动引擎 | `/codegarden` |
| 04 | **Security Graph** | MITRE ATT&CK · NVD CVE · 等保/关基/数安法 合规矩阵 | `/knowledge/process` |
| 05 | **MCP Server** | 9 个标准工具 · stdio / SSE 双通道 · 暴露给外部 AI Agent | `python -m backend.mcp_stdio_main` |

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Browser (React 18 SPA, :8898)                  │
│   路由 + React.lazy 分包 · hooks 数据层 · lib/api.ts · 设计令牌        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP / JSON / SSE
┌───────────────────────────────▼──────────────────────────────────────┐
│                    FastAPI 单进程 (uvicorn, :8000)                    │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────────┐  │
│  │ api/ 54 router│→│ services/ 86  │→│ repository/ 37 repo       │  │
│  │ (lazy 注册)   │  │ (业务编排)     │  │ (SQLite DAO, 每表一 repo) │  │
│  └──────┬───────┘  └──────┬────────┘  └────────────┬──────────────┘  │
│         │                 │                        │                 │
│  ┌──────▼───────┐  ┌──────▼────────┐   ┌───────────▼──────────────┐  │
│  │ collectors/  │  │ quality/      │  │ scheduler/ 47 jobs        │  │
│  │ 8 采集器      │→│ 13 门禁 pipeline│   │ APScheduler (进程内)      │  │
│  │ (Mixin 拆分)  │  │ (loose/strict)│   │ collect→post-ingest 链   │  │
│  └──────────────┘  └───────────────┘   └──────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────┐            ┌──────────────┐          ┌──────────────┐
   │ SQLite  │            │ knowledge/*.md│         │ WebDAV (坚果云)│
   │ WAL 模式 │            │ + llm-wiki-2.0│         │ zip+Fernet 同步│
   │ 运营层   │            │ (md 文件真相源) │          │ (每周一 10:30)│
   └─────────┘            └──────────────┘          └──────────────┘
```

技术选型（详见 README）：FastAPI · SQLite WAL · APScheduler · React 18 + Vite 5 + TypeScript ·
Fernet (PBKDF2 派生) · WebDAV zip 同步 · fastapi-mcp · loguru 结构化日志。

**显式不引入**：Redis / PostgreSQL / Celery / Elasticsearch / Docker / Prometheus ——
单人本地场景下进程内缓存 + SQLite FTS5 + APScheduler 足够（「简单胜过复杂」原则）。

---

## 二、后端架构

### 2.1 分层

```
backend/
├── api/           # 54 个 router (lazy import, feature flag 接线)
│   └── __init__.py # register_routers() 聚合注册
├── collectors/    # 8 个注册采集器 (14 个 BaseCollector 子类)
│   ├── base.py    # BaseCollector(ABC) — parsing/keywords/quality 已拆 Mixin
│   ├── parsing.py, keywords.py, quality_hook.py   # 从 base 拆出的模块
│   └── ai/ai_security/security/finance/startup/bid/github/tech/hn/reddit/gdelt/...
├── parsers/       # 独立解析器 (BaseSourceParser + 注册表)
├── domain/        # Pydantic 模型 (HotspotItem, CollectionReport, ...)
├── quality/       # 13 个门禁 + pipeline (loose/strict 双模式)
├── repository/    # SQLite DAO: db.py + 36 repo + migrations/ (59 个迁移)
├── scheduler/     # APScheduler 封装 + jobs.py (47 个 job, 数字由 scripts/generate_meta.py 反推维护)
├── security/      # Security Graph: MITRE STIX / graph / enricher / compliance
├── services/      # 业务编排 (86 个文件, 数字由 scripts/generate_meta.py 反推维护)
├── crypto.py      # PBKDF2 派生 + Fernet 加密 (secrets + 同步包)
├── config.py      # Pydantic Settings (env 前缀 HOTSPOT_)
└── main.py        # FastAPI app: lifespan → db/cache/export/scheduler/MCP/watchdog
```

### 2.2 数据流：采集 → 质量门禁 → SQLite

```
collect_all (每 300s, asyncio.Lock 防重叠)
  → asyncio.gather 并发跑 8 个 collector (单源异常隔离)
  → QualityGatesMixin._run_quality_gates   ← 13 门禁 (11 同步 + URL 内容异步抽样)
  → simhash 去重 (64-bit 指纹 + 8×8-bit 分桶索引, Hamming < 5 判重)
  → repo.upsert_many (单事务批量写入, 最新值覆盖)
  → trend.rebuild(24h) + 旁路写 raw_items / crawler_runs / bid_details
  → cache.invalidate("hotspots:*") + ("trends:*") + SSE 推送 collect_done
  → post-ingest 链: trend → fts → security_enrichment → url_check → export
```

要点：
- **DB 写全部进 thread pool**（`asyncio.to_thread`），不阻塞 event loop。
- 每个分类以 `collection_runs` 审计行记录 SUCCESS/PARTIAL/FAILED。
- 备用（fallback）数据打 `is_fallback` 标，不参与趋势统计。
- 采集完成事件经 `backend/api/events.py` SSE 实时推送前端。

### 2.3 质量门禁（quality/）

- `QualityGatePipeline` 顺序跑 **11 个同步门禁**：Schema / Recency / ContentQuality /
  NoiseContent / CategoryMatch / TitleSummary / SourceReputation / AuthorVerification /
  FinalUrl / Duplicate / BidRecency（另有 `*_gate.py` 共 13 个门禁文件，URLContentGate
  由独立异步 job 抽样执行）。
- **双模式**：`loose`（默认，失败打 flag + 扣分仍入库）／`strict`（`final_score < min_score`
  拒绝入库）。Hard/Soft 分层：任一 hard gate 失败即拒绝，soft gates 累加扣分。
- 结果落 `quality_check_logs` 表可追溯；`source_stats` / `coverage_runs` 评估每源产出。
- 每周日 05:00 清理 30 天前日志（曾达 440 万行 / 1.35GB）。

### 2.4 同步体系（services/sync_*）

跨端配置同步拆为 3 个可独立测试的模块（共约 2136 行）：

| 模块 | 职责 |
|------|------|
| `sync_service.py` | 编排：push / pull / bidirectional（733 行） |
| `sync_merge.py`   | 3-way merge 引擎：`three_way_merge()`（436 行） |
| `sync_bundle.py`  | 序列化：build/encrypt/decrypt bundle（967 行） |

详见第五章。

---

## 三、前端架构

```
frontend/src/
├── App.tsx          # Router + 布局 + ThemeContext + React.lazy 分包
├── components/      # 203 个组件 (security/ knowledge/ codegarden/ 分目录)
├── hooks/           # 26 个自定义 hooks (数据层)
├── lib/api.ts       # 统一 API 层 (fetch 封装: JSON/错误解析/AbortController/blob)
├── types/           # 类型 + CATEGORIES 常量表 + 工具函数
├── test/            # Vitest setup (jsdom)
└── index.css        # 设计令牌 (120 个 CSS 变量, dark/light 双主题)
```

- **路由与分包**：`react-router-dom` v6 `Routes/Route`（无其他路由库）；
  页面全部 `React.lazy` 按需加载，Suspense 包裹，减小首包体积。
- **数据层 = hooks**：`useHotspotData`（cursor 分页缓存 + 页大小 100–400）、
  `useTrendData` / `useSearch` / `useKnowledge` / `useSSE` 等 26 个 hooks 各管一块数据。
- **单例 store**：`useFavorites` 用模块级单例 + `useSyncExternalStore`，跨页共享
  收藏状态，乐观更新 + 失败回滚，多处挂载只发一次 GET。
- **设计令牌**：`index.css` 集中 `--color-*` / `--radius-*` / `--space-*` / `--font-*`；
  暗色为默认（`[data-theme="dark"]`），亮色为主题切换；SVG 图表库（ECharts/Recharts）
  经 `useThemeColors` 读取计算后样式。
- **现状注明**：前端 **无状态管理库（无 Redux/Zustand）、无 React Query** ——
  数据获取就是 hooks + fetch，状态共享用模块级单例 store，刻意保持轻量。

---

## 四、知识库体系（Knowledge）

**文件为真相源，SQLite 为读缓存**：`.md` 文件（YAML frontmatter）由 Agent/人直接读写，
`knowledge_sync.py` 负责 frontmatter ↔ SQLite 双向同步；`knowledge_watcher.py`
（watchdog）监听文件变更，1s 去抖后触发同步，冲突文件备份到 `knowledge/.conflicts/`。

```
knowledge/
├── items/       # L1 条目 (当前 4149 个 .md, 含 attention_score)
├── concepts/    # L2 概念 (96 个 .md + graph.json)
├── learning/    # L3 学习计划 + 任务队列 (pending/processing/done/failed)
├── content/     # L4 内容日历 + 草稿
├── summaries/   # 周报/回顾
├── SOUL.md      # 角色画像 (自动生成)
└── _MAP.md      # 自动索引
```

**v0.5 llm-wiki-2.0（知识真源升级，SPEC §18）**：`llm-wiki-2.0/` 为知识资产
主存储 —— md 文件唯一真源，SQLite 退化为运营层/索引缓存。存量 `knowledge/`
双轨保留（v0.5 期间不删除）。

```
llm-wiki-2.0/
├── items/       # L1 条目 (迁移自 knowledge/: 4149 个, 补 confidence/retention frontmatter)
├── concepts/    # L2 概念 (96 个 .md)
├── sources/     # 抓取元数据 (url/parser/quality_gate 决策链)
├── digest/      # 简报/结晶 (date-slug.md)
├── schema/      # SCHEMA.md — frontmatter 字段唯一真相源
├── retention.json # Ebbinghaus 衰减追踪 (current = initial*0.9^(days/7), <0.3 标 stale)
└── graph.json   # 6 种 typed edges (uses/depends/contradicts/caused/fixed/supersedes)
```

- **graph.json 运行时填充**（M3.5 Task13）：`concept_linker.py` 按条目概念共现
  累积 `uses` 边（weight + source_observation_count），保留人工/LLM 标注的其他
  5 种边；`scripts/check_graph_schema.py` + `scripts/check_retention_decay.py` CI 校验。
- **AI 能力单出口**（M5 Task19）：全仓 LLM 调用唯一入口 `backend/services/ai_hub.py`
  （合并自旧 `llm_service.py` + `ai_service.py`）；`ai_scores` 写路径唯一入口
  `ai_hub.write_score()`。`docs/llm_config.md` 有配置说明。
- **6 认知模式**：简报（Briefing）/ 快速扫描（Scan）/ 深度阅读（DeepRead）/
  告警（Alert）/ 整理（Outbox）/ 复习（Review），对应 `/knowledge/*` 路由。
- **注意力评分**（`attention_scorer.py`）：5 维加权（view 0.25 / dwell 0.25 /
  scroll 0.15 / favorited 0.20 / annotation 0.15），0–100 分，30 天窗口，
  由 1800s 间隔 job 聚合 + 自动清理。
  (v0.4.0: DeepReadMode 埋点 view/dwell/scroll, 注意力事件从此真实流动;
  复习 (SM-2) 由注意力事件自动创建, 不再是无数据死功能)
- **Chunk + FTS5**：条目按段落切分为 `knowledge_chunks`（含 char_start/end 原文定位），
  `knowledge_chunks_fts` 为 FTS5 外部内容表（触发器保持同步），支持全文检索。
  (v0.4.0 注: chunk 生成器尚未落地, 相关 API/表为预留)
- 相关 API：`knowledge_chunks_api.py`（chunk 级 API + FTS5）、`attention_events_api.py`。

---

## 五、跨设备同步与加密（Phase 42+）

- **Bundle schema**：`BUNDLE_VERSION = "1.0"`，zip 容器（内含 envelope.json +
  manifest.json，兼容旧纯 JSON 格式）。同步 13 类记录：favorites / todos / skills /
  custom_sources / codegarden_projects / codegarden_services / tags / hotspot_tags /
  reading_states / annotations / sm2_reviews / settings（含黑名单）/ secrets。
- **3-way merge**（`sync_merge.py`）：以 base/local/remote 三方合并——
  记录级按主键对齐；字段级 base==local→取 remote、base==remote→取 local；
  双方都改且不同 → 较新 `updated_at` 胜出，conflict_count +1。
- **加密**：`crypto.py` — PBKDF2-HMAC-SHA256（600k 次迭代，16 字节随机 salt）
  派生 Fernet key（AES-128-CBC + HMAC-SHA256 AEAD）；secrets 锁定态禁止 push。
- **删除通道**：merged bundle 缺席 = 对端删除（absence-as-deletion），本地多余记录
  按主键删除（favorites/todos/skills/custom_sources/annotations）；
  settings/secrets/codegarden 不做删除（语义特殊），reading_states/sm2_reviews 跳过。
- **上限**：`_SYNC_BUNDLE_MAX_ROWS = 100_000` 行 —— 全量同步上限，消除旧
  LIMIT 1000 截断导致的 absence-as-deletion 误判（个人库远小于此值）。
- **push 先 pull**：`bidirectional()` 先拉远端 —— 远端无文件则直接 push；
  远端 `merged_at` 较新 → pull（3-way merge）；本地较新 → push；相同时默认 push。
- **调度**：每周一 10:30 Asia/Shanghai 定时同步 + 启动时 catch-up 检查（auto_sync）。

---

## 六、运维与部署

- **启动**：`python run.py` → uvicorn（默认 `127.0.0.1:8000`）；
  环境变量 `HOTSPOT_HOST/PORT`（兼容旧 `HOST/PORT`）。
- **WORKERS=1**：SQLite WAL 单写者约束，多 worker 会锁竞争（`run.py` 默认 1）。
- **SQLite**（`repository/db.py`）：thread-local 连接 + autocommit +
  `journal_mode=WAL` / `synchronous=NORMAL` / `foreign_keys=ON` / `busy_timeout=5000`；
  启动跑 `PRAGMA integrity_check` + 应用 64 个迁移（幂等，`duplicate column` 容错）。
- **每日备份**：04:30 Asia/Shanghai 用 SQLite online backup API 快照到
  `backend/backups/hotspot-*.db`，**保留 1 份**（`BACKUP_RETENTION = 1`，v0.5 收紧）；
  WAL 增量备份 → `incremental/wal-{ts}-{seq}.bin` + `.sha256` 旁车。
  周日走 full + chain.meta checkpoint reset。
- **知识编译消费**：`compile_daily`（02:00 创建，配额 50 条/天）→
  `compile_consumer`（02:30 消费，配额 100 条/天，最旧优先、整任务粒度）→ 队列净流出；
  周日 `weekly_maintenance` 链式跑 soul → migrate → summary → db_diet → vacuum → full。
- **数据回收**：`stats_daily`（06:00）、`quality_logs_cleanup`（周日 05:00，30 天）、
  `collect_validations_cleanup`（每日 04:00）。
- **日志**：loguru 结构化日志，事件统一经 `observability.log_event` 打点
  （`startup_complete` / `collect_end` / `api_request` 等），无 Prometheus。
- **代理**：`backend/proxy_config.json`（.gitignore，首装自配）供 security/github 采集。

---

## 六点五、全站数据视图（M2-T6 物理分离 · v0.5）

> 单机工位机的存储架构按"温度层"分层, 让热/温/冷/冻各自的 I/O、备份、加密策略独立。
> 详见 `docs/v0.5_storage_design.md` (691 行)。

### 六点五.1 物理分离

| 温度层 | 文件 | 大小目标 | 加密 | 备份策略 |
|--------|------|----------|------|----------|
| **HOT** (主库) | `backend/hotspot.db` | <80 MB | 否 | 每日 WAL 增量 + 周日 full |
| **WARM** (业务流水) | `backend/hotspot-warm.db` | <80 MB | 否 | 周增量（与主库同步） |
| **COLD** (审计/历史) | `backend/hotspot-cold.db` | <500 MB | **Fernet 文件级 envelope** | 周 full (密文推远端) |
| **FROZEN** (资产/真源) | `knowledge/*.md` + `llm-wiki-2.0/*.md` | ~20 MB | 否 | git + 增量 zip |

启动期 `db.get_connection()` 自动 ATTACH:
```sql
ATTACH DATABASE 'backend/hotspot-warm.db' AS warm;
ATTACH DATABASE 'backend/hotspot-cold.db' AS cold;
```
若 `cold_db_key` env 设置 + `.enc` 旁车存在, cold 先解密到 tempfile 再 ATTACH。

### 六点五.2 表→温度层映射 (实时声明在 `scripts/retention.json`)

- HOT (~46 张): `hotspots`, `favorites`, `settings`, `sync_states`, `encryption_keys`,
  `knowledge_concepts`, `security_entities`, `cg_*`, `todos`, `llm_cache`, `mcp_tool_registry`...
- WARM (~56 张): `crawler_runs`, `collection_runs`, `coverage_runs`, `raw_items`,
  `content_fingerprints`, `collect_validations`, `planning_actions`, `knowledge_tasks`,
  `catchup_*`, `knowledge_links`, `knowledge_chunks`, `quality_check_logs` (live),
  `digests`, `weekly_reports`, `sync_history`...
- COLD (1 张起步): `quality_check_logs_archive`
- FROZEN: `knowledge/items/*.md`, `llm-wiki-2.0/items/*.md` (md 真源, git + zip)

### 六点五.3 写入路径约定 (T6.5)

所有生产 repo / service 代码:
```python
# 错 (v0.4): 写主库, 即使表已搬到 WARM
INSERT INTO crawler_runs (...) VALUES (...)

# 对 (v0.5): 表已搬到 warm.db, 必须指 alias
INSERT INTO warm.crawler_runs (...) VALUES (...)
```
44 个升级点（27 个文件）已自动批量替换。

### 六点五.4 备份链

```
backups/
├── hotspot-20260822_002348.db              (1 GB, BACKUP_RETENTION=1)
├── hotspot-20260822_002348.knowledge.zip   (4 MB)
└── incremental/                             (BACKUP_INCREMENTAL_DIR)
    ├── wal-20260823_043000-0000.bin       (~10 MB 每日)
    ├── wal-20260823_043000-0000.bin.sha256 (旁车 checksum)
    └── chain.meta                          (checkpoint_seq + sha256 + ts)
```

周日 full 后:
```bash
python scripts/check_backup_chain.py  # CI 校验
# 5/5 checks passed:
#   [OK] full_backup_exists
#   [OK] full_backup_quick_check (或 warn: vtable)
#   [OK] incremental_chain_count
#   [OK] incremental_sha256
#   [OK] knowledge_zip
```

### 六点五.5 COLD 加密

`scripts/cold_db_crypto.py encrypt|decrypt|verify`:
- 加密格式: `<16-byte salt><Fernet token>` → `hotspot-cold.db.enc`
- 启动期解密到 tempfile → ATTACH tempfile 为 `cold`
- 备份即密文, 离线拷贝安全 (e.g. 第三方硬盘不需再加密)

启用: `HOTSPOT_COLD_DB_KEY=<≥12 字符>` env, 启动自动 decrypt。

### 六点五.6 物理分离后的体积预估

| 文件 | v0.4 当前 | v0.5 目标 | 节省 |
|---|---:|---:|---:|
| `hotspot.db` (HOT) | 685 MB | **<80 MB** | 87% ↓ |
| `hotspot-warm.db` (WARM) | (新) | <80 MB | (新) |
| `hotspot-cold.db` (COLD, Fernet) | (新) | <500 MB (加密) | (新) |
| `backups/` full | 1 GB × 5 | 1 GB × 1 | 80% ↓ |
| `backups/incremental/` daily | (无) | 10 MB × 7 | (新) |
| **总计本地盘** | **2 GB+** | **<800 MB** | **60%+ ↓** |

---

## 七、质量保障

| 层 | 手段 |
|----|------|
| 后端测试 | **2288 个测试函数 / 158 个文件**（pytest），`tmp_path` + `monkeypatch` 隔离 |
| 前端测试 | **278 个用例 / 38 个测试文件**（Vitest + jsdom），与组件同目录 |
| CI（`.github/workflows/ci.yml`） | 后端四段：compileall → ruff → pip-audit → pytest；前端：npm audit → tsc → vitest → vite build |
| Lint | `ruff.toml`：E4/E7/E9 + F/I/UP/RUF/SIM/B + DTZ/ASYNC；忽略 RUF001–003（中文全角字符误报）等 |
| 依赖审计 | pip-audit（后端 lock）+ npm audit（前端） |

测试隔离 fixture（`backend/tests/conftest.py`）：
- `temp_db` — monkeypatch `config.db_path` 指向 tmp_path 临时库；
- `_isolate_knowledge_dirs`（autouse）— 把 11 个 service 的知识库路径常量重定向到
  tmp_path，防测试误写真实 `knowledge/`（曾致 4008 条目被清空）；
- `_disable_startup_catchup`（autouse）— 关闭启动追抓，防测试污染。

纯函数测试（最快，无 DB）：`test_sync_merge.py` / `test_auto_classifier.py` /
`test_knowledge_watcher.py`。

---

## 八、关键技术债务与路线图

| # | 项 | 状态/说明 |
|---|----|-----------|
| 1 | **crawler-v2 strangler** | 进行中：`crawler_sources` / `raw_items` / `crawler_runs` / `crawl_url_checks` / `source_scheduler` 旁路表已建（迁移 055–057），采集仍由 8 个 collector 驱动，源级调度/健康状态机逐步接管 |
| 2 | **sync P1 残余** | 3-way merge 已落地，但删除通道仅覆盖部分表；secrets 密文跨端语义仍需人工确认；settings 黑名单手工维护 |
| 3 | **RUF001–003 误报** | ruff 对中文全角字符（`。`/`，`/`（`）报 ambiguous-unicode，全仓忽略 —— 换行级 lint 精细化待办 |
| 4 | **组件过大** | `SyncPage.tsx` / `SecretsPage.tsx` 约 800 行，需要拆分 |
| 5 | **URL 校验降级** | URLValidityGate 已移出同步 pipeline（阻塞采集），由异步 job 承担，实时性弱于原设计 |
| 6 | **迁移历史债** | 早期迁移编号与文件名历史耦合（046 有 up/down 双文件），编号断号仅告警不自动改名 |

---

## 九、规划文档登记表 (Planning Document Registry)

> 本节是规划文档 (`docs/*_plan*.md` / `docs/*INTEGRATION*.md` / `docs/*_TASKS*.md`)
> 与代码实现的**唯一交叉引用锚点**。`scripts/generate_meta.py --check`
> 会扫描所有 frontmatter `status: draft` 状态的规划文档，
> 任何未在本表登记的 draft 文档 → CI 报错（防止规划与实现脱节）。
>
> 表头约定：每行必须包含 `docs/<文件名>.md` 的 backtick 反引号引用，
> 以便 `re.findall(r"`(docs/[^`]+\.md)`", text)` 机械扫描。
>
> 已登记引用总数：3 draft / 4 historical。

### 9.1 Draft 规划（激活态，等待实现）

| 文档 | 状态 | 目标版本 | 关联代码 | 依赖规划 |
|------|------|----------|----------|----------|
| [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) | `draft` | v0.6 | `backend/kl_pipeline/`, `backend/services/ai_hub.py`, `backend/collectors/secnews/`, `frontend/src/components/secnews/` | `docs/v0.5_refactor_plan.md` |
| [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md) | `draft` | v0.6 | `backend/kl_pipeline/`, `backend/services/ai_hub.py`, `backend/repository/kl_queue_repo.py` | `docs/HOTSPOT_SECNEWS_INTEGRATION.md`, `docs/v0.5_refactor_plan.md` |
| [`docs/v0.6_workstation_plan.md`](v0.6_workstation_plan.md) | `draft` | v0.6 | `backend/kl_pipeline/`, `backend/services/ai_hub.py`, `frontend/src/components/security/` | `docs/v0.5_refactor_plan.md`, `docs/audit_first_principles_plan.md`, `docs/HOTSPOT_SECNEWS_INTEGRATION.md` |

### 9.2 Historical / 已收敛（仅历史查阅，不阻塞 review）

| 文档 | 状态 | 收敛版本 |
|------|------|----------|
| `docs/v0.5_refactor_plan.md` | historical (v0.5 已落账) | v0.5.0 |
| `docs/audit_first_principles_plan.md` | historical (v0.4 已落账) | v0.4.0 |
| `docs/IMPROVEMENT_PLAN.md` | historical (v0.3 时代) | v0.3.x |
| `docs/crawler-v2-design.md` | historical (架构已定) | v0.4.x |

### 9.3 校验脚本

```bash
python scripts/generate_meta.py --check   # 同时校验: 架构数字 + draft 规划登记
```

新增规划文档流程：
1. 在 `docs/<新规划>.md` 顶部加 YAML frontmatter，至少包含
   `status: draft` / `target_version: <版本>` / `related_code: <代码路径>` / `depends_on: <前置规划>`。
2. 在上方 §9.1 表格中加一行 backtick 引用 `docs/<新规划>.md`。
3. 跑 `python scripts/generate_meta.py --check`；应输出 `OK` 且 exit 0。

---

## 附录：设计原则（保留自 v3.0 方案）

1. **本地优先**（Local-First）：数据落本地 SQLite + 文件，进程崩溃/重启不丢。
2. **简单胜过复杂**：单进程、嵌入式存储、零外部服务；不加 Redis/PG/Celery。
3. **写入一次，查询多次**：写入路径重（门禁+去重+审计），读取路径轻（缓存+索引）。
4. **优雅退化**：单个数据源失败不阻塞其他源；DB/门禁不可用时兜底跳过。
5. **可观测但不重型**：结构化日志 + 轻量事件打点，不引入 Prometheus/Grafana。
6. **可扩展不预留**：通过 `BaseCollector` / `BaseGate` 抽象扩展，不为不确定需求预留接口。
