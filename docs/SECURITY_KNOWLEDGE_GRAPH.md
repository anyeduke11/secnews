# 安全知识图谱专项 · 系统架构文档

> **版本**: v1.0.0
> **日期**: 2026-07-20
> **范围**: hotspot v1.5+ 安全知识图谱 + 安全术语标准化
> **部署**: 纯本地单机（复用 hotspot 既有栈）
> **基线**: 对齐 `ARCHITECTURE.md`、`CodeGarden_PRD_v2.0.md` 的分层约定

---

## 一、目标与原则

### 1.1 业务定位

| 维度 | 目标 |
|---|---|
| 用户量 | 单人本地使用（同一时刻 1 个客户端） |
| 部署 | 单进程、嵌入式存储、零外部依赖 |
| 数据量 | 优雅支撑 hotspot 现有 1k~100k 条热点 + 1 万级安全实体 |
| API 响应 | P95 < 200ms（缓存命中 < 50ms） |
| 故障恢复 | 外部 MITRE/NVD 故障不影响采集主路径；本地缓存兜底 |

### 1.2 设计原则（与 hotspot 主项目一致）

1. **本地优先**：所有持久化落本地 SQLite，进程崩溃/重启不丢
2. **简单胜过复杂**：单进程、嵌入式存储、不为分布式需求预留接口
3. **采集主路径不阻塞**：外部 API 调用全部异步，不侵入 `CollectionService.run_once()`
4. **可重建数据不跨端同步**：MITRE/NVD 数据可从外部重建，不纳入 WebDAV sync_bundle
5. **可观测但不重型**：结构化日志 + 简单 metrics，不引入新的监控栈
6. **可扩展不预留**：通过抽象类扩展新本体源，不为不确定的需求预留接口

### 1.3 关键决策

| 决策项 | 结论 | 说明 |
|---|---|---|
| 安全图谱与通用图谱关系 | 同构合并，前端 view 切换 | 不新建前端页面，复用 `KnowledgeGraph.tsx` |
| ATT&CK 数据存储 | 全量 STIX 解析 → `security_entities` + `security_edges` | 支持离线查询，MITRE CC-BY-4.0 署名 |
| NVD CVE 查询策略 | 按需查询 + 本地缓存（TTL 30 天） | 避免 20 万+ CVE 全量同步 |
| 术语同义词存储 | `security_synonyms` 表，支持多 locale | 初期 zh-CN，预留扩展 |
| 合规本体存储 | 内置种子数据 + 用户可扩展 | 等保2.0 / 关基条例 / 数安法 |
| 术语标准化时机 | 入库前可选调用，不强制 | 保持 `auto_classifier.py` 纯函数 |
| 跨端同步 | `security_terms` 纳入 sync_bundle；`security_entities`/`security_edges` 不纳入 | 前者用户自定义，后者可重建 |

---

## 二、现状诊断

### 2.1 现有安全相关能力

| 能力 | 现状 | 局限 |
|---|---|---|
| 安全分类 | `Category.SECURITY`，6 大分类之一 | 仅一级分类，无子类型 |
| 安全采集器 | 17+ 权威安全源（THN/安全客/FreeBuf/CNNVD/奇安信/绿盟等） | 仅抓取标题/摘要，无 CVE/ATT&CK 结构化提取 |
| 安全标签映射 | `auto_classifier.py` 有 20+ security 标签 | 自由文本，无标准化 ID，无同义词/层级 |
| 通用知识图谱 | `graph_builder.py`，concept 共现边 | 无安全领域异构节点/语义边 |
| 知识条目元数据 | `knowledge_items` 有 `domain/topic/type/tags/concepts` | 无 `cve_ids`/`attack_techniques`/`compliance_refs` |

### 2.2 距目标差距

```
当前：安全热点聚合（flat list + 通用分类）
       ↓
目标：安全知识图谱（CVE → 技术 → 合规 → 知识条目 的关联网络）
```

| 缺失模块 | 安全从业者价值 |
|---|---|
| CVE 结构化提取 + NVD 关联 | 快速定位漏洞详情、CVSS、受影响产品 |
| ATT&CK 战术/技术图谱 | 理解攻击路径、对齐检测/防护策略 |
| 合规条款映射 | 热点内容 ↔ 等保/关基/数据安全法 的合规覆盖分析 |
| 术语标准化 | 统一内部知识库/采集标签，消除 "等保"/"等级保护"/"等保2.0-三级" 等歧义 |
| 安全专用视图 | 时间线（CVE 发布 + 热点关联）、威胁矩阵、合规覆盖度热力图 |

---

## 三、目标架构总览

### 3.1 分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                      Browser (React SPA)                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   KnowledgePage                          │   │
│  │  [概念图谱] [ATT&CK] [CVE] [合规矩阵]  ← view 切换      │   │
│  │         │           │          │                          │   │
│  │         ▼           ▼          ▼                          │   │
│  │  KnowledgeGraph  SecurityGraph  SecurityTimeline ...      │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼───────────────────────────────────┐
│                      FastAPI 进程 (单进程)                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              API Router Layer                            │   │
│  │  /api/knowledge/*  ← 现有通用知识 API                    │   │
│  │  /api/security/*   ← 新增安全图谱 + 术语 API             │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │              Service Layer                                │   │
│  │                                                          │   │
│  │  ┌──────────────────┐  ┌──────────────────────────┐     │   │
│  │  │ HotspotService   │  │ SecurityGraphService     │     │   │
│  │  │ TrendService     │  │ TerminologyService       │     │   │
│  │  │ CollectionService│  │                          │     │   │
│  │  └──────────────────┘  └──────────────────────────┘     │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │          SecurityGraphEngine                       │   │   │
│  │  │  - enrich_item()  热点条目 enrichment              │   │   │
│  │  │  - build_graph()  安全图谱构建                     │   │   │
│  │  │  - get_attack_path() ATT&CK 路径查询               │   │   │
│  │  │  - get_cve_knowledge() CVE 关联查询                │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │              Repository Layer                             │   │
│  │                                                          │   │
│  │  HotspotRepository  TrendRepository  FavoriteRepository  │   │
│  │  KnowledgeRepo      ┌──────────────────────────┐         │   │
│  │                      │   SecurityRepository     │         │   │
│  │                      │   (security_entities/    │         │   │
│  │                      │    security_edges/       │         │   │
│  │                      │    security_terms/       │         │   │
│  │                      │    security_synonyms/    │         │   │
│  │                      │    security_taxonomy)    │         │   │
│  │                      └──────────────────────────┘         │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │              SQLite (hotspot.db + WAL)                    │   │
│  │  hotspots / trend_points / favorites / todos             │   │
│  │  knowledge_items / knowledge_concepts / knowledge_tasks   │   │
│  │  security_entities / security_edges                       │   │
│  │  security_terms / security_synonyms / security_taxonomy   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Scheduler (APScheduler)                       │   │
│  │  - collect_all(300s)        ← 现有，不动                  │   │
│  │  - trend_rebuild(300s)      ← 现有，不动                  │   │
│  │  - security_enrichment(300s) ← 新增，异步 enrichment      │   │
│  │  - mitre_sync(weekly)       ← 新增，ATT&CK 增量更新      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              External Data Sources (异步，可选)            │   │
│  │  MITRE ATT&CK (GitHub raw)  NVD API 2.0                  │   │
│  │  [降级：本地缓存兜底，外部故障不影响主路径]                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 与现有 hotspot 架构的对齐关系

| 现有模块 | 对应关系 | 改造方式 |
|---|---|---|
| `backend/collectors/` | 安全采集器已有（`security_collector.py`） | 不动，新增 enrichment 后处理 |
| `backend/services/collection_service.py` | 采集编排入口 | 微量侵入：本地 enrichment（正则 + 本地缓存） |
| `backend/services/graph_builder.py` | 通用概念共现图谱 | 不动，安全图谱独立路径 |
| `backend/services/auto_classifier.py` | 规则化自动分类 | 新增 wrapper，原函数不动 |
| `backend/scheduler/scheduler.py` | 17 个现有 job | 新增 2 个 job，不侵入现有 job |
| `backend/api/__init__.py` | 18 个 router 注册 | 新增 `/api/security/*` router |
| `frontend/src/components/KnowledgeGraph.tsx` | 通用图谱可视化 | 扩展 `view` prop，安全节点渲染 |
| `frontend/src/types/index.ts` | 803 行类型定义 | 新增 `SecurityEntity`/`SecurityEdge` 等 |
| `backend/services/sync_bundle.py` | WebDAV 跨端同步 | `security_terms` 纳入，其余不纳入 |
| `backend/repository/db.py` | 迁移 runner | 新增 `022_security_graph.sql` |

---

## 四、数据模型设计

### 4.1 新增表

#### `security_entities`

```sql
CREATE TABLE IF NOT EXISTS security_entities (
    id          TEXT PRIMARY KEY,          -- CVE-2024-38077 / T1059 / 等保2.0-三级
    entity_type TEXT NOT NULL,             -- tactic|technique|cve|cwe|compliance|product|cpe
    name        TEXT NOT NULL,             -- "Command and Scripting Interpreter"
    description TEXT,                      -- 简要描述
    external_ref TEXT,                     -- MITRE URL / NVD URL / 标准文档 URL
    metadata    TEXT,                      -- JSON: {cvss, severity, products, etc.}
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_security_entities_type 
    ON security_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_security_entities_name 
    ON security_entities(name);
```

#### `security_edges`

```sql
CREATE TABLE IF NOT EXISTS security_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL,             -- uses|subtechnique-of|mitigates|causes|fixes|requires|related-to
    weight      REAL DEFAULT 1.0,
    metadata    TEXT,                      -- JSON: {source, confidence, etc.}
    created_at  TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES security_entities(id),
    FOREIGN KEY (target_id) REFERENCES security_entities(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_security_edge 
    ON security_edges(source_id, target_id, edge_type);
```

#### `security_terms`

```sql
CREATE TABLE IF NOT EXISTS security_terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical     TEXT NOT NULL UNIQUE,     -- 规范形式："等保2.0-三级"
    term_type     TEXT NOT NULL,            -- cve|cwe|attack_tactic|attack_technique|compliance|product|generic
    category      TEXT,                     -- "security" | "compliance" | "vulnerability"
    definition    TEXT,                     -- 简要定义
    external_id   TEXT,                     -- "CVE-2024-38077" / "T1059"
    external_ref  TEXT,                     -- MITRE URL / NVD URL
    metadata      TEXT,                     -- JSON: {cvss, severity, etc.}
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_security_terms_canonical 
    ON security_terms(canonical);
CREATE INDEX IF NOT EXISTS idx_security_terms_type 
    ON security_terms(term_type);
```

#### `security_synonyms`

```sql
CREATE TABLE IF NOT EXISTS security_synonyms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id       INTEGER NOT NULL,
    synonym       TEXT NOT NULL,
    locale        TEXT DEFAULT 'zh-CN',
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_term_synonym 
    ON security_synonyms(term_id, synonym, locale);
```

#### `security_taxonomy`

```sql
CREATE TABLE IF NOT EXISTS security_taxonomy (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id     INTEGER,
    term_id       INTEGER NOT NULL,
    sort_order    INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES security_terms(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_taxonomy_parent_term 
    ON security_taxonomy(parent_id, term_id);
```

### 4.2 扩展现有表

#### `knowledge_concepts` 扩展

```sql
-- 在 018_knowledge.sql 或 022_security_graph.sql 中执行
ALTER TABLE knowledge_concepts ADD COLUMN entity_type TEXT DEFAULT 'generic';
-- 'generic'|'tactic'|'technique'|'cve'|'cwe'|'compliance'|'product'
ALTER TABLE knowledge_concepts ADD COLUMN external_id TEXT;
ALTER TABLE knowledge_concepts ADD COLUMN external_ref TEXT;
```

#### `knowledge_items` 扩展

```sql
ALTER TABLE knowledge_items ADD COLUMN cve_ids TEXT;            -- JSON: ["CVE-2024-38077"]
ALTER TABLE knowledge_items ADD COLUMN attack_techniques TEXT;  -- JSON: ["T1059", "T1566"]
ALTER TABLE knowledge_items ADD COLUMN compliance_refs TEXT;    -- JSON: ["等保2.0-三级"]
ALTER TABLE knowledge_items ADD COLUMN threat_actors TEXT;      -- JSON: ["APT29"]
ALTER TABLE knowledge_items ADD COLUMN products TEXT;           -- JSON: ["Windows", "Exchange"]
```

---

## 五、后端架构设计

### 5.1 目录结构

```
backend/
├── security/                              ← 新增子目录
│   ├── __init__.py
│   ├── mitre_attack.py                    # MITRE ATT&CK STIX 数据获取 + 解析
│   ├── nvd_cve.py                         # NVD CVE API 2.0 客户端
│   ├── compliance.py                      # 合规本体（等保/关基/数据安全法）
│   ├── enricher.py                        # 热点条目 → 安全实体 enrichment
│   ├── graph.py                           # SecurityGraphEngine
│   └── terminology.py                     # 安全术语标准化引擎
│
├── services/
│   ├── security_graph_service.py          # 业务编排层（新增）
│   └── terminology_service.py             # 术语标准化 Service（新增）
│
├── repository/
│   └── security_repo.py                   # security_* 表 CRUD（新增）
│
├── domain/
│   └── security_models.py                 # SecurityEntity / SecurityEdge dataclass（新增）
│
├── api/
│   └── security.py                        # /api/security/* router（新增）
│
├── collectors/
│   └── security_collector.py              # 现有，不动
│
├── services/
│   ├── collection_service.py              # 微量修改：本地 enrichment
│   ├── auto_classifier.py                 # 微量修改：新增 wrapper
│   └── graph_builder.py                   # 不动
│
└── migrations/
    └── 022_security_graph.sql             # 5 张新表 + 2 张表扩展
```

### 5.2 Domain 层

```python
# backend/domain/security_models.py
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

@dataclass
class SecurityEntity:
    id: str                          # "CVE-2024-38077" / "T1059"
    entity_type: str                 # tactic|technique|cve|cwe|compliance|product|cpe
    name: str                        # "Command and Scripting Interpreter"
    description: Optional[str] = None
    external_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

@dataclass
class SecurityEdge:
    source_id: str
    target_id: str
    edge_type: str                   # uses|subtechnique-of|mitigates|causes|fixes|requires
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

@dataclass
class SecurityTerm:
    id: int
    canonical: str
    term_type: str
    category: Optional[str] = None
    definition: Optional[str] = None
    external_id: Optional[str] = None
    external_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
```

### 5.3 Repository 层

```python
# backend/repository/security_repo.py
class SecurityRepository:
    # security_entities CRUD
    def upsert_entity(self, entity: SecurityEntity) -> None: ...
    def get_entity(self, entity_id: str) -> Optional[SecurityEntity]: ...
    def list_entities(self, entity_type: str = None, name_pattern: str = None) -> list[SecurityEntity]: ...
    def search_entities(self, query: str, entity_types: list[str] = None) -> list[SecurityEntity]: ...

    # security_edges CRUD
    def upsert_edge(self, edge: SecurityEdge) -> None: ...
    def get_edges(self, entity_id: str = None, edge_type: str = None) -> list[SecurityEdge]: ...
    def get_related(self, entity_id: str, depth: int = 1) -> dict: ...

    # security_terms + synonyms + taxonomy
    def upsert_term(self, term: SecurityTerm) -> SecurityTerm: ...
    def get_term_by_canonical(self, canonical: str) -> Optional[SecurityTerm]: ...
    def search_terms(self, query: str, term_type: str = None) -> list[dict]: ...
    def add_synonym(self, term_id: int, synonym: str, locale: str = "zh-CN") -> None: ...
    def get_synonyms(self, term_id: int) -> list[str]: ...
    def get_taxonomy(self, term_type: str = None) -> list[dict]: ...
```

### 5.4 Service 层

#### SecurityGraphEngine

```python
# backend/security/graph.py
class SecurityGraphEngine:
    def __init__(self, repo: SecurityRepository, knowledge_repo: KnowledgeRepo): ...

    def build_security_graph(self, view: str = "full") -> dict:
        """构建安全知识图谱，view ∈ {full, attack, cve, compliance}"""
        nodes, edges = [], []

        if view in ("full", "attack"):
            nodes.extend(self._load_attack_nodes())
            edges.extend(self._load_attack_edges())

        if view in ("full", "cve"):
            nodes.extend(self._load_cve_nodes())
            edges.extend(self._load_cve_edges())

        if view in ("full", "compliance"):
            nodes.extend(self._load_compliance_nodes())
            edges.extend(self._load_compliance_edges())

        # 关联知识条目
        nodes.extend(self._load_knowledge_item_nodes())
        edges.extend(self._build_knowledge_edges(nodes))

        return {"nodes": nodes, "edges": edges}

    def enrich_item(self, item: KnowledgeItem) -> KnowledgeItem:
        """对热点条目做 enrichment，提取 CVE/ATT&CK/合规 标签"""
        # 1. 正则提取 CVE IDs
        # 2. 正则提取 ATT&CK IDs (T\d{4}(\.\d{3})?)
        # 3. 正则提取合规关键词 → 映射到 compliance entities
        # 4. 查本地 security_entities 补全名称
        # 返回增强后的 item（不修改原对象）
```

#### TerminologyService

```python
# backend/services/terminology_service.py
class TerminologyService:
    def __init__(self, repo: SecurityRepository): ...

    def normalize(self, text: str) -> dict:
        """标准化流程：
        1. 精确匹配 canonical
        2. 精确匹配 synonym
        3. 正则提取标准 ID（CVE / ATT&CK）
        4. 模糊匹配（difflib.get_close_matches）
        5. 无匹配 → 返回原文，match_type="none"
        """

    def get_synonyms(self, canonical: str) -> list[str]: ...
    def get_hierarchy(self, canonical: str) -> dict: ...
    def search(self, query: str, term_type: str = None, limit: int = 20) -> list[dict]: ...
    def suggest_tags(self, title: str, content: str = "") -> list[dict]: ...
```

### 5.5 数据获取策略

#### MITRE ATT&CK（首次全量 + 每周增量）

```
首次同步：
  MitreAttackClient.sync_to_db(clear=True)
    → 下载 https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json
    → 解析 STIX bundle → security_entities + security_edges
    → 预计：~1000 个 technique + ~100 个 tactic + ~500 个 software + edges

增量更新：
  scheduler: mitre_sync_job (Cron: Sun 04:00 Asia/Shanghai)
    → 检查 MITRE GitHub latest release
    → 若更新：下载 → diff → 增量 upsert
    → 预计：每月 ~50 个新增/变更
```

#### NVD CVE（按需查询 + 缓存）

```
触发条件：enrich_item() 从 hotspot item 中提取到 CVE ID
  → 查本地 security_entities 是否已存在
  → 若不存在/过期（>30天）：
      NVDClient.fetch_cve(cve_id)
        → GET https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-YYYY-NNNNN
        → 带指数退避（5 req/30s 限制）
        → 存入 security_entities（cvss/severity/products）
  → 若存在且未过期：返回缓存
```

#### 合规本体（内置种子 + 手动扩展）

```python
# backend/security/compliance.py
COMPLIANCE_BUILTIN = [
    {"id": "等保2.0-一级", "name": "网络安全等级保护2.0 第一级", "category": "等保"},
    {"id": "等保2.0-二级", "name": "网络安全等级保护2.0 第二级", "category": "等保"},
    {"id": "等保2.0-三级", "name": "网络安全等级保护2.0 第三级", "category": "等保"},
    {"id": "等保2.0-四级", "name": "网络安全等级保护2.0 第四级", "category": "等保"},
    {"id": "关基条例", "name": "关键信息基础设施安全保护条例", "category": "关基"},
    {"id": "数安法", "name": "中华人民共和国数据安全法", "category": "数据安全"},
    {"id": "网安法", "name": "中华人民共和国网络安全法", "category": "网络安全"},
    {"id": "个人信息保护法", "name": "中华人民共和国个人信息保护法", "category": "隐私"},
    # 可继续扩展：等保技术要求（安全通信网络/安全区域边界/安全计算环境...）
]
```

---

## 六、前端架构设计

### 6.1 组件结构

```
frontend/src/
├── components/
│   ├── KnowledgePage.tsx              ← 现有，扩展 view 切换器
│   ├── KnowledgeGraph.tsx             ← 现有，扩展 view prop
│   └── security/                      ← 新增子目录
│       ├── SecurityGraph.tsx          # 安全图谱可视化（复用 KnowledgeGraph 逻辑）
│       ├── SecurityEntityDetail.tsx   # 安全实体详情面板（CVE/ATT&CK/合规）
│       ├── SecurityTimeline.tsx       # CVE 发布时间线 + 热点关联
│       ├── ComplianceMatrix.tsx       # 合规要求矩阵
│       └── TermStandardizer.tsx       # 术语输入框 + 标准化建议
│
├── hooks/
│   └── useSecurityGraph.ts            # 安全图谱数据 hook
│
├── types/
│   └── index.ts                       # 新增 SecurityEntity / SecurityEdge 等类型
│
└── api/
    └── security.ts                    # 安全相关 API 调用（新增）
```

### 6.2 前端类型扩展

```typescript
// frontend/src/types/index.ts（新增）
export interface SecurityEntity {
  id: string;
  entity_type: 'tactic' | 'technique' | 'cve' | 'cwe' | 'compliance' | 'product' | 'cpe';
  name: string;
  description?: string;
  external_ref?: string;
  metadata?: Record<string, any>;
}

export interface SecurityEdge {
  source_id: string;
  target_id: string;
  edge_type: 'uses' | 'subtechnique-of' | 'mitigates' | 'causes' | 'fixes' | 'requires' | 'related-to';
  weight: number;
  metadata?: Record<string, any>;
}

export interface SecurityGraphResponse {
  nodes: (SecurityEntity | KnowledgeConcept | GraphNode)[];
  edges: (SecurityEdge | GraphEdge)[];
  stats: {
    tactics: number;
    techniques: number;
    cves: number;
    compliance_items: number;
  };
}

export interface SecurityTerm {
  id: number;
  canonical: string;
  term_type: string;
  category?: string;
  definition?: string;
  external_id?: string;
  external_ref?: string;
  synonyms: string[];
}

export interface SecurityTimelineEntry {
  date: string;
  cve_id: string;
  title: string;
  severity?: string;
  related_hotspots: Array<{ id: string; title: string; category: string }>;
}
```

### 6.3 路由与视图切换

**不新增独立路由**，在现有 `KnowledgePage.tsx` 中扩展视图切换器：

```tsx
// KnowledgePage.tsx（修改）
const VIEWS = ['concepts', 'attack', 'cve', 'compliance', 'timeline'] as const;
type View = typeof VIEWS[number];

function KnowledgePage() {
  const [view, setView] = useState<View>('concepts');
  
  return (
    <div>
      <div className="view-tabs">
        {VIEWS.map(v => (
          <button key={v} onClick={() => setView(v)}>{viewLabels[v]}</button>
        ))}
      </div>
      {view === 'concepts' && <KnowledgeGraph view="general" />}
      {view === 'attack' && <SecurityGraph view="attack" />}
      {view === 'cve' && <SecurityGraph view="cve" />}
      {view === 'compliance' && <ComplianceMatrix />}
      {view === 'timeline' && <SecurityTimeline />}
    </div>
  );
}
```

---

## 七、核心业务流

### 7.1 安全图谱构建流

```
mitre_sync_job (每周日 04:00 Asia/Shanghai)
  → MitreAttackClient.sync_to_db()
    → 下载 STIX bundle
    → 解析 → SecurityRepository.upsert_entity() / upsert_edge()
    → 完成（约 2-5 分钟）

security_enrichment_job (每 300s，异步)
  → SecurityGraphEngine.enrich_batch()
    → 扫描近 24h hotspot items 中未 enrichment 的条目
    → 对每条 item：
        a. 正则提取 CVE IDs → 查本地 security_entities（未命中则 NVD 按需查询）
        b. 正则提取 ATT&CK IDs → 查本地 security_entities
        c. 正则提取合规关键词 → 映射到 compliance entities
        d. 更新 knowledge_items (cve_ids / attack_techniques / compliance_refs)
    → 完成（不阻塞采集主路径）

前端 GET /api/security/graph?view=attack
  → SecurityGraphService.get_graph(view="attack")
    → SecurityGraphEngine.build_security_graph(view="attack")
      → _load_attack_nodes() → security_entities WHERE entity_type IN ('tactic','technique')
      → _load_attack_edges() → security_edges WHERE edge_type IN ('uses','subtechnique-of')
      → _load_knowledge_item_nodes() → JOIN knowledge_items + knowledge_concepts
      → _build_knowledge_edges() → 知识条目 ↔ 安全实体的关联边
    → 返回 {nodes, edges, stats}
  → 前端 SecurityGraph.tsx 渲染
```

### 7.2 术语标准化流

```
用户输入 / 系统采集
  → TerminologyService.normalize(text)
    → 1. 精确匹配 canonical（O(1)）
    → 2. 精确匹配 synonym（B-tree 索引）
    → 3. 正则提取标准 ID（CVE-YYYY-NNNNN / T\d{4}(\.\d{3})?）
    → 4. 模糊匹配（difflib.get_close_matches）
    → 返回 {canonical, term_type, match_type, confidence}

auto_classifier 集成（可选）：
  batch_classify_with_terminology(items, term_svc)
    → 对每个 item 的 tags 先 normalize
    → 再调用原有 classify_item()
    → 标签统一为规范形式

知识图谱构建（可选）：
  graph_builder 扩展 wrapper
    → 对 tags + concepts 做 normalize
    → 用 canonical terms 构建共现边
```

### 7.3 CVE 告警触发流（可选 Phase 5）

```
security_enrichment_job
  → 检测到高危 CVE（CVSS >= 9.0）
    → 写入 cg_events 表（status=pending）
      → cg_event_process_job (每 60s)
        → 读取 pending 事件
        → 触发 Playbook（如：发送通知、标记知识条目）
```

---

## 八、与现有系统的集成点

| 集成点 | 方式 | 改造量 | 是否侵入主路径 |
|---|---|---|---|
| `CollectionService.run_once()` | 本地 enrichment（正则 + 本地缓存），不调外部 API | +10 行 | 微量侵入 |
| 新增 `security_enrichment_job` | scheduler 独立 job | 新增 1 个 job | 不侵入 |
| 新增 `mitre_sync_job` | scheduler 独立 job | 新增 1 个 job | 不侵入 |
| `graph_builder.py` | 不动，安全图谱独立路径 | 0 行 | 不侵入 |
| `auto_classifier.py` | 新增 `batch_classify_with_terminology()` wrapper | +15 行 | 不侵入 |
| `KnowledgeGraph.tsx` | 扩展 `view` prop | +50 行 | 微量侵入 |
| `sync_bundle.py` | `security_terms` 纳入 sync_bundle | +10 行 | 不侵入 |
| `knowledge_watcher` | 监听 `security_*` 表变更（可选） | 可选 | 不侵入 |

---

## 九、性能与容量预估

| 数据规模 | 预估行数 | 查询模式 | 索引策略 |
|---|---|---|---|
| `security_entities` | 1,000~5,000 | 按 type/name 查询 | entity_type, name |
| `security_edges` | 5,000~20,000 | 按 source/target 查询 | source_id, target_id |
| `security_terms` | 500~2,000 | 精确匹配 + 模糊搜索 | canonical |
| `security_synonyms` | 1,000~5,000 | 精确匹配 | term_id + synonym |
| `security_taxonomy` | 500~1,000 | 按 parent 查询 | parent_id, term_id |

**查询性能**：
- `build_security_graph(view="attack")`：预计 < 100ms（1k nodes + 5k edges）
- `normalize(text)`：精确匹配 < 1ms，模糊匹配 < 10ms
- `enrich_item()`：正则提取 < 1ms，本地缓存查询 < 5ms

---

## 十、可观测性

遵循 hotspot 现有日志规范（`loguru` 结构化日志）：

```python
# backend/security/graph.py
log = logging.getLogger("hotspot.security_graph")

log.info("security graph built", extra={
    "trace_id": "",
    "view": view,
    "nodes": len(nodes),
    "edges": len(edges),
    "duration_ms": round((time.time() - start) * 1000, 2),
})
```

关键 metrics：
- `security_enrichment_job`：处理条目数、NVD 命中率、失败数
- `mitre_sync_job`：同步实体数、增量/全量标记
- `normalize()`：匹配类型分布（exact/synonym/regex/fuzzy/none）

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| MITRE ATT&CK STIX 格式变更 | 解析失败，图谱不完整 | 版本锁定（固定 commit SHA）+ 解析失败时保留旧数据 |
| NVD API Rate Limit / 故障 | enrichment 延迟或失败 | 降级到本地缓存；外部故障不影响采集主路径 |
| 术语歧义（如 "木马" 多义） | 错误标准化 | 初期仅做精确/正则匹配，不启用模糊匹配；后续引入上下文消歧 |
| SQLite 写入竞争 | 多 job 同时写 security_* 表 | 复用现有 `get_connection()` 线程局部连接，autocommit 模式 |
| 数据量增长（CVE 20万+） | 不提前规划会导致未来迁移困难 | `security_entities` 仅存热点相关的 CVE，不做全量同步 |
