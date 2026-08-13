# Phase 14 — 子系统联动

> **版本**: v2.0 (Phase 14)
> **日期**: 2026-07-31
> **周期**: ~3 天
> **spec 路径**: `.trae/specs/phase14-subsystem-linkage/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.10.7
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md` Phase 14
> **前置**: Phase 12 (T3/T4/T5 触发器 + 告警系统) ✅, Phase 13 (复利可视化 + 4 模式) ✅
> **里程碑**: M3 — 抓取现代化 + 子系统联动

---

## 1. 背景与目标

### 1.1 背景

Phase 8-13 完成了知识子系统的 5 阶段生命周期闭环、告警系统、复利可视化和规划引导，但三个子系统（Knowledge / Codegarden / Security）之间仍相互隔离：

- **Knowledge → Codegarden**: 知识库中提取的 tech_stack 实体（如 fastapi、react）应自动触发 Codegarden 项目技术栈漂移评估，判断是否更新项目配置
- **Knowledge → Security**: 知识库中提取的 CVE 实体（entity_type=cve）应自动同步到 security_entities 表，避免安全图谱数据滞后
- **Security → Knowledge**: security_entities 中的 CVE 节点应引用 knowledge items 中的对应实体，形成双向引用
- **跨域 entity 命名空间**: 不同子系统使用相同的 entity_type 枚举值（concept/tool/vendor/person/cve/technique/standard/event），但缺乏统一约束

### 1.2 目标

1. **tech_stack_drift 任务**: 知识库新 tech → Codegarden 项目评估，判断是否需更新 tech_stack
2. **CVE 双向同步**: Knowledge item_entities 的 CVE → security_entities 同步，双向去重 + 重试
3. **跨域 entity 命名空间**: 统一 entity_type 枚举为 8 种类型，确保所有子系统使用一致
4. **Security Graph 引用 Knowledge**: security_entities 中 CVE 节点的 metadata 字段引用 knowledge item_entities 对应记录
5. **测试**: 15+ 联动场景用例

### 1.3 不在范围内

- ❌ 修改现有 T1-T5 触发器实现
- ❌ 修改告警引擎
- ❌ 修改 security_entities 表结构（不新增迁移）
- ❌ 修改 knowledge_items 表结构
- ❌ 修改 cg_projects 表结构

---

## 2. 范围

### 2.1 必做

**tech_stack_drift 任务（Task 14.1）**
- `backend/services/codegarden_drift.py`
- 扫描 knowledge_items 表，提取 item_entities 中 entity_type='tool' 的实体名
- 与 cg_projects 表的 tech_stack（JSON 数组）对比
- 若发现新 tech（存在于 knowledge 但不在 tech_stack 中）→ 插入评估记录到 cg_drift_assessments 表
- 返回 drift 报告：new_techs, affected_projects, matched_count
- 可通过 API 或 scheduler job 触发

**CVE 双向同步（Task 14.2）**
- `backend/services/cve_knowledge_sync.py`
- 从 knowledge_items 的 item_entities 中提取 entity_type='cve' 的记录
- 检查 security_entities 表中是否已存在同名 CVE（name = CVE编号）
- 若不存在 → 插入 security_entities 记录（entity_type='cve'）
- 若存在但 metadata 未引用 knowledge → 更新 metadata JSON 追加 knowledge_ref
- 支持重试（失败时记录日志，不阻塞）
- 双向去重：同一 CVE 编号在 security_entities 中只保留一条记录

**跨域 entity 命名空间（Task 14.3）**
- 统一 entity_type 枚举值（现有 8 种）：
  - concept / tool / vendor / person / cve / technique / standard / event
- 检查 item_entities 表（migration 043 已有 CHECK 约束）
- 检查 security_entities 表（已有 entity_type 字段但无 CHECK 约束）
- 添加 migration 050 对 security_entities.entity_type 添加 CHECK 约束
- 更新现有记录的 entity_type 值（若不符合新枚举）

**Security Graph 引用 Knowledge（Task 14.4）**
- 修改 `security/graph.py` 的 `_load_cve_nodes()` 方法
- 在 CVE 节点返回数据中包含 knowledge_ref 字段（从 metadata JSON 提取）
- 在 `_build_knowledge_edges()` 中添加 security_entity → knowledge_item 的边
- 确保 security graph API 返回的 CVE 节点包含 knowledge 链接信息

**测试（Task 14.5）**
- test_codegarden_drift.py — 5 用例
- test_cve_knowledge_sync.py — 5 用例
- test_entity_namespace.py — 3 用例
- test_security_graph_knowledge.py — 2 用例
- 总计 15+ 用例

### 2.2 明确不做

- ❌ 不修改告警引擎（Phase 12 已完成）
- ❌ 不新增 migration 以外的表结构
- ❌ 不做 tech_stack_drift 自动触发（手动触发 + scheduler 可选）
- ❌ 不做 CVE 反向同步（security → knowledge）
- ❌ 不修改 MITRE ATT&CK 同步逻辑

---

## 3. 数据模型

### 3.1 新表 `cg_drift_assessments`（migration 050）

```sql
-- migration 050_v2.0_drift_assessments.sql
-- 目的: tech_stack_drift 评估记录表

CREATE TABLE IF NOT EXISTS cg_drift_assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,               -- cg_projects.id
    tech_name       TEXT NOT NULL,               -- 发现的新技术栈名称
    source_item_id  TEXT,                        -- 来源 knowledge_items.id
    source_domain   TEXT,                        -- 来源 domain (如 security, ai)
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                        'pending', 'reviewed', 'applied', 'dismissed'
                    )),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at     TEXT,
    notes           TEXT,
    UNIQUE(project_id, tech_name)
);
CREATE INDEX IF NOT EXISTS idx_cg_drift_status ON cg_drift_assessments(status);
```

### 3.2 Migration 050 扩展: security_entities CHECK 约束

```sql
-- 对 security_entities.entity_type 添加 CHECK 约束
-- 仅在 SQLite 支持的情况下做（可通过应用层校验替代）
-- 此处使用应用层校验，不修改已有 migration
```

### 3.3 现有字段复用

- `item_entities.entity_type` — 8 种枚举值，区分 entity 类型
- `item_entities.entity_name` — CVE 编号/技术栈名称等
- `security_entities.entity_type` — 安全实体类型
- `security_entities.name` — CVE 编号
- `security_entities.metadata` — JSON 字段，用于存储 knowledge_ref
- `cg_projects.tech_stack` — JSON 数组，项目技术栈列表
- `knowledge_items.domain` — 来源域，用于 drift 评估

---

## 4. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/codegarden/drift/assess` | 触发 tech_stack drift 评估 |
| GET | `/api/codegarden/drift/assessments` | 获取 drift 评估列表 |
| PUT | `/api/codegarden/drift/assessments/{id}` | 更新评估状态 (reviewed/applied/dismissed) |
| POST | `/api/cve/sync` | 触发 CVE 双向同步 |

---

## 5. 实现细节

### 5.1 tech_stack_drift 任务

```
func assess_drift():
  1. 扫描 knowledge_items 表，JOIN item_entities WHERE entity_type='tool'
  2. 按 entity_name 分组，统计每个 tech 出现在多少个 knowledge items 中
  3. 对于每个 tech，查询 cg_projects WHERE tech_stack LIKE '%tech_name%'
  4. 若 tech 不在任何项目的 tech_stack 中 → 跳过（新 tech 但无项目使用）
  5. 若 tech 在某个项目的 tech_stack 中 → 记录为"已匹配"（无需动作）
  6. 返回报告: {new_techs: [...], affected_projects: [...], matched_count: N}
  
  注意: 不自动修改 cg_projects.tech_stack，仅记录评估结果到 cg_drift_assessments
```

### 5.2 CVE 双向同步

```
func sync_cve_to_security():
  1. 查询 item_entities WHERE entity_type='cve'
  2. 对每个 entity_name（即 CVE 编号）:
     a. 查询 security_entities WHERE entity_type='cve' AND name=entity_name
     b. 若不存在 → INSERT INTO security_entities (id, entity_type, name, metadata)
        - id: 自动生成 UUID 或使用 'CVE-YYYY-NNNN' 格式
        - metadata: {"knowledge_refs": ["item_id_1", "item_id_2"]}
     c. 若存在但 metadata 不包含当前 item_id → UPDATE metadata
  3. 返回报告: {synced: N, already_exists: N, updated: N, failed: N}
```

### 5.3 Security Graph 引用 Knowledge

```
修改 _load_cve_nodes() 方法:
  - 原有查询: SELECT * FROM security_entities WHERE entity_type='cve'
  - 新增: 对每个 CVE 节点，从 metadata JSON 提取 knowledge_refs
  - 若 knowledge_refs 存在 → 将节点标记为 linked=true
  - 在节点属性中添加 knowledge_count = len(knowledge_refs)

修改 _build_knowledge_edges() 方法:
  - 遍历 knowledge_item 节点，检查其 cve_ids 字段
  - 对每个 cve_id，查找 security_entities 中对应 entity
  - 添加 edge: source=knowledge_item_id, target=security_entity_id, edge_type='references'
```

---

## 6. 测试计划

### 6.1 tech_stack_drift 测试（5 用例）

| 用例 | 验证 |
|------|------|
| test_drift_detect_new_tech | 发现新 tech 时生成评估记录 |
| test_drift_no_matching_project | 无匹配项目时跳过 |
| test_drift_already_matched | 已匹配的 tech 不重复评估 |
| test_drift_status_update | 评估状态可更新 |
| test_drift_api_endpoint | POST /api/codegarden/drift/assess 返回报告 |

### 6.2 CVE 同步测试（5 用例）

| 用例 | 验证 |
|------|------|
| test_sync_new_cve | 新 CVE 插入 security_entities |
| test_sync_existing_cve | 已存在的 CVE 跳过 |
| test_sync_update_metadata | 已有 CVE 更新 knowledge_ref |
| test_sync_no_duplicate | 同 CVE 不重复插入 |
| test_sync_api_endpoint | POST /api/cve/sync 返回报告 |

### 6.3 跨域 entity 命名空间测试（3 用例）

| 用例 | 验证 |
|------|------|
| test_entity_types_enum | 8 种 entity_type 枚举值一致 |
| test_item_entities_valid | item_entities 记录符合枚举 |
| test_security_entities_valid | security_entities 记录符合枚举 |

### 6.4 Security Graph 引用测试（2 用例）

| 用例 | 验证 |
|------|------|
| test_cve_node_knowledge_ref | CVE 节点含 knowledge_ref 属性 |
| test_knowledge_edge_created | knowledge 与 security 间有边 |

### 6.5 回归测试

- Phase 12 告警引擎测试 15/15 PASS
- Phase 13 规划服务测试 8/8 PASS
- 前端全量测试通过

---

## 7. 验收标准

### 7.1 单元测试门禁

- tech_stack_drift 测试: 5/5 PASS
- CVE 同步测试: 5/5 PASS
- 跨域 entity 命名空间测试: 3/3 PASS
- Security Graph 引用测试: 2/2 PASS
- **总计**: 15+ 用例全 PASS

### 7.2 行为验收

- POST /api/codegarden/drift/assess 返回 drift 报告
- CVE 从 knowledge item_entities 同步到 security_entities
- security_entities 中 CVE 节点 metadata 含 knowledge_refs
- Security Graph 返回的 CVE 节点含 knowledge_count 属性
- 跨域 entity_type 8 种枚举值一致

### 7.3 回归测试

- Phase 12 告警测试不退化
- Phase 13 规划服务测试不退化
- 前端全量测试通过