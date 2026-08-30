# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 产品定位

hotspot 是面向 **AI + 安全从业者** 的单机本地工作站（v0.6.3）。知识域以 `llm-wiki-2.0/` md 文件为唯一真相源（wiki-first 哲学），SQLite 仅做投影索引；AI 调用经 `backend/services/ai_hub/` 包单出口；SecNews 为**统一工作台**（`/secnews` 6 tab，v0.6.3 起 workbench 已并入）；dsh 认知大脑为受管子进程（前端 `/secnews/settings` 一键启停），pi 执行 agent 经 `/api/agents/*`；CRM 业绩座舱于 v0.6 完成。架构数字由 `scripts/generate_meta.py` AST 反推维护（当前 47 jobs / 14 collectors / 65 routers / 96 services）。详细机制见 `docs/ARCHITECTURE.md`，跑测试与生成迁移见 `backend/requirements*.txt` 与 `backend/repository/migrations/`。历史设计见 `docs/archived/`。

## Commands

```bash
# Backend
python run.py                          # 启动后端 (uvicorn, 默认 0.0.0.0:8000)
cd backend && pip install -r requirements.txt  # 安装依赖

# Frontend
cd frontend && npm install && npm run dev  # 启动前端 (默认 http://localhost:8898)
cd frontend && npm run build                # 生产构建 (tsc + vite build)

# Tests (backend)
.venv/bin/python3 -m pytest backend/tests/test_sync_merge.py -v  # 单个文件
.venv/bin/python3 -m pytest backend/tests/ -k "merge"            # 按关键字筛选
.venv/bin/python3 -m pytest backend/tests/test_auto_classifier.py -v  # 新测试(无DB依赖)

# Tests (frontend)
cd frontend && npx vitest run             # 全部前端测试
cd frontend && npx vitest run --watch     # watch 模式
cd frontend && npx tsc --noEmit           # 类型检查

# Compile check (backend)
.venv/bin/python3 -m py_compile backend/services/sync_merge.py

# Knowledge system
.venv/bin/python3 -c "from backend.services.auto_classifier import batch_classify; print('OK')"
```

## Architecture

### Five Subsystems (v0.6.3)

| # | Subsystem | 入口 | 说明 |
|---|-----------|------|------|
| 01 | **SecNews 热点聚合** | `/` | 14 采集器 · 11+ 质量门禁 · 趋势/搜索/导出 |
| 02 | **Knowledge LLM-Wiki** | `/knowledge` | `llm-wiki-2.0/` md 真源 · kl_pipeline 五阶段 · FTS5 |
| 03 | **CodeGarden** | `/codegarden` | 项目生命周期 + 服务网格 + 资源中枢 + 联动引擎 |
| 04 | **Security Graph** | `/knowledge/process` | MITRE ATT&CK · NVD CVE · 等保 / 关基 / 数安法 |
| 05 | **SecNews 统一工作台 (v0.6.3)** | `/secnews` | 6 tab: Feed / Pipeline / Knowledge / Analyze / Analytics / Settings |

### Backend (FastAPI, no async DB)

```
backend/
├── api/            # REST routers (65 include_router @ v0.6.3, 14 个按 feature_gates 条件注册)
│   ├── __init__.py # register_routers() aggregates all (lazy imports)
│   ├── codegarden.py, codegarden_ops.py  # 项目管理 + 运维层 (服务/资源/事件) endpoints
│   ├── knowledge_chunks_api.py  # v0.3.0 Phase 17: 知识库 chunk 级 API + FTS5
│   ├── attention_events_api.py  # v0.3.0 Phase 17: 注意力事件追踪
│   ├── events.py        # SSE 实时推送 (Phase 6)
│   ├── knowledge.py, maintenance.py, security.py  # Security Knowledge Graph
│   └── ...
├── collectors/     # 14 collectors extending BaseCollector + support modules
│   ├── base.py     # BaseCollector(ABC) — 已提取 parsing/keywords 模块
│   ├── parsing.py, keywords.py  # 从 base.py 提取的解析/关键词模块
│   ├── ai_security_collector.py  # AI 安全分类 (Phase 2)
│   ├── security_collector.py, github_collector.py, tech_collector.py, ai_collector.py, finance_collector.py, startup_collector.py, bid_collector.py
│   ├── hn_collector.py, reddit_collector.py, gdelt_collector.py, openbb_collector.py  # v0.3.0 Phase 11-12
│   ├── telegram_collector.py, ossinsight_collector.py  # v0.3.0 Phase 13 (延迟, 反爬时返回空)
│   └── sogou_search.py, bid_search.py, bid_status.py, aggregator.py  # support, not BaseCollector
├── parsers/        # 独立解析器 (Phase 1)
│   ├── __init__.py # parser 注册表 + get_parser()
│   ├── base_parser.py  # BaseSourceParser(ABC) + RawItem
│   ├── aihot_parser.py, jin10_parser.py, clsd_parser.py  # 具体解析器
├── domain/         # Pydantic models (HotspotItem, KnowledgeItem, etc.)
│   └── security_models.py  # SecurityEntity / SecurityEdge / SecurityTerm
├── quality/        # 11+ quality gates (flat layout, pipeline architecture) — 13 道已并入 Pipeline v0.6 收缩
│   ├── base.py     # GateContext + BaseGate(ABC)
│   ├── pipeline.py # QualityGatePipeline
│   ├── scorer.py, config.py, jobs.py, publisher_registry.py, source_coverage.py
│   └── *_gate.py   # author_verification, bid_recency, category_match, content_quality, duplicate, final_url, noise_content, recency, schema, source_reputation, title_summary, url_content, url_validity
├── repository/     # SQLite DAO layer (40 repos @ v0.6.3, one per table)
│   ├── db.py       # init_db, get_connection (thread-local, autocommit)
│   ├── migrations/ # 77 SQL migration files (001-077) — 含 v0.6 llm_secrets.provider / deep_reads / attack_data / compliance
│   ├── security_repo.py  # Security Knowledge Graph + Terminology
│   └── knowledge_repo.py
├── scheduler/      # APScheduler jobs (sync, collection, trends, security)
├── security/       # Security Knowledge Graph (Phase 1-5)
│   ├── mitre_attack.py  # MITRE ATT&CK STIX 同步
│   ├── graph.py         # SecurityGraphEngine
│   ├── enricher.py      # CVE/ATT&CK/合规提取
│   └── compliance.py    # 合规种子数据
├── services/       # Business logic (96 services @ v0.6.3, 含 ai_hub/ 包、kl_pipeline/wiki_fs/dsh/llm/model_router/process_supervisor/agent_bridge 等)
│   ├── sync_service.py     # Orchestration (921 lines)
│   ├── sync_merge.py       # 3-way merge engine (extracted)
│   ├── sync_bundle.py      # Build/encrypt/decrypt bundles (extracted)
│   ├── auto_classifier.py      # Tag→domain classification
│   ├── concept_linker.py       # Tag→concept mapping
│   ├── soul_service.py         # SOUL profile generation
│   ├── maintenance_service.py  # DB vacuum/cleanup
│   ├── terminology_service.py  # Security term normalization (Phase 4)
│   ├── security_graph_service.py  # Security graph orchestration (Phase 3)
│   ├── codegarden_*.py        # Phase 2b: scanner, project, service, resource, orchestration, github, knowledge_bridge
│   ├── attention_scorer.py    # v0.3.0 Phase 17: 5 维度注意力评分
│   ├── planning_service.py    # v0.3.0 Phase 13: 规划动作
├── crypto.py       # Fernet encryption, master key derivation
├── config.py       # Pydantic Settings (env prefix HOTSPOT_)
└── main.py         # FastAPI app entry, CORS, middleware
```

Key patterns:
- **SQLite** thread-local connections via `repository/db.py` — one connection per thread, autocommit mode
- **No async DB** — all DB calls are synchronous, only HTTP calls are async
- **Lazy imports** in `api/__init__.py` to avoid circular dependency at module load
- **Singleton repos** — each repository module exports a singleton instance

### Frontend (React + Vite + TypeScript)

```
frontend/src/
├── components/     # ~290 React components @ v0.6.3 — secnews/ 统一工作台 (v0.6.3 起 workbench 已并入) + crm/ 为 v0.6 新增
│   ├── Icon.tsx    # Shared SVG icon component
│   ├── SyncPage.tsx, SecretsPage.tsx  # Largest (~800 lines, needs splitting)
│   ├── ReportPage.tsx  # v0.3.0: 日报/周报/月报 (AIHot 风格)
│   ├── RegionFilter.tsx  # 标讯地区筛选 (Phase 8)
│   ├── security/     # Security Knowledge Graph (Phase 5)
│   │   ├── SecurityGraph.tsx, SecurityTimeline.tsx
│   │   ├── SecurityEntityDetail.tsx, ComplianceMatrix.tsx
│   │   └── TermStandardizer.tsx
│   ├── knowledge/    # 知识库组件
│   │   ├── KnowledgeTabs.tsx, DeepReadMode.tsx, ReviewMode.tsx, AttentionHeatmap.tsx
│   │   ├── InboxScanner.tsx, WikiBrowser.tsx, WikiItemBrowser.tsx  # v0.6 SecNews 知识库 tab
│   │   └── KnowledgeCompoundingDashboard.tsx, LifecycleProgress.tsx, KnowledgePlanningPanel.tsx  # v0.3.0
│   └── codegarden/ # Phase 2b: ProjectBoard, ProjectDetail, ServiceMesh, DependencyGraph, EventBus, PlaybookList, ResourceHub, ...
├── hooks/          # Custom hooks (useHotspotData, useTodos, useSync, useSSE, useSecurityGraph, etc.)
├── types/          # Shared types, helpers, CATEGORIES table
│   ├── index.ts    # ~500 lines — types, constants, utility functions
│   └── index.test.ts
├── test/           # Vitest setup
└── App.tsx         # Router + layout
```

Key patterns:
- **No routing library** — uses `react-router-dom` v6 `Routes`/`Route`
- **Shared Icon** — `Icon.tsx` used across all components (was 11 duplicated definitions)
- **Dark/light theme** — via `ThemeContext` in `App.tsx`
- **Charts** — `echarts-for-react` + `recharts` for visualizations
- **Vitest + jsdom** — frontend testing

### Knowledge Base (wiki-first: llm-wiki-2.0/ md 真源, SQLite 投影索引)

```
llm-wiki-2.0/
├── items/          # L1: Individual knowledge entries (~4149 .md files)
├── concepts/       # L2: Extracted concepts (~96 .md files + graph.json)
├── digest/         # 每日简报归档
├── sources/        # 原文来源留存
├── schema/         # frontmatter schema
├── SOUL.md         # Role profile (auto-generated from stats)
├── _MAP.md         # Auto-generated index map
└── _SCHEMA.md      # Frontmatter schema reference
```

- 单根解析: `backend/wiki_fs/root.py::resolve_wiki_root()` (env `HOTSPOT_WIKI_ROOT` 可覆盖); 旧 `knowledge/` 根 v0.5 P1 起不再读写
- kl_pipeline 五阶段 (raw → refine → link → structure → publish) 读写 frontmatter; `lifecycle` 字段为契约 (历史 `kl_stage` 兼容读)
- `wiki_events` 表为 md 世界与 SQLite 世界唯一事件桥梁

### CodeGarden (personal project lifecycle)

```
codegarden/
├── exports/   # Phase 2b export artifacts (scaffolded)
├── memory/    # Project-scoped memory (scaffolded)
├── playbooks/ # Playbook definitions (scaffolded)
├── prompts/   # Prompt templates (scaffolded)
├── sdds/      # Software design docs (scaffolded)
└── specs/     # Project specs (scaffolded)
```

Backed by `backend/api/codegarden.py` (项目管理) and `backend/api/codegarden_ops.py` (运维层: services, resources, dependencies, events, playbooks; 原 codegarden_phase2b.py). Business logic in `backend/services/codegarden_*.py`. DB tables come from migrations `019_codegarden.sql` and `021_codegarden_phase2b.sql`. See `docs/CodeGarden_PRD_v0.3.0.md` for the Phase 2b spec.

### Sync System (cross-device config)

The sync module was split into 3 files for testability:

```
sync_service.py  →  Orchestration: push/pull/bidirectional (921 lines)
sync_merge.py    →  3-way merge engine: MergeResult, three_way_merge() (437 lines)
sync_bundle.py   →  Serialization: build_bundle, encrypt/decrypt (853 lines)
```

- **3-way merge**: base/local/remote, record-level alignment, field-level last-write-wins
- **Encryption**: Fernet via master_key-derived key, envelope format
- **Transport**: WebDAV (坚果云), zip container format

### Testing

- **Backend**: 3025 tests @ v0.6.3, pytest with `tmp_path` + `monkeypatch` for DB isolation
- **Frontend**: Vitest + jsdom, 309 tests, tests colocated with components, 0 失败为新常态
- **New tests (no DB)**: `test_sync_merge.py`, `test_auto_classifier.py`, `test_knowledge_watcher.py`, `test_kl_pipeline.py`, `test_secnews_dashboard.py` — pure function tests, fastest to run
- **CI**: `.github/workflows/ci.yml` — Python compile + pytest + tsc + vitest + vite build + `generate_meta.py --check` + `harness_analyze.py --check`

### Key Design Decisions

- **Single-user**: no multi-user auth, no Redis/PostgreSQL/Celery/Docker
- **SQLite WAL mode**: single worker (WORKERS=1) to avoid lock contention
- **Proxy required**: `backend/proxy_config.json` (in `.gitignore`, must self-configure on first install) needed for security/github collectors — see README for the minimal config
- **Master key**: PBKDF2-derived Fernet key for secrets encryption + sync bundle encryption
- **Knowledge system**: file-first, SQLite is read cache; .md files are source of truth
- **Attention scoring**: 5-dimensional weighted (view_count/dwell_time/scroll_depth/is_favorited/annotation_count), 0-100 scale, aggregated via 1800s interval job with 30-day window + auto-cleanup
- **Chunk storage**: paragraph-level segmentation with FTS5 full-text search, char_start/end for原文跳转
- **Knowledge 域模式**: Review (SM-2 复习) + DeepRead (重分析 4 节报告, S4-2) 两条主路径; Briefing/Scan/Alert/Outbox 4 模式 v0.7.0 已删除 (简报能力在 /secnews feed 简报卡, v0.6.3 起 workbench 也已并入 /secnews 统一工作台)

## Docs & Tooling Notes

- `docs/` holds the design corpus: `ARCHITECTURE.md` (v3.0 optimization plan), `RUNBOOK.md`, `ADMIN_MANUAL.md`, `ACCEPTANCE.md`, `quality_gates.md`, `CodeGarden_PRD_v0.3.0.md`, `secnews-knowledge-design.md`, `DESIGN_GUIDE.md`. Consult these for subsystem rationale before large changes. Phase 17 spec at `.trae/specs/phase17-chunks-attention/`.
- `README.md` — quick start, data-source table, proxy config walkthrough.
- **Gortex (Cursor-only)**: `.cursor/rules/`, `.github/copilot-instructions.md`, `docs/AGENTS.md`, and `docs/CLAUDE.md` contain auto-generated Gortex code-intelligence blocks (the `/gortex-*` skill tables and "prefer graph tools" workflow). These are managed by the Gortex MCP server for Cursor — not hand-authored instructions. In Claude Code the Gortex MCP is not wired, so ignore those skill listings and use the standard search tools.
