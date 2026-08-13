# 安全知识图谱专项 · 开发计划

> **版本**: v1.0.0
> **日期**: 2026-07-20
> **关联文档**:
> - [SECURITY_KNOWLEDGE_GRAPH.md](./SECURITY_KNOWLEDGE_GRAPH.md) 系统架构
> - [SECURITY_KNOWLEDGE_GRAPH_PRD.md](./SECURITY_KNOWLEDGE_GRAPH_PRD.md) 产品需求
> - [ARCHITECTURE.md](./ARCHITECTURE.md) hotspot 主架构
> - [CodeGarden_PRD_v1.7.md](./CodeGarden_PRD_v1.7.md) CodeGarden PRD（分层对齐参考）

---

## 一、总体时间线

```
Phase 1（基础设施）：第 1-2 周
Phase 2（MITRE 同步）：第 3 周
Phase 3（图谱核心）：第 4-5 周
Phase 4（术语标准化）：第 6 周
Phase 5（前端可视化）：第 7-8 周
Phase 6（NVD + 告警）：第 9 周（可选）
```

---

## 二、Phase 1：基础设施（第 1-2 周）

### 目标
建立安全图谱的数据存储层，与现有 hotspot 架构完全对齐。

### 任务清单

#### T1.1 数据库迁移

**文件**: `backend/repository/migrations/022_security_graph.sql`

**内容**:
```sql
-- 022_security_graph.sql: v1.5+ Security Knowledge Graph + Terminology

-- 1. 安全实体表
CREATE TABLE IF NOT EXISTS security_entities (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    external_ref TEXT,
    metadata    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_entities_type ON security_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_security_entities_name ON security_entities(name);

-- 2. 安全语义边表
CREATE TABLE IF NOT EXISTS security_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL,
    weight      REAL DEFAULT 1.0,
    metadata    TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES security_entities(id),
    FOREIGN KEY (target_id) REFERENCES security_entities(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_security_edge ON security_edges(source_id, target_id, edge_type);

-- 3. 术语表
CREATE TABLE IF NOT EXISTS security_terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical     TEXT NOT NULL UNIQUE,
    term_type     TEXT NOT NULL,
    category      TEXT,
    definition    TEXT,
    external_id   TEXT,
    external_ref  TEXT,
    metadata      TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_terms_canonical ON security_terms(canonical);
CREATE INDEX IF NOT EXISTS idx_security_terms_type ON security_terms(term_type);

-- 4. 同义词表
CREATE TABLE IF NOT EXISTS security_synonyms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id       INTEGER NOT NULL,
    synonym       TEXT NOT NULL,
    locale        TEXT DEFAULT 'zh-CN',
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_term_synonym ON security_synonyms(term_id, synonym, locale);

-- 5. 术语层级表
CREATE TABLE IF NOT EXISTS security_taxonomy (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id     INTEGER,
    term_id       INTEGER NOT NULL,
    sort_order    INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES security_terms(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_taxonomy_parent_term ON security_taxonomy(parent_id, term_id);

-- 6. 扩展现有表：knowledge_concepts
ALTER TABLE knowledge_concepts ADD COLUMN entity_type TEXT DEFAULT 'generic';
ALTER TABLE knowledge_concepts ADD COLUMN external_id TEXT;
ALTER TABLE knowledge_concepts ADD COLUMN external_ref TEXT;

-- 7. 扩展现有表：knowledge_items
ALTER TABLE knowledge_items ADD COLUMN cve_ids TEXT;
ALTER TABLE knowledge_items ADD COLUMN attack_techniques TEXT;
ALTER TABLE knowledge_items ADD COLUMN compliance_refs TEXT;
ALTER TABLE knowledge_items ADD COLUMN threat_actors TEXT;
ALTER TABLE knowledge_items ADD COLUMN products TEXT;
```

**验收标准**:
- [ ] 迁移在全新数据库上执行成功
- [ ] 迁移在已有数据库上执行成功（向后兼容）
- [ ] `schema_version` 表记录版本 22
- [ ] 所有索引创建成功

#### T1.2 Domain 模型

**文件**: `backend/domain/security_models.py`（新增）

**内容**:
```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

@dataclass
class SecurityEntity:
    id: str
    entity_type: str
    name: str
    description: Optional[str] = None
    external_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

@dataclass
class SecurityEdge:
    source_id: str
    target_id: str
    edge_type: str
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

**验收标准**:
- [ ] 3 个 dataclass 定义完整
- [ ] 与 Repository 层的参数对齐
- [ ] 有 `from_row()` / `to_dict()` 方法（可选，便于调试）

#### T1.3 SecurityRepository

**文件**: `backend/repository/security_repo.py`（新增）

**内容**:
```python
class SecurityRepository:
    # security_entities
    def upsert_entity(self, entity: SecurityEntity) -> None: ...
    def get_entity(self, entity_id: str) -> Optional[SecurityEntity]: ...
    def list_entities(self, entity_type: str = None, name_pattern: str = None) -> list[SecurityEntity]: ...
    def search_entities(self, query: str, entity_types: list[str] = None) -> list[SecurityEntity]: ...

    # security_edges
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

**验收标准**:
- [ ] 所有 CRUD 方法实现
- [ ] 使用 `get_connection()` 线程局部连接
- [ ] 错误处理符合项目规范（`InternalException`）
- [ ] 单测覆盖率 >= 80%

#### T1.4 内置术语种子数据

**文件**: `backend/security/compliance.py`（新增）

**内容**: 等保2.0 / 关基条例 / 数安法 / 网安法 / 个保法

**验收标准**:
- [ ] 内置数据可导入数据库
- [ ] 支持后续扩展（新增合规条款无需改代码）

### Phase 1 交付物
- [ ] `022_security_graph.sql` 迁移文件
- [ ] `backend/domain/security_models.py`
- [ ] `backend/repository/security_repo.py`
- [ ] `backend/security/compliance.py`
- [ ] `backend/tests/test_security_repo.py`（新增）
- [ ] 迁移执行脚本（可选）

### Phase 1 阻塞条件
- 无

---

## 三、Phase 2：MITRE ATT&CK 同步（第 3 周）

### 目标
将 MITRE ATT&CK 数据同步到本地 `security_entities` + `security_edges` 表。

### 任务清单

#### T2.1 MITRE ATT&CK STIX 解析

**文件**: `backend/security/mitre_attack.py`（新增）

**内容**:
```python
class MitreAttackClient:
    BASE_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack"
    
    async def fetch_tactics(self) -> list[dict]: ...
    async def fetch_techniques(self) -> list[dict]: ...
    async def fetch_software(self) -> list[dict]: ...
    async def fetch_groups(self) -> list[dict]: ...
    
    def sync_to_db(self, clear: bool = False) -> int:
        """将 MITRE STIX 数据同步到 security_entities + security_edges"""
```

**关键设计**:
- 首次同步：`clear=True` 清空旧数据，全量同步
- 增量同步：`clear=False`，仅 upsert 变更部分
- 版本锁定：固定 MITRE commit SHA，避免上游格式变更导致解析失败
- 解析逻辑：
  - `attack-pattern` → `security_entities` (entity_type='technique')
  - `tactic` → `security_entities` (entity_type='tactic')
  - `relationship` (type='uses') → `security_edges` (edge_type='uses')
  - `relationship` (type='subtechnique-of') → `security_edges` (edge_type='subtechnique-of')

**验收标准**:
- [ ] 可下载 STIX bundle（~20MB）
- [ ] 解析出 ~1000 个 technique + ~100 个 tactic
- [ ] 解析出 ~5000 个 edges（uses / subtechnique-of）
- [ ] 同步耗时 < 5 分钟
- [ ] 解析失败时保留旧数据，不抛异常到调用方

#### T2.2 Scheduler Job

**文件**: `backend/scheduler/jobs.py`（新增 job）

**内容**:
```python
def mitre_sync_job():
    """每周日 04:00 Asia/Shanghai 同步 MITRE ATT&CK 数据"""
    from backend.security.mitre_attack import MitreAttackClient
    client = MitreAttackClient()
    try:
        count = client.sync_to_db(clear=False)
        log.info("mitre sync completed", extra={"count": count})
    except Exception as e:
        log.error("mitre sync failed", extra={"error": str(e)})
```

**文件**: `backend/scheduler/scheduler.py`（注册 job）

**验收标准**:
- [ ] job 注册到 HotspotScheduler
- [ ] 触发器：Cron(day_of_week='sun', hour=4, minute=0, timezone='Asia/Shanghai')
- [ ] 执行失败不影响其他 job

#### T2.3 API 端点

**文件**: `backend/api/security.py`（新增 router）

**内容**:
```python
router = APIRouter(prefix="/api/security", tags=["security"])

@router.get("/entities")
async def list_entities(entity_type: str = None, q: str = None): ...

@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str): ...

@router.get("/entities/{entity_id}/related")
async def get_related(entity_id: str, depth: int = 1): ...
```

**验收标准**:
- [ ] 可查询 tactic / technique 列表
- [ ] 可查询单个实体详情
- [ ] 可查询关联节点（depth=1）

### Phase 2 交付物
- [ ] `backend/security/mitre_attack.py`
- [ ] `backend/api/security.py`（基础查询）
- [ ] `backend/tests/test_mitre_attack.py`（新增）
- [ ] scheduler job 注册

### Phase 2 阻塞条件
- 无（MITRE ATT&CK 数据公开可用）

---

## 四、Phase 3：安全图谱核心（第 4-5 周）

### 目标
构建安全知识图谱引擎，支持 view 切换（attack/cve/compliance/full）。

### 任务清单

#### T3.1 SecurityGraphEngine

**文件**: `backend/security/graph.py`（新增）

**内容**:
```python
class SecurityGraphEngine:
    def __init__(self, repo: SecurityRepository, knowledge_repo: KnowledgeRepo): ...

    def build_security_graph(self, view: str = "full") -> dict:
        """构建安全知识图谱"""
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
        """对热点条目做 enrichment（本地正则 + 本地缓存，不调外部 API）"""
        import re
        cve_ids = re.findall(r"CVE-\d{4}-\d{4,}", item.title + " " + (item.summary or ""))
        attack_ids = re.findall(r"T\d{4}(?:\.\d{3})?", item.title + " " + (item.summary or ""))
        # 查本地 security_entities 补全名称
        # 返回增强后的 item
```

**验收标准**:
- [ ] `build_security_graph(view="attack")` 返回 ATT&CK 子图
- [ ] `build_security_graph(view="cve")` 返回 CVE 子图
- [ ] `build_security_graph(view="compliance")` 返回合规子图
- [ ] `build_security_graph(view="full")` 返回完整安全图谱
- [ ] `enrich_item()` 不调用外部 API
- [ ] 构建耗时 < 100ms

#### T3.2 SecurityGraphService

**文件**: `backend/services/security_graph_service.py`（新增）

**内容**:
```python
class SecurityGraphService:
    def __init__(self):
        self._repo = SecurityRepository()
        self._engine = SecurityGraphEngine(self._repo, knowledge_repo)

    def get_graph(self, view: str = "full") -> dict:
        """对外暴露的图谱接口"""
        return self._engine.build_security_graph(view)

    def search_entities(self, query: str, entity_type: str = None) -> list[dict]: ...

    def enrich_hotspot_item(self, item: HotspotItem) -> dict:
        """对热点条目做安全 enrichment"""
        return self._engine.enrich_item(item)
```

**验收标准**:
- [ ] 与 SecurityGraphEngine 对齐
- [ ] 错误处理符合项目规范

#### T3.3 CollectionService 集成（微量侵入）

**文件**: `backend/services/collection_service.py`（修改）

**修改点**: 在 `run_once()` 的 `upsert_many` 之后，增加本地 enrichment：

```python
# 本地 enrichment（仅正则 + 本地缓存，不调外部 API）
try:
    from backend.security.enricher import enrich_batch
    enriched_items = enrich_batch(items)
    # 更新 knowledge_items 的 cve_ids / attack_techniques / compliance_refs
except Exception as e:
    log.warning(f"local enrichment failed: {e}")
```

**验收标准**:
- [ ] 采集主路径不阻塞
- [ ] enrichment 失败不影响入库
- [ ] 正则提取 CVE/ATT&CK ID 准确率 >= 90%

#### T3.4 security_enrichment_job

**文件**: `backend/scheduler/jobs.py`（新增 job）

**内容**:
```python
def security_enrichment_job():
    """每 300s 扫描近 24h 未 enrichment 的 hotspot items，异步 enrichment"""
    from backend.security.enricher import enrich_batch
    from backend.services.hotspot_service import HotspotService
    svc = HotspotService()
    items = svc.list_hotspots(since=24h)
    enrich_batch(items)
```

**文件**: `backend/scheduler/scheduler.py`（注册 job）

**触发器**: `IntervalTrigger(seconds=300)`

**验收标准**:
- [ ] job 注册成功
- [ ] 执行失败不影响其他 job
- [ ] 不阻塞采集主路径

#### T3.5 API 端点扩展

**文件**: `backend/api/security.py`（修改）

**新增**:
```python
@router.get("/graph")
async def get_security_graph(view: str = "full"): ...
```

**验收标准**:
- [ ] `GET /api/security/graph?view=attack` 返回 ATT&CK 子图
- [ ] `GET /api/security/graph?view=cve` 返回 CVE 子图
- [ ] `GET /api/security/graph?view=compliance` 返回合规子图
- [ ] `GET /api/security/graph?view=full` 返回完整安全图谱
- [ ] 响应格式：`{nodes, edges, stats}`

### Phase 3 交付物
- [ ] `backend/security/graph.py`
- [ ] `backend/security/enricher.py`
- [ ] `backend/services/security_graph_service.py`
- [ ] `backend/api/security.py`（扩展）
- [ ] `backend/scheduler/jobs.py`（新增 job）
- [ ] `backend/scheduler/scheduler.py`（注册 job）
- [ ] `backend/services/collection_service.py`（微量修改）
- [ ] `backend/tests/test_security_graph.py`（新增）
- [ ] `backend/tests/test_enricher.py`（新增）

### Phase 3 阻塞条件
- 无

---

## 五、Phase 4：术语标准化（第 6 周）

### 目标
实现安全术语标准化服务，与现有 auto_classifier 集成。

### 任务清单

#### T4.1 TerminologyService

**文件**: `backend/services/terminology_service.py`（新增）

**内容**:
```python
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

**验收标准**:
- [ ] 精确匹配 < 1ms
- [ ] 模糊匹配 < 10ms
- [ ] 正则提取 CVE/ATT&CK ID 准确率 >= 95%
- [ ] 无匹配时返回原文，不抛异常

#### T4.2 auto_classifier 集成

**文件**: `backend/services/auto_classifier.py`（修改）

**修改点**: 新增 wrapper，原函数不动：

```python
def batch_classify_with_terminology(items: list[dict], term_svc=None) -> list[dict]:
    """可选的安全术语标准化版本"""
    if term_svc is None:
        return batch_classify(items)
    for item in items:
        item["tags"] = _normalize_tags(item.get("tags", []), term_svc)
    return batch_classify(items)
```

**验收标准**:
- [ ] 原 `classify_item()` 函数签名不变
- [ ] 新 wrapper 可选调用
- [ ] 不传 `term_svc` 时降级到原有纯规则

#### T4.3 术语 API

**文件**: `backend/api/security.py`（新增 router）

**内容**:
```python
terminology_router = APIRouter(prefix="/api/security/terminology", tags=["security-terminology"])

@terminology_router.post("/normalize")
async def normalize_term(text: str): ...

@terminology_router.get("/search")
async def search_terms(query: str, term_type: str = None, limit: int = 20): ...

@terminology_router.get("/taxonomy")
async def get_taxonomy(term_type: str = None): ...
```

**验收标准**:
- [ ] POST /api/security/terminology/normalize 返回标准化结果
- [ ] GET /api/security/terminology/search 支持搜索
- [ ] GET /api/security/terminology/taxonomy 返回层级结构

### Phase 4 交付物
- [ ] `backend/services/terminology_service.py`
- [ ] `backend/api/security.py`（新增 terminology sub-router）
- [ ] `backend/services/auto_classifier.py`（新增 wrapper）
- [ ] `backend/tests/test_terminology_service.py`（新增）

### Phase 4 阻塞条件
- 无

---

## 六、Phase 5：前端可视化（第 7-8 周）

### 目标
在现有 KnowledgePage 中扩展安全视图。

### 任务清单

#### T5.1 前端类型扩展

**文件**: `frontend/src/types/index.ts`（修改）

**新增类型**:
```typescript
export interface SecurityEntity { ... }
export interface SecurityEdge { ... }
export interface SecurityGraphResponse { ... }
export interface SecurityTerm { ... }
export interface SecurityTimelineEntry { ... }
```

**验收标准**:
- [ ] 新增 5 个类型定义
- [ ] 与后端响应格式对齐

#### T5.2 KnowledgePage 视图切换

**文件**: `frontend/src/components/KnowledgePage.tsx`（修改）

**修改点**: 增加视图切换器

```tsx
const VIEWS = ['concepts', 'attack', 'cve', 'compliance', 'timeline'] as const;
function KnowledgePage() {
  const [view, setView] = useState<View>('concepts');
  return (
    <div>
      <div className="view-tabs">
        {VIEWS.map(v => <button key={v} onClick={() => setView(v)}>{viewLabels[v]}</button>)}
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

**验收标准**:
- [ ] 5 个视图可切换
- [ ] 切换无闪烁

#### T5.3 SecurityGraph 组件

**文件**: `frontend/src/components/security/SecurityGraph.tsx`（新增）

**内容**: 基于现有 `KnowledgeGraph.tsx` 扩展，支持安全实体节点渲染

**验收标准**:
- [ ] 支持 view=attack（战术/技术分层）
- [ ] 支持 view=cve（CVE 列表 + severity 着色）
- [ ] 支持缩放/拖拽
- [ ] 节点样式按 entity_type 区分

#### T5.4 SecurityEntityDetail 组件

**文件**: `frontend/src/components/security/SecurityEntityDetail.tsx`（新增）

**内容**: 点击节点展示详情

**验收标准**:
- [ ] 展示实体基本信息
- [ ] 展示关联知识条目
- [ ] 展示外部链接（NVD/MITRE）

#### T5.5 SecurityTimeline 组件

**文件**: `frontend/src/components/security/SecurityTimeline.tsx`（新增）

**内容**: CVE 发布时间线 + 热点关联

**验收标准**:
- [ ] 按日期展示 CVE
- [ ] 支持 severity 筛选
- [ ] 展示关联热点条目

#### T5.6 ComplianceMatrix 组件

**文件**: `frontend/src/components/security/ComplianceMatrix.tsx`（新增）

**内容**: 合规要求矩阵

**验收标准**:
- [ ] 展示合规条款列表
- [ ] 展示关联知识条目
- [ ] 支持条款筛选

#### T5.7 TermStandardizer 组件

**文件**: `frontend/src/components/security/TermStandardizer.tsx`（新增）

**内容**: 术语输入框 + 标准化建议

**验收标准**:
- [ ] 输入时实时显示标准化建议
- [ ] 支持同义词展示
- [ ] 支持层级展开

### Phase 5 交付物
- [ ] `frontend/src/types/index.ts`（扩展）
- [ ] `frontend/src/components/KnowledgePage.tsx`（修改）
- [ ] `frontend/src/components/security/SecurityGraph.tsx`
- [ ] `frontend/src/components/security/SecurityEntityDetail.tsx`
- [ ] `frontend/src/components/security/SecurityTimeline.tsx`
- [ ] `frontend/src/components/security/ComplianceMatrix.tsx`
- [ ] `frontend/src/components/security/TermStandardizer.tsx`
- [ ] `frontend/src/hooks/useSecurityGraph.ts`

### Phase 5 阻塞条件
- 无

---

## 七、Phase 6：NVD 集成 + 告警（第 9 周，可选）

### 目标
集成 NVD CVE API，支持高危 CVE 告警。

### 任务清单

#### T6.1 NVDClient

**文件**: `backend/security/nvd_cve.py`（新增）

**内容**:
```python
class NVDClient:
    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    
    async def fetch_cve(self, cve_id: str) -> dict: ...
    async def search_cve(self, keyword: str, days: int = 7) -> list[dict]: ...
    
    def normalize_cve(self, raw: dict) -> SecurityEntity: ...
```

**关键设计**:
- Rate limit 处理：5 req/30s（无 key），指数退避
- 缓存：`security_entities` 中 CVE 实体，TTL 30 天
- 降级：NVD 故障时返回本地缓存

**验收标准**:
- [ ] 可查询 CVE 详情
- [ ] Rate limit 处理正确
- [ ] 降级策略生效

#### T6.2 NVD 集成到 enrichment

**文件**: `backend/security/enricher.py`（修改）

**修改点**: 对提取的 CVE ID，查询 NVD 补全 metadata

**验收标准**:
- [ ] enrichment 后 CVE 实体包含 CVSS/severity/products
- [ ] NVD 故障时降级（仅保留 CVE ID，不阻塞）

#### T6.3 CVE 告警触发

**文件**: `backend/scheduler/jobs.py`（可选）

**内容**:
```python
def security_enrichment_job():
    ...
    # 检测到高危 CVE（CVSS >= 9.0）
    if cve_metadata.get("cvss", 0) >= 9.0:
        from backend.services.codegarden_orchestration_service import cg_event_process_job
        cg_event_process_job.create_event(
            event_type="high_severity_cve",
            source="security_enrichment",
            data={"cve_id": cve_id, "cvss": cvss}
        )
```

**验收标准**:
- [ ] CVSS >= 9.0 时触发事件
- [ ] 事件写入 cg_events 表

### Phase 6 交付物
- [ ] `backend/security/nvd_cve.py`
- [ ] `backend/security/enricher.py`（修改）
- [ ] `backend/scheduler/jobs.py`（可选修改）
- [ ] `backend/tests/test_nvd_cve.py`（新增）

### Phase 6 阻塞条件
- 无（NVD API 公开可用）

---

## 八、测试计划

### 8.1 后端测试

| 测试文件 | 覆盖模块 | 预计用例数 |
|---|---|---|
| `test_security_repo.py` | SecurityRepository | 20+ |
| `test_mitre_attack.py` | MitreAttackClient | 10+ |
| `test_security_graph.py` | SecurityGraphEngine | 15+ |
| `test_enricher.py` | enricher.py | 10+ |
| `test_terminology_service.py` | TerminologyService | 15+ |
| `test_nvd_cve.py` | NVDClient | 10+ |
| `test_security_api.py` | /api/security/* | 10+ |

**目标**: 新增测试覆盖率 >= 80%

### 8.2 前端测试

| 测试文件 | 覆盖模块 | 预计用例数 |
|---|---|---|
| `SecurityGraph.test.tsx` | SecurityGraph 组件 | 8+ |
| `SecurityEntityDetail.test.tsx` | SecurityEntityDetail 组件 | 6+ |
| `SecurityTimeline.test.tsx` | SecurityTimeline 组件 | 6+ |
| `ComplianceMatrix.test.tsx` | ComplianceMatrix 组件 | 6+ |
| `TermStandardizer.test.tsx` | TermStandardizer 组件 | 6+ |
| `useSecurityGraph.test.ts` | useSecurityGraph hook | 8+ |

**目标**: 新增测试覆盖率 >= 60%

### 8.3 集成测试

| 场景 | 说明 |
|---|---|
| MITRE 同步 → 图谱构建 | 同步后构建图谱，验证节点/边正确 |
| CVE 提取 → NVD 查询 → 缓存 | 提取 CVE ID，查询 NVD，验证缓存生效 |
| 术语标准化 → auto_classifier | 标准化标签后分类，验证结果一致 |
| 采集主路径 → 本地 enrichment | 采集后 enrichment，验证不阻塞 |

---

## 九、发布计划

### 9.1 灰度发布

1. **第 1 周**: 基础设施就绪，仅内部测试
2. **第 2 周**: MITRE 同步 + 基础 API，可查询 ATT&CK
3. **第 3-4 周**: 安全图谱核心，前端 view 切换
4. **第 5 周**: 术语标准化，auto_classifier 集成
5. **第 6-7 周**: 前端可视化完善
6. **第 8 周**: NVD + 告警（可选）

### 9.2 回滚策略

| 场景 | 回滚方式 |
|---|---|
| 迁移失败 | `schema_version` 回滚，保留旧数据 |
| MITRE 同步失败 | 保留旧数据，不影响采集主路径 |
| NVD 故障 | 降级到本地缓存，不阻塞 |
| 前端问题 | 热回退到 `view="concepts"` |

---

## 十、依赖关系

```
Phase 1（基础设施）
  ↓
Phase 2（MITRE 同步） ← 依赖 T1.1, T1.2, T1.3
  ↓
Phase 3（图谱核心）   ← 依赖 T2.1, T2.2, T2.3
  ↓
Phase 4（术语标准化）  ← 依赖 T1.3
  ↓
Phase 5（前端可视化）  ← 依赖 T3.1, T3.2, T3.5
  ↓
Phase 6（NVD + 告警）  ← 依赖 T3.3, T6.1
```

**并行机会**:
- Phase 4（术语标准化）可与 Phase 3（图谱核心）并行（仅依赖 Phase 1）
- Phase 5（前端可视化）可与 Phase 4 并行（仅依赖 Phase 3 的 API）

---

## 十一、工作量估算

| Phase | 任务数 | 预计工时 | 备注 |
|---|---|---|---|
| Phase 1 | 4 | 16-24h | 迁移 + Repository + 种子数据 |
| Phase 2 | 3 | 8-12h | MITRE STIX 解析 + scheduler |
| Phase 3 | 5 | 16-24h | 图谱引擎 + enrichment + API |
| Phase 4 | 3 | 8-12h | 术语服务 + auto_classifier 集成 |
| Phase 5 | 7 | 16-24h | 前端组件 + 视图切换 |
| Phase 6 | 3 | 8-12h | NVD 集成 + 告警（可选） |
| **总计** | **25** | **72-108h** | 约 2-3 周（全职） |

---

## 十二、风险与缓解

| 风险 | 影响 | 缓解措施 | 负责人 |
|---|---|---|---|
| MITRE STIX 格式变更 | 解析失败 | 版本锁定（固定 commit SHA）+ 解析失败保留旧数据 | 后端 |
| NVD API Rate Limit | enrichment 延迟 | 降级到本地缓存 + 指数退避 | 后端 |
| 术语歧义 | 错误标准化 | 初期仅精确/正则，不启用模糊匹配 | 后端 |
| 前端图谱性能（>1000 节点） | 卡顿 | 虚拟滚动 + 分层渲染 | 前端 |
| 数据量增长 | 查询变慢 | 索引优化 + 分页 | 后端 |

---

## 十三、验收标准汇总

### 13.1 功能验收

- [ ] 安全图谱可查询（attack/cve/compliance/full）
- [ ] MITRE ATT&CK 数据同步成功
- [ ] CVE 自动提取 + NVD 关联
- [ ] 术语标准化可用（精确/正则/模糊）
- [ ] auto_classifier 集成后分类准确率不下降
- [ ] 前端 5 个视图可切换
- [ ] 采集主路径不阻塞

### 13.2 性能验收

- [ ] 安全图谱构建 < 100ms
- [ ] 术语标准化 < 1ms（精确）
- [ ] 前端图谱渲染 >= 30 FPS（1000 节点）

### 13.3 兼容性验收

- [ ] 现有采集主路径零破坏
- [ ] 现有知识图谱零破坏
- [ ] 现有 auto_classifier 零破坏
- [ ] sync_bundle 向后兼容

---

## 十四、附录

### 14.1 文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/repository/migrations/022_security_graph.sql` | 新增 | 5 张新表 + 2 张表扩展 |
| `backend/domain/security_models.py` | 新增 | SecurityEntity / SecurityEdge / SecurityTerm |
| `backend/repository/security_repo.py` | 新增 | 5 张表 CRUD |
| `backend/security/__init__.py` | 新增 | 子目录标记 |
| `backend/security/mitre_attack.py` | 新增 | MITRE ATT&CK STIX 解析 |
| `backend/security/nvd_cve.py` | 新增 | NVD CVE API 客户端 |
| `backend/security/compliance.py` | 新增 | 合规本体种子数据 |
| `backend/security/enricher.py` | 新增 | 热点条目 enrichment |
| `backend/security/graph.py` | 新增 | SecurityGraphEngine |
| `backend/security/terminology.py` | 新增 | 术语标准化引擎 |
| `backend/services/security_graph_service.py` | 新增 | 业务编排层 |
| `backend/services/terminology_service.py` | 新增 | 术语 Service |
| `backend/services/collection_service.py` | 修改 | 微量增加本地 enrichment |
| `backend/services/auto_classifier.py` | 修改 | 新增 wrapper |
| `backend/api/security.py` | 新增 | /api/security/* router |
| `backend/scheduler/jobs.py` | 修改 | 新增 2 个 job |
| `backend/scheduler/scheduler.py` | 修改 | 注册新 job |
| `backend/services/sync_bundle.py` | 修改 | security_terms 纳入 sync_bundle |
| `frontend/src/types/index.ts` | 修改 | 新增 SecurityEntity 等类型 |
| `frontend/src/components/KnowledgePage.tsx` | 修改 | 视图切换器 |
| `frontend/src/components/KnowledgeGraph.tsx` | 修改 | 扩展 view prop |
| `frontend/src/components/security/SecurityGraph.tsx` | 新增 | 安全图谱组件 |
| `frontend/src/components/security/SecurityEntityDetail.tsx` | 新增 | 实体详情面板 |
| `frontend/src/components/security/SecurityTimeline.tsx` | 新增 | CVE 时间线 |
| `frontend/src/components/security/ComplianceMatrix.tsx` | 新增 | 合规矩阵 |
| `frontend/src/components/security/TermStandardizer.tsx` | 新增 | 术语标准化组件 |
| `frontend/src/hooks/useSecurityGraph.ts` | 新增 | 安全图谱 hook |

### 14.2 与现有文档的交叉引用

| 现有文档 | 关联章节 |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 第 3 节（目标架构总览）、第 5 节（数据层设计） |
| [CodeGarden_PRD_v1.7.md](./CodeGarden_PRD_v1.7.md) | 第 1.3 节（与 hotspot 的关系）、第 3 节（模块边界） |
| [SPEC.md](./SPEC.md) | 第 2.2 节（分类与色值） |
| [SECURITY_KNOWLEDGE_GRAPH.md](./SECURITY_KNOWLEDGE_GRAPH.md) | 全文档（系统架构） |
| [SECURITY_KNOWLEDGE_GRAPH_PRD.md](./SECURITY_KNOWLEDGE_GRAPH_PRD.md) | 全文档（产品需求） |

### 14.3 术语表

| 术语 | 说明 |
|---|---|
| ATT&CK | MITRE Adversarial Tactics, Techniques, and Common Knowledge |
| CVE | Common Vulnerabilities and Exposures |
| CWE | Common Weakness Enumeration |
| NVD | National Vulnerability Database（美国国家漏洞数据库） |
| STIX | Structured Threat Information eXpression |
| CVSS | Common Vulnerability Scoring System |
| enrichment | 对已有数据提取/关联额外结构化信息的过程 |
| canonical term | 规范术语（标准形式） |
| synonym | 同义词 |
| taxonomy | 术语层级体系 |
| sync_bundle | WebDAV 跨端同步的数据包 |
