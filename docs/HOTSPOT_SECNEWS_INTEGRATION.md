---
status: draft
target_version: v0.6
phase: SecNews Integration
related_code: backend/kl_pipeline/;backend/services/ai_hub.py;backend/collectors/secnews/;frontend/src/components/secnews/
depends_on: docs/v0.5_refactor_plan.md;docs/audit_first_principles_plan.md
owner: integration
last_reviewed: 2026-08-24
---

# Hotspot × dsh-SecNews 整合方案
## 让 Hotspot 成为网络安全从业者的 AI 工作台

> 版本 v1.0 ｜ 2026-08-24
> 基线: Hotspot v1.7 / dsh-SecNews v5 (P2 完成)

---

## 0. 整合目标与约束

### 0.1 一句话目标

将 dsh-SecNews 的"安全资讯聚合 + 知识管线引擎 + 报纸风看板"整合进 Hotspot，
让 Hotspot 从"AI + 安全从业者工作站"升级为**网络安全从业者的完整 AI 工作台**，
覆盖：**信息采集 → 知识沉淀 → AI 研判 → 执行输出** 全生命周期。

### 0.2 两条铁律（继承双方 AGENTS.md）

| # | 铁律 | 来源 |
|---|------|------|
| T1 | 禁止以任何形式引用、调用、反代、读取旧 `../hotspot` 独立服务 | dsh-SecNews AGENTS.md |
| T2 | 不删除已有信息；列表排序必须用 `ingested_at DESC`；敏感字段 Fernet 加密 | Hotspot AGENTS.md |

### 0.3 技术栈统一决策

| 层面 | 现状 | 整合后 |
|------|------|--------|
| 后端运行时 | Hotspot: Python 3.11+ / dsh: Node 26 | **Hotspot Python 统一后端** |
| 前端运行时 | Hotspot: React 18 / Vite 5 / TS / Tailwind 3 | **统一技术栈，不做混合微前端** |
| 数据库 | Hotspot: SQLite (WAL) / dsh: SQLite (WAL+FTS5) | **SQLite 统一（Hotspot 主库 + FTS5 扩展）** |
| 知识文件 | Hotspot: `knowledge/` llm-wiki-2.0 / dsh: `data/wiki/` | **Hotspot `knowledge/` 为唯一真相源** |
| AI 能力 | Hotspot: 直连 LLM / dsh: `/api/cap` 分层路由 | **Hotspot `llm_status` + `secrets` 统一路由** |
| 前端构建 | Hotspot: Vite / dsh: 原生 ESM（无构建） | **统一走 Vite 构建管道** |

> **核心理由**：两个独立进程维护成本过高，dsh-SecNews 的核心能力（wiki 管线引擎、报纸看板、CVE 抽取）都可以在 Hotspot 的 Python 后端中重建或直接移植；前端统一在一个 React 应用中，避免跨 iframe/端口通信的复杂性。

---

## 1. 现状对照分析

### 1.1 dsh-SecNews 独有的价值资产（需整合进 Hotspot）

| 资产 | 说明 | 整合优先级 |
|------|------|-----------|
| **KL 管线引擎** | `kl:raw → kl:refine → kl:link → kl:structure → kl:publish` 五阶段状态机 + kl_queue 队列 | **P0** |
| **wiki 文件系统** | `fsstore.ts` 读写契约 frontmatter + 块序列解析 + 迁移工具 | **P0** |
| **Pipeline 观测台** | 漏斗五阶段横条、队列卡片、死信表、token 台账 | **P1** |
| **书签导入** | Netscape HTML 解析、存活三态检测（HEAD+重定向）、每周日批扫 | **P1** |
| **inbox 扫描** | 文件投递区（处理后移入 items/ 或 quarantine/） | **P1** |
| **模型分层路由** | script/flash/big/embed 四档 + 每档独立 agent 配置 | **P2** |
| **报纸风看板 UI** | `web/dashboard/` 原生 ESM 看板（feed/pipeline/knowledge/settings） | **P1**（风格参考，用 React 重写） |
| **CVE/ATT&CK/合规正则** | `enrich.ts` 纯正则抽取（T\d{4}、CVE-YYYY-NNNN、等保/关基） | **P0**（已有 enrich，需增强） |
| **质量门禁** | 8 道 Gate（category-relevance、content-length、recency、simhash、source-trust、title-quality、url-duplicate、url-valid） | **P1**（与 Hotspot 13 道合并） |
| **概念链接器** | `concept-linker.ts` FTS 共现 + 概念 slug 匹配生成 `related` 权重边 | **P0** |
| **token 台账** | `token-ledger.ts` 按任务记录 in/out tokens，SSE 可得 usage | **P1** |
| **Cubox 只读挂载** | 本地 Cubox 导出目录浏览视图 | **P2** |

### 1.2 Hotspot 已有的能力（dsh-SecNews 可受益）

| 能力 | 说明 |
|------|------|
| 三层架构路由 | `/data` → `/judge` → `/action` 统一导航 |
| 质量门禁 13 道 Gate | 已有更完整的 Pipeline |
| MCP Server | SSE 端点 + tool registry |
| CodeGarden Phase 2b | 服务网格 + 资源中枢 + 联动引擎 |
| Fernet 加密 | 敏感字段（密钥、凭据）统一加密 |
| 跨端同步 | WebDAV 配置同步 |
| 前端设计系统 | LayerCard / LayerTable / LayerBadge / CSS 变量 |
| 14 采集器 | 比 dsh 的 5 源更丰富 |
| Feature Gates | codegarden/mcp/sync/tech_stack/security_graph 开关 |
| 统一搜索 | `/api/search` 跨层搜索 |
| 报告系统 | 日报/周报/月报 + 简报 |

---

## 2. 整合架构设计

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hotspot 统一入口 (React + Vite)              │
│                    前端端口: 8898 (不变)                         │
├─────────────────────────────────────────────────────────────────┤
│  LayerNav: [资料层] [判断层] [行动层] │ [安全看板] │ [设置]       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  资料层      │  │  判断层      │  │  行动层                  │ │
│  │  /data/*     │  │  /judge/*    │  │  /action/*               │ │
│  │             │  │             │  │                         │ │
│  │ HotspotGrid │  │ QualityGate │  │ TodosPage               │ │
│  │ (30+ 源)    │  │ TrendChart  │  │ ReportPage               │ │
│  │ DataImport  │  │ SecNewsKPI  │  │ Codegarden               │ │
│  │ (URL/书签)  │  │ Pipeline    │  │ BidAlert                 │ │
│  │ Favorites   │  │ CVE 热力图  │  │ KnowledgeCompound        │ │
│  │ History     │  │ ATT&CK 图谱 │  │ SkillsPage               │ │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────────┘ │
│         │                │                                      │
│         ▼                ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             安全看板 (新增顶层 Tab)                        │   │
│  │  /secnews/*                                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ Feed 视图 │ │ Pipeline │ │Knowledge │ │ Settings │   │   │
│  │  │ (报纸风)  │ │ 观测台   │ │ 浏览    │ │          │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    FastAPI 统一后端 (Python)                    │
│                    后端端口: 8000 (不变)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  hotspots.py │  │  security.py│  │  kl_pipeline.py (新增)  │ │
│  │  (30+ 采集器)│  │ (MITRE/CVE) │  │  管线引擎 + kl_queue    │ │
│  ├─────────────┤  ├─────────────┤  ├─────────────────────────┤ │
│  │  quality.py  │  │  trends.py  │  │  wiki_fs.py (新增)     │ │
│  │  13 道 Gate  │  │ 趋势分析    │  │  wiki 文件读写/迁移     │ │
│  ├─────────────┤  ├─────────────┤  ├─────────────────────────┤ │
│  │  bid_alert.py│  │  reports.py │  │  enrich_v2.py (增强)   │ │
│  │ 标讯/投标提醒│  │ 报告生成    │  │  CVE/ATT&CK/合规正则    │ │
│  ├─────────────┤  ├─────────────┤  ├─────────────────────────┤ │
│  │  codegarden  │  │  mcp.py     │  │  token_ledger.py (新增)│ │
│  │ 服务网格     │  │ MCP Server  │  │  token 台账             │ │
│  ├─────────────┤  ├─────────────┤  ├─────────────────────────┤ │
│  │  collectors/ │  │  scheduler/ │  │  secnews_dashboard.py   │ │
│  │  14 采集器   │  │  30 任务    │  │  (新增) 看板数据聚合    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
│  SQLite (WAL + FTS5): hotspots / knowledge / kl_queue / wiki  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
外部源 (RSS/URL/书签/Cubox)
        │
        ▼
  collectors/ (14 采集器)
        │
        ▼
  quality/ (13 道 Gate → hotspots 表)
        │
        ▼
  ┌────────────────────────────────────┐
  │  kl_pipeline.py (五阶段引擎)       │
  │  kl:raw → kl:refine → kl:link →   │
  │  kl:structure → kl:publish         │
  │  (wiki 文件 ← 文件真相源)         │
  └────────────┬───────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
  knowledge/       SQLite 索引
  items/*.md       kl_queue / FTS5
  concepts/*.md    token_ledger
  graph.json       reviews
       │               │
       └───────┬───────┘
               ▼
       前端三层展示
       (/data / judge / action / secnews)
```

---

## 3. 分阶段实施计划

### Phase 0: 基础层整合（W0-W2）

> 目标：在 Hotspot 后端建立 KL 管线引擎 + wiki 文件系统的 Python 实现，前端新增"安全看板"顶层入口

#### 0.1 后端新增模块

```
backend/
├── kl_pipeline/
│   ├── __init__.py
│   ├── engine.py          # KL 管线引擎（kl:raw → publish 五阶段）
│   ├── queue.py           # kl_queue 表 + 到期任务消费 + 退避重试
│   ├── stages/
│   │   ├── refine.py      # 轻 AI refine（flash 档，topic/type/tags）
│   │   ├── link.py        # FTS 共现 + concept slug 匹配 → related 边
│   │   └── structure.py   # 概念卡提取 + graph.json 更新
│   └── obs/
│       ├── funnel.py      # 五阶段漏斗统计
│       └── ledger.py      # token 台账（按任务记录 in/out）
│
├── wiki_fs/
│   ├── __init__.py
│   ├── contract.py        # frontmatter 契约子集（稳定序序列化）
│   ├── store.py           # items/ concepts/ inbox/ quarantine 读写
│   ├── migrate.py         # 从 llm-wiki-2.0 一次性迁移（4149 items）
│   └── linker.py          # concept-linker（FTS 共现 → 权重边）
│
├── enrich_v2.py           # 增强版 enrich（CVE/ATT&CK/合规/到期时间）
├── secnews_dashboard.py   # 看板数据聚合 API（feed/pipeline/knowledge/stats）
└── collectors/
    └── secnews/           # dsh-SecNews 采集器 Python 移植
        ├── rss.py         # RSS/Atom 正则解析（5 源起）
        ├── json_api.py    # JSON API 采集（THN/Bellingcat 等）
        └── orchestrator.py # 采集编排 + 错峰 cron
```

#### 0.2 后端 API 新增路由

```python
# backend/api/kl_pipeline_api.py
POST   /api/kl/import/url          # URL 导入（抓取 → kl:raw）
POST   /api/kl/import/bookmarks    # 书签 HTML 导入
POST   /api/kl/inbox/scan          # inbox 扫描入库
GET    /api/kl/pipeline/stats      # 漏斗 + 队列 + 死信 + token 台账
POST   /api/kl/pipeline/drain      # 手动消费到期任务
POST   /api/kl/pipeline/advance    # 单条推进到下一阶段
POST   /api/kl/pipeline/retry      # 死信重试
GET    /api/kl/items/{id}          # wiki 条目详情
PUT    /api/kl/items/{id}          # 更新 frontmatter（单向投影）
GET    /api/kl/concepts            # 概念卡列表
GET    /api/kl/graph               # 知识图谱边

# backend/api/secnews_dashboard_api.py
GET    /api/secnews/feed           # 报纸风 feed 数据
GET    /api/secnews/pipeline       # 管线面板数据
GET    /api/secnews/knowledge      # 知识浏览数据
GET    /api/secnews/stats          # 看板统计
```

#### 0.3 前端新增组件

```
frontend/src/components/secnews/
├── layout/
│   ├── SecNewsShell.tsx          # 看板壳组件（三层导航 + 子路由）
│   └── LayerBadge.tsx            # 复用现有 LayerBadge
├── feed/
│   ├── FeedView.tsx              # 报纸风 Feed 视图（主看板）
│   ├── FeedCard.tsx              # 单条卡片（标题/来源/时间/标签）
│   └── FeedFilters.tsx           # 分类/时间/关键词筛选
├── pipeline/
│   ├── PipelineView.tsx          # 管线观测台（五阶段漏斗 + 队列卡片）
│   ├── FunnelBar.tsx             # 五阶段横条（kl:raw → publish）
│   ├── QueueCard.tsx             # 到期任务卡片
│   ├── ErrorTable.tsx            # 死信表 + 一键重试
│   └── TokenLedger.tsx           # token 台账表
├── knowledge/
│   ├── WikiBrowser.tsx           # wiki 文件浏览（items + concepts）
│   ├── ConceptGraph.tsx          # 概念图谱可视化（复用 KnowledgeGraph）
│   └── InboxScanner.tsx          # inbox 扫描入口
└── settings/
    ├── CollectionSettings.tsx    # RSS 源管理 + 采集 cron 配置
    └── PipelineSettings.tsx      # 模型档位 + refine 配置
```

#### 0.4 前端路由扩展

```tsx
// routes/index.tsx 新增
<Route path="/secnews" element={<P.SecNewsShell />}>
  <Route index element={<Navigate to="feed" replace />} />
  <Route path="feed" element={<P.SecNewsFeed />} />
  <Route path="pipeline" element={<P.SecNewsPipeline />} />
  <Route path="knowledge" element={<P.SecNewsKnowledge />} />
</Route>
```

#### 0.5 数据库 Schema 新增

```sql
-- kl_queue: KL 管线任务队列
CREATE TABLE IF NOT EXISTS kl_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,          -- wiki item id
    stage TEXT NOT NULL,            -- kl:refine|kl:link|kl:structure|kl:publish
    status TEXT DEFAULT 'pending',  -- pending|run|done|error
    priority INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    next_run_at TEXT,               -- ISO datetime
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(item_id, stage)
);

-- token_ledger: token 消耗台账
CREATE TABLE IF NOT EXISTS token_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,                   -- 关联 kl_queue.id
    item_id TEXT,
    model TEXT,                     -- script/flash/big/embed
    provider TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- wiki_items: wiki 文件索引（FTS5 虚拟表）
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_items_fts USING fts5(
    title, summary, tags, content,
    content='items',
    content_rowid='rowid'
);
```

### Phase 1: 管线引擎与知识整合（W2-W4）

> 目标：KL 五阶段管线跑通，书签导入可用，Pipeline 观测台上线

#### 1.1 KL 管线引擎实现

```python
# backend/kl_pipeline/engine.py (核心状态机)

from enum import Enum
from datetime import datetime, timedelta

class Stage(Enum):
    RAW = "kl:raw"
    REFINE = "kl:refine"
    LINK = "kl:link"
    STRUCTURE = "kl:structure"
    PUBLISH = "kl:publish"
    DEAD = "dead"
    ERROR = "error"

STAGE_ORDER = [
    Stage.RAW, Stage.REFINE, Stage.LINK,
    Stage.STRUCTURE, Stage.PUBLISH
]

class KLPipeline:
    def __init__(self, wiki_fs, db_session, llm_client):
        self.fs = wiki_fs
        self.db = db_session
        self.llm = llm_client

    def kickoff(self, item_id: str) -> None:
        """新条目入库后调用：入队 kl:refine（45s 延迟）"""
        self.db.enqueue_unique(item_id, Stage.REFINE.value,
                               datetime.now() + timedelta(seconds=45))

    def drain_due(self, limit: int = 20) -> dict:
        """消费到期任务（串行，共享 flash agent）"""
        tasks = self.db.due_tasks(limit)
        results = {"done": 0, "failed": 0}
        for task in tasks:
            self.db.mark_run(task.id)
            try:
                self._run_stage(task.item_id, Stage(task.stage))
                self.db.mark_done(task.id)
                results["done"] += 1
            except Exception as e:
                self.db.mark_error(task.id, str(e))
                results["failed"] += 1
        return results

    def advance(self, item_id: str) -> str:
        """手动推进一条到下一阶段"""
        doc = self.fs.read_item(item_id)
        current = Stage(doc.fm.get("lifecycle", Stage.RAW.value))
        next_stage = self._next_stage(current)
        if next_stage:
            self._run_stage(item_id, next_stage)
            return next_stage.value
        return current.value

    def _run_stage(self, item_id: str, stage: Stage) -> None:
        """执行单个阶段动作"""
        doc = self.fs.read_item(item_id)
        if not doc:
            raise ValueError(f"Item not found: {item_id}")

        if stage == Stage.REFINE:
            self._refine(item_id, doc)
        elif stage == Stage.LINK:
            self._link(item_id, doc)
        elif stage == Stage.STRUCTURE:
            self._structure(item_id, doc)
        elif stage == Stage.PUBLISH:
            self._publish(item_id, doc)

        # 更新 frontmatter lifecycle
        doc.fm["lifecycle"] = stage.value
        self.fs.write_item(item_id, doc)
        # 投影到 SQLite
        self.db.update_lifecycle(item_id, stage.value)

    def _refine(self, item_id: str, doc: dict) -> None:
        """轻 AI refine：抽 topic / type / difficulty / tags"""
        prompt = REFINE_PROMPT(doc.fm["title"], doc.body[:1200])
        result = self.llm.call_flash(prompt)  # flash 档
        parsed = extract_json(result)
        doc.fm.update({
            "topic": parsed.get("topic", ""),
            "type": parsed.get("type", "news"),
            "difficulty": parsed.get("difficulty", "intermediate"),
            "tags": parsed.get("tags", []),
        })
        # token 台账
        self.db.record_token_usage(item_id, "flash", parsed.get("usage", {}))

    def _link(self, item_id: str, doc: dict) -> None:
        """FTS 共现 + concept slug 匹配 → 生成 related 权重边"""
        related = self.fs.find_related(item_id, top_k=10)
        doc.fm["related"] = [{"id": r.id, "weight": r.weight} for r in related]
        self.fs.update_graph(item_id, related)

    def _structure(self, item_id: str, doc: dict) -> None:
        """概念卡提取：从 tags 映射到 concepts/*.md"""
        for tag in doc.fm.get("tags", []):
            concept_id = slugify(tag)
            if not self.fs.concept_exists(concept_id):
                self.fs.create_concept(concept_id, tag)
            self.fs.link_concept(item_id, concept_id)

    def _publish(self, item_id: str, doc: dict) -> None:
        """终态：标记为已发布，加入复习队列"""
        doc.fm["published"] = True
        doc.fm["published_at"] = datetime.now().isoformat()
        # 加入 SM-2 复习队列
        self.db.schedule_review(item_id)
```

#### 1.2 wiki 文件系统 Python 移植

```python
# backend/wiki_fs/store.py (核心文件操作)

import frontmatter  # 已有依赖
import os
from pathlib import Path

class WikiFs:
    def __init__(self, root: str):
        self.root = Path(root)
        self.items_dir = self.root / "items"
        self.concepts_dir = self.root / "concepts"
        self.inbox_dir = self.root / "inbox"
        self.quarantine_dir = self.root / "quarantine"
        for d in [self.items_dir, self.concepts_dir, self.inbox_dir, self.quarantine_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> list[str]:
        """列出所有 item id（不含扩展名）"""
        return [f.stem for f in self.items_dir.glob("*.md")]

    def read_item(self, item_id: str) -> dict | None:
        """读取 item，返回 {fm, body}"""
        path = self.items_dir / f"{item_id}.md"
        if not path.exists():
            return None
        post = frontmatter.load(path)
        return {"fm": dict(post.metadata), "body": post.content}

    def write_item(self, item_id: str, doc: dict) -> None:
        """写入 item（稳定序序列化）"""
        path = self.items_dir / f"{item_id}.md"
        post = frontmatter.Post(doc["body"], **stable_serialize(doc["fm"]))
        path.write_text(frontmatter.dumps(post), encoding="utf-8")

    def ingest_url(self, url: str) -> dict:
        """URL 导入：抓取 → 粗抽 → 落盘 kl:raw"""
        html = fetch_url(url)
        text = extract_main_text(html)
        item_id = generate_id(url)
        doc = {
            "fm": {
                "title": extract_title(html, url),
                "source_url": url,
                "source": "secnews",
                "category": "security",
                "ingested_at": datetime.now().isoformat(),
                "lifecycle": "kl:raw",
            },
            "body": text,
        }
        self.write_item(item_id, doc)
        # 投影到 SQLite
        self.db.project_item(item_id, doc)
        # 入队 refine
        self.pipeline.kickoff(item_id)
        return {"id": item_id, "title": doc["fm"]["title"]}

    def import_bookmarks(self, html: str) -> dict:
        """Netscape 书签 HTML 批量导入"""
        bookmarks = parse_netscape_html(html)
        added = 0
        dup = 0
        for bm in bookmarks:
            if self.db.url_exists(bm.url):
                dup += 1
                continue
            item_id = generate_id(bm.url)
            doc = {
                "fm": {
                    "title": bm.title,
                    "source_url": bm.url,
                    "source": "bookmark",
                    "category": categorize(bm.url),
                    "ingested_at": datetime.now().isoformat(),
                    "lifecycle": "kl:raw",
                    "alive": "unknown",
                },
                "body": f"# {bm.title}\n\nURL: {bm.url}\n\nAdded: {bm.add_date}",
            }
            self.write_item(item_id, doc)
            self.db.project_item(item_id, doc)
            self.pipeline.kickoff(item_id)
            added += 1
        return {"added": added, "dup": dup}
```

#### 1.3 前端看板组件

```tsx
// frontend/src/components/secnews/feed/FeedView.tsx
// 报纸风 Feed 视图 — 继承 dsh dashboard 的阅读动线，用 Hotspot 设计系统重写

import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import { LayerCard } from '../../components/layout/LayerCard';
import { Icon } from '../../components/Icon';
import type { SecNewsItem } from '../../types/secnews';

export function FeedView() {
  const [items, setItems] = useState<SecNewsItem[]>([]);
  const [filter, setFilter] = useState({ category: '', keyword: '' });

  useEffect(() => {
    apiFetch<SecNewsResponse>(`/api/secnews/feed?${new URLSearchParams(filter)}`)
      .then(r => setItems(r.items));
  }, [filter]);

  return (
    <div className="max-w-[1320px] mx-auto px-4 sm:px-8 lg:px-10 py-6">
      {/* 报纸风格头版 */}
      <header className="mb-8 border-b border-[var(--border-color)] pb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              SecNews 安全早报
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
              {new Date().toLocaleDateString('zh-CN', {
                year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
              })}
            </p>
          </div>
          <button className="btn-primary" onClick={() => {/* 刷新 */}}>
            <Icon name="refresh" className="w-4 h-4 mr-1" />
            刷新
          </button>
        </div>
      </header>

      {/* 分类标签栏 */}
      <FeedFilters value={filter} onChange={setFilter} />

      {/* 主内容区：头条 + 列表 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 头条 (大卡片) */}
        {items[0] && (
          <div className="lg:col-span-2">
            <LeadStory item={items[0]} />
          </div>
        )}
        {/* 侧边速览 */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            快速浏览
          </h2>
          {items.slice(1, 8).map(item => (
            <FeedCard key={item.id} item={item} compact />
          ))}
        </div>
      </div>

      {/* 全量列表 */}
      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.slice(8).map(item => (
          <FeedCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
```

### Phase 2: Pipeline 观测台 + 质量增强（W4-W6）

> 目标：Pipeline 全链路可观测，质量门禁与 dsh 的 8 道 Gate 合并

#### 2.1 Pipeline 观测台上线

```
┌─────────────────────────────────────────────────────────────────┐
│  Pipeline 观测台 (/secnews/pipeline)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ 五阶段漏斗 ──────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │  kl:raw ━━━━━━━━━━━━━━ 4149  ████████████████████  67%    │  │
│  │  kl:refine ━━━━━━━━━━━ 1200  ████████░░░░░░░░░░░░  19%    │  │
│  │  kl:link ━━━━━━━━━━━━━  511  ████░░░░░░░░░░░░░░░░   8%    │  │
│  │  kl:structure ━━━━━━━━━   17  █░░░░░░░░░░░░░░░░░░░   0%   │  │
│  │  kl:publish ━━━━━━━━━━━   17  █░░░░░░░░░░░░░░░░░░░   0%   │  │
│  │                                                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ 队列状态 ────────────────────────────────────────────────┐  │
│  │  待处理: 23  │  运行中: 2  │  失败: 3  │  今日完成: 156    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ 队列卡片 ────────────────────────────────────────────────┐  │
│  │  [kl:refine] item-8a3f  "CVE-2026-1234 分析"  等待中      │  │
│  │  [kl:link]   item-2b1c  "零信任架构实践"    运行中...     │  │
│  │  [kl:refine] item-9d4e  "API 安全指南"      失败 (退避 10m)│  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ Token 台账 (近 7 天) ────────────────────────────────────┐  │
│  │  模型        │ 调用次数 │  Input Tokens │ Output Tokens     │  │
│  │  flash      │    234   │    89,100    │    45,200          │  │
│  │  big        │     12   │    45,600    │    78,900          │  │
│  │  embed      │    456   │     0        │     0              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ 死信队列 ────────────────────────────────────────────────┐  │
│  │  [重试全部]                                                  │  │
│  │  item-3f2a  kl:refine  "XSS 防护"  错误: timeout (3/5)    │  │
│  │  item-7c8b  kl:link    "WAF 部署"  错误: parse error (5/5)│  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.2 质量门禁合并

Hotspot 已有 13 道 Gate，dsh-SecNews 有 8 道 Gate。合并策略：

| Hotspot Gate | dsh Gate | 合并后 | 说明 |
|---|---|---|---|
| `RecencyGate` | `recency` | ✅ 统一 | 保留 Hotspot "本周一" 截止 |
| `TitleQualityGate` | `title-quality` | ✅ 统一 | 保留 dsh 的正则强度 |
| `SourceTrustGate` | `source-trust` | ✅ 统一 | 保留 Hotspot 源信任分 |
| `DuplicateGate` | `url-duplicate` | ✅ 统一 | 保留 dsh 的 URL 规范化 |
| `URLValidityGate` | `url-valid` | ✅ 统一 | 保留 Hotspot `/articles/\d+` 规则 |
| `CategoryRelevanceGate` | `category-relevance` | ✅ 统一 | 保留 dsh 关键词匹配 |
| `ContentLengthGate` | `content-length` | ✅ 合并 | 保留 Hotspot 更长正文要求 |
| `SimHashGate` | `simhash` | ✅ 保留 | Hotspot 独有的语义去重 |
| `AttentionGate` | — | ✅ 保留 | Hotspot 独有 |
| `BidStatusGate` | — | ✅ 保留 | Hotspot 独有 |
| `CVEEnrichGate` | — | ✅ 新增 | CVE 编号提取 |
| `ATT&CKEnrichGate` | — | ✅ 新增 | MITRE ATT&CK 技术标注 |
| `ComplianceGate` | — | ✅ 新增 | 等保/关基/数据安全法 匹配 |

### Phase 3: 前端统一与 UI 升级（W6-W8）

> 目标：安全看板 UI 就绪，三层架构 + 看板完整覆盖

#### 3.1 安全看板路由结构

```
/secnews
├── /feed          — 报纸风 Feed 视图（主看板）
│   ├── 头版头条（LeadStory 大卡片）
│   ├── 分类标签栏（security / cve / apt / compliance / tools）
│   ├── 快速浏览侧栏（8 条缩略）
│   └── 全量网格（3 列卡片）
├── /pipeline      — 管线观测台
│   ├── 五阶段漏斗
│   ├── 队列状态卡片
│   ├── 死信表 + 重试
│   └── token 台账
├── /knowledge     — 知识浏览
│   ├── wiki items 列表（含 lifecycle 标签）
│   ├── concepts 图谱
│   └── inbox 扫描入口
└── /settings
    ├── 采集源管理
    ├── 模型档位配置
    └── 管线参数
```

#### 3.2 UI 设计规范（安全看板子规范）

```
色板（安全看板专用，继承 hotspot DESIGN_SYSTEM）：
├── 主背景: var(--bg-primary) #0a0e14 (dark)
├── 卡片: var(--bg-elevated) #141921
├── 边框: var(--border-color) #2a3340
├── 文字: var(--text-primary) #e6edf3
├── 安全领域色（仅用于分类标签，不侵入 accent 体系）：
│   ├── CVE/漏洞: #ef4444 (red-500)
│   ├── APT/威胁: #f59e0b (amber-500)
│   ├── 合规: #10b981 (emerald-500)
│   ├── 工具: #3b82f6 (blue-500)
│   └── 分析: #8b5cf6 (violet-500)
└── 统一 accent: #3b82f6

报纸风排版规则：
├── 头版头条：大字号 (text-3xl) + 摘要 + 来源 + 时间
├── 正文卡片：标题 + 摘要截断 (2行) + 标签 + 元信息
├── 分类标签：LayerBadge soft 变体 + 安全领域色
├── 间距：紧凑 (gap-3) 以承载更多信息
└── 字体：正文 Inter / 标签 JetBrains Mono
```

#### 3.3 数据层页面扩展

在 Hotspot 的 `DataLayerPage` 中新增"安全看板"入口按钮：

```tsx
// frontend/src/components/data/DataLayerPage.tsx 新增卡片
<LayerCard variant="highlight" onClick={() => navigate('/secnews/feed')}>
  <div className="flex items-center gap-3">
    <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
      <Icon name="shield" className="w-5 h-5 text-red-400" />
    </div>
    <div>
      <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
        安全看板
      </h3>
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
        RSS 聚合 + 知识管线 + CVE 追踪
      </p>
    </div>
  </div>
</LayerCard>
```

### Phase 4: AI 研判与深度分析（W8-W10）

> 目标：重 AI 按钮就绪，DeepRead / Assess / Compare 功能上线

#### 4.1 AI 能力路由

```python
# backend/api/llm_status.py (已有) 扩展

class SecNewsLLMRouter:
    """安全看板专用的模型分层路由"""

    TIERS = {
        "embed": {"provider": "ollama", "model": "nomic-embed-text"},     # 本地向量
        "flash": {"provider": "sensenova", "model": "deepseek-v3.1-flash"},  # 轻 AI
        "big":   {"provider": "deepseek", "model": "deepseek-v3.2"},      # 重 AI
    }

    def route(self, task_type: str) -> dict:
        if task_type in ("embed", "rerank"):
            return self.TIERS["embed"]
        elif task_type in ("refine", "classify", "score"):
            return self.TIERS["flash"]
        else:  # deepread, assess, compare
            return self.TIERS["big"]
```

#### 4.2 深度分析面板

```tsx
// frontend/src/components/secnews/DeepReadPanel.tsx
export function DeepReadPanel({ itemId }: { itemId: string }) {
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);

  const runDeepRead = async () => {
    setLoading(true);
    const result = await apiFetch<AnalysisResult>(`/api/kl/items/${itemId}/deep-read`, {
      method: 'POST',
    });
    setAnalysis(result);
    setLoading(false);
  };

  return (
    <LayerCard>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">深度研判</h3>
        <button
          className="btn-primary"
          onClick={runDeepRead}
          disabled={loading}
        >
          {loading ? 'AI 分析中...' : '发起深度分析'}
        </button>
      </div>
      {analysis && (
        <div className="space-y-4">
          <Section title="漏洞概述" content={analysis.summary} />
          <Section title="ATT&CK 映射" content={analysis.attack_mapping} />
          <Section title="修复建议" content={analysis.remediation} />
          <Section title="参考链接" links={analysis.references} />
        </div>
      )}
    </LayerCard>
  );
}
```

### Phase 5: 知识复利与复习（W10-W12）

> 目标：SM-2 复习与 wiki pipeline 打通，到期复习卡自动出现

#### 5.1 复习调度集成

```python
# backend/kl_pipeline/stages/publish.py

def _publish(self, item_id: str, doc: dict) -> None:
    """终态：标记发布 + 安排 SM-2 复习"""
    doc.fm["published"] = True
    doc.fm["published_at"] = datetime.now().isoformat()

    # 写入复习间隔（SM-2 初始参数）
    self.db.schedule_review(
        item_id=item_id,
        interval_days=1,  # 首次复习 1 天后
        ease_factor=2.5,
        repetitions=0,
    )
```

#### 5.2 前端复习模式

复用现有 `ReviewMode` 组件，数据源从 `reviews` 表读取（已与 wiki items 关联）。

### Phase 6: 存量迁移与清理（W12-W13）

> 目标：将 dsh-SecNews 的 4149 items 迁移到 Hotspot knowledge/ 目录

```bash
# 一次性迁移脚本
python backend/wiki_fs/migrate.py \
  --source /Users/duke/Documents/dsh-SecNews/secnews/data/wiki/items \
  --target /Users/duke/Documents/hotspot/knowledge/items \
  --concepts-source /Users/duke/Documents/dsh-SecNews/secnews/data/wiki/concepts \
  --concepts-target /Users/duke/Documents/hotspot/knowledge/concepts \
  --graph-source /Users/duke/Documents/dsh-SecNews/secnews/data/wiki/graph.json \
  --graph-target /Users/duke/Documents/hotspot/knowledge/graph.json \
  --dry-run  # 先预览，确认后去掉
```

迁移后：
- dsh-SecNews 的 `data/wiki/` 作为备份保留（不删除）
- Hotspot `knowledge/` 为唯一活跃知识库
- `graph.json` 合并（去重 URL 键）

---

## 4. API 对齐方案

### 4.1 错误格式统一

Hotspot 已有统一错误格式：
```json
{"detail": {"message": "...", "missing": "..."}}
```

新增的 KL Pipeline 和 SecNews Dashboard API 全部复用此格式。

### 4.2 前端 API 层扩展

```typescript
// frontend/src/types/secnews.ts

export interface SecNewsItem {
  id: string;
  title: string;
  summary?: string;
  source: string;
  url: string;
  category: 'cve' | 'apt' | 'compliance' | 'tools' | 'analysis' | 'news';
  published_at: string;
  ingested_at: string;
  score?: number;
  // wiki 扩展字段
  lifecycle?: string;      // kl:raw | kl:refine | ...
  topic?: string;
  type?: string;
  difficulty?: string;
  tags?: string[];
  related?: { id: string; weight: number }[];
}

export interface PipelineStats {
  funnel: { stage: string; count: number }[];
  queue: { pending: number; running: number; failed: number };
  errors: { task_id: number; item_id: string; stage: string; error: string }[];
  alive: { total: number; alive: number; dead: number; unknown: number };
  ledger: { date: string; model: string; calls: number; tokens: number }[];
}
```

---

## 5. 前端架构对齐

### 5.1 路由总览（整合后）

```
/                        → /data (重定向)
/editorial               → 报纸版式 (独立全屏)
/data                    → 资料层首页
/data/import             → 数据导入 (URL / 书签 / inbox)
/data/favorites          → 收藏夹
/data/history            → 历史记录
/judge                   → 判断层首页
/judge/trends            → 趋势分析
/judge/bid-analysis      → 标讯分析
/judge/quality           → 质量门禁 (重定向)
/action                  → 行动层首页
/action/report           → 报告生成
/action/compound         → 知识复利
/action/todos            → 待办
/action/codegarden        → CodeGarden (feature gate)
/action/codegarden/phase2b → 服务网格 (feature gate)
/action/bid-alert         → 投标提醒
/secnews                 → 安全看板首页 (新增)
/secnews/feed            → 报纸风 Feed
/secnews/pipeline        → 管线观测台
/secnews/knowledge       → 知识浏览
/secnews/settings        → 看板设置
/knowledge               → 知识管理 (兼容旧路由)
/knowledge/import        → ...
/knowledge/process       → ...
/knowledge/compile       → ...
/knowledge/compound      → ...
/codegarden              → CodeGarden (兼容旧路由)
/settings                → 全局设置
/report                  → 报告 (兼容)
```

### 5.2 设计系统复用

整合方案**不新建**设计系统，全部复用 Hotspot 现有 Layer 组件族：

| 需求 | 复用组件 | 新增 |
|------|----------|------|
| Feed 卡片 | LayerCard (`variant="compact"`) | FeedCard（安全领域色标签） |
| Pipeline 漏斗 | LayerCard (`variant="pipeline"`) | FunnelBar |
| 队列卡片 | LayerCard (`variant="default"`) | QueueCard |
| 表格 | LayerTable | ErrorTable |
| 徽标 | LayerBadge (`solid`/`soft`/`outline`) | 安全领域色映射 |
| 图标 | Icon.tsx | shield / bug / file-text 等安全语义图标 |
| 布局 | PageLayout + LayerHeader | SecNewsShell |

---

## 6. 数据库整合

### 6.1 统一 SQLite 策略

Hotspot 已有 `backend/repository/db.py` 管理 SQLite (WAL)。
新增表直接在同一 `hotspots.db` 中创建（或新建 `secnews.db` 作为二级库）。

**推荐二级库方案**：
```
backend/repository/
├── db.py                  # 主库 (hotspots.db)
├── secnews_db.py          # 二级库 (secnews.db) — wiki 管线专用
└── migrations/
    ├── 001_init.sql
    ├── 002_kl_pipeline.sql
    └── 003_token_ledger.sql
```

### 6.2 FTS5 全文检索整合

```sql
-- 扩展现有 FTS5 或新建 wiki_items_fts
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_items_fts USING fts5(
    title, summary, tags, content,
    content='wiki_items',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- 触发器：写入时同步 FTS
CREATE TRIGGER IF NOT EXISTS wiki_items_ai AFTER INSERT ON wiki_items BEGIN
    INSERT INTO wiki_items_fts(rowid, title, summary, tags, content)
    VALUES (new.rowid, new.title, new.summary, new.tags, new.content);
END;
```

---

## 7. 调度器整合

### 7.1 Hotspot APScheduler 任务扩展

```python
# backend/scheduler/jobs.py 新增

def register_secnews_jobs(svc: CollectionService):
    """注册 dsh-SecNews 定时任务"""

    # job 18: RSS 采集 (每 30 分钟，错峰)
    scheduler.add_job(
        func=secnews_rss_collect,
        trigger="interval",
        minutes=30,
        id="secnews_rss_collect",
        jitter=300,  # ±5 分钟防重叠
    )

    # job 19: 书签存活检测 (每周日 02:00 UTC)
    scheduler.add_job(
        func=secnews_liveness_sweep,
        trigger="cron",
        day_of_week="sun",
        hour=2,
        id="secnews_liveness_sweep",
    )

    # job 20: KL 管线兜底 (每小时)
    scheduler.add_job(
        func=secnews_pipeline_sweep,
        trigger="interval",
        hours=1,
        id="secnews_pipeline_sweep",
    )

    # job 21: 日报生成 (每天 08:00 UTC)
    scheduler.add_job(
        func=secnews_daily_digest,
        trigger="cron",
        hour=8,
        id="secnews_daily_digest",
    )

    # job 22: 备份 (每天 03:00 UTC)
    scheduler.add_job(
        func=secnews_backup,
        trigger="cron",
        hour=3,
        id="secnews_backup",
    )
```

---

## 8. 配置管理

### 8.1 Feature Gates 扩展

```toml
# backend/config/feature_gates.toml

[extensions]
codegarden = false
mcp = false
sync = false
tech_stack = false
security_graph = false
secnews = true        # 新增：安全看板（默认开启）

[secnews]
rss_interval_minutes = 30
refine_model = "deepseek-v3.1-flash"
deepread_model = "deepseek-v3.2"
embed_model = "nomic-embed-text"
embed_endpoint = "http://localhost:11434/v1"  # 本地 Ollama
daily_digest_time = "08:00"
```

### 8.2 环境变量

```bash
# .env 新增
HOTSPOT_SECNEWS_DB_PATH=./data/secnews.db
HOTSPOT_SECNEWS_WIKI_DIR=./knowledge
HOTSPOT_SECNEWS_RSS_INTERVAL=30
HOTSPOT_SECNEWS_REFINE_MODEL=deepseek-v3.1-flash
HOTSPOT_SECNEWS_EMBED_ENDPOINT=http://localhost:11434/v1
HOTSPOT_SECNEWS_DAILY_DIGEST=true
```

---

## 9. 测试策略

### 9.1 后端测试

```python
# backend/tests/test_kl_pipeline.py
# backend/tests/test_wiki_fs.py
# backend/tests/test_enrich_v2.py
# backend/tests/test_secnews_api.py
# backend/tests/test_secnews_integration.py (端到端)

# 端到端测试场景：
# 1. URL 导入 → kl:raw → 自动 refine → kl:refine
# 2. 书签导入 → kl:raw → 扫描 → 去重 → 投影
# 3. 存量迁移 → 4149 items → wiki/ → FTS 可检索
# 4. Pipeline 观测台 → 漏斗数据正确
# 5. Token 台账 → refine 消耗记录正确
```

### 9.2 前端测试

```tsx
// frontend/src/components/secnews/feed/FeedView.test.tsx
// frontend/src/components/secnews/pipeline/PipelineView.test.tsx
// frontend/src/components/secnews/knowledge/WikiBrowser.test.tsx
// frontend/src/components/secnews/DeepReadPanel.test.tsx

// E2E:
// 1. 打开 /secnews/feed → 显示 Feed 列表
// 2. 点击分类标签 → 筛选正确
// 3. 进入 /secnews/pipeline → 显示漏斗图
// 4. 发起深度分析 → 显示分析结果
```

---

## 10. 迁移路径（dsh-SecNews → Hotspot）

### 10.1 数据迁移

| 数据 | 源 | 目标 | 方式 |
|------|----|----|------|
| wiki items (4149) | `dsh-SecNews/secnews/data/wiki/items/*.md` | `hotspot/knowledge/items/*.md` | 一次性迁移脚本 |
| concepts (96) | `dsh-SecNews/secnews/data/wiki/concepts/*.md` | `hotspot/knowledge/concepts/*.md` | 一次性迁移脚本 |
| graph.json | `dsh-SecNews/secnews/data/wiki/graph.json` | `hotspot/knowledge/graph.json` | 合并去重 |
| retention.json | `dsh-SecNews/secnews/data/wiki/retention.json` | `hotspot/knowledge/retention.json` | 直接复制 |
| secnews.db (kl_queue + reviews) | `dsh-SecNews/secnews/data/secnews.db` | `hotspot/data/secnews.db` | 新建空库 + 存量重跑 |
| RSS 源配置 | `dsh-SecNews/secnews/packages/api/src/collector.ts` | `hotspot/backend/collectors/secnews/` | Python 移植 |

### 10.2 代码迁移

| dsh-SecNews 代码 | 去向 | 方式 |
|------------------|------|------|
| `packages/wiki/src/pipeline.ts` | `backend/kl_pipeline/engine.py` | Python 重写 |
| `packages/wiki/src/fsstore.ts` | `backend/wiki_fs/store.py` | Python 重写 |
| `packages/wiki/src/contract.ts` | `backend/wiki_fs/contract.py` | Python 重写 |
| `packages/wiki/src/refine.ts` | `backend/kl_pipeline/stages/refine.py` | Python 重写 |
| `packages/wiki/src/concept-linker.ts` | `backend/wiki_fs/linker.py` | Python 重写 |
| `packages/api/src/collector.ts` | `backend/collectors/secnews/rss.py` | Python 移植 |
| `packages/api/src/enrich.ts` | `backend/enrich_v2.py` | 增强现有 |
| `web/dashboard/` | `frontend/src/components/secnews/` | React 重写 |
| `packages/scheduler/src/cron.ts` | `backend/scheduler/jobs.py` | 接入 APScheduler |

### 10.3 dsh-SecNews 退役

迁移完成后：
1. **不删除** `dsh-SecNews/` 仓库（作为历史备份）
2. `deepseek-harness/` 保持只读锁 tag
3. 如需彻底退役：归档至冷存储 + 更新文档

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| KL 管线 Python 重写复杂度高 | 功能不一致 | 先移植核心 5 阶段状态机，边写边测 |
| 存量 4149 items 迁移数据损坏 | 知识丢失 | `--dry-run` 预览 + 备份 + 校验 hash |
| 前端组件膨胀 | 性能下降 | 继续 lazy load + 代码分割 |
| dsh 插件依赖 Cordis 不可替代 | 某些功能无法移植 | 评估每个依赖：仅 AI 能力通道需替代，其余可独立实现 |
| FTS5 查询性能 | 大量条目检索慢 | 加索引 + 分页 + 缓存 |
| 两个项目开发者习惯差异 | 代码风格不统一 | 严格执行 hotspot 编码约定 + lint |

---

## 12. 验收标准

### Phase 0 验收
- [ ] `/api/kl/import/url` 导入 URL → 落盘 `knowledge/items/{id}.md` (kl:raw)
- [ ] `/api/kl/pipeline/stats` 返回漏斗数据
- [ ] `/secnews/feed` 路由可访问，显示看板 UI
- [ ] LayerNav 新增"安全看板"入口

### Phase 1 验收
- [ ] KL 管线五阶段自动跑通（raw → refine → link → structure → publish）
- [ ] 书签 HTML 导入 → alive 三态检测 → 存活统计
- [ ] Pipeline 观测台显示真实漏斗 + 队列卡片 + 死信表
- [ ] Token 台账记录 refine 真实消耗

### Phase 2 验收
- [ ] 质量门禁 13+ 道 Gate 正常运行
- [ ] CVE/ATT&CK/合规正则抽取准确率 > 90%
- [ ] 每日 sweep 兜底运行，滞留条目自动入队

### Phase 3 验收
- [ ] 安全看板完整 UI 就绪（feed/pipeline/knowledge/settings）
- [ ] 三层架构 + 看板路由全覆盖
- [ ] 报纸风排版符合设计规范
- [ ] dark/light 主题切换正常

### Phase 4 验收
- [ ] DeepRead 按钮 → 重 AI 分析 → 四节报告（概述/ATT&CK/修复/参考）
- [ ] 模型分层路由正确（flash=refine, big=deepread）
- [ ] Token 台账按模型分档统计

### Phase 5 验收
- [ ] 到期复习卡自动出现（SM-2 集成）
- [ ] 复习结果单向投影回 wiki frontmatter
- [ ] 复习完成率 ≥ 60%

### Phase 6 验收
- [ ] 4149 items + 96 concepts 全部迁移到 `knowledge/`
- [ ] FTS5 全文检索可命中迁移条目
- [ ] graph.json 合并后无重复边
- [ ] 迁移脚本幂等（可重复运行不报错）

---

## 13. 工作量估算

| Phase | 内容 | 人天 |
|-------|------|------|
| 0 | 后端基础模块 + 前端壳组件 + 路由 | 8 |
| 1 | KL 管线引擎 + wiki FS + 书签导入 + Pipeline UI | 10 |
| 2 | 质量门禁合并 + CVE/ATT&CK + sweep | 5 |
| 3 | 安全看板完整 UI + 三层路由整合 | 8 |
| 4 | AI 研判 + DeepRead + 模型路由 | 6 |
| 5 | 复习集成 + 复利打通 | 4 |
| 6 | 存量迁移 + 清理 | 3 |
| **合计** | | **44 人天** |

---

## 14. 后续演进（P3+）

1. **向量语义检索**：embed 模型 + 向量索引 → 语义搜索（替代纯 FTS）
2. **多机网格**：CVE 情报自动同步 + 多设备知识联邦
3. **30 天自动归档**：publish 超过 30 天的条目自动归档
4. **MCP 出口**：secnews 知识库对外暴露 MCP tools
5. **CLI 入口**：`secnews <command>` 命令行操作
6. **Cubox 深度集成**：Cubox 标注 → wiki annotations 双向同步

---

*本方案由分析 Hotspot v1.7 和 dsh-SecNews v5 现状后输出，所有技术细节基于双方实际代码库。*
