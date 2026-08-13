# Tasks — Phase 14 子系统联动

## 任务列表

### Task 14.1: 创建 migration 050 (cg_drift_assessments + entity_type 约束)
- [x] 创建 `backend/repository/migrations/050_v2.0_drift_assessments.sql`
  - `cg_drift_assessments` 表（含 status CHECK 约束、UNIQUE(project_id, tech_name)）
  - 索引 `idx_cg_drift_status`
  - 应用层 entity_type 校验函数（不修改已执行的 migration）

### Task 14.2: 创建 tech_stack drift 服务
- [x] 创建 `backend/services/codegarden_drift.py`
  - `assess_drift()` 函数：扫描 knowledge_items + item_entities → 对比 cg_projects.tech_stack → 写入 cg_drift_assessments
  - `get_assessments()` 查询评估列表
  - `update_assessment_status()` 更新状态
  - 返回 drift 报告格式：{new_techs, affected_projects, matched_count}

### Task 14.3: 创建 CVE 同步服务
- [x] 创建 `backend/services/cve_knowledge_sync.py`
  - `sync_cve_to_security()` 函数：item_entities(entity_type='cve') → security_entities 同步
  - 去重逻辑：同 CVE 编号只保留一条记录
  - metadata 更新：追加 knowledge_refs
  - 返回报告：{synced, already_exists, updated, failed}

### Task 14.4: 创建 drift API 端点
- [x] 新建 `backend/api/codegarden_phase14.py`
  - POST `/api/codegarden/drift/assess` — 触发 drift 评估
  - GET `/api/codegarden/drift/assessments` — 获取评估列表
  - PUT `/api/codegarden/drift/assessments/{id}` — 更新状态
  - POST `/api/cve/sync` — 触发 CVE 同步
- [x] 注册新路由到 `backend/api/__init__.py`

### Task 14.5: 修改 Security Graph 引用 Knowledge
- [x] 修改 `backend/security/graph.py`
  - `_load_cve_nodes()`: 从 metadata 提取 knowledge_refs，添加 knowledge_count 和 linked 属性
  - `_build_knowledge_edges()`: 添加 knowledge_item → security_entity 的 references 边

### Task 14.6: 添加 scheduler job（可选，DP2）
- [x] 修改 `backend/scheduler/jobs.py` + `backend/scheduler/scheduler.py`
  - Job 38: `cg_drift_assess` — IntervalTrigger(seconds=3600)
  - Job 39: `cve_sync_to_security` — IntervalTrigger(seconds=1800)

### Task 14.7: 编写测试（15+ 用例）
- [x] 创建 `backend/tests/test_codegarden_drift.py` — 5/5 PASS
- [x] 创建 `backend/tests/test_cve_knowledge_sync.py` — 5/5 PASS
- [x] 创建 `backend/tests/test_entity_namespace.py` — 3/3 PASS
- [x] 创建 `backend/tests/test_security_graph_knowledge.py` — 2/2 PASS
- [x] 运行全部 15 测试，全部 PASS

## 任务依赖关系
- Task 14.1（migration）→ Task 14.2（drift 服务）→ Task 14.4（drift API）
- Task 14.1（migration）→ Task 14.3（CVE 同步）→ Task 14.4（CVE API）
- Task 14.3（CVE 同步）→ Task 14.5（Security Graph 引用）
- Task 14.6（scheduler）在 Task 14.2/14.3 完成后可选
- Task 14.7（测试）依赖所有其他任务

## 并行化建议
- Task 14.1（migration）、Task 14.2（drift 服务）、Task 14.3（CVE 同步）可并行
- Task 14.4（API）需等待 Task 14.2/14.3
- Task 14.5（Security Graph）需等待 Task 14.3
- Task 14.7（测试）最后执行