# Tasks

## Phase 3.1: 健康状态机
- [x] Task 3.1.1: 创建 `crawler_sources` 补充字段迁移（`057_crawler_v2_phase3.sql`）
  - 新增 `source_alerts` 表（id, source_id, alert_type, level, message, created_at）
  - `crawler_sources` 补充字段（`grace_rounds` 用于 grace 期间连续有产出计数）
  - 执行迁移
- [x] Task 3.1.2: 创建 `SourceHealthMachine` 服务
  - 实现 5 状态（active/stale/dead/grace/disabled）自动流转
  - `apply_run_result(source_id, run_result)` 方法
  - 连续失败计数 + 指数退避 `cooldown_until` 计算
  - `grace_rounds` 递增/重置逻辑
  - 单元测试覆盖所有状态流转路径

## Phase 3.2: 源级调度器
- [x] Task 3.2.1: 创建 `SourceSchedulerService` 服务
  - 每 60s tick 查询待调度源（排除 dead/disabled/cooldown 中源）
  - 按 priority DESC 排序，并发度控制（默认 3）
  - 调用 `CollectionService.run_one(source_id)` 执行单源采集
  - 采集完成后触发 `SourceHealthMachine.apply_run_result()`
  - 写 `crawler_runs` 记录
- [x] Task 3.2.2: 创建 `source_scheduler_repo.py` 仓储
  - `get_schedulable(limit, now_iso)` — 查询待调度源
  - `update_health_state(source_id, **fields)` — 更新健康状态字段
  - `get_run_stats(source_id, since_hours)` — 查询最近 N 小时运行统计
- [x] Task 3.2.3: 注册 `source_scheduler_tick_job`（每 60s）到 scheduler.py
- [x] Task 3.2.4: 实现 `CollectionService.run_one(source_id)` 单源采集方法
  - 根据源配置（kind/url/feed_url/cadence_seconds）执行单源采集
  - 返回 `RunResult`（fetched_count, accepted_count, duration_ms, status, error_msg）

## Phase 3.3: 死源探活
- [x] Task 3.3.1: 创建 `SourceProber` 服务
  - 对 dead 源执行 HEAD/GET 探测（超时 10s）
  - HEAD 405/501 时 fallback 到 GET
  - 2xx/3xx → `status='grace'`, `consecutive_failures=0`
  - 4xx/5xx → 保留 dead, 更新 `last_error`
- [x] Task 3.3.2: 注册 `source_probe_job`（每日 03:30 Asia/Shanghai）到 scheduler.py
- [x] Task 3.3.3: 创建 `POST /api/sources/{source_id}/probe` 手动探活端点

## Phase 3.4: 源级告警
- [x] Task 3.4.1: 创建 `source_alert_repo.py` 仓储
  - `insert(alert)` — 写入告警
  - `list(source_id, level, since, page, page_size)` — 分页查询
  - `has_recent(source_id, alert_type, within_hours)` — 去重检查
  - `get_stats(since_hours)` — 按级别聚合统计
- [x] Task 3.4.2: 创建 `SourceAlerter` 服务
  - 基于 `crawler_runs` 聚合数据检查 6 条告警规则
  - 24h 去重，命中 → 写入 `source_alerts`
  - 6 条规则：连续失败、拒绝率异常、HTTP 状态异常、耗时异常、URL 校验通过率低、核心 P0 源死亡
- [x] Task 3.4.3: 注册 `source_alert_eval_job`（每 300s）到 scheduler.py

## Phase 3.5: 健康状态 API
- [x] Task 3.5.1: 创建 `GET /api/sources/health/v2` 端点（返回所有源健康状态）
- [x] Task 3.5.2: 创建 `GET /api/sources/stats` 端点（返回聚合统计）
- [x] Task 3.5.3: 创建 `GET /api/sources/alerts` 端点（返回告警列表）

## Phase 3.6: 集成验证
- [x] Task 3.6.1: 编译检查 + 现有测试全部通过（86 passed, 无回归）
- [x] Task 3.6.2: 创建 `test_source_health_machine.py` 测试健康状态机所有流转路径（26 tests）
- [x] Task 3.6.3: 创建 `test_source_scheduler_repo.py` 测试调度器仓储逻辑（20 tests）
- [x] Task 3.6.4: 创建 `test_source_alerter.py` 测试告警规则（26 tests）
- [x] Task 3.6.5: 新 3 个 job 注册到 scheduler.py（source_scheduler_tick/source_probe/source_alert_eval）

# Task Dependencies
- [Task 3.1.2] depends on [Task 3.1.1]
- [Task 3.2.1] depends on [Task 3.1.2] (健康状态机反馈)
- [Task 3.2.2] depends on [Task 3.1.1]
- [Task 3.2.3] depends on [Task 3.2.1]
- [Task 3.2.4] depends on [Task 3.2.1] (调度器需要单源采集方法)
- [Task 3.3.1] depends on [Task 3.1.2] (探活后触发状态流转)
- [Task 3.3.2] depends on [Task 3.3.1]
- [Task 3.3.3] depends on [Task 3.3.1]
- [Task 3.4.1] depends on [Task 3.1.1]
- [Task 3.4.2] depends on [Task 3.4.1]
- [Task 3.4.3] depends on [Task 3.4.2]
- [Task 3.5.1] depends on [Task 3.1.2]
- [Task 3.5.2] depends on [Task 3.1.2]
- [Task 3.5.3] depends on [Task 3.4.1]
- [Task 3.6.1] depends on [Tasks 3.1-3.5]
- [Task 3.6.2] depends on [Task 3.1.2]
- [Task 3.6.3] depends on [Task 3.2.1]
- [Task 3.6.4] depends on [Task 3.4.2]
- [Task 3.6.5] depends on [Task 3.6.1]