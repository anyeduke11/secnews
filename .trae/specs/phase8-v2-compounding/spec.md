# Phase 8 — 复利基础设施 + 资讯收藏聚合

> **版本**: v2.0 (Phase 8)
> **日期**: 2026-07-28
> **周期**: ~6 天
> **spec 路径**: `.trae/specs/phase8-v2-compounding/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.10.2
> **前置**: v1.7.6 Phase 7 (MCP Server) + v1.8 (catchup) + v1.9 (checkpoint & validation)
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md`

## 1. 背景与目标

### 1.1 背景

hotspot v1.7 的瓶颈在于：**知识库日增量 = 0**。虽然有 46 源采集、28 源活跃，但采集到的信息只停留在 `hotspots` 表，没有自动推进到 `knowledge_items` 的 5 阶段 lifecycle 闭环。用户需要手动收藏、手动标记、手动整理——复利闭环不存在。

v2.0 的核心是**让知识库每天自动增长**（日增量 ≥ 10 items/天），通过 5 阶段 + 5 触发器强制推进 lifecycle。Phase 8 是这一切的数据地基。

### 1.2 目标

1. **数据底座**：新增 4 张核心表（`content_fingerprints` / `ai_scores` / `item_entities` / `knowledge_links`），支撑去重/评分/实体链接/知识复用
2. **去重能力**：64-bit simhash + URL canonicalize，跨源去重准确率 ≥ 95%
3. **MCP tool 扩展**：4 个新 MCP tool（score_item / enrich_concept / link_items / trigger_codegarden_drift），外部 Agent 可调
4. **资讯收藏聚合视图**：5 类数据源合并 + 去重 + 分页，前端可筛选/搜索

### 1.3 不在范围内

- ❌ T1/T2 触发器实施（Phase 9）
- ❌ 状态机引擎（Phase 9）
- ❌ 可读 ID 规范化（Phase 10）
- ❌ 遗留清理（Phase 14）
- ❌ lifecycle 5 阶段迁移 SQL（`046_lifecycle_v2.sql` 已存在，Phase 9 上线前执行）

## 2. 范围

### 2.1 必做

**数据迁移（migration 043）**
- 新增 4 张表：`content_fingerprints` / `ai_scores` / `item_entities` / `knowledge_links`
- 6 个索引（按查询模式优化）

**simhash 去重**
- `backend/services/simhash.py`：64-bit simhash + Hamming distance + URL canonicalize
- 集成到 `backend/services/collection_service.py`：collect() 后立即去重
- 去重准确率 ≥ 95%（1000 条样本测试）

**4 个新 MCP tool**
- `backend/api/mcp_phase8.py`，注册 4 个 tool：
  - `score_item(hotspot_id, score, reason, scorer)` → 写 `ai_scores` 表
  - `enrich_concept(concept_name, content, source)` → 写 `concepts/{name}.md`
  - `link_items(from_id, to_id, link_type, confidence)` → 写 `knowledge_links` 表
  - `trigger_codegarden_drift(project_id)` → tech_stack 评估

**资讯收藏聚合视图**
- 后端：`backend/services/imported_aggregator.py` + `backend/api/knowledge_imported.py`
- 前端：`KnowledgeFavoritesView.tsx` + `useImported.ts` hook + 5th action card + 路由
- 5 数据源：favorites / cubox / bookmark / secnews_archive / secnews
- 筛选：5 类型 + 名称搜索 + 时间范围 + 分页

### 2.2 明确不做

- ❌ 不修改 `collection_service.py` 的 asyncio.Lock（已知问题，独立修复）
- ❌ 不改动 Proxy 配置体系
- ❌ 不实现 lifecycle 5 阶段迁移（`046_lifecycle_v2.sql` 已存在，Phase 9 执行）
- ❌ 不实现 T1/T2 触发器（Phase 9）
- ❌ 不实现可读 ID（Phase 10）

## 3. 数据模型

### 3.1 migration 043：4 张新表

```sql
-- migration 043_v2.0_fingerprints_scores.sql
-- 目的: Phase 8 复利基础设施 — 跨源去重/AI 评分/实体连接/知识复用关联

-- 1. 跨源去重
CREATE TABLE IF NOT EXISTS content_fingerprints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id    TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    simhash       BIGINT NOT NULL,              -- 64-bit simhash
    url_canonical TEXT NOT NULL,                 -- 规范化 URL
    title_norm    TEXT NOT NULL,                 -- 规范化标题
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(hotspot_id)
);
CREATE INDEX IF NOT EXISTS idx_fp_simhash ON content_fingerprints(simhash);
CREATE INDEX IF NOT EXISTS idx_fp_url_canonical ON content_fingerprints(url_canonical);

-- 2. AI 评分
CREATE TABLE IF NOT EXISTS ai_scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id  TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    score       REAL NOT NULL CHECK(score >= 0 AND score <= 10),  -- 0-10
    reason      TEXT,                                               -- LLM 可解释理由
    scorer      TEXT,                                               -- 'agent:claude-desktop' / 'agent:cursor' / 'rule'
    scored_at   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_score ON ai_scores(hotspot_id, scored_at);

-- 3. 实体连接
CREATE TABLE IF NOT EXISTS item_entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     TEXT NOT NULL,                    -- knowledge_items.id
    entity_name TEXT NOT NULL,                    -- 如 'prompt-injection'
    entity_type TEXT NOT NULL CHECK(entity_type IN (
        'concept', 'tool', 'vendor', 'person', 'cve', 'technique', 'standard', 'event'
    )),
    confidence  REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
    source      TEXT CHECK(source IN ('rule', 'agent', 'manual')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(item_id, entity_name, entity_type)
);
CREATE INDEX IF NOT EXISTS idx_entity_name ON item_entities(entity_name);
CREATE INDEX IF NOT EXISTS idx_item_id ON item_entities(item_id);

-- 4. 知识复用关联（复利核心）
CREATE TABLE IF NOT EXISTS knowledge_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_item_id    TEXT NOT NULL,
    to_item_id      TEXT NOT NULL,
    link_type       TEXT NOT NULL CHECK(link_type IN (
        'similar', 'prerequisite', 'extension', 'contradiction', 'source'
    )),
    confidence      REAL DEFAULT 0.5 CHECK(confidence >= 0 AND confidence <= 1),
    created_by      TEXT CHECK(created_by IN ('agent', 'rule', 'manual')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_item_id, to_item_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_kl_from ON knowledge_links(from_item_id);
CREATE INDEX IF NOT EXISTS idx_kl_to ON knowledge_links(to_item_id);
```

### 3.2 现有表扩展

| 表 | 变更 | 备注 |
|----|------|------|
| `knowledge_items` | 无变更（Phase 8） | 字段扩展在 Phase 16（chunks/attention_score）|
| `favorites` | 无变更 | 保持单表入口 |
| `knowledge_repo.list_items()` | 扩展筛选参数 | 新增 `sources`/`keyword`/`exclude_urls` 参数 |

## 4. API 设计

### 4.1 MCP Tool 端点（`mcp_phase8.py`）

```python
# 注册 4 个 MCP tool（读/写模式见 B.7.1）
[
    ToolDef(
        name="score_item",
        description="AI 评分：给热点打 0-10 分并附理由",
        input_schema={
            "type": "object",
            "properties": {
                "hotspot_id": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 10},
                "reason": {"type": "string"},
                "scorer": {"type": "string", "enum": ["agent:claude-desktop", "agent:cursor", "rule"]}
            },
            "required": ["hotspot_id", "score", "scorer"]
        }
    ),
    ToolDef(
        name="enrich_concept",
        description="背景补全：写入 knowledge/concepts/{name}.md",
        input_schema={
            "type": "object",
            "properties": {
                "concept_name": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string"}
            },
            "required": ["concept_name", "content"]
        }
    ),
    ToolDef(
        name="link_items",
        description="知识关联：在 two items 之间建立关联",
        input_schema={
            "type": "object",
            "properties": {
                "from_id": {"type": "string"},
                "to_id": {"type": "string"},
                "link_type": {"type": "string", "enum": ["similar", "prerequisite", "extension", "contradiction", "source"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["from_id", "to_id", "link_type"]
        }
    ),
    ToolDef(
        name="trigger_codegarden_drift",
        description="Codegarden drift 评估：检查新 tech 对项目 tech_stack 的影响",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"}
            },
            "required": ["project_id"]
        }
    )
]
```

### 4.2 资讯收藏聚合 API

```python
# GET /api/knowledge/imported?page=1&page_size=20&type=favorites&keyword=xxx&since=2026-01-01&until=2026-07-28
# 返回聚合的 5 源数据

Response:
{
    "items": [
        {
            "id": "uuid",
            "title": "...",
            "url": "...",
            "source_type": "favorites|cubox|bookmark|secnews_archive|secnews",
            "source_name": "Cubox",
            "ingested_at": "2026-07-28T10:00:00",
            "origin": "cubox | 手动收藏 | 书签导入 | 归档 | 实时"
        }
    ],
    "total": 128,
    "page": 1,
    "page_size": 20
}

# 参数说明
# - type: 筛选数据源类型（单选或多选，默认全部）
# - keyword: 标题/内容搜索（LIKE %keyword%）
# - since/until: 时间范围（ingested_at 维度）
# - page/page_size: 分页（默认 20/页，最大 100）
```

### 4.3 与 `/api/favorites` 的分工

| 端点 | 数据源 | 用途 | 前端 |
|------|--------|------|------|
| `/api/favorites` | favorites 表（单表） | 最严格"已收藏"语义，导出 xlsx 用 | HotspotCard ⭐ 按钮 |
| `/api/knowledge/imported` | 5 源聚合（favorites ∪ cubox ∪ bookmark ∪ secnews_archive ∪ secnews） | "看看我导入了什么"全景视图 | KnowledgeFavoritesView 页面 |

## 5. 架构设计

### 5.1 simhash 去重流程

```
collect() 完成
    ↓
URL canonicalize（去除 tracking params、hash、统一协议）
    ↓
title 规范化（小写、去除标点、trim）
    ↓
64-bit simhash 计算
    ↓
Hamming distance 与已有指纹对比（阈值 < 5）
    ↓
重复 → 跳过（记录 duplicate_count）
不重复 → 插入 content_fingerprints → 继续入库
```

### 5.2 MCP tool 副作用模式

所有 4 个新 MCP tool 遵循**副作用模式**（一次调用完成完整业务）：

- `score_item`：写入 `ai_scores` 表 → 返回 `{status: "ok", score_id: N}`
- `enrich_concept`：写入 `concepts/{name}.md` 文件 → 返回 `{status: "ok", file: "concepts/{name}.md"}`
- `link_items`：写入 `knowledge_links` 表 + 更新 `knowledge_items.knowledge_links` 计数 → 返回 `{status: "ok", link_id: N}`
- `trigger_codegarden_drift`：评估 project tech_stack → 触发事件 → 返回 `{status: "ok", drift_score: 0.8}`

### 5.3 资讯收藏聚合数据流

```
请求 /api/knowledge/imported
    ↓
imported_aggregator.py:
  ├─ favorites_repo.list()         → 来源 favorites
  ├─ knowledge_repo.list_items()   → 来源 secnews（filter by source）
  ├─ 读取 cubox 缓存文件           → 来源 cubox
  ├─ 读取 bookmark JSON 文件       → 来源 bookmark
  └─ 读取 secnews_archive 标记     → 来源 secnews_archive
    ↓
合并 → 去重（URL 去重） → 排序（ingested_at DESC）→ 分页 → 返回
```

## 6. 测试策略

| 测试文件 | 用例数 | 覆盖 |
|---------|--------|------|
| `test_simhash.py` | 5 | simhash 碰撞、Hamming 距离、URL canonicalize、空输入、边界 |
| `test_mcp_phase8.py` | 8 | 4 tool × 2 用例（正常 + 异常）|
| `test_fingerprint.py` | 5 | 指纹写入、去重检测、重复跳过、索引验证 |
| `test_imported_aggregator.py` | 8 | 5 源合并、去重、分页、keyword 筛选、type 筛选、时间范围、边界 |
| `test_knowledge_imported_api.py` | 7 | API 参数、分页、错误处理、空结果 |
| `KnowledgeFavoritesView.test.tsx` | 5 | 渲染、筛选、搜索、分页、空状态 |

## 7. 验收标准

| 维度 | 验收 |
|------|------|
| **数据迁移** | 4 张新表 schema 校验通过，CRUD 全过 |
| **simhash 去重** | 1000 条样本去重准确率 ≥ 95% |
| **MCP tool** | 13 tool 全部通过外部 Agent 调通（9 保留 + 4 新增）|
| **MCP tool 性能** | score_item 写入 P95 < 500ms |
| **资讯收藏聚合** | 5 类型 + 名称 + 时间 + 分页 e2e 8 用例通过 |
| **聚合 API 性能** | P95 < 300ms |
| **去重集成** | collect() 后重复内容自动跳过，unit test 5 用例通过 |

## 8. 依赖与前置

| 任务 | 前置依赖 | 可并行 |
|------|---------|--------|
| 8.1 migration 043 | 无 | ✅ 与 8.2 并行 |
| 8.2 simhash 实现 | 无 | ✅ 与 8.1 并行 |
| 8.3 去重集成 | 8.2 | ❌ |
| 8.4-8.7 MCP tool | 8.1 | ✅ 与 8.2/8.9 并行 |
| 8.8 测试 | 8.1~8.7 | ❌ |
| 8.9 收藏聚合后端 | 无 | ✅ 与 8.1~8.7 并行 |
| 8.10 收藏聚合前端 | 8.9 | ❌ |
| 8.11 收藏聚合 e2e | 8.10 | ❌ |