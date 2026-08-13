# Tasks — Phase 12: T3/T4/T5 触发器 + 告警系统

## 任务清单

### Group A: T3 触发器（kl:link → kl:structure）

- [x] Task A1: 创建 `backend/services/triggers/t3_link_to_structure.py`
  - [x] `T3Trigger` 类，`run_once()` 方法
  - [x] `_fetch_candidates()` — 查询 lifecycle='kl:link' 的 items
  - [x] `_count_links(item_id)` — 查询 knowledge_links 表统计关联数
  - [x] `_generate_summary(item)` — 从 content 提取前 200 字摘要
  - [x] `_update_lifecycle(item_id, stage)` — 更新 lifecycle
  - [x] 关联数 ≥ 3 正常推进；< 3 也推进但标 low_link
  - [x] 异常时通过 RetryPolicy 入死信队列
  - [x] 集成 KLMetrics 指标计数

### Group B: T4 触发器（kl:structure → kl:publish）

- [x] Task B1: 创建 `backend/services/triggers/t4_structure_to_publish.py`
  - [x] `T4Trigger` 类，`run_once()` 方法
  - [x] `_fetch_candidates()` — 查询 lifecycle='kl:structure' 的 items
  - [x] `_get_latest_score(item_id)` — 从 ai_scores 取最近评分
  - [x] `_is_stable(item)` — 检查 updated_at < now - 24h
  - [x] `_write_to_md(item)` — 调用 `knowledge_sync.write_item_to_md()`
  - [x] `_update_lifecycle(item_id, stage)` — 更新 lifecycle
  - [x] score < 8.0 跳过；24h 窗口不满足跳过
  - [x] 异常时通过 RetryPolicy 入死信队列

### Group C: T5 触发器（kl:publish → kl:refine，用户主动）

- [x] Task C1: 创建 `backend/services/triggers/t5_publish_to_refine.py`
  - [x] `T5Trigger` 类，`rollback(item_id)` 方法
  - [x] `_backup_md(item_id)` — 备份 .md 到 `knowledge/backups/`
  - [x] `_mark_stale(item_id)` — 标记 stale_at 时间戳
  - [x] `_update_lifecycle(item_id, LIFECYCLE_REFINE)` — 回滚
  - [x] 非 publish 状态拒绝回滚
  - [x] 备份目录自动创建

- [x] Task C2: 创建 `backend/api/kl_rollback_api.py`
  - [x] `POST /api/kl/rollback/{item_id}` — 调用 T5Trigger.rollback()
  - [x] 返回 404 当 item 不存在
  - [x] 返回 400 当 item 非 publish 状态
  - [x] 注册到 `api/__init__.py`

### Group D: 调度器扩展

- [x] Task D1: 更新 `backend/scheduler/jobs.py`
  - [x] 新增 `kl_trigger_t3_job()` — 600s 调度
  - [x] 新增 `kl_trigger_t4_job()` — 1800s 调度
  - [x] 更新 `__all__`

- [x] Task D2: 更新 `backend/scheduler/scheduler.py`
  - [x] job 34 — `kl_trigger_t3`（IntervalTrigger, 600s）
  - [x] job 35 — `kl_trigger_t4`（IntervalTrigger, 1800s）

### Group E: 告警规则引擎

- [x] Task E1: 创建 migration `048_v2.0_alert_rules.sql`
  - [x] `alert_rules` 表（rule_type, enabled, config）
  - [x] `alert_events` 表（rule_type, title, severity, status, etc.）
  - [x] 索引：status, created_at, rule_type
  - [x] 3 条种子数据（tech_stack_cve, critical_cve, bid_match）

- [x] Task E2: 创建 `backend/services/alert_engine.py`
  - [x] `AlertEngine` 类
  - [x] `_load_rules()` — 从 alert_rules 加载启用规则
  - [x] `evaluate_all()` — 评估所有规则
  - [x] `_evaluate_rule(rule)` — 路由到具体规则评估方法
  - [x] `_trigger_alert(...)` — 写入 alert_events 表
  - [x] `_evaluate_tech_stack_cve(rule)` — 规则 1
  - [x] `_evaluate_critical_cve(rule)` — 规则 2
  - [x] `_evaluate_bid_match(rule)` — 规则 3

- [x] Task E3: 创建 `backend/api/alert_api.py`
  - [x] `GET /api/alerts/v2` — 告警列表（支持 status/severity 过滤）
  - [x] `GET /api/alerts/v2/unread-count` — 未读告警数
  - [x] `PUT /api/alerts/v2/{id}/read` — 标记已读
  - [x] `PUT /api/alerts/v2/read-all` — 全部已读
  - [x] `PUT /api/alerts/v2/{id}/resolve` — 标记已解决
  - [x] `POST /api/alerts/v2/evaluate` — 手动触发规则评估
  - [x] 注册到 `api/__init__.py`

### Group F: 告警规则具体实现

- [x] Task F1: 规则 1 — tech_stack CVE 影响
  - [x] 查询最近 24h 的 security_items 提取 CVE
  - [x] 匹配 cg_projects.tech_stack
  - [x] 触发告警
  - [x] 单元测试 (test_alert_engine.py)

- [x] Task F2: 规则 2 — 关键 CVE 告警
  - [x] 查询最近 24h 的 security_items 提取 CVSS
  - [x] CVSS ≥ 9.0 触发告警
  - [x] 单元测试 (test_alert_engine.py)

- [x] Task F3: 规则 3 — 标讯命中
  - [x] 查询最近 24h 的 bid_items
  - [x] 关键词匹配 cg_projects.tech_stack
  - [x] 触发告警
  - [x] 单元测试 (test_alert_engine.py)

### Group G: 告警 UI

- [x] Task G1: 创建 `frontend/src/components/AlertCenter.tsx`
  - [x] Inbox 列表：告警标题、时间、severity、状态
  - [x] severity 颜色区分：critical=红, high=橙, medium=黄, low=灰
  - [x] 标记已读/全部已读按钮
  - [x] 红色横幅显示未读告警数
  - [x] 集成到导航栏

### Group H: 测试

- [x] Task H1: 创建 `backend/tests/test_t3_trigger.py`（10 用例 ✅）
- [x] Task H2: 创建 `backend/tests/test_t4_trigger.py`（10 用例 ✅）
- [x] Task H3: 创建 `backend/tests/test_t5_trigger.py`（11 用例 ✅）
- [x] Task H4: 创建 `backend/tests/test_alert_engine.py`（15 用例 ✅）
- [x] Task H5: 全量回归测试
  - [x] 运行所有 Phase 12 测试（46/46 PASS）
  - [x] 运行 Phase 10 T1/T2 回归测试（22/22 PASS）
  - [x] 运行 Phase 11 回归测试（138 passed）
  - [x] 运行前端测试（256/256 PASS）

## 任务依赖

- [x] [Task A1] 无前置（独立）✅
- [x] [Task B1] 无前置（独立）✅
- [x] [Task C1] 无前置（独立）✅
- [x] [Task C2] 依赖 [Task C1] ✅
- [x] [Task D1/D2] 依赖 [Task A1, B1] ✅
- [x] [Task E1] 无前置（独立）✅
- [x] [Task E2] 依赖 [Task E1] ✅
- [x] [Task E3] 依赖 [Task E2] ✅
- [x] [Task F1/F2/F3] 依赖 [Task E2] ✅
- [x] [Task G1] 依赖 [Task E3] ✅
- [x] [Task H1/H2/H3/H4] 依赖 [Task A1, B1, C1, E2] ✅
- [x] [Task H5] 依赖 [Task H1-H4] ✅