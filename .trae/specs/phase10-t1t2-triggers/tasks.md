# Phase 10 — T1/T2 触发器实施 任务分解

> **spec**: `.trae/specs/phase10-t1t2-triggers/spec.md`
> **Group 划分**: A(state-machine + migration) → B(t1-trigger) → C(t2-trigger) → D(retry+metrics) → E(scheduler) → F(tests) → G(docs)

---

## Group A: 状态机引擎 + DB Migration

### Task A1: 创建 kl_state_machine 状态机

**Files:**
- Create: `backend/services/kl_state_machine.py`
- Create: `backend/tests/test_kl_state_machine.py`

- [ ] **Step 1**: 实现 5 阶段常量（LIFECYCLE_RAW/REFINE/LINK/STRUCTURE/PUBLISH）
- [ ] **Step 2**: 实现 `TRANSITIONS` 字典（5 阶段单向 DAG + T5 回滚）
- [ ] **Step 3**: 实现 `can_transition(from, to)` / `transition(from, to, actor)` / `is_terminal(stage)`
- [ ] **Step 4**: 实现 `STAGE_LABELS` 中文标签字典
- [ ] **Step 5**: 写 15 个单测（合法转换 5 + 非法转换 5 + is_terminal 2 + 边界 3）
- [ ] **Step 6**: 运行：`.venv/bin/python -m pytest backend/tests/test_kl_state_machine.py -v`
- [ ] **Step 7**: 提交: `feat(services): A1 add kl_state_machine — 5-stage transition engine`

### Task A2: 创建 kl_dead_letters 迁移

**Files:**
- Create: `backend/repository/migrations/044_v2.0_kl_dead_letters.sql`

注: db.py 的 _apply_migrations 自动扫描 migrations/*.sql 按字典序加载，无需修改 db.py。

- [ ] **Step 1**: 创建迁移文件，1 张表（kl_dead_letters）+ 2 个索引，SQL 内容见 spec §3.2
- [ ] **Step 2**: 手动执行迁移验证：`.venv/bin/python -c "from backend.repository.db import init_db; init_db()"`
- [ ] **Step 3**: sqlite3 验证表存在 + 字段完整 + CHECK 约束
- [ ] **Step 4**: 提交: `feat(db): A2 migration 044 — add kl_dead_letters table`

---

## Group B: T1 触发器 (kl:raw → kl:refine)

### Task B1: T1 触发器实现

**Files:**
- Create: `backend/services/triggers/__init__.py`
- Create: `backend/services/triggers/t1_raw_to_refine.py`
- Create: `backend/tests/test_t1_trigger.py`

- [ ] **Step 1**: 创建 `triggers/__init__.py`（空目录标记）
- [ ] **Step 2**: 实现 `T1Trigger` 类，含 `__init__(metrics, retry_policy, simhash_module)` 依赖注入
- [ ] **Step 3**: 实现 `_fetch_candidates()`：查询 `lifecycle='kl:raw'` 且 `ingested_at < now - 5min` 的 items（限 50 条）
- [ ] **Step 4**: 实现 `_is_duplicate(item)`：查 `content_fingerprints.url_canonical` 精确匹配
- [ ] **Step 5**: 实现 `_get_latest_score(hotspot_id)`：查 `ai_scores` 最近 score，无则 fallback 5.0
- [ ] **Step 6**: 实现 `_extract_tags(item)`：从 `item.concepts` (JSON) 解析，无则空列表
- [ ] **Step 7**: 实现 `_update_lifecycle(item_id, new_stage)`：更新 SQLite + 记录 `updated_at`
- [ ] **Step 8**: 实现 `run_once()`：整合上述 5 步 + metrics 记录 + retry_policy 错误处理
- [ ] **Step 9**: 写 12 个单测（candidates 查询 + 去重 + 评分 fallback + tag 提取 + lifecycle 推进 + metrics 5 + retry 1 + 边界 2）
- [ ] **Step 10**: 运行：`.venv/bin/python -m pytest backend/tests/test_t1_trigger.py -v`
- [ ] **Step 11**: 提交: `feat(services): B1 add T1Trigger — kl:raw → kl:refine with simhash + scoring`

---

## Group C: T2 触发器 (kl:refine → kl:link)

### Task C1: T2 触发器实现

**Files:**
- Create: `backend/services/triggers/t2_refine_to_link.py`
- Create: `backend/tests/test_t2_trigger.py`

- [ ] **Step 1**: 实现 `T2Trigger` 类，含 `__init__(metrics, retry_policy)` 依赖注入
- [ ] **Step 2**: 实现 `_fetch_candidates()`：查询 `lifecycle='kl:refine'` 的 items（限 50 条）
- [ ] **Step 3**: 实现 `_find_related_items(item)`：从 `item.concepts` (JSON) 解析 concept 列表，查询 `knowledge_items` 同 concept 的其它 items（最多 5 个）
- [ ] **Step 4**: 实现 `_write_links(from_id, related_ids)`：写 `knowledge_links` 表（type='similar', confidence=0.7, created_by='trigger'）
- [ ] **Step 5**: 实现 `_update_lifecycle(item_id, new_stage)`：更新 SQLite
- [ ] **Step 6**: 实现 `run_once()`：整合 + metrics + retry_policy
- [ ] **Step 7**: 写 10 个单测（candidates + entity 查找 + link 写入 + lifecycle + low_link + metrics + 边界 2）
- [ ] **Step 8**: 运行：`.venv/bin/python -m pytest backend/tests/test_t2_trigger.py -v`
- [ ] **Step 9**: 提交: `feat(services): C1 add T2Trigger — kl:refine → kl:link with concept linking`

---

## Group D: 重试策略 + Prometheus 指标

### Task D1: 重试 + 死信服务

**Files:**
- Create: `backend/services/retry_policy.py`
- Create: `backend/repository/kl_dead_letter_repo.py`
- Create: `backend/tests/test_retry_policy.py`

- [ ] **Step 1**: 实现 `with_retry(fn, max_attempts=3, backoff=(1,5,30))` 装饰器
- [ ] **Step 2**: 实现 `KLDeadLetterRepository` 类：add / get_active / update_attempts / list_active_count / resolve
- [ ] **Step 3**: 实现 `RetryPolicy` 类：handle_failure（attempts 累计 + 3 次后入死信）
- [ ] **Step 4**: 写 8 个单测（with_retry 3 + 死信 add 1 + update_attempts 1 + list_active 1 + 边界 2）
- [ ] **Step 5**: 运行：`.venv/bin/python -m pytest backend/tests/test_retry_policy.py -v`
- [ ] **Step 6**: 提交: `feat(services): D1 add retry_policy + kl_dead_letter_repo — 3-attempt with DLQ`

### Task D2: Prometheus 指标

**Files:**
- Create: `backend/metrics/__init__.py`
- Create: `backend/metrics/kl_metrics.py`
- Create: `backend/api/kl_metrics_api.py`
- Create: `backend/tests/test_kl_metrics.py`

- [ ] **Step 1**: 创建 `metrics/__init__.py`（空目录标记）
- [ ] **Step 2**: 实现 `KLMetrics` 类（counters / gauges / histograms）见 spec §6
- [ ] **Step 3**: 实现 `inc(name, n=1)` / `set_stage_counts(counts)` / `observe(name, value)` / `snapshot()`
- [ ] **Step 4**: 实现 `backend/api/kl_metrics_api.py`：`GET /api/kl/metrics` 返回 metrics.snapshot() JSON
- [ ] **Step 5**: 在 `backend/api/__init__.py` 的 `register_routers()` 中注册 `kl_metrics_api` 路由
- [ ] **Step 6**: 写 5 个单测（inc 1 + set 1 + observe 1 + snapshot 1 + 边界 1）
- [ ] **Step 7**: 运行：`.venv/bin/python -m pytest backend/tests/test_kl_metrics.py -v`
- [ ] **Step 8**: 提交: `feat(metrics): D2 add KLMetrics + /api/kl/metrics endpoint`

---

## Group E: 调度器注册

### Task E1: scheduler jobs 注册

**Files:**
- Modify: `backend/scheduler/jobs.py`
- Modify: `backend/scheduler/scheduler.py`

- [ ] **Step 1**: 在 `jobs.py` 追加 `kl_trigger_t1_job` / `kl_trigger_t2_job` / `kl_dead_letter_retry_job`（见 spec §7.2）
- [ ] **Step 2**: 在 `scheduler.py` 的 `start()` 末尾追加 3 个 `add_job`（spec §7.3）
- [ ] **Step 3**: 启动 backend 验证 scheduler 启动日志包含 3 个新 job ID
- [ ] **Step 4**: 写集成测试 `test_phase10_integration.py`：启动 scheduler → 等待 5s → 验证 3 个 job 至少跑过 1 次
- [ ] **Step 5**: 运行：`.venv/bin/python -m pytest backend/tests/test_phase10_integration.py -v`
- [ ] **Step 6**: 提交: `feat(scheduler): E1 register kl_trigger_t1/t2/dead_letter_retry jobs`

---

## Group F: 测试 & 验证

### Task F1: 全量测试

- [ ] **Step 1**: 运行 state machine 测试：`.venv/bin/python -m pytest backend/tests/test_kl_state_machine.py -v`
- [ ] **Step 2**: 运行 T1 测试：`.venv/bin/python -m pytest backend/tests/test_t1_trigger.py -v`
- [ ] **Step 3**: 运行 T2 测试：`.venv/bin/python -m pytest backend/tests/test_t2_trigger.py -v`
- [ ] **Step 4**: 运行 retry policy 测试：`.venv/bin/python -m pytest backend/tests/test_retry_policy.py -v`
- [ ] **Step 5**: 运行 metrics 测试：`.venv/bin/python -m pytest backend/tests/test_kl_metrics.py -v`
- [ ] **Step 6**: 运行集成测试：`.venv/bin/python -m pytest backend/tests/test_phase10_integration.py -v`
- [ ] **Step 7**: 编译检查：`.venv/bin/python -m py_compile backend/services/kl_state_machine.py backend/services/triggers/*.py backend/services/retry_policy.py backend/metrics/kl_metrics.py`
- [ ] **Step 8**: 提交: `test(phase10): F1 all Phase 10 tests pass — state_machine/t1/t2/retry/metrics`

### Task F2: 回归测试

- [ ] **Step 1**: 运行 Phase 8 测试：`.venv/bin/python -m pytest backend/tests/test_simhash.py backend/tests/test_fingerprint.py backend/tests/test_mcp_phase8.py backend/tests/test_imported_aggregator.py backend/tests/test_knowledge_imported_api.py -v`
- [ ] **Step 2**: 运行 Phase 9 测试：`.venv/bin/python -m pytest backend/tests/test_catchup_checkpoint_repo.py backend/tests/test_collection_logger.py backend/tests/test_collect_validator.py backend/tests/test_catchup_phase9.py backend/tests/test_catchup_api.py backend/tests/test_catchup_watchdog.py -v`
- [ ] **Step 3**: 验证所有现有测试不退化（除已知 75 个 pre-existing 失败）

---

## Group G: 文档更新

### Task G1: Phase 10 changelog

**Files:**
- Create: `docs/phase10_changelog.md`

- [ ] **Step 1**: 记录新增文件清单（6 个 backend + 6 个 test）
- [ ] **Step 2**: 记录新增 scheduler jobs（job 31/32/33）
- [ ] **Step 3**: 记录新表 kl_dead_letters（migration 044）
- [ ] **Step 4**: 记录测试覆盖（56 用例全 PASS）
- [ ] **Step 5**: 提交: `docs(phase10): G1 add phase10 changelog`

### Task G2: 更新 dev plan 状态

**Files:**
- Modify: `docs/hotspot_v2.0_dev_plan.md`

- [ ] **Step 1**: 顶部状态行：当前 Phase: 10 → 当前 Phase: 11
- [ ] **Step 2**: 目录 Phase 9 行追加 "(已完成)"
- [ ] **Step 3**: 目录 Phase 10 行追加 "(已完成)"
- [ ] **Step 4**: 提交: `docs(phase10): G2 update dev plan phase 10 status`

---

# Task Dependencies

- [A1, A2] no dependencies (start immediately, parallel)
- [B1] depends on [A1, A2] (needs migration + state machine)
- [C1] depends on [A1, A2] (needs migration + state machine)
- [D1] depends on [A2] (needs dead_letter table)
- [D2] depends on [A1] (needs stage labels from state machine)
- [E1] depends on [B1, C1, D1, D2] (needs all triggers)
- [F1, F2] depends on [E1]
- [G1, G2] depends on [F1] (needs all tests passing)
