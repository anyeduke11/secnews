# Checklist

## Phase 3.1: 健康状态机
- [x] 迁移 `057_crawler_v2_phase3.sql` 创建 `source_alerts` 表 + `grace_rounds` 字段
- [x] `SourceHealthMachine.apply_run_result()` 实现 active→stale（连续失败3次）
- [x] `SourceHealthMachine.apply_run_result()` 实现 stale→dead（连续失败5次）
- [x] `SourceHealthMachine.apply_run_result()` 实现 stale→active（单轮产出>0）
- [x] `SourceHealthMachine.apply_run_result()` 实现 dead→grace（探活成功）
- [x] `SourceHealthMachine.apply_run_result()` 实现 grace→active（连续3轮有产出）
- [x] `SourceHealthMachine.apply_run_result()` 实现 grace→dead（grace期连续失败3次）
- [x] 指数退避 `cooldown_until` 计算正确（上限 2^6 * 300s = 5.33h）
- [x] 单元测试覆盖所有 7 条状态流转路径

## Phase 3.2: 源级调度器
- [x] `SourceSchedulerService` 每 60s tick 查询待调度源
- [x] 排除 dead/disabled/cooldown 中源
- [x] 按 priority DESC 排序，并发度控制（默认 3）
- [x] 调用 `CollectionService.run_one(source_id)` 执行单源采集
- [x] 采集完成后触发 `SourceHealthMachine.apply_run_result()`
- [x] 写 `crawler_runs` 记录
- [x] `source_scheduler_repo.py` 实现 get_schedulable / update_health_state / get_run_stats
- [x] `source_scheduler_tick_job` 注册到 scheduler.py
- [x] `CollectionService.run_one(source_id)` 实现单源采集

## Phase 3.3: 死源探活
- [x] `SourceProber` 对 dead 源执行 HEAD/GET 探测
- [x] HEAD 405/501 fallback 到 GET
- [x] 2xx/3xx → status='grace', consecutive_failures=0
- [x] 4xx/5xx → 保留 dead, 更新 last_error
- [x] `source_probe_job` 注册到 scheduler.py（每日 03:30 Asia/Shanghai）
- [x] `POST /api/sources/{source_id}/probe` 手动探活端点

## Phase 3.4: 源级告警
- [x] `source_alert_repo.py` 实现 insert / list / has_recent / get_stats
- [x] `SourceAlerter` 检查 6 条告警规则
- [x] 24h 去重，命中 → 写入 `source_alerts`
- [x] `source_alert_eval_job` 注册到 scheduler.py（每 300s）

## Phase 3.5: 健康状态 API
- [x] `GET /api/sources/health/v2` 返回所有源健康状态（crawler_sources 表）
- [x] `GET /api/sources/stats` 返回聚合统计
- [x] `GET /api/sources/alerts` 返回告警列表

## Phase 3.6: 集成验证
- [x] 编译检查通过（无 import/type 错误）
- [x] 现有测试全部通过（86 passed, 无回归）
- [x] `test_source_health_machine.py` 覆盖所有 7 条状态流转路径（26 tests）
- [x] `test_source_scheduler_repo.py` 覆盖调度器仓储逻辑（20 tests）
- [x] `test_source_alerter.py` 覆盖告警规则（26 tests）
- [x] 新测试共计 77 个，全部通过
- [x] 3 个新 job 注册到 scheduler.py：source_scheduler_tick, source_probe, source_alert_eval