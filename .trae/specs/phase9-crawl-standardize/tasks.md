# Phase 9 — 资讯抓取流程标准化 任务分解

> **spec**: `.trae/specs/phase9-crawl-standardize/spec.md`
> **Group 划分**: A(migration) → B(checkpoint-repo) → C(logger) → D(validator) → E(catchup-service) → F(api) → G(startup) → H(tests)

---

## Group A: DB Schema（migration 042）

### Task A1: 迁移文件 042_v1.9_catchup_checkpoints.sql

**Files:**
- Create: `backend/repository/migrations/042_v1.9_catchup_checkpoints.sql`

db.py 的 _apply_migrations 自动扫描 migrations/*.sql 按字典序加载，无需修改 db.py。

- [x] **Step 1**: 创建迁移文件，含 2 张表（catchup_checkpoints / collect_validations）+ 6 个索引，SQL 内容见 spec §2.1
- [x] **Step 2**: 手动执行迁移验证：`.venv/bin/python -c "from backend.repository.db import init_db; init_db()"`
- [x] **Step 3**: sqlite3 验证 2 张表存在 + 字段完整 + CHECK 约束
- [x] **Step 4**: 提交: `feat(db): A1 migration 042 — add catchup_checkpoints + collect_validations tables`

---

## Group B: Checkpoint Repository

### Task B1: catchup_checkpoint_repo

**Files:**
- Create: `backend/repository/catchup_checkpoint_repo.py`
- Create: `backend/tests/test_catchup_checkpoint_repo.py`

- [x] **Step 1**: 实现 `CatchupCheckpointRepository` 类，含 CRUD 方法：
  - `upsert(run_id, category, source_name, ...)` — 插入或更新 checkpoint
  - `get(run_id, category, source_name)` — 获取单条
  - `list_by_run(run_id)` — 列出 run 所有 checkpoint
  - `mark_done(run_id, category, source_name, items_count)` — 标完成
  - `mark_failed(run_id, category, source_name, error_msg)` — 标失败
  - `mark_skipped(run_id, category, source_name)` — 标跳过
  - `list_recent_done(category, source_name, window_hours=24)` — 续传查询
- [x] **Step 2**: 写 13 个单测（upsert / get / list / mark_done / mark_failed / mark_skipped / list_recent_done / 边界）
- [x] **Step 3**: 运行：`.venv/bin/python -m pytest backend/tests/test_catchup_checkpoint_repo.py -v`
- [x] **Step 4**: 提交: `feat(repo): B1 add CatchupCheckpointRepository for per-source checkpoints`

---

## Group C: Collection Logger

### Task C1: collection_logger

**Files:**
- Create: `backend/services/collection_logger.py`
- Create: `backend/tests/test_collection_logger.py`

- [x] **Step 1**: 实现结构化日志函数 `log_collect_event(event_type, **kwargs)`
  - 事件类型：collect_start / source_done / source_failed / source_skipped / collect_done / validate_done
  - 统一 schema：event / timestamp / run_id / category / source / duration_ms / items_count / error
- [x] **Step 2**: 实现 `log_validation(validation_type, severity, payload)` — 验证日志
- [x] **Step 3**: 写 8 个单测（6 事件类型 × 字段完整性 + 验证日志 + 边界）
- [x] **Step 4**: 运行：`.venv/bin/python -m pytest backend/tests/test_collection_logger.py -v`
- [x] **Step 5**: 提交: `feat(services): C1 add collection_logger for structured collect events`

---

## Group D: Collection Validator

### Task D1: collect_validator

**Files:**
- Create: `backend/services/collect_validator.py`
- Create: `backend/tests/test_collect_validator.py`

- [x] **Step 1**: 实现 4 类验证函数：
  - `validate_source_regression(results)` — 源退化检测（历史 yield > 0 但本次 = 0 → warn）
  - `validate_time_coverage_gap(results)` — 时间窗口空隙检测（1h bins 连续 ≥ 3 个空 → warn）
  - `validate_category_anomaly(results)` — 分类级异常检测（本次 > 2x 历史 avg → info）
  - `validate_cross_source(results)` — 跨源一致性检测（转载比 > 80% → info）
- [x] **Step 2**: 实现 `validate_and_persist(run_id, results)` — 执行全部验证 + 写入 collect_validations 表
- [x] **Step 3**: 实现 `list_recent_validations(run_id, include_resolved, limit)` — 查询验证结果
- [x] **Step 4**: 实现 `auto_resolve_old_validations(older_than_days)` — 归档旧验证
- [x] **Step 5**: 写 11 个单测（4 类验证 × 2-3 用例 + report 序列化 + 边界）
- [x] **Step 6**: 运行：`.venv/bin/python -m pytest backend/tests/test_collect_validator.py -v`
- [x] **Step 7**: 提交: `feat(services): D1 add collect_validator with 4 validation types`

---

## Group E: Catchup Service Integration

### Task E1: catchup_service — per-source checkpoint + 日志 + 验证

**Files:**
- Modify: `backend/services/catchup_service.py`
- Create: `backend/tests/test_catchup_service.py`
- Create: `backend/tests/test_catchup_phase9.py`

- [x] **Step 1**: 在 `_execute_catchup_run` 中添加 per-source checkpoint 记录：
  - 开始前 upsert checkpoint (status='pending')
  - 完成后 mark_done / mark_failed
  - 续传检测：同一 (cat, source) 24h 内 done → skipped
- [x] **Step 2**: 集成结构化日志：collect_start / source_done / source_failed / source_skipped / collect_done
- [x] **Step 3**: 集成 collect_validator：run 完成后调 validate_and_persist
- [x] **Step 4**: 实现异常隔离：单源失败不阻塞整轮，整轮崩溃标 failed
- [x] **Step 5**: 实现 mode=auto 与 mode=manual 解耦
- [x] **Step 6**: 写 8 个集成测试（test_catchup_phase9.py）
- [x] **Step 7**: 写 service 级单测（test_catchup_service.py）
- [x] **Step 8**: 运行：`.venv/bin/python -m pytest backend/tests/test_catchup_phase9.py backend/tests/test_catchup_service.py -v`
- [x] **Step 9**: 提交: `feat(services): E1 integrate checkpoint + logger + validator into catchup_service`

---

## Group F: API Layer

### Task F1: catchup API — 验证状态 + 迁移

**Files:**
- Modify: `backend/api/catchup.py`
- Create: `backend/tests/test_catchup_api.py`

- [x] **Step 1**: 扩展 `GET /api/catchup/status` 返回 validation 摘要（last_run_validations + validation_summary）
- [x] **Step 2**: 添加 `GET /api/catchup/runs/{run_id}/checkpoints` — per-source 进度
- [x] **Step 3**: 添加 `GET /api/catchup/runs/{run_id}/validations` — 验证结果
- [x] **Step 4**: 写 7 个 API 单测（test_catchup_api.py）
- [x] **Step 5**: 运行：`.venv/bin/python -m pytest backend/tests/test_catchup_api.py -v`
- [x] **Step 6**: 提交: `feat(api): F1 extend catchup API with validation + checkpoint endpoints`

---

## Group G: Startup Integration

### Task G1: main.py lifespan hook

**Files:**
- Modify: `backend/main.py`

- [x] **Step 1**: 在 lifespan 中添加启动后自动追抓钩子：
  - 调用 `should_enqueue_auto()` 5 分钟防抖
  - 计算 `since_iso = current_week_start() UTC`
  - 调用 `enqueue_catchup(mode="auto", since=since_iso, ...)`
  - 标记 `mark_auto_enqueued()`
- [x] **Step 2**: 异常隔离：失败不阻塞服务启动，只记 warn
- [x] **Step 3**: 提交: `feat(main): G1 add startup auto-catchup hook in lifespan`

### Task G2: Scheduler jobs

**Files:**
- Modify: `backend/scheduler/jobs.py`
- Modify: `backend/scheduler/scheduler.py`

- [x] **Step 1**: 实现 `catchup_watchdog_job` — 每 60s 检测孤儿 run（>10min 未完成）
- [x] **Step 2**: 实现 `source_revival_check_job` — 每日 03:00 检测死源复活
- [x] **Step 3**: 实现 `collect_validations_cleanup_job` — 每日 04:00 归档旧 validation
- [x] **Step 4**: 注册 3 个 job 到 scheduler.start()
- [x] **Step 5**: 提交: `feat(scheduler): G2 add catchup watchdog + revival check + validation cleanup jobs`

---

## Group H: Tests & Verification

### Task H1: 全量测试

- [x] **Step 1**: 运行 checkpoint repo 测试：`.venv/bin/python -m pytest backend/tests/test_catchup_checkpoint_repo.py -v`
- [x] **Step 2**: 运行 logger 测试：`.venv/bin/python -m pytest backend/tests/test_collection_logger.py -v`
- [x] **Step 3**: 运行 validator 测试：`.venv/bin/python -m pytest backend/tests/test_collect_validator.py -v`
- [x] **Step 4**: 运行集成测试：`.venv/bin/python -m pytest backend/tests/test_catchup_phase9.py -v`
- [x] **Step 5**: 运行 API 测试：`.venv/bin/python -m pytest backend/tests/test_catchup_api.py -v`
- [x] **Step 6**: 运行 service 测试：`.venv/bin/python -m pytest backend/tests/test_catchup_service.py -v`
- [x] **Step 7**: 运行 watchdog 测试：`.venv/bin/python -m pytest backend/tests/test_catchup_watchdog.py -v`
- [x] **Step 8**: 编译检查：`.venv/bin/python -m py_compile backend/services/catchup_service.py && .venv/bin/python -m py_compile backend/services/collection_logger.py && .venv/bin/python -m py_compile backend/services/collect_validator.py`
- [x] **Step 9**: 提交: `test(phase9): H1 all Phase 9 tests pass — checkpoint/logger/validator/catchup`

### Task H2: 文档更新

- [x] **Step 1**: 创建 `docs/phase9_changelog.md`，记录 Phase 9 新增功能
- [x] **Step 2**: 更新 `docs/hotspot_v2.0_dev_plan.md` 标记 Phase 9 状态
- [x] **Step 3**: 提交: `docs(phase9): H2 add phase9 changelog + update dev plan`