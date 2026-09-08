---
status: draft
target_version: v0.6
phase: SecNews Integration / W0-W2
related_code: backend/kl_pipeline/;backend/services/ai_hub.py;backend/repository/kl_queue_repo.py
depends_on: docs/HOTSPOT_SECNEWS_INTEGRATION.md;docs/v0.5_refactor_plan/README.md
owner: integration
last_reviewed: 2026-08-24
---

# SecNews 整合执行任务清单
## Phase 0 — 基础层（W0-W2）

> **对接方案**：`docs/HOTSPOT_SECNEWS_INTEGRATION.md` §3 Phase 0
> **执行前提**：v0.5 M1-M5 已完成（基线 2662 tests, 0.5.0 版本）

---

## S0-1: 新建 `backend/kl_pipeline/` 包结构

**目标**：建立 KL 管线引擎的 Python 包骨架

### 文件清单

| 文件 | 行数目标 | 职责 |
|------|---------|------|
| `backend/kl_pipeline/__init__.py` | 10 | re-export KLPipeline + Stage |
| `backend/kl_pipeline/engine.py` | ~200 | KLPipeline 主类（五阶段状态机） |
| `backend/kl_pipeline/queue.py` | ~120 | kl_queue 表 DAO（enqueue/due/mark_run/mark_done/mark_error） |
| `backend/kl_pipeline/stages/__init__.py` | 5 | re-export |
| `backend/kl_pipeline/stages/refine.py` | ~80 | 轻 AI refine（prompt + JSON 解析 + frontmatter 回写） |
| `backend/kl_pipeline/stages/link.py` | ~80 | FTS 共现 + concept slug 匹配 → related 边 |
| `backend/kl_pipeline/stages/structure.py` | ~60 | 概念卡提取 + graph.json 更新 |
| `backend/kl_pipeline/stages/publish.py` | ~50 | 终态标记 + 复习调度 |
| `backend/kl_pipeline/obs/__init__.py` | 5 | re-export |
| `backend/kl_pipeline/obs/funnel.py` | ~60 | 五阶段漏斗统计 |
| `backend/kl_pipeline/obs/ledger.py` | ~50 | token 台账 |

### engine.py 核心接口

```python
class KLPipeline:
    def __init__(self, wiki_fs, db_session, llm_client):
        ...

    def kickoff(self, item_id: str) -> None:
        """新条目入队 kl:refine（45s 延迟）"""

    def drain_due(self, limit: int = 20) -> dict:
        """消费到期任务，返回 {done, failed}"""

    def advance(self, item_id: str) -> str:
        """手动推进一条到下一阶段，返回新阶段名"""

    def sweep(self) -> int:
        """每日兜底：滞留条目重新入队，返回入队数"""

    def retry_errors(self, wiki_id: str | None = None) -> int:
        """error 任务重排为 pending，返回重排数"""
```

### queue.py 核心接口

```python
class KLQueue:
    def __init__(self, db):
        self.db = db

    def enqueue_unique(self, item_id: str, stage: str, next_run: datetime) -> bool:
        """幂等入队（item_id + stage 唯一），返回是否新增"""

    def due(self, limit: int) -> list[dict]:
        """返回到期任务列表（status=pending, next_run_at <= now）"""

    def mark_run(self, queue_id: int) -> None:
        """标记为运行中"""

    def mark_done(self, queue_id: int) -> None:
        """标记为完成，删除行"""

    def mark_error(self, queue_id: int, error: str) -> None:
        """标记为失败，记录 error"""

    def stats(self) -> dict:
        """各状态计数"""
```

### 验收标准
- [ ] `ls backend/kl_pipeline/` 列出全部文件
- [ ] `python -c "from backend.kl_pipeline import KLPipeline; print('OK')"` 不报错
- [ ] `wc -l backend/kl_pipeline/*.py` 每个文件 < 200 行
- [ ] `pytest backend/tests/test_kl_pipeline.py -v` 至少 5 个基础用例全绿

---

## S0-2: 新建 `backend/wiki_fs/` 包结构

**目标**：Python 移植 wiki 文件系统（原 TypeScript fsstore.ts）

### 文件清单

| 文件 | 行数目标 | 职责 |
|------|---------|------|
| `backend/wiki_fs/__init__.py` | 10 | re-export WikiFs |
| `backend/wiki_fs/contract.py` | ~60 | frontmatter 契约子集（稳定序序列化） |
| `backend/wiki_fs/store.py` | ~150 | items/ concepts/ inbox/ quarantine 读写 |
| `backend/wiki_fs/migrate.py` | ~100 | 从 llm-wiki-2.0 一次性迁移 |
| `backend/wiki_fs/linker.py` | ~80 | concept-linker（FTS 共现 → 权重边） |

### store.py 核心接口

```python
class WikiFs:
    def __init__(self, root: str):
        """root 指向 knowledge/ 目录"""

    def list_ids(self) -> list[str]:
        """列出所有 item id（不含 .md 扩展名）"""

    def read_item(self, item_id: str) -> dict | None:
        """返回 {"fm": dict, "body": str} 或 None"""

    def write_item(self, item_id: str, doc: dict) -> None:
        """原子写入（.tmp → rename），frontmatter 稳定序"""

    def ingest_url(self, url: str, title: str, text: str) -> dict:
        """URL 导入 → kl:raw → 返回 {"id": str, "title": str}"""

    def import_bookmarks(self, html: str) -> dict:
        """Netscape HTML → items → 返回 {"added": int, "dup": int}"""

    def scan_inbox(self) -> dict:
        """扫描 inbox/ → 移入 items/ 或 quarantine/"""

    def list_concepts(self) -> list[dict]:
        """列出所有概念卡"""

    def create_concept(self, concept_id: str, name: str, tags: list[str]) -> None:
        """创建概念卡"""

    def find_related(self, item_id: str, top_k: int = 10) -> list[dict]:
        """FTS 共现查询，返回 [{id, weight}]"""
```

### 验收标准
- [ ] `python -c "from backend.wiki_fs import WikiFs; print('OK')"` 不报错
- [ ] 创建临时 WikiFs → write_item → read_item → fm/body 一致
- [ ] 块序列 frontmatter 解析正确（source_items/tags 块列表）
- [ ] `import_bookmarks` 处理测试 HTML → added > 0

---

## S0-3: 增强 `backend/enrich_v2.py`

**目标**：在现有 enrich 基础上增加 CVE/ATT&CK/合规/到期时间抽取

### 新增正则规则

```python
# 新增到 enrich_v2.py
CVE_PATTERN = r'CVE-\d{4}-\d{4,7}'
ATTACK_PATTERN = r'\bT\d{4}(\.\d{3})?\b'  # MITRE ATT&CK 技术 ID
COMPLIANCE_PATTERN = r'等保|关基|数据安全法|网络安全法|等级保护|GB/T|ISO 27001|SOC 2'
DEADLINE_PATTERN = r'(?:截止|到期|deadline)[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})'
BID_STATUS_PATTERN = r'(?:招标|中标|成交|变更|终止|询价|比选)'
```

### API 接入

在 `backend/api/enrich.py` 中：
```python
@router.post("/enrich/cve")
async def enrich_cve(title: str, summary: str) -> dict:
    """仅抽取 CVE 编号 + 上下文"""
```

### 验收标准
- [ ] "CVE-2026-1234" → 匹配正确
- [ ] "T1566.001" → 匹配正确
- [ ] "等保三级" → 匹配合规标签
- [ ] "截止：2026-09-01" → 提取日期
- [ ] 误报率 < 5%（ATT&CK 需上下文约束）

---

## S0-4: 新建 `backend/secnews_dashboard.py`

**目标**：安全看板数据聚合服务（feed/pipeline/knowledge/stats）

### 接口定义

```python
class SecNewsDashboard:
    def __init__(self, db, wiki_fs, pipeline):
        ...

    def get_feed(self, category: str = "", keyword: str = "", limit: int = 30) -> dict:
        """报纸风 Feed 数据（按 ingested_at DESC 排序）"""

    def get_pipeline_stats(self) -> dict:
        """管线观测数据（漏斗 + 队列 + 死信 + token 台账）"""

    def get_knowledge_stats(self) -> dict:
        """知识库统计（items 数 / concepts 数 / 各 lifecycle 分布）"""

    def get_dashboard_stats(self) -> dict:
        """看板总览（今日新增 / 管线健康度 / top 分类 / 最近 refine）"""
```

### 验收标准
- [ ] `python -c "from backend.secnews_dashboard import SecNewsDashboard; print('OK')"` 不报错
- [ ] `get_feed()` 返回包含 items 列表 + 总数
- [ ] `get_pipeline_stats()` 返回 funnel + queue + ledger

---

## S0-5: 新建 `backend/api/kl_pipeline_api.py`

**目标**：KL 管线 REST API

### 路由清单

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/kl/import/url` | URL 导入（抓取 → kl:raw） |
| POST | `/api/kl/import/bookmarks` | 书签 HTML 导入 |
| POST | `/api/kl/inbox/scan` | inbox 扫描入库 |
| GET | `/api/kl/pipeline/stats` | 漏斗 + 队列 + 死信 + token 台账 |
| POST | `/api/kl/pipeline/drain` | 手动消费到期任务 |
| POST | `/api/kl/pipeline/advance` | 单条推进到下一阶段 |
| POST | `/api/kl/pipeline/retry` | 死信重试 |
| GET | `/api/kl/items/{id}` | wiki 条目详情 |
| PUT | `/api/kl/items/{id}` | 更新 frontmatter（单向投影） |
| GET | `/api/kl/concepts` | 概念卡列表 |
| GET | `/api/kl/graph` | 知识图谱边 |

### 请求/响应示例

```json
// POST /api/kl/import/url
// Request: {"url": "https://..."}
// Response: {"id": "item-abc123", "title": "..."}

// GET /api/kl/pipeline/stats
// Response:
{
  "funnel": [
    {"stage": "kl:raw", "count": 4149},
    {"stage": "kl:refine", "count": 1200},
    ...
  ],
  "queue": {"pending": 23, "running": 2, "failed": 3},
  "errors": [...],
  "alive": {"total": 100, "alive": 80, "dead": 10, "unknown": 10},
  "ledger": [...]
}
```

### 验收标准
- [ ] `curl -X POST http://localhost:8000/api/kl/import/url -d '{"url":"https://..."}'` 返回 id + title
- [ ] `curl http://localhost:8000/api/kl/pipeline/stats` 返回有效 JSON
- [ ] `curl http://localhost:8000/api/kl/items/{id}` 返回 frontmatter + body
- [ ] 错误时返回 `{"detail": {"message": "...", "missing": "..."}}` 格式

---

## S0-6: 新建 `backend/api/secnews_dashboard_api.py`

**目标**：安全看板数据聚合 API

### 路由清单

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/secnews/feed` | 报纸风 Feed 数据 |
| GET | `/api/secnews/pipeline` | 管线面板数据 |
| GET | `/api/secnews/knowledge` | 知识浏览数据 |
| GET | `/api/secnews/stats` | 看板统计 |

### 验收标准
- [ ] 4 个路由全部返回有效 JSON
- [ ] 注册到 `backend/api/__init__.py` 的 `register_routers()`
- [ ] `pytest backend/tests/ -k secnews -q` 至少 4 个 API 测试通过

---

## S0-7: 前端新建 `frontend/src/components/secnews/` 组件目录

**目标**：安全看板前端组件骨架

### 文件清单

| 文件 | 职责 |
|------|------|
| `layout/SecNewsShell.tsx` | 看板壳组件（三层导航 + 子路由） |
| `layout/SecNewsHeader.tsx` | 看板页头（标题 + 日期 + 刷新按钮） |
| `feed/FeedView.tsx` | 报纸风 Feed 视图 |
| `feed/FeedCard.tsx` | 单条卡片 |
| `feed/FeedFilters.tsx` | 分类/时间/关键词筛选 |
| `pipeline/PipelineView.tsx` | 管线观测台壳 |
| `pipeline/FunnelBar.tsx` | 五阶段横条 |
| `pipeline/QueueCard.tsx` | 队列卡片 |
| `pipeline/TokenLedger.tsx` | token 台账表 |
| `knowledge/WikiBrowser.tsx` | wiki 浏览 |
| `knowledge/InboxScanner.tsx` | inbox 扫描入口 |
| `settings/CollectionSettings.tsx` | 采集源管理 |
| `settings/PipelineSettings.tsx` | 管线参数配置 |

### 验收标准
- [ ] `ls frontend/src/components/secnews/` 列出全部组件
- [ ] 每个组件至少导出且无 TS 编译错误
- [ ] `npx tsc --noEmit` 通过

---

## S0-8: 前端新增 `/secnews` 路由

**目标**：安全看板路由接入

### 修改文件

**`frontend/src/routes/lazy-imports.ts`** 新增：
```tsx
export const SecNewsShell = React.lazy(() =>
  import('../components/secnews/layout/SecNewsShell').then(m => ({ default: m.SecNewsShell }))
);
export const SecNewsFeed = React.lazy(() =>
  import('../components/secnews/feed/FeedView').then(m => ({ default: m.FeedView }))
);
export const SecNewsPipeline = React.lazy(() =>
  import('../components/secnews/pipeline/PipelineView').then(m => ({ default: m.PipelineView }))
);
export const SecNewsKnowledge = React.lazy(() =>
  import('../components/secnews/knowledge/WikiBrowser').then(m => ({ default: m.WikiBrowser }))
);
```

**`frontend/src/routes/index.tsx`** 新增路由组：
```tsx
<Route path="/secnews" element={<Suspense fallback={<PageFallback />}><P.SecNewsShell /></Suspense>}>
  <Route index element={<Navigate to="feed" replace />} />
  <Route path="feed" element={<Suspense fallback={<PageFallback />}><P.SecNewsFeed /></Suspense>} />
  <Route path="pipeline" element={<Suspense fallback={<PageFallback />}><P.SecNewsPipeline /></Suspense>} />
  <Route path="knowledge" element={<Suspense fallback={<PageFallback />}><P.SecNewsKnowledge /></Suspense>} />
</Route>
```

### 验收标准
- [ ] `http://localhost:8898/secnews` 可访问（显示看板壳）
- [ ] `/secnews/feed` 显示 Feed 视图
- [ ] `/secnews/pipeline` 显示 Pipeline 视图
- [ ] `/secnews/knowledge` 显示 Wiki 浏览视图
- [ ] 路由切换无白屏（Suspense fallback 正常）

---

## S0-9: 数据库迁移

**目标**：新增 kl_queue + token_ledger + wiki_items_fts

### 迁移文件

```sql
-- backend/repository/migrations/070_kl_pipeline.sql

-- KL 管线任务队列
CREATE TABLE IF NOT EXISTS kl_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    next_run_at TEXT,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(item_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_kl_stage_status ON kl_queue(stage, status, next_run_at);

-- Token 消耗台账
CREATE TABLE IF NOT EXISTS token_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    item_id TEXT,
    model TEXT,
    provider TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ledger_item ON token_ledger(item_id, created_at);

-- wiki_items 全文检索
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_items_fts USING fts5(
    title, summary, tags, content,
    tokenize='porter unicode61'
);
```

### 验收标准
- [ ] `sqlite3 backend/hotspot.db ".tables"` 包含 kl_queue + token_ledger + wiki_items_fts
- [ ] `sqlite3 backend/hotspot.db ".schema kl_queue"` 显示完整 schema
- [ ] `pytest backend/tests/test_kl_pipeline.py -q` 迁移测试通过

---

## S0-10: LayerNav 新增「安全看板」入口按钮

**目标**：在顶层导航增加安全看板入口

### 修改文件

**`frontend/src/components/judge/JudgeLayerPage.tsx`** 或新建共享导航：
- 在 LayerNav 组件中增加第四个入口「安全看板」
- 图标：shield 图标
- 路由：`/secnews/feed`

### 验收标准
- [ ] 顶部导航栏可见「安全看板」按钮
- [ ] 点击跳转到 `/secnews/feed`
- [ ] 当前所在 Tab 高亮

---

## S0-11: DataLayerPage 新增「安全看板」快捷入口卡片

**目标**：在资料层首页增加安全看板入口

### 修改文件

**`frontend/src/components/data/DataLayerPage.tsx`**：
```tsx
{features.secnews && (
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
)}
```

### 验收标准
- [ ] DataLayerPage 显示「安全看板」卡片
- [ ] 点击跳转到 `/secnews/feed`
- [ ] feature_gates.toml 中 secnews=false 时卡片隐藏

---

## Phase 0 总验收

```bash
# 后端
.venv/bin/python -m pytest backend/tests/ --tb=short -q  # ≥2662, 0 error
.venv/bin/python -c "from backend.kl_pipeline import KLPipeline; from backend.wiki_fs import WikiFs; print('OK')"

# 前端
cd frontend && npx tsc --noEmit  # 0 TS errors
cd frontend && npx vitest run   # 全绿

# 数据库
sqlite3 backend/hotspot.db ".tables" | grep -E "kl_queue|token_ledger|wiki_items_fts"  # 3 表全有

# 路由
curl -s http://localhost:8000/api/kl/pipeline/stats | python -m json.tool  # 有效 JSON
curl -s http://localhost:8898/secnews | grep -i "security"  # 页面包含安全看板
```

---

*Phase 0 完成后，继续 Phase 1（管线引擎 + 书签导入 + Pipeline UI）*
