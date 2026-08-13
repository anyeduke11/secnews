# Checklist — Phase 14 子系统联动

## Migration 050
- [x] `cg_drift_assessments` 表创建成功，含 status CHECK 约束和 UNIQUE 索引
- [x] `idx_cg_drift_status` 索引创建成功

## Tech Stack Drift 服务
- [x] `assess_drift()` 扫描 knowledge_items + item_entities 并生成评估报告
- [x] `get_assessments()` 返回评估列表
- [x] `update_assessment_status()` 更新状态成功
- [x] 无匹配项目时不生成评估记录
- [x] 已匹配的 tech 不重复评估

## CVE 同步服务
- [x] 新 CVE 插入 security_entities 成功
- [x] 已存在的 CVE 跳过，不重复插入
- [x] 已有 CVE 更新 metadata 追加 knowledge_refs
- [x] 同步失败时记录日志，不阻塞

## API 端点
- [x] POST `/api/codegarden/drift/assess` 返回 drift 报告
- [x] GET `/api/codegarden/drift/assessments` 返回评估列表
- [x] PUT `/api/codegarden/drift/assessments/{id}` 更新状态成功
- [x] POST `/api/cve/sync` 返回同步报告
- [x] 新路由已注册到 `backend/api/__init__.py`

## Security Graph 引用 Knowledge
- [x] CVE 节点含 knowledge_count 和 linked 属性
- [x] knowledge_item → security_entity 的 references 边存在

## 测试
- [x] test_codegarden_drift.py 5/5 PASS
- [x] test_cve_knowledge_sync.py 5/5 PASS
- [x] test_entity_namespace.py 3/3 PASS
- [x] test_security_graph_knowledge.py 2/2 PASS
- [x] 总计 15 用例 PASS

## 验收标准
- [x] POST /api/codegarden/drift/assess 返回格式正确的 drift 报告
- [x] CVE 从 knowledge item_entities 同步到 security_entities
- [x] security_entities 中 CVE 节点 metadata 含 knowledge_refs
- [x] Security Graph 返回的 CVE 节点含 knowledge_count 属性
- [x] 跨域 entity_type 8 种枚举值一致