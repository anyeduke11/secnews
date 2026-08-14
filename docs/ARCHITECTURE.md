# SecNews（hotspot）· 现状架构文档

> 本文档描述 **2026-08 当前代码** 的真实架构，供新开发者快速理解系统。
> 定位：现状概览，不是设计历史；历史决策与演进见 `docs/IMPROVEMENT_PLAN.md`。
> 所有数字均从代码/文件核对（迁移 59、router 51、测试 2288/278、备份保留 7、同步上限 100k）。

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
│  │ api/ 51 router│→│ services/ 81  │→│ repository/ 36 repo       │  │
│  │ (lazy 注册)   │  │ (业务编排)     │  │ (SQLite DAO, 每表一 repo) │  │
│  └──────┬───────┘  └──────┬────────┘  └────────────┬──────────────┘  │
│         │                 │                        │                 │
│  ┌──────▼───────┐  ┌──────▼────────┐   ┌───────────▼──────────────┐  │
│  │ collectors/  │  │ quality/      │   │ scheduler/ 36 jobs        │  │
│  │ 8 采集器      │→│ 13 门禁 pipeline│   │ APScheduler (进程内)      │  │
│  │ (Mixin 拆分)  │  │ (loose/strict)│   │ collect→post-ingest 链   │  │
│  └──────────────┘  └───────────────┘   └──────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────┐            ┌──────────────┐          ┌──────────────┐
   │ SQLite  │            │ knowledge/*.md│         │ WebDAV (坚果云)│
   │ WAL 模式 │            │ (文件真相源)   │          │ zip+Fernet 同步│
   │ 1 个 db  │            │ + watchdog    │          │ (每周一 10:30)│
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
├── api/           # 51 个 router (lazy import, feature flag 接线)
│   └── __init__.py # register_routers() 聚合注册
├── collectors/    # 8 个注册采集器 (14 个 BaseCollector 子类)
│   ├── base.py    # BaseCollector(ABC) — parsing/keywords/quality 已拆 Mixin
│   ├── parsing.py, keywords.py, quality_hook.py   # 从 base 拆出的模块
│   └── ai/ai_security/security/finance/startup/bid/github/tech/hn/reddit/gdelt/...
├── parsers/       # 独立解析器 (BaseSourceParser + 注册表)
├── domain/        # Pydantic 模型 (HotspotItem, CollectionReport, ...)
├── quality/       # 13 个门禁 + pipeline (loose/strict 双模式)
├── repository/    # SQLite DAO: db.py + 36 repo + migrations/ (59 个迁移)
├── scheduler/     # APScheduler 封装 + jobs.py (36 个 job)
├── security/      # Security Graph: MITRE STIX / graph / enricher / compliance
├── services/      # 业务编排 (81 个文件)
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
├── items/       # L1 条目 (当前 4143 个 .md, 含 attention_score)
├── concepts/    # L2 概念 (96 个 .md + graph.json)
├── learning/    # L3 学习计划 + 任务队列 (pending/processing/done/failed)
├── content/     # L4 内容日历 + 草稿
├── summaries/   # 周报/回顾
├── SOUL.md      # 角色画像 (自动生成)
└── _MAP.md      # 自动索引
```

- **6 认知模式**：简报（Briefing）/ 快速扫描（Scan）/ 深度阅读（DeepRead）/
  告警（Alert）/ 整理（Outbox）/ 复习（Review），对应 `/knowledge/*` 路由。
- **注意力评分**（`attention_scorer.py`）：5 维加权（view 0.25 / dwell 0.25 /
  scroll 0.15 / favorited 0.20 / annotation 0.15），0–100 分，30 天窗口，
  由 1800s 间隔 job 聚合 + 自动清理。
- **Chunk + FTS5**：条目按段落切分为 `knowledge_chunks`（含 char_start/end 原文定位），
  `knowledge_chunks_fts` 为 FTS5 外部内容表（触发器保持同步），支持全文检索。
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
  启动跑 `PRAGMA integrity_check` + 应用 59 个迁移（幂等，`duplicate column` 容错）。
- **每日备份**：04:30 Asia/Shanghai 用 SQLite online backup API 快照到
  `backend/backups/hotspot-*.db`，保留 **7 份**（`BACKUP_RETENTION = 7`），超龄自动删。
- **知识编译消费**：`compile_daily`（02:00 创建，配额 50 条/天）→
  `compile_consumer`（02:30 消费，配额 100 条/天，最旧优先、整任务粒度）→ 队列净流出；
  周日 `weekly_maintenance` 链式跑 soul → migrate → summary。
- **数据回收**：`stats_daily`（06:00）、`quality_logs_cleanup`（周日 05:00，30 天）、
  `collect_validations_cleanup`（每日 04:00）。
- **日志**：loguru 结构化日志，事件统一经 `observability.log_event` 打点
  （`startup_complete` / `collect_end` / `api_request` 等），无 Prometheus。
- **代理**：`backend/proxy_config.json`（.gitignore，首装自配）供 security/github 采集。

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

## 附录：设计原则（保留自 v3.0 方案）

1. **本地优先**（Local-First）：数据落本地 SQLite + 文件，进程崩溃/重启不丢。
2. **简单胜过复杂**：单进程、嵌入式存储、零外部服务；不加 Redis/PG/Celery。
3. **写入一次，查询多次**：写入路径重（门禁+去重+审计），读取路径轻（缓存+索引）。
4. **优雅退化**：单个数据源失败不阻塞其他源；DB/门禁不可用时兜底跳过。
5. **可观测但不重型**：结构化日志 + 轻量事件打点，不引入 Prometheus/Grafana。
6. **可扩展不预留**：通过 `BaseCollector` / `BaseGate` 抽象扩展，不为不确定需求预留接口。
