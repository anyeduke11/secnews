# SecNews（hotspot）· 现状架构文档

> 📜 **状态标注 (2026-08-28)**: hotspot 活跃开发中 — 当前代码 v0.6.2，对应 `docs/SECNEWS_INTEGRATION_TASKS.md` Phase 4-6 已全部交付 (Phase 4 合规矩阵 `5c657d99` / Phase 6 wiki 迁移 `309a83da` + FTS5 同步 `e53790cc`)。
>
> **退役文档**: [`HOTSPOT_RETIREMENT.md`](HOTSPOT_RETIREMENT.md) (含冻结横幅, 当前为参考档案)
> **整合 spec**: [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](docs/HOTSPOT_SECNEWS_INTEGRATION.md) + [`docs/SECNEWS_INTEGRATION_TASKS.md`](docs/SECNEWS_INTEGRATION_TASKS.md)
> **代码审计**: [`docs/CODE_AUDIT_2026-08-28.md`](docs/CODE_AUDIT_2026-08-28.md) (架构深度分析)

> 本文档描述 **2026-08-28 当前代码 (v0.6.2)** 的真实架构，供新开发者快速理解系统。
> **定位**：现状导览 (≤ 200 行)；详细专题见 [docs/code-wiki/](code-wiki/CODE_WIKI.md) 5 个分章节文件。
> 所有数字均从代码/文件核对（迁移 60+、router 63、jobs 47、collectors 14、services 93、测试 2892/322、备份保留 7、同步上限 100k），`scripts/generate_meta.py --check` 是 CI 门禁。
> v0.6 (2026-08-23 → 08-28): SecNews 工作台 5 视图 (Briefing/Pipeline/Knowledge/Analyze/Settings) + kl_pipeline 五阶段管线 + DSH HTTP 桥接 + CRM 业绩座舱 + wiki_items_fts 完整同步层 + dsh-SecNews 归档, 详见 `docs/CODE_AUDIT_2026-08-28.md`。
> v0.5 (2026-08-21 → 08-23): llm-wiki-2.0 数据底座 + ai_hub LLM 单出口 + Hot/Warm/Cold 分层 + dlq retry + 性能三任务, 详见 `docs/v0.5_refactor_plan/README.md`。
> v0.4.0 (2026-08-16): 审计重构 Phase 0-6 落地, 详见 `docs/audit_first_principles_plan.md`。

---

## 一、系统总览

面向 **AI + 安全从业者** 的单机本地工作站：一个人 · 一台电脑 · 零外部服务。
五个子系统共享同一个 FastAPI 进程与 SQLite 数据库：

| # | 子系统 | 说明 | 入口 |
|---|--------|------|------|
| 01 | **SecNews 热点聚合** | 14 采集器 · 11+ 质量门禁 · 趋势/搜索/导出 | `/` |
| 02 | **Knowledge LLM-Wiki** | `llm-wiki-2.0/` md 真源 · kl_pipeline 五阶段 · FTS5 | `/knowledge` |
| 03 | **CodeGarden** | 项目生命周期 + 服务网格 + 资源中枢 + 联动引擎 | `/codegarden` |
| 04 | **Security Graph** | MITRE ATT&CK · NVD CVE · 等保/关基/数安法 | `/knowledge/process` |
| 05 | **SecNews 工作台 (v0.6)** | 5 视图: Briefing / Pipeline / Knowledge / Analyze / Settings | `/workbench` |
| 06 | **CRM 业绩座舱 (v0.6.0)** | 客户/商机/状态机/KPI 聚合 | `/crm` |

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (React 18 SPA, :8898) — workbench/ 5 视图 + secnews/ + crm/  + data/judge/action 历史
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP / JSON / SSE
┌───────────────▼──────────────────────────────────────────────┐
│  FastAPI 单进程 (uvicorn, :8000) — 63 router / 93 services    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │ collectors/  │→│ quality/     │→│ scheduler/ 47 jobs │   │
│  │ 14 BaseColl.  │  │ 11+ gates    │  │ APScheduler         │   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘   │
│         │                │                    │             │
│  ┌──────▼───────┐  ┌──────▼────────┐  ┌────────▼────────┐  │
│  │ api/ 63 router│  │ services/ 93  │  │ repository/ 37  │  │
│  │ (lazy 注册)   │  │ (业务编排)     │  │ (SQLite DAO)    │  │
│  └──────────────┘  └──────┬────────┘  └─────────────────┘  │
└─────────────────────────┬──────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────────┐
        ▼                 ▼                     ▼
  ┌──────────┐     ┌───────────────┐     ┌──────────────┐
  │ SQLite   │     │ llm-wiki-2.0/ │     │ WebDAV 同步   │
  │ WAL+ATTACH│     │ (md 真源 + FTS) │     │ (zip+Fernet)  │
  │ HOT/WARM │     │ + watchdog    │     │ 每周一 10:30   │
  │ /COLD    │     │ (P0-3 即时同步) │     └──────────────┘
  └──────────┘     └───────────────┘
```

**显式不引入**：Redis / PostgreSQL / Celery / Elasticsearch / Docker / Prometheus ——
单机本地场景下进程内缓存 + SQLite FTS5 + APScheduler 足够。

**深入文档指针表**（导览→细节）：

| 主题 | 详见 |
|---|---|
| 后端分层与数据流 | [docs/code-wiki/02-backend.md](code-wiki/02-backend.md) (397 行) |
| 前端架构 | [docs/code-wiki/03-frontend.md](code-wiki/03-frontend.md) (179 行) |
| 子系统详解 | [docs/code-wiki/04-subsystems.md](code-wiki/04-subsystems.md) (141 行) |
| 知识库体系 | [docs/code-wiki/04-subsystems.md](code-wiki/04-subsystems.md) §2 |
| 同步与加密 | [docs/code-wiki/02-backend.md](code-wiki/02-backend.md) §3 + §4 |
| 运维与部署 | [docs/code-wiki/05-running.md](code-wiki/05-running.md) (158 行) |
| 仓库整体布局 | [docs/code-wiki/01-architecture.md](code-wiki/01-architecture.md) (225 行) |
| Wiki 索引 | [docs/code-wiki/CODE_WIKI.md](code-wiki/CODE_WIKI.md) |
| 历史决策 | [docs/v0.5_refactor_plan/README.md](v0.5_refactor_plan/README.md) |
| 代码审计 | [docs/CODE_AUDIT_2026-08-28.md](docs/CODE_AUDIT_2026-08-28.md) |

---

## 二、全站数据视图（Hot / Warm / Cold / Frozen · v0.5）

> 单机工位机按"温度层"分层, 让热/温/冷/冻各自的 I/O、备份、加密策略独立。
> 详见 `docs/v0.5_storage_design.md` (691 行)。

| 温度层 | 文件 | 大小目标 | 加密 | 备份策略 |
|--------|------|----------|------|----------|
| **HOT** (主库) | `backend/hotspot.db` | <80 MB | 否 | 每日 WAL 增量 + 周日 full |
| **WARM** (业务流水) | `backend/hotspot-warm.db` | <80 MB | 否 | 周增量 |
| **COLD** (审计/历史) | `backend/hotspot-cold.db` | <500 MB | **Fernet envelope** | 周 full (密文) |
| **FROZEN** (资产/真源) | `knowledge/*.md` + `llm-wiki-2.0/*.md` | ~20 MB | 否 | git + 增量 zip |

启动期 `db.get_connection()` 自动 ATTACH `hotspot-warm.db AS warm` + `hotspot-cold.db AS cold`；
生产 repo 代码对 WARM 表写操作必须指 `warm.` alias（如 `INSERT INTO warm.crawler_runs`）。

COLD 加密: `scripts/cold_db_crypto.py encrypt|decrypt|verify`，格式 `<16-byte salt><Fernet token>` → `hotspot-cold.db.enc`。

---

## 三、关键技术债务与路线图

| # | 项 | 状态 |
|---|----|------|
| 1 | **data/judge/action 三层目录退役** (v0.6+ 工作台替代) | 待 P2-3 加 `@deprecated` + `workbench_legacy` gate |
| 2 | **DSH 桥接层** | P1-2 降级为实验性 (`dsh = false` 默认)；需 DSH_ENDPOINT 才启用 |
| 3 | **6 cognitive modes** (Briefing/Scan/Alert/Outbox) | P1-5 加 `@deprecated`，v0.7 退役 |
| 4 | **crawler-v2 strangler** | `crawler_sources` / `source_scheduler` 已建，源级调度逐步接管 |
| 5 | **SecNEWS Phase 6 存量迁移** (S6-1..S6-4) | Phase 6 wiki_items_fts + migrate_wiki.py 已落，S6-3/S6-4 待 |
| 6 | **组件过大** | `SyncPage.tsx` / `SecretsPage.tsx` 约 800 行，需拆分 |
| 7 | **Mimosa 密封扫描** | 未启用 (P2-4, 见 [docs/SECURITY_AUDIT.md](SECURITY_AUDIT.md) §1; 工具不可用待 sandbox 释放) |

---

## 四、设计原则

1. **本地优先**（Local-First）：数据落本地 SQLite + 文件，进程崩溃/重启不丢。
2. **简单胜过复杂**：单进程、嵌入式存储、零外部服务。
3. **写入一次，查询多次**：写入路径重（门禁+去重+审计），读取路径轻（缓存+索引）。
4. **优雅退化**：单源失败不阻塞其他；DB/门禁不可用时兜底跳过。
5. **可观测但不重型**：结构化日志 + 轻量事件打点，无 Prometheus/Grafana。
6. **可扩展不预留**：通过 `BaseCollector` / `BaseGate` 抽象扩展。

---

## 五、规划文档登记（generate_meta draft 校验）

| 文档 | 状态 | 说明 |
|---|---|---|
| [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) | draft | SecNews 集成总览 (Phase 0-6 映射) |
| [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md) | draft | SecNews 集成任务清单 |
| [`docs/v0.6_workstation_plan.md`](v0.6_workstation_plan.md) | draft | Workstation 5 视图重构方案 |
