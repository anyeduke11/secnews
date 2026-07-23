# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 产品定位

hotspot 是面向 **AI + 安全从业者** 的单人本地工作站。安全与 AI 是双核心领域——安全数据源最广（17 源）、knowledge 库中安全 + AI 内容合计占 65%、CodeGarden 定位即「AI 协作全生命周期管理」；金融/创业/招标/科技/GitHub 为辅助领域。三大子系统（SecNews 热点聚合 / Knowledge 知识闭环 / CodeGarden 项目管理）均围绕这一人群设计。AI 安全交叉内容（OWASP LLM Top 10、对抗 ML、prompt injection、AI 红队）是区别于纯安全或纯 AI 产品的差异化方向。

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

### Three Subsystems

| Subsystem | Path | Purpose |
|-----------|------|---------|
| **SecNews** | `backend/` | Multi-domain news aggregation (7 domains, 30+ sources) |
| **Knowledge LLM-Wiki** | `knowledge/` | File-based knowledge base w/ concepts, learning plans, SOUL profile |
| **CodeGarden** | `codegarden/` + `backend/api/codegarden*.py` | Personal code project lifecycle management |

### Backend (FastAPI, no async DB)

```
backend/
├── api/            # REST routers (23 routers, ~50 lines each)
│   ├── __init__.py # register_routers() aggregates all (lazy imports)
│   ├── codegarden.py, codegarden_phase2b.py  # Phase 1 + Phase 2b endpoints
│   ├── events.py        # SSE 实时推送 (Phase 6)
│   ├── knowledge.py, maintenance.py, security.py  # Security Knowledge Graph
│   └── ...
├── collectors/     # 8 collectors extending BaseCollector + support modules
│   ├── base.py     # BaseCollector(ABC) — 已提取 parsing/keywords 模块
│   ├── parsing.py, keywords.py  # 从 base.py 提取的解析/关键词模块
│   ├── ai_security_collector.py  # AI 安全分类 (Phase 2)
│   ├── security_collector.py, github_collector.py, tech_collector.py, ai_collector.py, finance_collector.py, startup_collector.py, bid_collector.py
│   └── sogou_search.py, bid_search.py, bid_status.py, aggregator.py  # support, not BaseCollector
├── parsers/        # 独立解析器 (Phase 1)
│   ├── __init__.py # parser 注册表 + get_parser()
│   ├── base_parser.py  # BaseSourceParser(ABC) + RawItem
│   ├── aihot_parser.py, jin10_parser.py, clsd_parser.py  # 具体解析器
├── domain/         # Pydantic models (HotspotItem, KnowledgeItem, etc.)
│   └── security_models.py  # SecurityEntity / SecurityEdge / SecurityTerm
├── quality/        # 13 quality gates (flat layout, pipeline architecture)
│   ├── base.py     # GateContext + BaseGate(ABC)
│   ├── pipeline.py # QualityGatePipeline
│   ├── scorer.py, config.py, jobs.py, publisher_registry.py, source_coverage.py
│   └── *_gate.py   # author_verification, bid_recency, category_match, content_quality, duplicate, final_url, noise_content, recency, schema, source_reputation, title_summary, url_content, url_validity
├── repository/     # SQLite DAO layer (20 repos, one per table)
│   ├── db.py       # init_db, get_connection (thread-local, autocommit)
│   ├── migrations/ # 23 SQL migration files (001-023)
│   ├── security_repo.py  # Security Knowledge Graph + Terminology
│   └── knowledge_repo.py
├── scheduler/      # APScheduler jobs (sync, collection, trends, security)
├── security/       # Security Knowledge Graph (Phase 1-5)
│   ├── mitre_attack.py  # MITRE ATT&CK STIX 同步
│   ├── graph.py         # SecurityGraphEngine
│   ├── enricher.py      # CVE/ATT&CK/合规提取
│   └── compliance.py    # 合规种子数据
├── services/       # Business logic (41 files)
│   ├── sync_service.py     # Orchestration (was 1266, now 371 lines)
│   ├── sync_merge.py       # 3-way merge engine (extracted)
│   ├── sync_bundle.py      # Build/encrypt/decrypt bundles (extracted)
│   ├── auto_classifier.py      # Tag→domain classification
│   ├── concept_linker.py       # Tag→concept mapping
│   ├── soul_service.py         # SOUL profile generation
│   ├── maintenance_service.py  # DB vacuum/cleanup
│   ├── terminology_service.py  # Security term normalization (Phase 4)
│   ├── security_graph_service.py  # Security graph orchestration (Phase 3)
│   └── codegarden_*.py        # Phase 2b: scanner, project, service, resource, orchestration, github, knowledge_bridge
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
├── components/     # ~60 React components
│   ├── Icon.tsx    # Shared SVG icon component
│   ├── SyncPage.tsx, SecretsPage.tsx  # Largest (~800 lines, needs splitting)
│   ├── RegionFilter.tsx  # 标讯地区筛选 (Phase 8)
│   ├── security/     # Security Knowledge Graph (Phase 5)
│   │   ├── SecurityGraph.tsx, SecurityTimeline.tsx
│   │   ├── SecurityEntityDetail.tsx, ComplianceMatrix.tsx
│   │   └── TermStandardizer.tsx
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

### Knowledge Base (file system, no DB)

```
knowledge/
├── items/          # L1: Individual knowledge entries (~405 .md files)
├── concepts/       # L2: Extracted concepts (~35 .md files + graph.json)
├── learning/       # L3: Learning plans + tasks
│   └── tasks/      # Pending/processing/done/failed task files
├── content/        # L4: Content calendar + drafts
├── summaries/      # Generated summaries
├── SOUL.md         # Role profile (auto-generated from stats)
├── _MAP.md         # Auto-generated index map
└── _SCHEMA.md      # Frontmatter schema reference
```

Frontmatter-driven `.md` files. Sync to SQLite via `knowledge_sync.py`:
- `sync_item_to_db()` / `sync_concept_to_db()` — parse YAML frontmatter → SQLite
- `write_item_to_md()` — write SQLite → .md file
- Watchdog (`knowledge_watcher.py`) detects file changes, debounces, syncs

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

Backed by `backend/api/codegarden.py` (Phase 1) and `backend/api/codegarden_phase2b.py` (Phase 2b: services, resources, dependencies, events, playbooks). Business logic in `backend/services/codegarden_*.py`. DB tables come from migrations `019_codegarden.sql` and `021_codegarden_phase2b.sql`. See `docs/CodeGarden_PRD_v2.0.md` for the Phase 2b spec.

### Sync System (cross-device config)

The sync module was split into 3 files for testability:

```
sync_service.py  →  Orchestration: push/pull/bidirectional (371 lines)
sync_merge.py    →  3-way merge engine: MergeResult, three_way_merge() (246 lines)
sync_bundle.py   →  Serialization: build_bundle, encrypt/decrypt (400 lines)
```

- **3-way merge**: base/local/remote, record-level alignment, field-level last-write-wins
- **Encryption**: Fernet via master_key-derived key, envelope format
- **Transport**: WebDAV (坚果云), zip container format

### Testing

- **Backend**: 67 test files, pytest with `tmp_path` + `monkeypatch` for DB isolation
- **Frontend**: Vitest + jsdom, tests colocated with components (e.g. `codegarden/ProjectList.test.tsx`, `codegarden/ProjectCard.test.tsx`)
- **New tests (no DB)**: `test_sync_merge.py`, `test_auto_classifier.py`, `test_knowledge_watcher.py` — pure function tests, fastest to run
- **CI**: `.github/workflows/ci.yml` — Python compile + pytest + tsc + vitest + vite build

### Key Design Decisions

- **Single-user**: no multi-user auth, no Redis/PostgreSQL/Celery/Docker
- **SQLite WAL mode**: single worker (WORKERS=1) to avoid lock contention
- **Proxy required**: `backend/proxy_config.json` (in `.gitignore`, must self-configure on first install) needed for security/github collectors — see README for the minimal config
- **Master key**: PBKDF2-derived Fernet key for secrets encryption + sync bundle encryption
- **Knowledge system**: file-first, SQLite is read cache; .md files are source of truth

## Docs & Tooling Notes

- `docs/` holds the design corpus: `ARCHITECTURE.md` (v3.0 optimization plan), `RUNBOOK.md`, `ADMIN_MANUAL.md`, `ACCEPTANCE.md`, `quality_gates.md`, `CodeGarden_PRD_v2.0.md`, `secnews-knowledge-design.md`, `DESIGN_GUIDE.md`. Consult these for subsystem rationale before large changes.
- `README.md` — quick start, data-source table, proxy config walkthrough.
- **Gortex (Cursor-only)**: `.cursor/rules/`, `.github/copilot-instructions.md`, `docs/AGENTS.md`, and `docs/CLAUDE.md` contain auto-generated Gortex code-intelligence blocks (the `/gortex-*` skill tables and "prefer graph tools" workflow). These are managed by the Gortex MCP server for Cursor — not hand-authored instructions. In Claude Code the Gortex MCP is not wired, so ignore those skill listings and use the standard search tools.
